"""Where a match should run, according to one latency model.

Two decisions, both made only from the model's predictions and the current
player count on every node (the same inputs a placement algorithm has):

  place      a new match arrives: put it on the node that leaves the lowest
             predicted worst-player p95 across the whole system; ties go to
             the nearer node.
  rebalance  every few seconds: is there one match whose move to another
             node lowers the predicted worst-player p95 enough to be worth
             disconnecting its ten players? If the worst stays the same, a
             move is still taken when it lowers the players' mean predicted
             p95 enough - that is how matches drift back to the near edge
             when load falls.

Hysteresis (a minimum gain) and a per-match cooldown stop a match bouncing
between two nodes on noise. The load-blind analytical model predicts the same
latency for a node at any load, so it never sees a reason to move a match off
a crowded node; the only moves it ever makes are toward a nearer node.
"""
import math
import time
from dataclasses import dataclass

import numpy as np

from placement.models import MODELS, load_nodes, load_rows

CAPACITY = 100           # server max-players
GRID_RUNS = ["grid1", "grid2"]


@dataclass
class Gains:
    worst_ms: float = 10.0       # a move must lower the predicted worst by this ...
    worst_frac: float = 0.20     # ... and by this fraction of it
    mean_ms: float = 3.0         # or, worst unchanged, lower the mean by this
    cooldown_s: float = 60.0     # a match that just moved stays put this long


class Policy:
    def __init__(self, model_name, nodes=None, gains=None):
        self.name = model_name
        self.nodes = {n["name"]: n for n in (nodes or load_nodes())}
        self.order = sorted(self.nodes, key=lambda n: self.nodes[n]["rtt_ms"])
        self.model = MODELS[model_name]().fit(load_rows(runs=GRID_RUNS))
        self.gains = gains or Gains()

    def predict(self, node, players):
        return self.model.predict(self.nodes[node], players) if players else None

    def observe(self, node, players, measured_p95):
        """A measured steady window. The offline models ignore it."""

    def score(self, load):
        """(worst, player-weighted mean) predicted p95 for a load dict."""
        preds = {n: self.predict(n, p) for n, p in load.items() if p}
        if not preds:
            return 0.0, 0.0
        total = sum(load[n] for n in preds)
        return max(preds.values()), sum(preds[n] * load[n] for n in preds) / total

    def capacity_factor(self, node):
        return 1.0

    def place(self, load, size):
        best = None
        for n in self.order:
            if load.get(n, 0) + size > CAPACITY:
                continue
            trial = dict(load)
            trial[n] = trial.get(n, 0) + size
            worst, mean = self.score(trial)
            key = (round(worst, 3), round(mean, 3))
            if best is None or key < best[0]:
                best = (key, n)
        return best[1] if best else None

    def rebalance(self, load, matches, now, size):
        """matches: {mid: (node, last_move_time)}. Returns (mid, src, dst,
        before, after) for the single best move, or None."""
        g = self.gains
        worst0, mean0 = self.score(load)
        best = None
        for mid, (src, last) in matches.items():
            if now - last < g.cooldown_s:
                continue
            for dst in self.order:
                if dst == src or load.get(dst, 0) + size > CAPACITY:
                    continue
                trial = dict(load)
                trial[src] -= size
                trial[dst] = trial.get(dst, 0) + size
                worst, mean = self.score(trial)
                gain_worst = worst0 - worst
                ok = (gain_worst >= g.worst_ms and gain_worst >= g.worst_frac * worst0) or \
                     (worst <= worst0 + 0.5 and mean0 - mean >= g.mean_ms)
                if ok and (best is None or (worst, mean) < best[3:5]):
                    best = (mid, src, dst, worst, mean)
        if not best:
            return None
        mid, src, dst, worst, mean = best
        return {"match": mid, "src": src, "dst": dst,
                "predicted_worst_before": worst0, "predicted_worst_after": worst,
                "predicted_mean_before": mean0, "predicted_mean_after": mean}


class LivePolicy(Policy):
    """The learned model, corrected from live measurements.

    The offline model knows each node's capacity from the grid. If a node
    gets slower while running (a noisy neighbour, a throttled host, a CPU
    quota cut) every offline model keeps predicting the old curve. This one
    compares each steady 10 s window with its own prediction and estimates
    how much more each player now costs that node: the factor c such that
    the node at P players behaves as the grid measured it at c x P. A node
    whose CPU was halved behaves like c = 2. Prediction for that node then
    uses c x P, which moves the knee, not just the level. (Scaling the
    node's cores instead would ask the trees about nodes smaller than any
    they were fitted on, where they cannot extrapolate.)

    c is the value in [0.5, 4] that best explains the window, with a small
    pull toward 1, smoothed with an exponential moving average in log space.
    A window is used only if c could change its prediction by 1.5x or more:
    in the flat region every c explains it equally well, and it must not move
    the estimate."""
    GRID = np.geomspace(0.5, 4.0, 43)
    ALPHA = 0.5
    PRIOR = 0.08
    INFORMATIVE = math.log(1.5)   # a window counts if c can move the prediction 1.5x
    VIOLATION_MS = 100.0          # a window this slow is remembered ...
    HOLD_S = 300.0                # ... for this long

    def __init__(self, nodes=None, gains=None):
        super().__init__("learned", nodes, gains)
        self.name = "learned-live"
        self.log_c = {n: 0.0 for n in self.nodes}
        self.broke = {}           # node -> (players, measured p95, time) of a violation

    def capacity_factor(self, node):
        return math.exp(self.log_c[node])

    def _raw(self, node, players, c):
        return self.model.predict(self.nodes[node], players * c)

    def predict(self, node, players):
        if not players:
            return None
        pred = self._raw(node, players, self.capacity_factor(node))
        # One scale factor only approximates a node whose knee moved: light
        # windows below the new knee look healthy and pull c back down. A
        # violation actually measured is not forgotten that easily: at that
        # load or more the node is predicted at least that slow until the
        # memory expires, after which the controller may probe it again.
        b = self.broke.get(node)
        if b and players >= b[0] and time.time() - b[2] < self.HOLD_S:
            pred = max(pred, b[1])
        return pred

    def observe(self, node, players, measured_p95):
        if not players or measured_p95 is None or measured_p95 <= 0:
            return
        y = math.log(measured_p95)
        preds = [math.log(self._raw(node, players, c)) for c in self.GRID]
        # In the flat region every c predicts nearly the same latency, so the
        # window carries no evidence about c. Updating anyway pulls the
        # estimate back to the prior, the controller then moves a match back
        # onto a node that is still slow, and that match pays for it.
        if max(preds) - min(preds) < self.INFORMATIVE:
            return
        cost = [abs(p - y) + self.PRIOR * abs(math.log(c)) for p, c in zip(preds, self.GRID)]
        best = math.log(self.GRID[int(np.argmin(cost))])
        self.log_c[node] = (1 - self.ALPHA) * self.log_c[node] + self.ALPHA * best
        if measured_p95 > self.VIOLATION_MS:
            now, b = time.time(), self.broke.get(node)
            # keep the lightest load seen to break the budget
            if b is None or players <= b[0] or now - b[2] >= self.HOLD_S:
                self.broke[node] = (players, measured_p95, now)


POLICIES = ("analytical", "queueing", "learned", "learned-live")


def make_policy(name):
    return LivePolicy() if name == "learned-live" else Policy(name)

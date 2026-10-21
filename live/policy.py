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
from dataclasses import dataclass

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

    def score(self, load):
        """(worst, player-weighted mean) predicted p95 for a load dict."""
        preds = {n: self.predict(n, p) for n, p in load.items() if p}
        if not preds:
            return 0.0, 0.0
        total = sum(load[n] for n in preds)
        return max(preds.values()), sum(preds[n] * load[n] for n in preds) / total

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

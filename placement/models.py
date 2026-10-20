"""Latency models: given a node and the players on it, predict p95 player RTT.

Three models, one interface - `predict(node, players) -> ms` - so a placement
algorithm can be run with any of them and the only thing that changes is the
latency term:

  analytical  propagation + size / bandwidth. The model edge placement work
              ranks nodes with. It has no term for load, so it returns the
              same number for 1 player and for 100.

  queueing    analytical + an M/M/1 waiting term, s / (1 - u), where
              u = players / capacity. The "load-aware" closed form. Its one
              free parameter s is fitted to the same measurements the learned
              model sees, so it is the strongest version of the closed form,
              not a strawman.

  learned     analytical + a server delay learned from measurements: gradient
              boosted trees on (utilization, players, cores), predicting the
              in-game p95 minus the network RTT. No assumed shape.

A node is a dict with `name`, `cores` and `rtt_ms` (the measured idle ICMP RTT
- see placement/nodes.json).
"""
import json
import math
from pathlib import Path

import numpy as np

# docs/07-capacity.md: ~100 players per core before tick time breaks 50 ms.
PLAYERS_PER_CORE = 100

# The size/bandwidth term, kept so the analytical model is written out in full:
# one chat message (~100 B) over an unshaped 1 Gb/s veth. It is 0.0008 ms -
# negligible, which is itself part of the point: on this path the formula's
# only live term is distance.
MSG_BYTES = 100
LINK_BPS = 1e9


def utilization(node, players):
    return players / (PLAYERS_PER_CORE * node["cores"])


class Analytical:
    name = "analytical"

    def fit(self, rows):
        return self

    def predict(self, node, players):
        return node["rtt_ms"] + MSG_BYTES * 8 / LINK_BPS * 1000


class Queueing(Analytical):
    """M/M/1: rtt + s / (1 - u). Above u = 1 the queue is unstable and the
    model's answer is infinite; it is capped so algorithms can still compare."""
    name = "queueing"
    CAP_MS = 60_000.0

    def __init__(self, s_ms=None):
        self.s_ms = s_ms

    def fit(self, rows):
        # least squares for s on server delay = s / (1 - u), stable rows only
        x, y = [], []
        for r in rows:
            u = r["utilization"]
            if u < 0.99:
                x.append(1.0 / (1.0 - u))
                y.append(max(r["rtt_p95_ms"] - r["net_rtt_ms"], 0.0))
        x, y = np.array(x), np.array(y)
        self.s_ms = float((x @ y) / (x @ x))
        return self

    def predict(self, node, players):
        u = utilization(node, players)
        base = super().predict(node, players)
        if u >= 1:
            return self.CAP_MS
        return min(base + self.s_ms / (1.0 - u), self.CAP_MS)


class Learned(Analytical):
    name = "learned"
    FEATURES = ("utilization", "players", "cores")

    def __init__(self, **gbr_args):
        from sklearn.ensemble import GradientBoostingRegressor
        args = dict(n_estimators=300, max_depth=3, learning_rate=0.05,
                    subsample=0.8, random_state=0)
        args.update(gbr_args)
        self.gbr = GradientBoostingRegressor(**args)

    @staticmethod
    def _x(util, players, cores):
        return [util, players, cores]

    def fit(self, rows):
        X = [self._x(r["utilization"], r["players"], r["cores"]) for r in rows]
        # server delay spans 1 ms to seconds, so learn it in log space
        y = [math.log1p(max(r["rtt_p95_ms"] - r["net_rtt_ms"], 0.0)) for r in rows]
        self.gbr.fit(np.array(X), np.array(y))
        return self

    def predict(self, node, players):
        x = self._x(utilization(node, players), players, node["cores"])
        delay = math.expm1(float(self.gbr.predict(np.array([x]))[0]))
        return super().predict(node, players) + max(delay, 0.0)


MODELS = {"analytical": Analytical, "queueing": Queueing, "learned": Learned}

REPO = Path(__file__).resolve().parents[1]


def load_rows(path=REPO / "data" / "dataset.csv", runs=None, deployments=False):
    """Dataset rows as dicts of floats. Grid rows only unless deployments=True:
    the single-node grid is what models are trained on, the deployments are
    what they are tested against."""
    import csv
    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if runs and r["run"] not in runs:
                continue
            if r["deployment"] and not deployments:
                continue
            if not r["rtt_n"] or int(r["rtt_n"]) == 0:
                continue
            row = dict(r)
            for k in ("cores", "bots", "players", "utilization", "net_rtt_ms",
                      "rtt_p50_ms", "rtt_p95_ms", "rtt_p99_ms", "net_rtt_idle_ms"):
                row[k] = float(r[k])
            # The load is what the server actually held: the median of its own
            # player count over the window. Not the bots launched - an
            # overloaded node stops admitting logins (edge1 held 50 of 60).
            # A median is untouched by the brief dip of a respawning bot.
            if row["players"] != row["players"]:          # NaN: no samples
                row["players"] = row["bots"]
            row["players"] = round(row["players"])
            row["utilization"] = row["players"] / (PLAYERS_PER_CORE * row["cores"])
            out.append(row)
    return out


def load_nodes(path=REPO / "placement" / "nodes.json"):
    return json.loads(Path(path).read_text())

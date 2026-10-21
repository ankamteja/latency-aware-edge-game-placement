"""The real-time placement loop.

One run = one demand scenario driven against the live testbed under one
policy (one latency model making every placement and migration decision).
Every model is also evaluated in shadow on every tick - its prediction for
each loaded node next to what that node measured - so a run under one
policy still scores all three models.

Each tick (2 s):
  1. apply the scenario: matches arrive and leave on a fixed schedule, the
     same for every policy
  2. read every bot's new latency samples, attribute them to the node the
     match was on when it sent them
  3. every 5 s: server counters (players, tick time, CPU) on every node
  4. measured p50 / p95 per node over the last 10 s; the worst node is the
     worst-off players' latency
  5. every 10 s: ask the policy whether one match should move, and move it

A run writes results/live/<run>/{meta.json, timeline.jsonl, migrations.jsonl,
summary.json}.
"""
import json
import os
import queue
import random
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from live import testbed as tb
from live.policy import CAPACITY, Policy
from placement.models import MODELS, load_nodes

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "results" / "live"
TICK_S = 2.0
SERVER_EVERY_S = 5.0
REBALANCE_EVERY_S = 10.0
WINDOW_S = 10.0
MIN_SAMPLES = 20          # fewer samples than this in a window: no percentile
BUDGET_MS = 100.0
SIZE = tb.MATCH_SIZE

SCENARIOS = {
    # 14 matches (140 players) arrive one every 25 s, hold, then 8 leave.
    "standard": dict(peak=14, arrive_every=25, hold=150, low=6, depart_every=25, tail=90, seed=7),
    # short check that everything moves: 6 matches, about 4 minutes
    "quick": dict(peak=6, arrive_every=15, hold=40, low=3, depart_every=15, tail=40, seed=7),
    # no schedule: the operator adds and removes load (live/load.sh or the
    # dashboard) and the run lasts until it is stopped
    "manual": dict(peak=0, arrive_every=0, hold=0, low=0, depart_every=0, tail=4 * 3600, seed=7),
}
MAX_MATCHES = 16          # usernames bot0..bot159 are opped on every server


def schedule(name):
    """[(t_seconds, 'arrive'|'depart', match_id)] and the run length."""
    s = SCENARIOS[name]
    ev, t = [], 0.0
    for mid in range(s["peak"]):
        ev.append((t, "arrive", mid))
        t += s["arrive_every"]
    t += s["hold"]
    rng = random.Random(s["seed"])
    leaving = rng.sample(range(s["peak"]), s["peak"] - s["low"])
    for mid in leaving:
        ev.append((t, "depart", mid))
        t += s["depart_every"]
    return ev, t + s["tail"]


def pct(xs, p):
    return float(np.percentile(xs, p)) if len(xs) >= MIN_SAMPLES else None


@dataclass
class Match:
    mid: int
    node: str
    seg: int
    since: float                    # time of the last move (0 = never moved)
    tail: tb.Tail
    moved_at: float | None = None   # wall time of the stop, while players reconnect
    back: dict = field(default_factory=dict)   # bot -> first sample after the move
    gaps: list = field(default_factory=list)   # per move: last player back, seconds

    def close_gap(self, now):
        """A move's outage ends when the last of its players is back (or, if
        some never return, when the match is next touched)."""
        if self.moved_at is None:
            return
        last = max(self.back.values()) if self.back else now
        self.gaps.append(max(0.0, last - self.moved_at))
        self.moved_at, self.back = None, {}


def write_atomic(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


ARRIVALS = ("nearest", "model")


class Run:
    """arrival: where a new match lands before the controller acts.
      nearest  the matchmaker puts it on the nearest node with room, as a
               distance-based matchmaker does; only the controller's model
               decides whether it later moves. The default: the two policies
               then differ in exactly one thing.
      model    the policy's own model places it too."""

    def __init__(self, policy_name, scenario="standard", arrival="nearest"):
        self.arrival = arrival
        self.policy = Policy(policy_name)
        self.shadow = {m: (self.policy if m == policy_name else Policy(m)) for m in MODELS}
        self.nodes = {n["name"]: n for n in load_nodes()}
        self.scenario = scenario
        self.events, self.length = schedule(scenario)
        self.id = (time.strftime("%Y%m%d-%H%M%S") + f"{int(time.time() * 1000) % 1000:03d}"
                   + f"-{policy_name}-{scenario}-{arrival}")
        self.dir = RESULTS / self.id
        self.matches: dict[int, Match] = {}
        self.samples = {n: deque() for n in self.nodes}   # (ts_ms, rtt)
        self.all_rtt = []
        self.server = {n: {} for n in self.nodes}
        self.cpu = tb.CpuMeter()
        self.timeline, self.migrations, self.log = [], [], deque(maxlen=200)
        # recent raw telemetry exactly as read: bot latency lines and server
        # console output, so the dashboard can show where every number comes from
        self.raw = deque(maxlen=80)
        # (model, node, predicted, measured): one row per node per 10 s window
        # in which that node's load did not change, so a prediction is never
        # graded against samples taken at a different load
        self.shadow_rows = []
        self.load_since = {n: 0.0 for n in self.nodes}   # last load change per node
        self.last_shadow = 0.0
        self.state = {}
        self.lock = threading.Lock()
        self.stop_flag = threading.Event()
        self.commands = queue.Queue()     # operator load, applied on the next tick
        self.status = "starting"
        self.t0 = None
        self._closed_gaps = []       # migration gaps of matches that have left

    # ---- bookkeeping --------------------------------------------------------
    def load(self):
        out = {n: 0 for n in self.nodes}
        for m in self.matches.values():
            out[m.node] += SIZE
        return out

    def note(self, kind, text, **kw):
        e = {"t": round(self.elapsed(), 1), "kind": kind, "text": text, **kw}
        self.log.appendleft(e)
        return e

    def elapsed(self):
        return time.time() - self.t0 if self.t0 else 0.0

    # ---- actions ------------------------------------------------------------
    def arrive(self, mid):
        load = self.load()
        if self.arrival == "nearest":
            node = next((n for n in self.policy.order if load[n] + SIZE <= CAPACITY), None)
        else:
            node = self.policy.place(load, SIZE)
        if node is None:
            self.note("reject", f"match {mid} rejected, every node full")
            return
        try:
            path = tb.start_match(self.id, mid, node, 0)
        except Exception as e:
            self.note("reject", f"match {mid} could not start: {e}")
            return
        # since=0: the cooldown guards against bouncing after a move, not
        # against correcting where the matchmaker first put a match
        self.matches[mid] = Match(mid, node, 0, 0.0, tb.Tail(path))
        self.load_since[node] = time.time()
        pred = self.policy.predict(node, self.load()[node])
        self.note("arrive", f"match {mid} placed on {node}", node=node,
                  predicted_ms=round(pred, 1) if pred else None)

    def overload(self, node, count, source="dashboard"):
        """Operator command: put `count` new matches straight onto `node`,
        whatever the policy would choose - the way a flash crowd or a
        careless matchmaker lands load. The controller then reacts."""
        load, placed = self.load(), 0
        free = [i for i in range(MAX_MATCHES) if i not in self.matches]
        for mid in free[:count]:
            if load[node] + SIZE > CAPACITY:
                break
            try:
                path = tb.start_match(self.id, mid, node, 0)
            except Exception as e:
                self.note("reject", f"match {mid} could not start: {e}")
                break
            self.matches[mid] = Match(mid, node, 0, 0.0, tb.Tail(path))
            self.load_since[node] = time.time()
            load[node] += SIZE
            placed += 1
        self.note("overload", f"{source}: added {placed * SIZE} bots ({placed} match"
                  f"{'es' if placed != 1 else ''}) on {node}",
                  node=node, requested=count, placed=placed, source=source)

    def unload(self, count, node=None, source="dashboard"):
        mids = sorted((m.mid for m in self.matches.values() if node in (None, m.node)), reverse=True)
        self.note("unload", f"{source}: removing {min(count, len(mids)) * SIZE} bots"
                  f"{' from ' + node if node else ''}", source=source)
        for mid in mids[:count]:
            self.depart(mid)

    def apply_commands(self):
        while True:
            try:
                cmd = self.commands.get_nowait()
            except queue.Empty:
                return
            src = cmd.get("source", "dashboard")
            if cmd["action"] == "add":
                self.overload(cmd["node"], cmd["matches"], src)
            elif cmd["action"] == "remove":
                self.unload(cmd["matches"], cmd.get("node"), src)

    def depart(self, mid):
        m = self.matches.pop(mid, None)
        if m:
            tb.stop_match(mid)
            m.close_gap(time.time())
            self._closed_gaps += m.gaps
            self.load_since[m.node] = time.time()
            self.note("depart", f"match {mid} left {m.node}", node=m.node)

    def migrate(self, d):
        m = self.matches[d["match"]]
        tb.stop_match(m.mid)
        self.drain(m)                       # the source's last samples still count
        m.close_gap(time.time())
        try:
            path = tb.start_match(self.id, m.mid, d["dst"], m.seg + 1)
        except Exception as e:
            self.matches.pop(m.mid)
            self.note("reject", f"match {m.mid} could not move to {d['dst']}: {e}")
            return
        m.seg += 1
        m.node = d["dst"]
        m.since = m.moved_at = time.time()
        m.back = {}
        m.tail = tb.Tail(path)
        self.load_since[d["src"]] = self.load_since[d["dst"]] = time.time()
        rec = {"t": round(self.elapsed(), 1), **{k: (round(v, 1) if isinstance(v, float) else v)
                                                 for k, v in d.items()}}
        self.migrations.append(rec)
        self.note("migrate", f"match {m.mid} moved {d['src']} to {d['dst']}", **rec)

    # ---- measurement --------------------------------------------------------
    def drain(self, m):
        lines = m.tail.read()
        for ts, bot, rtt in lines[-2:]:          # a sample of each match per tick
            self.raw.appendleft({"ts": ts, "src": m.node, "text": f"{bot} rtt {rtt:.0f} ms  (m{m.mid:02d})"})
        for ts, bot, rtt in lines:
            if m.moved_at is not None and bot not in m.back:
                m.back[bot] = ts / 1000
            self.samples[m.node].append((ts, rtt))
            self.all_rtt.append(rtt)
        if m.moved_at is not None and (len(m.back) >= SIZE or time.time() - m.moved_at > 60):
            m.close_gap(time.time())

    def read_samples(self):
        now_ms = time.time() * 1000
        for m in self.matches.values():
            self.drain(m)
        for q in self.samples.values():
            while q and q[0][0] < now_ms - WINDOW_S * 1000:
                q.popleft()

    def read_servers(self):
        with ThreadPoolExecutor(len(self.nodes)) as ex:
            res = dict(zip(self.nodes, ex.map(lambda n: tb.server_sample(n, self.cpu), self.nodes)))
        now_ms = int(time.time() * 1000)
        for n, r in res.items():
            self.server[n] = r
            for line in r.get("raw", []):
                self.raw.appendleft({"ts": now_ms, "src": n, "text": line, "kind": "server"})

    def snapshot(self):
        load = self.load()
        nodes, worst = {}, None
        for n, spec in self.nodes.items():
            rtts = [r for _, r in self.samples[n]]
            p95 = pct(rtts, 95) if load[n] else None
            preds = {m: (round(pol.predict(n, load[n]), 1) if load[n] else None)
                     for m, pol in self.shadow.items()}
            if p95 is not None:
                worst = p95 if worst is None else max(worst, p95)
                if (time.time() - self.last_shadow >= WINDOW_S
                        and time.time() - self.load_since[n] >= WINDOW_S):
                    for m, pv in preds.items():
                        self.shadow_rows.append((m, n, pv, p95))
            nodes[n] = {"cores": spec["cores"], "rtt_ms": spec["rtt_ms"], "players": load[n],
                        "server_players": self.server[n].get("players"),
                        "online": self.server[n].get("online", []),
                        "mspt_ms": self.server[n].get("mspt_ms"),
                        "cpu_pct": self.server[n].get("cpu_pct"),
                        "p50_ms": pct(rtts, 50) if load[n] else None, "p95_ms": p95,
                        "samples": len(rtts), "predicted": preds,
                        "matches": sorted(m.mid for m in self.matches.values() if m.node == n)}
        if time.time() - self.last_shadow >= WINDOW_S:
            self.last_shadow = time.time()
        pw, _ = self.policy.score(load)
        row = {"t": round(self.elapsed(), 1), "worst_p95_ms": worst,
               "predicted_worst_ms": round(pw, 1) if any(load.values()) else None,
               "players": sum(load.values()),
               "nodes": {n: {"players": v["players"], "p95_ms": v["p95_ms"]} for n, v in nodes.items()}}
        self.timeline.append(row)
        return nodes, row

    def summary(self):
        tl = [r for r in self.timeline if r["worst_p95_ms"] is not None]
        over = sum(1 for r in tl if r["worst_p95_ms"] > BUDGET_MS)
        gaps = [g for m in self.matches.values() for g in m.gaps] + self._closed_gaps
        out = {
            "run": self.id, "policy": self.policy.name, "scenario": self.scenario,
            "arrival": self.arrival, "duration_s": round(self.elapsed(), 1), "status": self.status,
            "samples": len(self.all_rtt),
            "pooled_p50_ms": pct(self.all_rtt, 50), "pooled_p95_ms": pct(self.all_rtt, 95),
            "pooled_p99_ms": pct(self.all_rtt, 99),
            "share_samples_over_budget": (float(np.mean(np.array(self.all_rtt) > BUDGET_MS))
                                          if self.all_rtt else None),
            "worst_p95_median_ms": float(np.median([r["worst_p95_ms"] for r in tl])) if tl else None,
            "worst_p95_max_ms": max((r["worst_p95_ms"] for r in tl), default=None),
            "time_over_budget_share": over / len(tl) if tl else None,
            "migrations": len(self.migrations),
            "migration_gap_mean_s": float(np.mean(gaps)) if gaps else None,
            "budget_ms": BUDGET_MS,
            "shadow": self.shadow_scores(),
        }
        return out

    def shadow_scores(self):
        out = {}
        for m in MODELS:
            rows = [(p, y) for mm, _, p, y in self.shadow_rows if mm == m and p is not None]
            if not rows:
                continue
            p, y = np.array(rows).T
            yb, pb = y > BUDGET_MS, p > BUDGET_MS
            tp, fp, fn = int((yb & pb).sum()), int((~yb & pb).sum()), int((yb & ~pb).sum())
            prec = tp / (tp + fp) if tp + fp else 0.0
            rec = tp / (tp + fn) if tp + fn else 0.0
            out[m] = {"windows": len(rows), "median_abs_err_ms": float(np.median(np.abs(p - y))),
                      "mae_ms": float(np.mean(np.abs(p - y))),
                      "accuracy": float(np.mean(yb == pb)), "precision": prec, "recall": rec,
                      "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
                      "positives": int(yb.sum())}
        return out

    # ---- loop ---------------------------------------------------------------
    def run(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        meta = {"run": self.id, "policy": self.policy.name, "scenario": self.scenario,
                "arrival": self.arrival,
                "scenario_params": SCENARIOS[self.scenario], "length_s": self.length,
                "tick_s": TICK_S, "window_s": WINDOW_S, "rebalance_every_s": REBALANCE_EVERY_S,
                "gains": self.policy.gains.__dict__, "capacity": CAPACITY, "budget_ms": BUDGET_MS,
                "started": time.strftime("%Y-%m-%d %H:%M:%S")}
        write_atomic(self.dir / "meta.json", json.dumps(meta, indent=2))
        tb.stop_all()
        # same gate as every grid cell: nothing from a previous run attached
        self.status = "waiting for empty servers"
        for _ in range(45):
            counts = [tb.server_sample(n, self.cpu)["players"] for n in self.nodes]
            if all(c == 0 for c in counts):
                break
            time.sleep(2)
        self.t0 = time.time()
        self.status = "running"
        pending = list(self.events)
        last_server = last_rebal = -1e9
        tlf = (self.dir / "timeline.jsonl").open("w")
        try:
            while not self.stop_flag.is_set() and self.elapsed() < self.length:
                tick = time.time()
                t = self.elapsed()
                while pending and pending[0][0] <= t:
                    _, kind, mid = pending.pop(0)
                    if kind == "arrive":
                        self.arrive(mid)
                    else:
                        self.depart(mid)
                self.apply_commands()
                self.read_samples()
                if t - last_server >= SERVER_EVERY_S:
                    self.read_servers()
                    last_server = t
                if t - last_rebal >= REBALANCE_EVERY_S and self.matches:
                    d = self.policy.rebalance(
                        self.load(), {m.mid: (m.node, m.since) for m in self.matches.values()},
                        time.time(), SIZE)
                    if d:
                        self.migrate(d)
                    last_rebal = t
                nodes, row = self.snapshot()
                tlf.write(json.dumps(row) + "\n")
                tlf.flush()
                with self.lock:
                    self.state = self.public(nodes)
                time.sleep(max(0.0, TICK_S - (time.time() - tick)))
            self.status = "stopped" if self.stop_flag.is_set() else "finished"
        except Exception as e:                      # keep the testbed clean on any failure
            self.status = f"failed: {e}"
            raise
        finally:
            tb.stop_all()
            tlf.close()
            for m in self.matches.values():
                m.close_gap(time.time())
            write_atomic(self.dir / "migrations.jsonl",
                         "".join(json.dumps(m) + "\n" for m in self.migrations))
            s = self.summary()
            write_atomic(self.dir / "summary.json", json.dumps(s, indent=2))
            with self.lock:
                self.state = {**self.state, "status": self.status, "summary": s}

    def public(self, nodes):
        return {"run": self.id, "policy": self.policy.name, "scenario": self.scenario,
                "arrival": self.arrival, "status": self.status, "t": round(self.elapsed(), 1), "length_s": self.length,
                "updated": time.time(), "budget_ms": BUDGET_MS, "nodes": nodes,
                "series": self.timeline[-450:], "migrations": self.migrations[-50:],
                "log": list(self.log)[:60], "raw": list(self.raw)[:60],
                "summary": self.summary()}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="run one live scenario without the dashboard")
    ap.add_argument("--policy", choices=list(MODELS), default="learned")
    ap.add_argument("--scenario", choices=list(SCENARIOS), default="quick")
    ap.add_argument("--arrival", choices=ARRIVALS, default="nearest")
    a = ap.parse_args()
    r = Run(a.policy, a.scenario, a.arrival)
    print("run", r.id, "length", r.length, "s")
    r.run()
    print(json.dumps(r.summary(), indent=2))

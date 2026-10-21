"""Build a static replay of the dashboard for hosting anywhere.

    python -m live.build_site            # writes site/

The live dashboard drives containers on the testbed host, so it cannot be put
on a web host. This builds the same page backed by files instead of a server:
every finished scenario run in results/live/ becomes a sequence of frames the
page plays back as if it were live, and the offline pages read the same data
the server would serve. Nothing in a frame is invented: players, p95, tick
time, CPU, quota and the live model's cost factor are the run's own logged
values; each model's prediction is recomputed from that logged load; which
match sat on which node is rebuilt from the logged per-node counts and the
logged migrations. What the logs do not keep (raw telemetry lines, the
terminal) is hidden in the replay.
"""
import csv
import json
import shutil
from pathlib import Path

from live.controller import SCENARIOS
from live.policy import POLICIES, make_policy
from placement.models import load_nodes

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "results" / "live"
SITE = REPO / "site"
STATIC = Path(__file__).parent / "static"
SIZE = 10


def jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def offline():
    """The same payload as the server's /api/offline."""
    cells = [r for r in read_csv(REPO / "data" / "cells.csv") if r["run"] in ("grid1", "grid2")]
    curves = {}
    for r in cells:
        curves.setdefault(r["node"], {}).setdefault(int(r["bots"]), []).append(float(r["rtt_p95_ms"]))
    curves = {n: sorted((k, sum(v) / len(v)) for k, v in d.items()) for n, d in curves.items()}
    deploy = read_csv(REPO / "results" / "placement" / "deployments.csv")
    plan = json.loads((REPO / "results" / "placement" / "plan.json").read_text())
    chosen = {e["deployment"] for e in plan["entries"]}
    return {"curves": curves, "deployments": [d for d in deploy if d["deployment"] in chosen],
            "metrics": read_csv(REPO / "results" / "model" / "metrics.csv")}


def frames(meta, tl, mig, models, specs):
    """One dashboard state per logged tick, plus the event log."""
    on = {n: [] for n in specs}                  # node -> match ids, as rebuilt
    next_id, events, out = 0, [], []
    migs = sorted(mig, key=lambda m: m["t"])
    mi = 0
    cut = meta["scenario_params"].get("cut")
    cut_done = False
    for row in tl:
        t = row["t"]
        while mi < len(migs) and migs[mi]["t"] <= t:
            m = migs[mi]
            mid = m["match"]
            for n in on:
                if mid in on[n]:
                    on[n].remove(mid)
            on[m["dst"]].append(mid)
            events.append({"t": m["t"], "kind": "migrate", "text": f"match {mid} moved {m['src']} to {m['dst']}",
                           **{k: m[k] for k in m if k.startswith("predicted")}})
            next_id = max(next_id, mid + 1)
            mi += 1
        if cut and not cut_done and t >= cut["t"]:
            base = specs[cut["node"]]["cores"]
            events.append({"t": cut["t"], "kind": "capacity",
                           "text": f"scenario: {cut['node']} CPU set to {cut['cores']:g} of its {base:g} cores"})
            cut_done = True
        for n, v in row["nodes"].items():
            want = (v.get("players") or 0) // SIZE
            while len(on[n]) < want:
                on[n].append(next_id)
                events.append({"t": t, "kind": "arrive", "text": f"match {next_id} placed on {n}"})
                next_id += 1
            while len(on[n]) > want:
                mid = max(on[n])
                on[n].remove(mid)
                events.append({"t": t, "kind": "depart", "text": f"match {mid} left {n}"})
        nodes = {}
        for n, v in row["nodes"].items():
            p = v.get("players") or 0
            cf = v.get("capacity_factor") or 1.0
            pred = {}
            for name, pol in models.items():
                if not p:
                    pred[name] = None
                elif name == "learned-live":
                    # the logged cost factor applied to the learned curve; the
                    # violation memory is not in the logs and is left out
                    pred[name] = round(pol.model.predict(pol.nodes[n], p * cf), 1)
                else:
                    pred[name] = round(pol.predict(n, p), 1)
            nodes[n] = {"cores": specs[n]["cores"], "rtt_ms": specs[n]["rtt_ms"], "players": p,
                        "quota_cores": v.get("quota_cores"), "capacity_factor": v.get("capacity_factor"),
                        "server_players": p, "online": [], "mspt_ms": v.get("mspt_ms"),
                        "cpu_pct": v.get("cpu_pct"), "p50_ms": None, "p95_ms": v.get("p95_ms"),
                        "samples": None, "predicted": pred, "matches": sorted(on[n])}
        out.append({"t": t, "nodes": nodes})
    return out, events


def main():
    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "data" / "runs").mkdir(parents=True)
    specs = {n["name"]: n for n in load_nodes()}
    models = {name: make_policy(name) for name in POLICIES}
    index = []
    for d in sorted(RESULTS.iterdir()):
        if not (d / "summary.json").exists():
            continue
        summ = json.loads((d / "summary.json").read_text())
        meta = json.loads((d / "meta.json").read_text())
        if summ.get("status") != "finished":
            continue                             # manual sessions have no schedule to replay
        tl, mig = jsonl(d / "timeline.jsonl"), jsonl(d / "migrations.jsonl")
        fr, ev = frames(meta, tl, mig, models, specs)
        (SITE / "data" / "runs" / f"{d.name}.json").write_text(json.dumps(
            {"summary": summ, "timeline": tl, "migrations": mig, "meta": meta,
             "frames": fr, "events": ev}, separators=(",", ":")))
        index.append(summ)
        print("run", d.name, len(fr), "frames")
    index.sort(key=lambda s: s["run"], reverse=True)
    (SITE / "data" / "runs.json").write_text(json.dumps(index))
    (SITE / "data" / "offline.json").write_text(json.dumps(offline()))
    scen = sorted({s["scenario"] for s in index})
    (SITE / "data" / "options.json").write_text(json.dumps(
        {"policies": list(POLICIES), "scenarios": {k: SCENARIOS[k] for k in scen},
         "arrivals": ["nearest"], "busy": False, "running": False}))
    page = (STATIC / "index.html").read_text()
    page = page.replace("<script>", '<script src="replay.js"></script>\n<script>', 1)
    (SITE / "index.html").write_text(page)
    shutil.copy(STATIC / "replay.js", SITE / "replay.js")
    (SITE / ".nojekyll").write_text("")
    print("wrote", SITE)


if __name__ == "__main__":
    main()

"""The end-to-end test: deploy each model's placement and measure who was right.

  plan    for every scenario (total players) and every latency model, compute
          the optimal placement under that model (fitted on the grid runs),
          and write results/placement/plan.json. Identical placements from
          different models are deployed once.
  score   read the deployed cells back (results/raw/<tag>/<deployment>/<node>/)
          and write results/placement/deployments.csv: per model and scenario,
          the measured p95 of every loaded node, the worst of them, and the
          p95 over every player's samples pooled.

    python -m placement.experiment plan --players 40,80,120,160
    controller/deploy_plan.sh place-a              # deploys everything in plan.json
    python -m placement.experiment score --tag place-a
"""
import argparse
import json
from pathlib import Path

import numpy as np

from placement.models import MODELS, load_rows
from placement.run import place

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results" / "placement"
GRID = ["grid1", "grid2"]


def plan(players_list, match_size):
    rows = load_rows(runs=GRID)
    entries, deployments = [], {}
    for players in players_list:
        for model in MODELS:
            p = place(model, "optimal", players, match_size, rows=rows)
            name = "p{}-{}".format(players, "-".join(
                str(p["placement"][n]) for n in ("edge1", "edge2", "edge3", "cloud")))
            deployments[name] = p["deploy_arg"]
            entries.append({**p, "deployment": name})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "plan.json").write_text(json.dumps(
        {"entries": entries, "deployments": deployments}, indent=2) + "\n")
    for e in entries:
        print(f"{e['players']:4d}  {e['model']:10s}  {e['deploy_arg']:40s}"
              f"  predicted worst p95 {e['predicted_worst_p95_ms']} ms")
    print(f"{len(deployments)} distinct deployments")


def rtt_samples(cell):
    meta = json.loads((cell / "meta.json").read_text())
    s0, s1 = meta["steady_start_ms"], meta["steady_end_ms"]
    out = []
    for line in (cell / "bot.csv").read_text(errors="replace").splitlines():
        parts = line.split(",")
        if len(parts) == 4 and parts[2] == "rtt" and parts[0].isdigit():
            if s0 <= int(parts[0]) < s1:
                out.append(float(parts[3]))
    kicks = sum(1 for line in (cell / "bot.csv").read_text(errors="replace").splitlines()
                if ",kicked," in line)
    return out, kicks, meta


def score(tag):
    p = json.loads((OUT / "plan.json").read_text())
    rows = []
    for e in p["entries"]:
        d = REPO / "results" / "raw" / tag / e["deployment"]
        if not d.exists():
            continue
        per_node, pooled, kicks = {}, [], 0
        for node, n in e["placement"].items():
            if n == 0:
                continue
            s, k, _ = rtt_samples(d / node)
            per_node[node] = float(np.percentile(s, 95)) if s else float("nan")
            pooled += s
            kicks += k
        rows.append({
            "tag": tag, "players": e["players"], "model": e["model"],
            "deployment": e["deployment"], "placement": e["deploy_arg"],
            "predicted_worst_p95_ms": e["predicted_worst_p95_ms"],
            "measured_worst_p95_ms": round(max(per_node.values()), 1),
            "measured_pooled_p95_ms": round(float(np.percentile(pooled, 95)), 1),
            "measured_pooled_p99_ms": round(float(np.percentile(pooled, 99)), 1),
            "measured_node_p95_ms": json.dumps({k: round(v, 1) for k, v in per_node.items()}),
            "kicks": kicks,
        })
    import csv
    path = OUT / "deployments.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{'players':>7}  {'model':10s}  {'placement':38s} {'pred worst':>10} {'meas worst':>10} {'pooled p95':>10} kicks")
    for r in rows:
        print(f"{r['players']:>7}  {r['model']:10s}  {r['placement']:38s} {r['predicted_worst_p95_ms']:>10} "
              f"{r['measured_worst_p95_ms']:>10} {r['measured_pooled_p95_ms']:>10} {r['kicks']}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("plan")
    a.add_argument("--players", default="40,80,120,160")
    a.add_argument("--match-size", type=int, default=10)
    b = sub.add_parser("score")
    b.add_argument("--tag", required=True)
    args = ap.parse_args()
    if args.cmd == "plan":
        plan([int(x) for x in args.players.split(",")], args.match_size)
    else:
        score(args.tag)


if __name__ == "__main__":
    main()

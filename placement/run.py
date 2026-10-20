"""Compute a placement and print it as JSON.

    python -m placement.run --model learned --algo optimal --players 120

The learned and queueing models are fitted on data/dataset.csv (grid runs
only) before placing. Output: players per node, the predicted p95 per loaded
node, the predicted worst p95, and a --placement string ready for
controller/deploy.sh.
"""
import argparse
import json

from placement.algorithms import ALGORITHMS, score
from placement.models import MODELS, load_nodes, load_rows


def place(model_name, algo, players, match_size=10, runs=None, rows=None):
    nodes = load_nodes()
    model = MODELS[model_name]()
    if model_name != "analytical":
        model.fit(rows if rows is not None else load_rows(runs=runs))
    k = players // match_size
    placement = ALGORITHMS[algo](nodes, k, match_size, model)
    worst, mean = score(placement, nodes, model, match_size)
    return {
        "model": model_name,
        "algo": algo,
        "players": players,
        "match_size": match_size,
        "placement": {n["name"]: c * match_size for n, c in zip(nodes, placement)},
        "predicted_p95_ms": {n["name"]: round(model.predict(n, c * match_size), 1)
                             for n, c in zip(nodes, placement) if c},
        "predicted_worst_p95_ms": round(worst, 1),
        "predicted_mean_p95_ms": round(mean, 1),
        "deploy_arg": ",".join(f"{n['name']}={c * match_size}" for n, c in zip(nodes, placement)),
    }


def main():
    ap = argparse.ArgumentParser(description="latency-model-driven placement")
    ap.add_argument("--model", choices=sorted(MODELS), required=True)
    ap.add_argument("--algo", choices=sorted(ALGORITHMS), required=True)
    ap.add_argument("--players", type=int, required=True)
    ap.add_argument("--match-size", type=int, default=10)
    ap.add_argument("--runs", help="comma list of grid runs to fit on (default: all)")
    a = ap.parse_args()
    runs = a.runs.split(",") if a.runs else None
    print(json.dumps(place(a.model, a.algo, a.players, a.match_size, runs), indent=2))


if __name__ == "__main__":
    main()

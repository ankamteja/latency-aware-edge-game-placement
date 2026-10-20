"""How well does each latency model predict - and rank - the measured nodes?

Three tests, each one a different claim:

  cross-replicate     fit on one grid replicate, predict the other. Can the
                      model reproduce the curve it was shown, on fresh data?
  leave-one-node-out  fit on three nodes, predict the fourth, whose capacity
                      the model has never seen. Does what it learned transfer
                      to a node of a different size - i.e. is utilization
                      really the unit that travels?
  ranking             for every load level all four nodes were measured at,
                      which node does each model pick, and how much worse is
                      that node's MEASURED p95 than the best node's (regret)?
                      This is the question a placement algorithm asks.

Training always uses 30 s window rows; testing uses whole-cell rows (the full
steady window), so a test number is never computed from rows the model saw.

    python -m model.evaluate               # writes results/model/
"""
import csv
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from placement.models import MODELS, PLAYERS_PER_CORE, load_nodes, load_rows

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results" / "model"
GRID_RUNS = ("grid1", "grid2")


def cells(runs):
    return load_rows(REPO / "data" / "cells.csv", runs=runs)


def node_of(row, nodes):
    n = dict(next(x for x in nodes if x["name"] == row["node"]))
    n["rtt_ms"] = row["net_rtt_idle_ms"]   # the distance actually measured in this cell
    return n


def errors(model, test, nodes):
    out = []
    for r in test:
        pred = model.predict(node_of(r, nodes), r["players"])
        out.append({"cell_id": r["cell_id"], "node": r["node"], "bots": int(r["bots"]),
                    "players": r["players"],
                    "measured_p95_ms": r["rtt_p95_ms"], "predicted_p95_ms": round(pred, 2),
                    "abs_err_ms": round(abs(pred - r["rtt_p95_ms"]), 2),
                    "log_err": round(abs(math.log(pred) - math.log(r["rtt_p95_ms"])), 4)})
    return out


def summary(errs):
    a = np.array([e["abs_err_ms"] for e in errs])
    l = np.array([e["log_err"] for e in errs])
    return {"n": len(errs), "mae_ms": round(float(a.mean()), 1),
            "median_abs_err_ms": round(float(np.median(a)), 1),
            # mean |log(pred/measured)|, shown as a typical factor off
            "typical_factor": round(float(math.exp(l.mean())), 2)}


def fit(name, rows):
    return MODELS[name]().fit(rows)


def cross_replicate(nodes):
    res, detail = {}, []
    for name in MODELS:
        errs = []
        for train, test in (("grid1", "grid2"), ("grid2", "grid1")):
            m = fit(name, load_rows(runs=[train]))
            e = errors(m, cells([test]), nodes)
            for x in e:
                x.update(model=name, split=f"{train}->{test}")
            errs += e
        res[name] = summary(errs)
        detail += errs
    return res, detail


def leave_one_node_out(nodes):
    res, detail = defaultdict(dict), []
    rows = load_rows(runs=list(GRID_RUNS))
    test_cells = cells(list(GRID_RUNS))
    for held in [n["name"] for n in nodes]:
        train = [r for r in rows if r["node"] != held]
        test = [r for r in test_cells if r["node"] == held]
        for name in MODELS:
            e = errors(fit(name, train), test, nodes)
            for x in e:
                x.update(model=name, split=f"without-{held}")
            res[held][name] = summary(e)
            detail += e
    return dict(res), detail


def ranking(nodes):
    """Per load level: measured p95 per node (mean over replicates), each
    model's pick (fitted on both replicates), and the regret of that pick."""
    test = cells(list(GRID_RUNS))
    measured = defaultdict(lambda: defaultdict(list))
    for r in test:
        measured[int(r["bots"])][r["node"]].append(r["rtt_p95_ms"])
    names = [n["name"] for n in nodes]
    levels = sorted(L for L, m in measured.items() if all(n in m for n in names))
    models = {name: fit(name, load_rows(runs=list(GRID_RUNS))) for name in MODELS}
    out = []
    for L in levels:
        meas = {n: float(np.mean(measured[L][n])) for n in names}
        best = min(meas, key=meas.get)
        row = {"players": L, **{f"measured_{n}": round(meas[n], 1) for n in names},
               "measured_best": best}
        for name, m in models.items():
            pred = {n["name"]: m.predict(n, L) for n in nodes}
            pick = min(pred, key=pred.get)
            row[f"{name}_pick"] = pick
            row[f"{name}_regret_ms"] = round(meas[pick] - meas[best], 1)
        out.append(row)
    return out


def write_csv(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    nodes = load_nodes()
    cr, cr_detail = cross_replicate(nodes)
    lono, lono_detail = leave_one_node_out(nodes)
    rank = ranking(nodes)
    write_csv(cr_detail, OUT / "cross_replicate.csv")
    write_csv(lono_detail, OUT / "leave_one_node_out.csv")
    write_csv(rank, OUT / "ranking.csv")

    q = MODELS["queueing"]().fit(load_rows(runs=list(GRID_RUNS)))
    lines = ["# Latency model evaluation", "",
             f"Queueing model fitted service term s = {q.s_ms:.2f} ms "
             f"(capacity {PLAYERS_PER_CORE} players/core).", "",
             "## Cross-replicate (fit one grid replicate, predict the other)", "",
             "| model | cells | MAE (ms) | median abs err (ms) | typical factor off |",
             "|---|---|---|---|---|"]
    for name, s in cr.items():
        lines.append(f"| {name} | {s['n']} | {s['mae_ms']} | {s['median_abs_err_ms']} | {s['typical_factor']}x |")
    lines += ["", "## Leave one node out (median abs err ms / typical factor off)", "",
              "| held-out node | " + " | ".join(MODELS) + " |",
              "|---|" + "---|" * len(MODELS)]
    for held, per in lono.items():
        lines.append(f"| {held} | " + " | ".join(
            f"{per[m]['median_abs_err_ms']} / {per[m]['typical_factor']}x" for m in MODELS) + " |")
    lines += ["", "## Node ranking at each load (measured p95 ms; pick and regret per model)", "",
              "| players | " + " | ".join(n["name"] for n in nodes) + " | best | "
              + " | ".join(f"{m} pick (regret)" for m in MODELS) + " |",
              "|---|" + "---|" * (len(nodes) + 1 + len(MODELS))]
    for r in rank:
        lines.append(f"| {r['players']} | " + " | ".join(str(r[f'measured_{n["name"]}']) for n in nodes)
                     + f" | {r['measured_best']} | "
                     + " | ".join(f"{r[f'{m}_pick']} ({r[f'{m}_regret_ms']})" for m in MODELS) + " |")
    (OUT / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

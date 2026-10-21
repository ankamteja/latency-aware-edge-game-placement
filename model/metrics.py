"""Every standard score for the three latency models, from held-out predictions.

The models are regressors: each predicts a p95 latency in ms. So there are
three families of score, each answering a different question:

  regression      how far off is the number?  MAE, RMSE, median error, MAPE,
                  R^2 on log10 latency (latency spans 5 ms to 30 s, so on a
                  linear scale R^2 is decided by the few multi-second cells),
                  Spearman rank correlation.
  classification  turn the prediction into the decision a placement algorithm
                  actually makes: "will this node violate a latency budget at
                  this load?" Positive = measured p95 above the threshold.
                  Accuracy, precision, recall, F1, balanced accuracy and the
                  confusion matrix, at 50 ms and 100 ms. The thresholds are
                  our choice, not a property of the data - both are reported.
  ranking         for one match, does the model pick the node that measured
                  best? Top-1 accuracy and mean regret over the load levels
                  all four nodes were measured at.

Every prediction scored here is out of sample: cross-replicate (fit on one
grid replicate, predict the other) and, when it exists, the held-out
replicate (fit on grid1+grid2, predict grid3).

    python -m model.metrics          # writes results/model/metrics.{md,csv}
"""
import csv
import math

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import (accuracy_score, balanced_accuracy_score,
                             confusion_matrix, f1_score, precision_score,
                             r2_score, recall_score)

from model.evaluate import OUT, cross_replicate, held_out, held_out_runs, ranking
from placement.models import MODELS, load_nodes

THRESHOLDS_MS = (50, 100)


def regression(rows):
    y = np.array([r["measured_p95_ms"] for r in rows])
    p = np.array([r["predicted_p95_ms"] for r in rows])
    err = np.abs(p - y)
    return {
        "n": len(rows),
        "mae_ms": float(err.mean()),
        "rmse_ms": float(np.sqrt(((p - y) ** 2).mean())),
        "median_abs_err_ms": float(np.median(err)),
        "mape_pct": float((err / y).mean() * 100),
        "r2_log10": float(r2_score(np.log10(y), np.log10(p))),
        "spearman_rho": float(spearmanr(y, p).statistic),
    }


def classification(rows, thr):
    y = np.array([r["measured_p95_ms"] > thr for r in rows])
    p = np.array([r["predicted_p95_ms"] > thr for r in rows])
    tn, fp, fn, tp = confusion_matrix(y, p, labels=[False, True]).ravel()
    return {
        "threshold_ms": thr, "positives": int(y.sum()), "n": len(rows),
        "accuracy": accuracy_score(y, p),
        "precision": precision_score(y, p, zero_division=0),
        "recall": recall_score(y, p, zero_division=0),
        "f1": f1_score(y, p, zero_division=0),
        "balanced_accuracy": balanced_accuracy_score(y, p),
        "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
    }


def ranking_scores(rank):
    out = {}
    for name in MODELS:
        hits = [r[f"{name}_pick"] == r["measured_best"] for r in rank]
        out[name] = {"levels": len(rank), "top1_accuracy": float(np.mean(hits)),
                     "mean_regret_ms": float(np.mean([r[f"{name}_regret_ms"] for r in rank]))}
    return out


def by_model(detail):
    return {name: [r for r in detail if r["model"] == name] for name in MODELS}


def fmt(x, nd=2):
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)


def section(title, groups, lines, flat):
    lines += [f"## {title}", "", "### Regression", "",
              "| model | n | MAE ms | RMSE ms | median abs err ms | MAPE % | R² (log10) | Spearman ρ |",
              "|---|---|---|---|---|---|---|---|"]
    for name, rows in groups.items():
        g = regression(rows)
        flat.append({"split": title, "model": name, "kind": "regression", **g})
        lines.append(f"| {name} | {g['n']} | {fmt(g['mae_ms'],1)} | {fmt(g['rmse_ms'],1)} | "
                     f"{fmt(g['median_abs_err_ms'],1)} | {fmt(g['mape_pct'],1)} | "
                     f"{fmt(g['r2_log10'])} | {fmt(g['spearman_rho'])} |")
    for thr in THRESHOLDS_MS:
        pos = sum(r["measured_p95_ms"] > thr for r in next(iter(groups.values())))
        n = len(next(iter(groups.values())))
        lines += ["", f"### Classification: does p95 exceed {thr} ms? ({pos} of {n} cells do)", "",
                  "| model | accuracy | precision | recall | F1 | balanced acc. | TP | FP | FN | TN |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for name, rows in groups.items():
            c = classification(rows, thr)
            flat.append({"split": title, "model": name, "kind": f"classification@{thr}ms", **c})
            lines.append(f"| {name} | {fmt(c['accuracy'])} | {fmt(c['precision'])} | "
                         f"{fmt(c['recall'])} | {fmt(c['f1'])} | {fmt(c['balanced_accuracy'])} | "
                         f"{c['tp']} | {c['fp']} | {c['fn']} | {c['tn']} |")
    lines.append("")


def main():
    nodes = load_nodes()
    lines = ["# Latency model metrics", "",
             "All predictions are out of sample. Positive class = measured p95 above the threshold "
             "(the node violates the latency budget at that load). See model/metrics.py for definitions.", ""]
    flat = []
    _, cr = cross_replicate(nodes)
    section("Cross-replicate (fit one grid replicate, predict the other)", by_model(cr), lines, flat)
    _, ho = held_out(nodes)
    if ho:
        section(f"Held-out replicate (fit on grid1+grid2, predict {'+'.join(held_out_runs())})",
                by_model(ho), lines, flat)
    rs = ranking_scores(ranking(nodes))
    lines += ["## Ranking: does the model pick the measured-best node for one match?", "",
              "| model | load levels | top-1 accuracy | mean regret ms |", "|---|---|---|---|"]
    for name, r in rs.items():
        flat.append({"split": "ranking", "model": name, "kind": "ranking", **r})
        lines.append(f"| {name} | {r['levels']} | {fmt(r['top1_accuracy'])} | {fmt(r['mean_regret_ms'],1)} |")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "metrics.md").write_text("\n".join(lines) + "\n")
    keys = sorted({k for row in flat for k in row}, key=lambda k: (k not in ("split", "model", "kind"), k))
    with (OUT / "metrics.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(flat)
    print("\n".join(lines))


if __name__ == "__main__":
    main()

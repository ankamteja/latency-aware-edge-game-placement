"""How sure are the model scores? A paired bootstrap over cells.

    python -m model.uncertainty      # writes results/model/uncertainty.md

The cross-replicate (50 cells) and held-out (25 cells) scores in metrics.md
are point estimates from a few dozen cells. Here the cells are resampled with
replacement, 2000 times, and every model is scored on the same resample, so
the difference between two models is measured on identical data each time.
Reported: the 95% percentile interval of each model's median absolute error
and F1, and of the difference in median error between pairs of models, with
the share of resamples in which the first model is better.

Cells are not independent (one node's ladder shares a curve), so these
intervals are, if anything, narrower than the truth.
"""
import csv
from collections import defaultdict

import numpy as np

from model.evaluate import OUT, held_out_runs

B = 2000
SEED = 7
MODELS = ("analytical", "queueing", "learned")
PAIRS = (("learned", "queueing"), ("learned", "analytical"), ("queueing", "analytical"))
THRESHOLDS = (50, 100)


def load(path):
    """{cell: {model: (measured, predicted)}} for one test split."""
    cells = defaultdict(dict)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            # cross-replicate predicts each replicate from the other: a cell
            # id already names its replicate, so cells stay distinct
            cells[r["cell_id"]][r["model"]] = (float(r["measured_p95_ms"]),
                                               float(r["predicted_p95_ms"]))
    return {c: m for c, m in cells.items() if all(k in m for k in MODELS)}


def f1(y, p, thr):
    yt, pt = y > thr, p > thr
    tp = np.sum(yt & pt)
    denom = 2 * tp + np.sum(~yt & pt) + np.sum(yt & ~pt)
    return 2 * tp / denom if denom else np.nan


def boot(cells):
    ids = sorted(cells)
    y = np.array([cells[c][MODELS[0]][0] for c in ids])
    pred = {m: np.array([cells[c][m][1] for c in ids]) for m in MODELS}
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(ids), size=(B, len(ids)))
    med = {m: np.median(np.abs(pred[m][idx] - y[idx]), axis=1) for m in MODELS}
    f1s = {(m, t): np.array([f1(y[i], pred[m][i], t) for i in idx]) for m in MODELS
           for t in THRESHOLDS}
    point = {m: float(np.median(np.abs(pred[m] - y))) for m in MODELS}
    f1p = {(m, t): f1(y, pred[m], t) for m in MODELS for t in THRESHOLDS}
    return len(ids), point, med, f1p, f1s


def ci(a):
    a = a[~np.isnan(a)]
    return np.percentile(a, 2.5), np.percentile(a, 97.5)


def section(title, path):
    cells = load(path)
    n, point, med, f1p, f1s = boot(cells)
    out = [f"## {title} ({n} cells, {B} paired resamples)", "",
           "| model | median abs error, ms [95% CI] | F1, p95 > 50 ms [95% CI] | F1, p95 > 100 ms [95% CI] |",
           "|---|---|---|---|"]
    for m in MODELS:
        lo, hi = ci(med[m])
        cells_f1 = []
        for t in THRESHOLDS:
            a, b = ci(f1s[(m, t)])
            cells_f1.append(f"{f1p[(m, t)]:.2f} [{a:.2f}, {b:.2f}]")
        out.append(f"| {m} | {point[m]:.1f} [{lo:.1f}, {hi:.1f}] | " + " | ".join(cells_f1) + " |")
    out += ["", "| difference in median error | ms [95% CI] | first model better in |",
            "|---|---|---|"]
    for a, b in PAIRS:
        d = med[a] - med[b]
        lo, hi = ci(d)
        out.append(f"| {a} - {b} | {point[a] - point[b]:+.1f} [{lo:+.1f}, {hi:+.1f}] "
                   f"| {np.mean(d < 0) * 100:.0f}% of resamples |")
    return out + [""]


def main():
    lines = ["# Uncertainty of the model scores", "",
             "Paired bootstrap over cells; see model/uncertainty.py for the method",
             "and why the intervals are optimistic.", ""]
    lines += section("Cross-replicate", OUT / "cross_replicate.csv")
    if (OUT / "held_out.csv").exists():
        lines += section(f"Held-out replicates ({'+'.join(held_out_runs())})", OUT / "held_out.csv")
    (OUT / "uncertainty.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()

"""One table of every finished live run, from the run logs.

    python -m live.summarize          # writes results/live/summary.md

Grouped by scenario and controller, one row per run, so repeated runs of the
same pair sit next to each other. For capacity-drop runs the worst node's p95
is also split at the cut, because before it the controllers face the same
arrivals and after it they face different nodes.
"""
import json
import statistics as st
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results" / "live"
BUDGET_MS = 100.0


def load(d):
    meta = json.loads((d / "meta.json").read_text())
    summ = json.loads((d / "summary.json").read_text())
    tl = [json.loads(l) for l in (d / "timeline.jsonl").read_text().splitlines() if l.strip()]
    return meta, summ, tl


def window(tl, lo, hi):
    w = [r["worst_p95_ms"] for r in tl if lo <= r["t"] < hi and r["worst_p95_ms"]]
    if not w:
        return None
    return st.median(w), sum(x > BUDGET_MS for x in w) / len(w), max(w)


def fmt_ms(x):
    return f"{x / 1000:.1f} s" if x >= 1000 else f"{x:.0f} ms"


def main():
    runs = []
    for d in sorted(RESULTS.iterdir()):
        if not (d / "summary.json").exists():
            continue
        meta, summ, tl = load(d)
        if summ.get("status") != "finished":
            continue
        runs.append((meta, summ, tl, d.name))
    lines = ["# Live runs", "", "Every finished run in results/live/, from its own logs.",
             "Worst = the worst node's p95 over the last 10 s, sampled every tick.", ""]
    for sc in sorted({m["scenario"] for m, *_ in runs}):
        rows = [r for r in runs if r[0]["scenario"] == sc]
        rows.sort(key=lambda r: (r[0]["policy"], r[3]))
        cut = rows[0][0]["scenario_params"].get("cut")
        lines += [f"## {sc}", ""]
        head = "| run | controller | worst p95, median | time over 100 ms | worst, max | moves | mean reconnect |"
        sep = "|---|---|---|---|---|---|---|"
        if cut:
            head += f" after the cut ({cut['t']} s): median / over 100 ms / max |"
            sep += "---|"
        lines += [head, sep]
        for meta, summ, tl, name in rows:
            gap = summ.get("migration_gap_mean_s")
            row = (f"| {name} | {meta['policy']} | {fmt_ms(summ['worst_p95_median_ms'])} "
                   f"| {summ['time_over_budget_share'] * 100:.0f}% | {fmt_ms(summ['worst_p95_max_ms'])} "
                   f"| {summ['migrations']} | {f'{gap:.1f} s' if gap else '-'} |")
            if cut:
                w = window(tl, cut["t"], 1e9)
                row += (f" {fmt_ms(w[0])} / {w[1] * 100:.0f}% / {fmt_ms(w[2])} |" if w else " - |")
            lines.append(row)
        lines.append("")
    out = RESULTS / "summary.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()

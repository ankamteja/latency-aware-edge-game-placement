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
# learned-live runs before this one ran without the violation memory (commit
# 67bb894); they are reported as their own configuration
MEMORY_FROM = "20261021-112507411"


def label(meta, name):
    """learned-live has three versions: no violation memory, memory but
    learning from join windows too, and memory plus the settle rule
    (meta observe_settle_s, live/controller.py OBSERVE_SETTLE_S)."""
    p = meta["policy"]
    if p == "learned-live" and name < MEMORY_FROM:
        return "learned-live, first version"
    if p == "learned-live" and "observe_settle_s" not in meta:
        return "learned-live, before the settle rule"
    return p


def load(d):
    meta = json.loads((d / "meta.json").read_text())
    summ = json.loads((d / "summary.json").read_text())
    tl = [json.loads(l) for l in (d / "timeline.jsonl").read_text().splitlines() if l.strip()]
    return meta, summ, tl


def at_cut(tl, cut):
    """When the quota change actually took effect (the scenario asks for it at
    cut["t"]; applying it takes a few seconds) and how many players the cut
    node held just before. A controller that had already emptied the node is
    not tested on noticing the cut, only on staying away."""
    node = cut["node"]
    t = next((r["t"] for r in tl if r["nodes"][node].get("quota_cores") == cut["cores"]), cut["t"])
    before = [r for r in tl if r["t"] < t]
    return t, (before[-1]["nodes"][node]["players"] if before else None)


def window(tl, lo, hi):
    w = [r["worst_p95_ms"] for r in tl if lo <= r["t"] < hi and r["worst_p95_ms"]]
    if not w:
        return None
    return st.median(w), sum(x > BUDGET_MS for x in w) / len(w), max(w)


def fmt_ms(x):
    return f"{x / 1000:.1f} s" if x >= 1000 else f"{x:.0f} ms"


def span(vals, fmt):
    vals = sorted(vals)
    mid = st.median(vals)
    return fmt(mid) if len(vals) == 1 else f"{fmt(mid)} [{fmt(vals[0])}, {fmt(vals[-1])}]"


def aggregate(runs):
    """Per scenario and controller: the median over runs, [lowest, highest]."""
    pct = lambda v: f"{v * 100:.0f}%"
    out = ["## By configuration", "",
           "Median over runs, with [lowest, highest] when there is more than one.", ""]
    for sc in sorted({m["scenario"] for m, *_ in runs}):
        rows = [r for r in runs if r[0]["scenario"] == sc]
        cut = rows[0][0]["scenario_params"].get("cut")
        head = "| scenario | controller | runs | worst p95, median | time over 100 ms | moves |"
        sep = "|---|---|---|---|---|---|"
        if cut:
            head += f" {cut['node']} players at the cut | after the cut: time over 100 ms |"
            sep += "---|---|"
        out += [head, sep]
        for lab in sorted({label(m, n) for m, _, _, n in rows}):
            g = [r for r in rows if label(r[0], r[3]) == lab]
            line = (f"| {sc} | {lab} | {len(g)} | {span([r[1]['worst_p95_median_ms'] for r in g], fmt_ms)} "
                    f"| {span([r[1]['time_over_budget_share'] for r in g], pct)} "
                    f"| {span([r[1]['migrations'] for r in g], lambda v: f'{v:g}')} |")
            if cut:
                cuts = [at_cut(r[2], cut) for r in g]
                w = [window(r[2], t, 1e9) for (t, _), r in zip(cuts, g)]
                held = ", ".join(str(p) for _, p in cuts)
                line += f" {held} | {span([x[1] for x in w if x], pct)} |"
            out.append(line)
        out.append("")
    return out


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
        rows.sort(key=lambda r: (label(r[0], r[3]), r[3]))
        cut = rows[0][0]["scenario_params"].get("cut")
        lines += [f"## {sc}", ""]
        head = "| run | controller | worst p95, median | time over 100 ms | worst, max | moves | mean reconnect |"
        sep = "|---|---|---|---|---|---|---|"
        if cut:
            head += f" cut took effect | {cut['node']} players then | after the cut: median / over 100 ms / max |"
            sep += "---|---|---|"
        lines += [head, sep]
        for meta, summ, tl, name in rows:
            gap = summ.get("migration_gap_mean_s")
            row = (f"| {name} | {label(meta, name)} | {fmt_ms(summ['worst_p95_median_ms'])} "
                   f"| {summ['time_over_budget_share'] * 100:.0f}% | {fmt_ms(summ['worst_p95_max_ms'])} "
                   f"| {summ['migrations']} | {f'{gap:.1f} s' if gap else '-'} |")
            if cut:
                t, held = at_cut(tl, cut)
                w = window(tl, t, 1e9)
                row += f" {t:.0f} s | {held} |"
                row += (f" {fmt_ms(w[0])} / {w[1] * 100:.0f}% / {fmt_ms(w[2])} |" if w else " - |")
            lines.append(row)
        lines.append("")
    lines += aggregate(runs)
    out = RESULTS / "summary.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()

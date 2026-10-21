"""Figures from live runs, for the write-up and the slides.

    python -m live.figures                 # writes figures/fig6_*.png, fig7_*.png

  fig6_live_ab.png              the standard schedule under each controller:
                                worst node's p95 over time, migrations marked,
                                and the players connected (same for both)
  fig7_live_capacity_drop.png   edge1's CPU halved mid-run: edge1's p95 and
                                players under each controller, and the
                                live-corrected model's estimate of how much
                                more each player costs edge1

Each figure uses the typical run of each controller for that scenario (the
one with the median worst-player p95 over its runs); pass --ab or --drop to
pick others.
"""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from model.figures import FIG, INK, MUTED  # noqa: E402  (shared style)
from placement.models import load_nodes  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results" / "live"
COLOR = {"analytical": "#2a78d6", "queueing": "#eb6834", "learned": "#1baf7a",
         "learned-live": "#8a5cc2"}
LABEL = {"analytical": "analytical (load-blind)", "queueing": "queueing (M/M/1)",
         "learned": "learned", "learned-live": "learned, corrected live"}
BUDGET_MS = 100


def load(run_dir):
    d = Path(run_dir)
    meta = json.loads((d / "meta.json").read_text())
    tl = [json.loads(l) for l in (d / "timeline.jsonl").read_text().splitlines() if l.strip()]
    mig = [json.loads(l) for l in (d / "migrations.jsonl").read_text().splitlines() if l.strip()]
    summ = json.loads((d / "summary.json").read_text()) if (d / "summary.json").exists() else {}
    return {"dir": d, "meta": meta, "tl": tl, "mig": mig, "summary": summ}


def representative(scenario, policies):
    """For each policy, the finished run whose worst-player median is the
    median of its runs: the typical run, not the luckiest or the newest.
    learned-live runs from before the violation memory are left out. In a
    capacity-drop, runs whose controller had already emptied the cut node
    are left out too: they cannot show the cut being noticed (docs/09 9.6)."""
    from live.summarize import at_cut
    by = {}
    for d in sorted(RESULTS.iterdir()):
        if not (d / "summary.json").exists() or not (d / "meta.json").exists():
            continue
        r = load(d)
        p = r["meta"]["policy"]
        if r["meta"]["scenario"] != scenario or p not in policies \
                or r["summary"].get("status") != "finished":
            continue
        if p == "learned-live" and "observe_settle_s" not in r["meta"]:
            continue                 # earlier versions; summary.md lists them
        cut = r["meta"]["scenario_params"].get("cut")
        if cut and at_cut(r["tl"], cut)[1] == 0:
            continue
        by.setdefault(p, []).append(r)
    out = []
    for p in policies:
        if p in by:
            runs = sorted(by[p], key=lambda r: r["summary"]["worst_p95_median_ms"])
            out.append(runs[(len(runs) - 1) // 2])
    return out


def fig_ab(runs, path):
    fig, (ax, axp) = plt.subplots(2, 1, figsize=(8, 5.2), sharex=True,
                                  gridspec_kw={"height_ratios": [3, 1.2]})
    for r in runs:
        p = r["meta"]["policy"]
        pts = [(x["t"], x["worst_p95_ms"]) for x in r["tl"] if x["worst_p95_ms"]]
        ax.plot(*zip(*pts), color=COLOR[p], lw=1.6,
                label=f"{LABEL[p]}: {len(r['mig'])} migrations")
        for m in r["mig"]:
            ax.axvline(m["t"], color=COLOR[p], lw=0.6, alpha=0.35, ymax=0.06)
    ax.axhline(BUDGET_MS, color="#d05a52", lw=1, ls="--")
    ax.text(2, BUDGET_MS * 1.12, "100 ms budget", color="#d05a52", fontsize=8)
    ax.set_yscale("log")
    ax.set_ylabel("worst node's p95, ms")
    ax.set_title("Same arrivals and departures under each controller, real testbed")
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, hi * 30)             # headroom: the legend sits above the curves
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    tl = runs[0]["tl"]
    axp.plot([x["t"] for x in tl], [x["players"] for x in tl], color=MUTED, lw=1.4)
    axp.set_ylabel("players")
    axp.set_xlabel("time, s")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def fig_drop(runs, path):
    fig, (ax, axn, axc) = plt.subplots(3, 1, figsize=(8, 6.4), sharex=True,
                                       gridspec_kw={"height_ratios": [3, 1.2, 1.2]})
    cut = runs[0]["meta"]["scenario_params"]["cut"]
    for r in runs:
        p = r["meta"]["policy"]
        e = [(x["t"], x["nodes"]["edge1"]) for x in r["tl"]]
        # no players on edge1 = no latency: a gap in the line, not a ramp
        pts = [(t, n["p95_ms"] if n.get("players") and n.get("p95_ms") else float("nan"))
               for t, n in e]
        ax.plot(*zip(*pts), color=COLOR[p], lw=1.6, label=LABEL[p])
        axn.plot([t for t, _ in e], [n["players"] for _, n in e], color=COLOR[p], lw=1.4)
        if p == "learned-live":
            cf = [(t, n.get("capacity_factor")) for t, n in e if n.get("capacity_factor")]
            if cf:
                axc.plot(*zip(*cf), color=COLOR[p], lw=1.6)
    for a in (ax, axn, axc):
        a.axvline(cut["t"], color=INK, lw=0.8, ls=":")
    base = {n["name"]: n["cores"] for n in load_nodes()}[cut["node"]]
    ax.text(cut["t"] + 4, BUDGET_MS * 1.6,
            f"{cut['node']} CPU cut to {cut['cores']:g} of {base:g} cores", fontsize=8, color=INK)
    ax.axhline(BUDGET_MS, color="#d05a52", lw=1, ls="--")
    ax.set_yscale("log")
    ax.set_ylabel("edge1 p95, ms")
    ax.set_title("edge1 gets slower mid-run; no model is told")
    ax.legend(loc="upper left", fontsize=8)
    axn.set_ylabel("edge1 players")
    # the true factor: the node now has base / cut cores' worth of time per player
    axc.axhline(base / cut["cores"], color=MUTED, lw=0.8, ls="--")
    axc.set_ylabel("cost factor")
    axc.set_xlabel("time, s")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ab", nargs="*", help="run dirs for fig6 (default: the typical run per controller)")
    ap.add_argument("--drop", nargs="*", help="run dirs for fig7 (default: the typical run per controller)")
    a = ap.parse_args()
    ab = [load(d) for d in a.ab] if a.ab else representative("standard", ["analytical", "queueing", "learned", "learned-live"])
    drop = [load(d) for d in a.drop] if a.drop else representative("capacity-drop",
                                                                  ["queueing", "learned", "learned-live"])
    if ab:
        fig_ab(ab, FIG / "fig6_live_ab.png")
        print("wrote", FIG / "fig6_live_ab.png", [r["dir"].name for r in ab])
    if drop:
        fig_drop(drop, FIG / "fig7_live_capacity_drop.png")
        print("wrote", FIG / "fig7_live_capacity_drop.png", [r["dir"].name for r in drop])


if __name__ == "__main__":
    main()

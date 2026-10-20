"""Figures for the write-up, from data/cells.csv and results/model/.

    python -m model.figures          # writes figures/*.png

  fig1_p95_vs_players.png      measured p95 per node against player count,
                               with the analytical model's prediction for
                               each node drawn flat beside it
  fig2_delay_vs_utilization.png  server-side delay (p95 minus network RTT)
                               against utilization: do nodes of different
                               size land on one curve?
  fig3_layers_edge1.png        the four probes on edge1 under rising load:
                               the network stays flat, the game thread does not
  fig4_predicted_vs_measured.png  each model's cross-replicate predictions
  fig5_deployments.png         measured worst-player p95 of every deployed
                               placement, by model (if deployments exist)
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FIG = REPO / "figures"
GRID = ("grid1", "grid2")

# Fixed categorical order (identity follows the node, never its rank).
NODE_COLOR = {"edge1": "#2a78d6", "edge2": "#eb6834", "edge3": "#1baf7a", "cloud": "#c98500"}
MODEL_COLOR = {"analytical": "#2a78d6", "queueing": "#eb6834", "learned": "#1baf7a"}
INK, MUTED, GRIDC, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRIDC, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold",
    "legend.frameon": False, "lines.linewidth": 2,
})


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def grid_cells():
    return [r for r in read(REPO / "data" / "cells.csv") if r["run"] in GRID]


def by_node(cells):
    out = defaultdict(lambda: defaultdict(list))
    for r in cells:
        out[r["node"]][int(r["bots"])].append(r)
    return out


def save(fig, name):
    FIG.mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=180)
    plt.close(fig)
    print("wrote", FIG / name)


def fig1(cells, nodes):
    fig, ax = plt.subplots(figsize=(7, 4.3))
    groups = by_node(cells)
    for n in nodes:
        name, c = n["name"], NODE_COLOR[n["name"]]
        xs = sorted(groups[name])
        for x in xs:
            ax.scatter([x] * len(groups[name][x]), [float(r["rtt_p95_ms"]) for r in groups[name][x]],
                       s=18, color=c, alpha=0.45, linewidths=0, zorder=3)
        mean = [np.mean([float(r["rtt_p95_ms"]) for r in groups[name][x]]) for x in xs]
        ax.plot(xs, mean, color=c, marker="o", markersize=5, zorder=4,
                label=f"{name}  ({n['cores']:g} core, {n['rtt_ms']:.0f} ms)")
        ax.plot([0, 100], [n["rtt_ms"]] * 2, color=c, linestyle=(0, (4, 3)), linewidth=1.2, zorder=2)
    ax.set_yscale("log")
    ax.set_xlabel("players on the node")
    ax.set_ylabel("in-game RTT p95 (ms, log scale)")
    ax.set_title("Measured tail latency vs the load-blind model (dashed)")
    ax.legend(loc="upper left", fontsize=8.5)
    save(fig, "fig1_p95_vs_players.png")


def fig2(cells, nodes):
    fig, ax = plt.subplots(figsize=(7, 4.3))
    for n in nodes:
        rows = [r for r in cells if r["node"] == n["name"]]
        u = [int(r["bots"]) / (100 * n["cores"]) for r in rows]
        d = [max(float(r["rtt_p95_ms"]) - float(r["net_rtt_idle_ms"]), 0.5) for r in rows]
        ax.scatter(u, d, s=26, color=NODE_COLOR[n["name"]], label=n["name"], zorder=3,
                   edgecolors=SURFACE, linewidths=1)
    ax.axvline(1.0, color=MUTED, linewidth=1, linestyle=(0, (2, 2)))
    ax.text(1.01, ax.get_ylim()[0] * 1.5 if ax.get_yscale() == "log" else 1, "capacity",
            color=MUTED, fontsize=8)
    ax.set_yscale("log")
    ax.set_xlabel("utilization  u = players / (100 x cores)")
    ax.set_ylabel("server-side delay: p95 - network RTT (ms, log)")
    ax.set_title("Server delay against utilization, all four nodes")
    ax.legend(loc="upper left", fontsize=8.5)
    save(fig, "fig2_delay_vs_utilization.png")


def fig3(cells):
    rows = sorted([r for r in cells if r["node"] == "edge1" and r["run"] == "grid1"],
                  key=lambda r: int(r["bots"]))
    if not rows:
        return
    x = [int(r["bots"]) for r in rows]
    fig, ax = plt.subplots(figsize=(7, 4.3))
    series = [("ICMP ping p50 (network only)", "net_rtt_ms", "#2a78d6"),
              ("TCP handshake p50", "tcp_p50_ms", "#1baf7a"),
              ("status ping p50 (server process)", "status_p50_ms", "#c98500"),
              ("in-game RTT p95 (game thread)", "rtt_p95_ms", "#eb6834")]
    for label, key, c in series:
        ax.plot(x, [float(r[key]) for r in rows], color=c, marker="o", markersize=5, label=label)
    ax.set_yscale("log")
    ax.set_xlabel("players on edge1 (0.5 core, 5 ms)")
    ax.set_ylabel("ms (log scale)")
    ax.set_title("Same path, four depths: only the game thread degrades")
    ax.legend(loc="upper left", fontsize=8.5)
    save(fig, "fig3_layers_edge1.png")


def fig4():
    path = REPO / "results" / "model" / "cross_replicate.csv"
    if not path.exists():
        return
    rows = read(path)
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.6), sharex=True, sharey=True)
    for ax, model in zip(axes, ("analytical", "queueing", "learned")):
        rs = [r for r in rows if r["model"] == model]
        m = [float(r["measured_p95_ms"]) for r in rs]
        p = [float(r["predicted_p95_ms"]) for r in rs]
        for node, c in NODE_COLOR.items():
            idx = [i for i, r in enumerate(rs) if r["node"] == node]
            ax.scatter([m[i] for i in idx], [p[i] for i in idx], s=20, color=c, label=node,
                       edgecolors=SURFACE, linewidths=0.8, zorder=3)
        lo, hi = 3, max(m + p) * 1.5
        ax.plot([lo, hi], [lo, hi], color=MUTED, linewidth=1, zorder=2)
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_title(model)
        ax.set_xlabel("measured p95 (ms)")
    axes[0].set_ylabel("predicted p95 (ms)")
    axes[0].legend(fontsize=8, loc="upper left")
    fig.suptitle("Predicted vs measured, fitted on one replicate, tested on the other",
                 fontsize=11, fontweight="bold")
    save(fig, "fig4_predicted_vs_measured.png")


def fig5():
    path = REPO / "results" / "placement" / "deployments.csv"
    if not path.exists():
        return
    rows = read(path)
    scen = sorted({int(r["players"]) for r in rows})
    models = [m for m in ("analytical", "queueing", "learned") if any(r["model"] == m for r in rows)]
    fig, ax = plt.subplots(figsize=(7, 4.3))
    w = 0.8 / len(models)
    for j, m in enumerate(models):
        ys = []
        for s in scen:
            r = [x for x in rows if x["model"] == m and int(x["players"]) == s]
            ys.append(float(r[0]["measured_worst_p95_ms"]) if r else np.nan)
        xs = np.arange(len(scen)) + (j - (len(models) - 1) / 2) * w
        ax.bar(xs, ys, width=w * 0.92, color=MODEL_COLOR[m], label=f"{m} model", zorder=3)
    ax.set_yscale("log")
    ax.set_xticks(np.arange(len(scen)), [f"{s} players" for s in scen])
    ax.set_ylabel("worst node's measured p95 (ms, log)")
    ax.set_title("Each model's optimal placement, deployed and measured")
    ax.legend(fontsize=8.5, loc="upper left")
    save(fig, "fig5_deployments.png")


def main():
    nodes = json.loads((REPO / "placement" / "nodes.json").read_text())
    cells = grid_cells()
    if cells:
        fig1(cells, nodes)
        fig2(cells, nodes)
        fig3(cells)
    fig4()
    fig5()


if __name__ == "__main__":
    main()

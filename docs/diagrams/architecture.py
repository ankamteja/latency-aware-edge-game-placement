#!/usr/bin/env python3
"""Architecture figure for the edge placement testbed.

Two panels, labels only:
  top     the lab - client, four candidates, the emulated links between them
  bottom  how deep into a node each of the four probes reaches
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib import font_manager

W, H, DPI = 2400, 1700, 200

BG    = "#FFFFFF"
INK   = "#16181D"
GREY  = "#6B7280"
FAINT = "#9CA3AF"
FILL  = "#F4F5F7"
SHADE = "#E4E6EA"
RULE  = "#C9CDD4"
ACC   = "#B3261E"

FDIR = "/home/charan/.local/share/fonts"
for f in ("JetBrainsMono-Regular.ttf", "JetBrainsMono-Bold.ttf"):
    p = os.path.join(FDIR, f)
    if os.path.exists(p):
        font_manager.fontManager.addfont(p)
FAM = "JetBrains Mono" if any(
    fe.name == "JetBrains Mono" for fe in font_manager.fontManager.ttflist
) else "monospace"
plt.rcParams["font.family"] = FAM

fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=BG)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")


def t(x, y, s, size=10, color=INK, weight="normal", ha="left", va="center", **kw):
    ax.text(x, y, s, fontsize=size, color=color, fontweight=weight,
            ha=ha, va=va, zorder=8, **kw)


def box(x0, y0, x1, y1, fc=FILL, ec=INK, lw=1.6, r=4, z=2):
    ax.add_patch(FancyBboxPatch(
        (x0, y0), x1 - x0, y1 - y0,
        boxstyle=f"round,pad=0,rounding_size={r}",
        facecolor=fc, edgecolor=ec, linewidth=lw, zorder=z))


def arrow(x0, y0, x1, y1, color=INK, lw=1.6, head=10):
    ax.add_patch(FancyArrowPatch(
        (x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=head,
        color=color, linewidth=lw, zorder=6, shrinkA=0, shrinkB=0))


def line(x0, y0, x1, y1, color=INK, lw=1.6, z=4, ls="-"):
    ax.plot([x0, x1], [y0, y1], color=color, linewidth=lw, zorder=z,
            linestyle=ls, solid_capstyle="butt")


# ---------------------------------------------------------------- header ----
t(90, 1636, "edgegame testbed", 15, INK, "bold")
t(90, 1602, "containerlab, single host", 10, GREY)
line(90, 1570, W - 90, 1570, RULE, 1.4)

# --------------------------------------------------------------- panel 1 ----
CX0, CX1, CY0, CY1 = 90, 570, 1090, 1500
box(CX0, CY0, CX1, CY1)
t(CX0 + 26, CY1 - 42, "client", 13, INK, "bold")
t(CX0 + 26, CY1 - 76, "cores 12-27", 10, GREY)
line(CX0 + 26, CY1 - 102, CX1 - 26, CY1 - 102, RULE, 1.2)
for i, (name, desc) in enumerate([("bot.js", "load, in-game RTT"),
                                  ("probe.js", "tcp, status"),
                                  ("ping", "icmp")]):
    yy = CY1 - 146 - i * 78
    t(CX0 + 26, yy, name, 11, INK, "bold")
    t(CX0 + 26, yy - 28, desc, 9.5, GREY)
t(CX0 + 26, CY0 + 34, "eth1-eth4", 9.5, GREY)

SPX = 660
line(CX1, (CY0 + CY1) / 2, SPX, (CY0 + CY1) / 2, INK, 1.6)
line(SPX, 1075, SPX, 1445, INK, 1.6)

NODES = [("edge1", "0.5 core", "cores 0-1",  "2.5 ms", "5.10 ms",  "50"),
         ("edge2", "1 core",   "cores 2-3",  "7.5 ms", "15.25 ms", "100"),
         ("edge3", "2 cores",  "cores 4-6",  "15 ms",  "30.19 ms", "> 100"),
         ("cloud", "4 cores",  "cores 7-11", "20 ms",  "40.26 ms", "> 100")]
NX0, NX1 = 1560, 2310
for i, (name, quota, cset, half, rtt, nmax) in enumerate(NODES):
    y1 = 1500 - i * 110
    y0 = y1 - 90
    yc = (y0 + y1) / 2
    arrow(SPX, yc, NX0, yc, INK, 1.6, head=11)
    t(SPX + 20, yc + 22, f"netem {half} each end", 9.5, GREY)
    t(SPX + 20, yc - 22, f"RTT {rtt}", 10.5, INK, "bold")
    box(NX0, y0, NX1, y1)
    t(NX0 + 24, yc + 17, name, 12, INK, "bold")
    t(NX0 + 24, yc - 19, f"{quota}, {cset}", 9.5, GREY)
    t(NX1 - 24, yc + 17, f"N_max {nmax}", 10.5, INK, ha="right")

t(90, 1020, "N_max = players held before tick time exceeds the 50 ms budget", 9.5, FAINT)

line(90, 960, W - 90, 960, RULE, 1.4)

# --------------------------------------------------------------- panel 2 ----
t(90, 908, "probe depth", 13, INK, "bold")
t(90, 876, "one path, measured at four depths", 10, GREY)

BY0, BY1 = 290, 800
LAYERS = [("client",            90,  280,  FILL),
          ("wire\nnetem",       310, 500,  FILL),
          ("kernel\nnetstack",  520, 790,  FILL),
          ("tcp accept\nqueue", 810, 1080, FILL),
          ("server\nprocess",   1100, 1430, FILL),
          ("main game thread\n50 ms tick budget", 1450, 1880, SHADE)]
for label, x0, x1, fc in LAYERS:
    box(x0, BY0, x1, BY1, fc=fc, ec=INK, lw=1.4, r=4, z=1)
    t((x0 + x1) / 2, BY1 - 42, label, 9.5, INK, "bold", ha="center",
      linespacing=1.6)

RUNGS = [("icmp",    655,  FAINT),
         ("tcp",     945,  GREY),
         ("status",  1265, "#374151"),
         ("in-game", 1665, ACC)]
GUT = 1920
for i, (name, xturn, col) in enumerate(RUNGS):
    yc = 700 - i * 108
    arrow(282, yc + 11, xturn, yc + 11, col, 1.8, head=11)
    line(xturn, yc + 11, xturn, yc - 11, col, 1.8, z=6)
    arrow(xturn, yc - 11, 282, yc - 11, col, 1.8, head=11)
    line(xturn, yc, GUT - 12, yc, col, 0.9, ls=(0, (2, 3)))
    t(GUT, yc, name, 11, col, "bold")

BRK = 254
line(310, BRK, 790, BRK, INK, 1.6)
line(310, BRK, 310, BRK + 14, INK, 1.6)
line(790, BRK, 790, BRK + 14, INK, 1.6)
t(310, BRK - 36, "propagation_delay + data_size / bandwidth", 10.5, INK, "bold")
t(310, BRK - 66, "the analytical model reaches this far", 9.5, GREY)

t(1450, BRK - 36, "queueing delay", 10.5, ACC, "bold")
t(1450, BRK - 66, "no term in the model", 9.5, GREY)
line(1450, BRK, 1880, BRK, ACC, 1.6)
line(1450, BRK, 1450, BRK + 14, ACC, 1.6)
line(1880, BRK, 1880, BRK + 14, ACC, 1.6)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "architecture.png")
fig.savefig(OUT, facecolor=BG, dpi=DPI)
print("wrote", OUT)

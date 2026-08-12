#!/usr/bin/env python3
"""Code map: what every source file in the repo does, and the order they run in.

Line counts are the real ones (wc -l), not estimates.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib import font_manager

W, H, DPI = 2400, 940, 200

BG    = "#FFFFFF"
INK   = "#16181D"
GREY  = "#6B7280"
FAINT = "#9CA3AF"
FILL  = "#F4F5F7"
SHADE = "#E4E6EA"
RULE  = "#C9CDD4"

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


def Y(off):
    return H - off


def t(x, off, s, size=10, color=INK, weight="normal", ha="left", va="center", **kw):
    ax.text(x, Y(off), s, fontsize=size, color=color, fontweight=weight,
            ha=ha, va=va, zorder=8, **kw)


def box(x0, off0, x1, off1, fc=FILL, ec=INK, lw=1.5, r=4, z=2):
    y0, y1 = Y(off1), Y(off0)
    ax.add_patch(FancyBboxPatch(
        (x0, y0), x1 - x0, y1 - y0,
        boxstyle=f"round,pad=0,rounding_size={r}",
        facecolor=fc, edgecolor=ec, linewidth=lw, zorder=z))


def arrow(x0, off0, x1, off1, color=INK, lw=1.5, head=10):
    ax.add_patch(FancyArrowPatch(
        (x0, Y(off0)), (x1, Y(off1)), arrowstyle="-|>", mutation_scale=head,
        color=color, linewidth=lw, zorder=6, shrinkA=0, shrinkB=0))


def line(x0, off0, x1, off1, color=INK, lw=1.5, z=4):
    ax.plot([x0, x1], [Y(off0), Y(off1)], color=color, linewidth=lw, zorder=z,
            solid_capstyle="butt")


# ---------------------------------------------------------------- header ----
t(90, 50, "code map", 15, INK, "bold")
t(90, 82, "13 source files, 1103 lines", 10, GREY)
line(90, 112, W - 90, 112, RULE, 1.4)

GROUPS = [
    (90, 870, "topology/", "8 files, 525 lines", [
        ("nodes.env",           "52",  "node table: IPs, interfaces, cpu quotas"),
        ("edge-cloud.clab.yml", "152", "5 containers, 4 veth links, caps + cpusets"),
        ("Dockerfile.client",   "14",  "node image plus ip, ping, pkill"),
        ("prepare.sh",          "49",  "copy the golden server dir to each node"),
        ("up.sh",               "47",  "build, deploy, wait ready, netem, verify"),
        ("netem.sh",            "67",  "apply a delay profile to both link ends"),
        ("verify.sh",           "132", "preflight: quotas, cpusets, RTT, swap"),
        ("down.sh",             "12",  "destroy the lab"),
    ]),
    (910, 1610, "controller/", "3 files, 425 lines", [
        ("warmup.sh",   "80",  "pre-generate terrain on every node"),
        ("capacity.sh", "142", "ramp load, find N_max per node"),
        ("collect.sh",  "203", "run the grid, four phases per cell"),
    ]),
    (1650, 2310, "bots/", "2 files, 153 lines", [
        ("bot.js",   "76", "N clients: walk, chat-echo RTT"),
        ("probe.js", "77", "tcp handshake, server-status ping"),
    ]),
]

TOP, HDR, FR, PITCH = 150, 56, 252, 76
for x0, x1, title, count, rows in GROUPS:
    bot_off = FR + (len(rows) - 1) * PITCH + 46
    box(x0, TOP, x1, bot_off, fc=BG, ec=INK, lw=1.6)
    box(x0, TOP, x1, TOP + HDR, fc=SHADE, ec=INK, lw=1.6)
    t(x0 + 24, TOP + HDR / 2, title, 12, INK, "bold")
    t(x1 - 24, TOP + HDR / 2, count, 9.5, GREY, ha="right")
    for i, (name, ln, desc) in enumerate(rows):
        off = FR + i * PITCH
        t(x0 + 24, off, name, 10.5, INK, "bold")
        t(x1 - 24, off, ln, 9.5, FAINT, ha="right")
        t(x0 + 24, off + 26, desc, 9, GREY)

# controller drives the bots
arrow(1612, 300, 1648, 300, INK, 1.5, head=10)

# ------------------------------------------------------------- run order ----
t(910, 500, "run order", 12, INK, "bold")

PIPE = [("./up.sh", "deploy the lab"),
        ("./verify.sh", "preflight gate"),
        ("./warmup.sh", "generate terrain"),
        ("./capacity.sh", "find N_max"),
        ("./collect.sh", "run the grid"),
        ("results/raw/", "four streams per cell")]
PW, PG, PX = 442, 37, 910
for i, (name, sub) in enumerate(PIPE):
    col, row = i % 3, i // 3
    x0 = PX + col * (PW + PG)
    o0 = 538 + row * 150
    last = i == len(PIPE) - 1
    box(x0, o0, x0 + PW, o0 + 100, fc=SHADE if last else FILL, ec=INK, lw=1.5)
    t(x0 + PW / 2, o0 + 38, name, 11, INK, "bold", ha="center")
    t(x0 + PW / 2, o0 + 70, sub, 9, GREY, ha="center")
    if col < 2:
        arrow(x0 + PW, o0 + 50, x0 + PW + PG, o0 + 50, INK, 1.5, head=10)

# wrap from end of row 1 to start of row 2
XE = PX + 2 * (PW + PG) + PW
line(XE, 588, XE + 22, 588, INK, 1.5)
line(XE + 22, 588, XE + 22, 663, INK, 1.5)
line(XE + 22, 663, PX - 22, 663, INK, 1.5)
line(PX - 22, 663, PX - 22, 738, INK, 1.5)
arrow(PX - 22, 738, PX, 738, INK, 1.5, head=10)

# ---------------------------------------------------------------- notes -----
t(90, 880, "nodes.env is sourced by every script.   "
           "bots/ runs inside the client container, started by controller/ with docker exec.",
  9.5, GREY)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "code-map.png")
fig.savefig(OUT, facecolor=BG, dpi=DPI)
print("wrote", OUT)

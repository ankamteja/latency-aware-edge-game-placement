"""Slide 5 topology diagram, subnets as configured in topology/edge-cloud.clab.yml (/30)."""
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

out = sys.argv[1]
BG, LINE, TXT = "#111b2e", "#c9d1dc", "#ffffff"
fig = plt.figure(figsize=(13.76, 7.68), dpi=100)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1376); ax.set_ylim(768, 0); ax.axis("off")
fig.patch.set_facecolor(BG)

def box(x, y, w, h, face, edge, lines, sizes):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=12",
                                fc=face, ec=edge, lw=2))
    n = len(lines)
    for i, (t, s) in enumerate(zip(lines, sizes)):
        ax.text(x + w / 2, y + h * (i + 1) / (n + 1), t, color=TXT, fontsize=s,
                ha="center", va="center")

box(82, 315, 288, 142, "#e07020", "#f3a25a", ["CLIENT", ""], [24, 1])
box(94, 385, 264, 58, "#c25e14", "#f3a25a", ["bots / probes"], [17])
cx, cy = 370, 385
nodes = [("edge1", "0.5 core", "5 ms RTT", 788, 73, "#0b8f94", "#3fd0d4", "10.0.1.0/30"),
         ("edge2", "1 core", "15 ms RTT", 788, 240, "#0b8f94", "#3fd0d4", "10.0.2.0/30"),
         ("edge3", "2 cores", "30 ms RTT", 788, 407, "#0b8f94", "#3fd0d4", "10.0.3.0/30"),
         ("cloud", "4 cores", "40 ms RTT", 1045, 574, "#6a2f9e", "#b06ee0", "10.0.4.0/30")]
for name, cpu, rtt, x, y, face, edge, net in nodes:
    w, h = (228, 130) if name != "cloud" else (256, 140)
    tx, ty = x, y + h / 2
    ax.plot([cx, tx], [cy, ty], color=LINE, lw=1.3)
    f = 0.62 if name == "cloud" else 0.52
    mx, my = cx + (tx - cx) * f, cy + (ty - cy) * f
    import math
    ang = -math.degrees(math.atan2(ty - cy, tx - cx))
    below = name == "cloud"             # above the line it would crowd edge3's label
    ax.text(mx, my + (14 if below else -14), f"{net}, RTT {rtt.split()[0]} ms", color=TXT,
            fontsize=14, rotation=ang, rotation_mode="anchor", ha="center",
            va="top" if below else "bottom")
    box(x, y, w, h, face, edge, [name, cpu, rtt], [26, 16, 16])
fig.savefig(out, facecolor=BG)

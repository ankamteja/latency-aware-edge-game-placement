"""Join the raw measurement streams into the labelled dataset.

Every directory under results/raw/<tag>/ that holds a meta.json is one cell:
one node, one player count, four raw streams (bot.csv, probe.csv, icmp.txt,
server.csv). Grid cells come from controller/collect.sh, deployment cells from
controller/deploy.sh (one per loaded node of a placement); the layout is the
same.

Each cell's steady window is cut into fixed windows (default 30 s). One window
is one dataset row:

    features   node, cores, players, utilization, network RTT, CPU, MSPT
    labels     in-game RTT p50 / p95 / p99 / max in that window

Rows from one cell are not independent - they share the cell's load and
history - so every row carries a `cell_id`, and any evaluation must split by
cell (or by node / replicate), never by row.

Usage:
    python dataset/build_dataset.py --tags grid-a,grid-b,place1 --out data/
Writes data/dataset.csv (one row per window) and data/cells.csv (one row per
cell, whole steady window).
"""
import argparse
import csv
import json
import re
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "results" / "raw"

# Players a node holds per core before its tick time breaks the 50 ms budget,
# measured in docs/07-capacity.md (edge1: 50 at 0.5 core, edge2: 100 at 1 core).
PLAYERS_PER_CORE = 100

ICMP_RE = re.compile(r"^\[(\d+\.\d+)\].*time=([\d.]+) ms")
# "/mspt" output, colour codes already stripped by the collector; the 5 s
# average is the first number after the "1m:" label.
MSPT_RE = re.compile(r"1m:[^0-9]*([0-9.]+)")


def q(values, p):
    return float(np.percentile(values, p)) if len(values) else float("nan")


def med(values):
    return float(np.median(values)) if len(values) else float("nan")


def read_bot(path):
    rtt, kicks, respawns, errors = [], 0, 0, 0
    for line in path.read_text(errors="replace").splitlines():
        parts = line.split(",", 3)
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        t, kind = int(parts[0]), parts[2]
        if kind == "rtt" and len(parts) == 4:
            rtt.append((t, float(parts[3])))
        elif kind == "kicked":
            kicks += 1
        elif kind == "respawn":
            respawns += 1
        elif kind == "error":
            errors += 1
    return rtt, kicks, respawns, errors


def read_icmp(path):
    out = []
    if not path.exists():
        return out
    for line in path.read_text(errors="replace").splitlines():
        m = ICMP_RE.match(line)
        if m:
            out.append((int(float(m.group(1)) * 1000), float(m.group(2))))
    return out


def read_probe(path):
    tcp, status = [], []
    if not path.exists():
        return tcp, status
    for line in path.read_text(errors="replace").splitlines():
        parts = line.split(",")
        if len(parts) != 3 or not parts[0].isdigit():
            continue
        try:
            v = float(parts[2])
        except ValueError:
            continue
        (tcp if parts[1] == "tcp" else status).append((int(parts[0]), v))
    return tcp, status


def read_server(path):
    rows = []
    if not path.exists():
        return rows
    with path.open(newline="", errors="replace") as f:
        for r in csv.DictReader(f):
            try:
                t = int(r["epoch_ms"])
            except (TypeError, ValueError):
                continue
            m = MSPT_RE.search(r.get("mspt_raw") or "")
            try:
                cpu = float(r["cpu_percent"])
            except (TypeError, ValueError):
                cpu = float("nan")
            try:
                players = int(r["players"])
            except (TypeError, ValueError):
                players = -1
            rows.append((t, players, cpu, float(m.group(1)) if m else float("nan")))
    return rows


def within(series, t0, t1):
    return [v for t, v in series if t0 <= t < t1]


def cores_of(meta):
    quota, period = meta["cpu_max"].split()
    return int(quota) / int(period)


def describe(cell_dir, run, deployment, meta, streams, t0, t1):
    rtt, icmp, tcp, status, server = streams
    cores = cores_of(meta)
    win_rtt = within(rtt, t0, t1)
    srv = [s for s in server if t0 <= s[0] < t1]
    cpu = med([s[2] for s in srv if s[2] == s[2]])
    players = med([s[1] for s in srv if s[1] >= 0])
    icmp_w = within(icmp, t0, t1)
    return {
        "run": run,
        "deployment": deployment,
        "node": meta["target"],
        "cores": cores,
        "bots": meta["bots"],
        "players": players,
        "utilization": meta["bots"] / (PLAYERS_PER_CORE * cores),
        "net_rtt_ms": med(icmp_w),
        "icmp_p95_ms": q(icmp_w, 95),
        "tcp_p50_ms": med(within(tcp, t0, t1)),
        "status_p50_ms": med(within(status, t0, t1)),
        "cpu_percent": cpu,
        "cpu_util": cpu / (100 * cores) if cpu == cpu else float("nan"),
        "mspt_ms": med([s[3] for s in srv if s[3] == s[3]]),
        "rtt_n": len(win_rtt),
        "rtt_p50_ms": q(win_rtt, 50),
        "rtt_p95_ms": q(win_rtt, 95),
        "rtt_p99_ms": q(win_rtt, 99),
        "rtt_max_ms": max(win_rtt) if win_rtt else float("nan"),
        "host_mem_available_mb": meta.get("host_mem_available_mb_end", ""),
        "server_swap_mb": meta.get("server_swap_mb_end", ""),
    }


def build(tags, window_s):
    windows, cells = [], []
    for tag in tags:
        for meta_path in sorted((RAW / tag).rglob("meta.json")):
            cell_dir = meta_path.parent
            meta = json.loads(meta_path.read_text())
            rel = cell_dir.relative_to(RAW / tag)
            deployment = rel.parts[0] if len(rel.parts) > 1 else ""
            cell_id = f"{tag}/{rel}"
            rtt, kicks, respawns, errors = read_bot(cell_dir / "bot.csv")
            icmp = read_icmp(cell_dir / "icmp.txt")
            tcp, status = read_probe(cell_dir / "probe.csv")
            server = read_server(cell_dir / "server.csv")
            streams = (rtt, icmp, tcp, status, server)
            s0, s1 = meta["steady_start_ms"], meta["steady_end_ms"]

            idle_icmp = within(icmp, meta["bots_start_ms"] - meta["idle_seconds"] * 1000,
                               meta["bots_start_ms"])
            common = {
                "cell_id": cell_id,
                "players_held": meta["players_held"],
                "kicks": kicks,
                "respawns": respawns,
                "errors": errors,
                "net_rtt_idle_ms": med(idle_icmp),
            }
            row = describe(cell_dir, tag, deployment, meta, streams, s0, s1)
            cells.append({"cell_id": cell_id, **row, **common})

            n = int((s1 - s0) // (window_s * 1000))
            for w in range(n):
                t0 = s0 + w * window_s * 1000
                row = describe(cell_dir, tag, deployment, meta, streams, t0, t0 + window_s * 1000)
                windows.append({"cell_id": cell_id, "window": w, **row, **common})
    return windows, cells


def write(rows, path):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tags", required=True, help="comma list of results/raw/<tag> runs")
    ap.add_argument("--window", type=int, default=30, help="seconds per dataset row")
    ap.add_argument("--out", default=str(REPO / "data"))
    a = ap.parse_args()
    windows, cells = build(a.tags.split(","), a.window)
    out = Path(a.out)
    write(windows, out / "dataset.csv")
    write(cells, out / "cells.csv")
    print(f"{len(cells)} cells, {len(windows)} window rows -> {out}/")


if __name__ == "__main__":
    main()

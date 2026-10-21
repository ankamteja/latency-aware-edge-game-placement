"""The live testbed, seen from the controller: start and stop matches, read
server counters, and read every bot's latency samples as they arrive.

A match is ten bots in one bot.js process inside the client container. Its
tag (live-mNN) is on that process's command line, so it can be stopped on
its own. Moving a match means stopping that process and starting it again
pointed at another node: the same ten players disconnect from one server and
log in to the other, which is what a real migration costs them.

Every match segment (one match on one node) writes its own CSV under
topology/out/live/<run>/, which the client container sees as /out/live/<run>/.
"""
import math
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_HOST = REPO / "topology" / "out" / "live"
OUT_CTR = "/out/live"
CLIENT = "clab-edgegame-client"
NODE_IP = {"edge1": "10.0.1.2", "edge2": "10.0.2.2", "edge3": "10.0.3.2", "cloud": "10.0.4.2"}
MATCH_SIZE = 10

# Paper's /mspt: "...from last 5s; 10s; 1m: <avg>/<min>/<max>; ..." - the
# first number after "1m:" is the 5 s average (docs/07-capacity.md 7.3).
MSPT_RE = re.compile(r"1m:[^0-9]*([0-9.]+)")
LIST_RE = re.compile(r"are (\d+)")
COLOUR_RE = re.compile(r"\x1b\[[0-9;]*m|\xa7.")


def ctr(node):
    return f"clab-edgegame-{node}"


def sh(args, timeout=4):
    """stdout of a command, or "" if it fails or hangs: one slow docker exec
    must cost one sample, never the run."""
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout
    except (subprocess.SubprocessError, OSError):
        return ""


def rcon(node, cmd):
    return COLOUR_RE.sub("", sh(["docker", "exec", ctr(node), "rcon-cli", cmd]))


# ---- matches -----------------------------------------------------------------

def match_tag(mid):
    return f"live-m{mid:02d}"


def start_match(run, mid, node, seg):
    """Ten bots, usernames bot<10*mid> .. bot<10*mid+9>, joining 500 ms apart."""
    out = f"{OUT_CTR}/{run}/m{mid:02d}-s{seg:02d}-{node}.csv"
    cmd = (f"mkdir -p {OUT_CTR}/{run} && exec node /bots/bot.js {MATCH_SIZE} "
           f"{NODE_IP[node]} 25565 --tag={match_tag(mid)} --from={mid * MATCH_SIZE} "
           f"--offset=0 --every=500 > {out} 2>&1")
    r = subprocess.run(["docker", "exec", "-d", CLIENT, "sh", "-c", cmd],
                       capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        raise RuntimeError(f"could not start match {mid} on {node}: {r.stderr.strip()}")
    return OUT_HOST / run / f"m{mid:02d}-s{seg:02d}-{node}.csv"


def stop_match(mid, wait_s=3.0):
    """Stop one match and wait until its process is gone, so a replacement
    never overlaps it: until the old bots disconnect they still load the
    source server. The trailing space keeps live-m01 from matching live-m010."""
    pat = f"bot[.]js.*--tag={match_tag(mid)} "
    sh(["docker", "exec", CLIENT, "pkill", "-f", pat])
    end = time.time() + wait_s
    while time.time() < end and sh(["docker", "exec", CLIENT, "pgrep", "-f", pat]).strip():
        time.sleep(0.2)


def stop_all():
    sh(["docker", "exec", CLIENT, "pkill", "-f", "bot[.]js.*--tag=live-m"])


# ---- server counters ---------------------------------------------------------

@dataclass
class CpuMeter:
    """CPU from the container's own cgroup counter: % of one core."""
    last: dict = field(default_factory=dict)

    def read(self, node):
        txt = sh(["docker", "exec", ctr(node), "cat", "/sys/fs/cgroup/cpu.stat"])
        m = re.search(r"usage_usec (\d+)", txt)
        if not m:
            return None
        now, used = time.time(), int(m.group(1))
        prev = self.last.get(node)
        self.last[node] = (now, used)
        if not prev:
            return None
        return (used - prev[1]) / 1e6 / (now - prev[0]) * 100


def server_sample(node, cpu):
    """Never raises: a counter that cannot be read this time is None."""
    try:
        mspt_raw = rcon(node, "mspt").strip()
        list_raw = rcon(node, "list").strip()
        c = cpu.read(node)
        quota = cpu_quota(node)
    except Exception:
        return {"players": None, "mspt_ms": None, "cpu_pct": None, "online": [], "raw": [],
                "quota_cores": None}
    mspt, players = MSPT_RE.search(mspt_raw), LIST_RE.search(list_raw)
    names = list_raw.split(":", 1)[1].replace(" ", "").split(",") if ":" in list_raw else []
    return {
        "players": int(players.group(1)) if players else None,
        "mspt_ms": float(mspt.group(1)) if mspt else None,
        "cpu_pct": c,
        "quota_cores": quota,
        "online": [n for n in names if n],
        # what the server itself printed, for the dashboard's raw feed
        "raw": [f"rcon list: {list_raw[:90]}", f"rcon mspt: {' '.join(mspt_raw.split())[:110]}"],
    }


def set_cpu(node, cores):
    """Change a node's CPU quota while it runs: the "node got slower" event.
    docker update rewrites the container's cgroup cpu.max in place."""
    r = subprocess.run(["docker", "update", "--cpu-period", "100000",
                        "--cpu-quota", str(int(cores * 100000)), ctr(node)],
                       capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())


def cpu_quota(node):
    """Cores the node is allowed right now, read from its own cgroup."""
    txt = sh(["docker", "exec", ctr(node), "cat", "/sys/fs/cgroup/cpu.max"]).split()
    try:
        return int(txt[0]) / int(txt[1])
    except (IndexError, ValueError):
        return None


# ---- latency streams ---------------------------------------------------------

class Tail:
    """Incrementally read one segment's CSV.

    read() returns (epoch_ms, bot, rtt_ms) for every complete latency line
    written since the last call; a partial last line is kept for next time,
    and malformed or non-finite values are dropped."""

    def __init__(self, path):
        self.path, self.pos, self.buf = Path(path), 0, ""

    def read(self):
        try:
            with self.path.open("r", errors="replace") as f:
                f.seek(self.pos)
                chunk = f.read()
                self.pos = f.tell()
        except FileNotFoundError:
            return []
        self.buf += chunk
        lines = self.buf.split("\n")
        self.buf = lines.pop()
        out = []
        for line in lines:
            parts = line.strip().split(",")
            if len(parts) < 4 or parts[2] != "rtt" or not parts[0].isdigit():
                continue
            try:
                rtt = float(parts[3])
            except ValueError:
                continue
            if math.isfinite(rtt):
                out.append((int(parts[0]), parts[1], rtt))
        return out

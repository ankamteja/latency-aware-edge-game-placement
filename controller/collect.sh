#!/usr/bin/env bash
# Metric collection driver.
#
# Walks a grid of (placement target x player count). For each cell it:
#   1. waits until the target server has ZERO players left from the last cell
#   2. lets the server settle, then starts the probes and lets them run alone
#      for a while - that idle window is the network-only baseline for this
#      exact cell, measured rather than assumed
#   3. starts N bots, holds the load steady for the run duration
#   4. samples the server's own load counters the whole time
#   5. stops everything and writes the raw streams to one directory per cell
#
# It deliberately does NOT aggregate, join or label anything. Four independent
# raw streams per cell, plus a meta.json saying how they were produced.
#
# Usage:
#   ./collect.sh                                            # full grid
#   ./collect.sh --targets edge1 --loads 5 --duration 60     # one smoke cell
#   ./collect.sh --targets edge1,edge3 --loads 10,20
#
# Options:
#   --targets   comma list of node names             (default: all of them)
#   --loads     comma list of bot counts             (default 1,5,10,20,30,40)
#   --duration  seconds of steady load per cell      (default 120)
#   --idle      seconds of probe-only baseline       (default 20)
#   --settle    seconds of recovery between cells    (default 30)
#   --tag       name for the output directory        (default: UTC timestamp)
#               reusing a tag adds cells to that run, so different nodes
#               can be swept with different load ladders under one tag
#   --min-avail MB of host memory that must be available before a cell
#               starts                                 (default 1500)
#   --no-verify skip the pre-flight (only for a driver that already ran it)
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd .. && pwd)"
source "$REPO/topology/nodes.env"

TARGETS="${NODES// /,}"
LOADS=1,5,10,20,30,40
DURATION=120
IDLE=20
SETTLE=30
VERIFY=1
MIN_AVAIL=1500
TAG="$(date -u +%Y%m%dT%H%M%SZ)"

while [ $# -gt 0 ]; do
  case "$1" in
    --targets)   TARGETS="$2"; shift 2;;
    --loads)     LOADS="$2";   shift 2;;
    --duration)  DURATION="$2";shift 2;;
    --idle)      IDLE="$2";    shift 2;;
    --settle)    SETTLE="$2";  shift 2;;
    --tag)       TAG="$2";     shift 2;;
    --min-avail) MIN_AVAIL="$2";shift 2;;
    --no-verify) VERIFY=0;     shift 1;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done

CLIENT_CTR="$(ctr "$CLIENT")"
OUTDIR="$REPO/results/raw/$TAG"          # final home, on the host
CONTAINER_OUT="/out/$TAG"                # same place as seen from the client
mkdir -p "$REPO/topology/out/$TAG"

# ---------------------------------------------------------------------------
# Pre-flight. Refuse to collect against a testbed that is not verified good.
# ---------------------------------------------------------------------------
if [ "$VERIFY" = 1 ]; then
  "$REPO/topology/verify.sh" || { echo "pre-flight failed, aborting"; exit 1; }
fi

# ---------------------------------------------------------------------------
# helpers - shared with deploy.sh
# ---------------------------------------------------------------------------
source ./lib.sh

# ---------------------------------------------------------------------------
# the grid
# ---------------------------------------------------------------------------
echo
echo "collection tag : $TAG"
echo "targets        : $TARGETS"
echo "loads          : $LOADS"
echo "per cell       : ${SETTLE}s settle + ${IDLE}s idle baseline + ${DURATION}s steady load"
echo

for target in ${TARGETS//,/ }; do
  IP="$(node_ip "$target")"
  for N in ${LOADS//,/ }; do
    CELL="$target-${N}bots"
    HOST_CELL="$REPO/topology/out/$TAG/$CELL"
    mkdir -p "$HOST_CELL"
    echo "=== $CELL  (target $IP)"

    stop_target "$target" "$IP"
    wait_empty "$target"
    wait_mem
    # Let the server settle before the idle baseline starts. After a heavy cell
    # the game thread is still catching up, and a baseline measured during that
    # recovery is not a baseline.
    echo "    settling ${SETTLE}s"
    sleep "$SETTLE"

    # -- server-side sampler (host side, background)
    sample_server "$target" "$HOST_CELL/server.csv" &
    SAMPLER=$!

    # -- probes: start first so the idle window is captured
    docker exec -d "$CLIENT_CTR" sh -c \
      "node /bots/probe.js $IP 25565 1000 --tag=$target > $CONTAINER_OUT/$CELL/probe.csv 2>&1"
    docker exec -d "$CLIENT_CTR" sh -c \
      "ping -D -i 1 -n $IP > $CONTAINER_OUT/$CELL/icmp.txt 2>&1"

    echo "    idle baseline ${IDLE}s"
    sleep "$IDLE"

    BOTS_START=$(date +%s%3N)
    docker exec -d "$CLIENT_CTR" sh -c \
      "node /bots/bot.js $N $IP 25565 --tag=$target > $CONTAINER_OUT/$CELL/bot.csv 2>&1"

    # Bots join staggered at 500 ms each, so the load is not steady until they
    # are all in. Wait that out, then hold for the full duration.
    JOIN_WAIT=$(( N / 2 + 10 ))
    sleep "$JOIN_WAIT"
    STEADY_START=$(date +%s%3N)
    echo "    steady load ${DURATION}s ($(online "$target") players attached)"
    sleep "$DURATION"
    STEADY_END=$(date +%s%3N)
    HELD=$(online "$target" || echo -1)
    MEM_AVAIL_END=$(mem_avail_mb)
    SWAP_END=$(swap_mb "$target")

    kill "$SAMPLER" 2>/dev/null || true
    stop_target "$target" "$IP"

    cat > "$HOST_CELL/meta.json" <<EOF
{
  "tag": "$TAG",
  "target": "$target",
  "target_ip": "$IP",
  "bots": $N,
  "players_held": $HELD,
  "idle_seconds": $IDLE,
  "duration_seconds": $DURATION,
  "bots_start_ms": $BOTS_START,
  "steady_start_ms": $STEADY_START,
  "steady_end_ms": $STEADY_END,
  "cpu_max": "$(docker exec "$(ctr "$target")" cat /sys/fs/cgroup/cpu.max | tr -d '\r')",
  "cpuset": "$(docker inspect -f '{{.HostConfig.CpusetCpus}}' "$(ctr "$target")")",
  "host_mem_available_mb_end": $MEM_AVAIL_END,
  "server_swap_mb_end": $SWAP_END,
  "netem_delay": "$(docker exec "$(ctr "$target")" tc qdisc show dev eth1 2>/dev/null | grep -o 'delay [^ ]*' | head -1)"
}
EOF
    KICKS=$(grep -c ',kicked' "$HOST_CELL/bot.csv" 2>/dev/null) || KICKS=0
    echo "    held $HELD players, $KICKS kicks, $(grep -c ',rtt,' "$HOST_CELL/bot.csv" 2>/dev/null || true) rtt samples"
  done
done

# The client wrote into the bind mount; copy the cells to their final home.
# Copy the CONTENTS: with a plain `cp -a src dst`, a second run under the same
# tag would land in dst/<tag>/ instead of next to the first run's cells.
mkdir -p "$OUTDIR"
cp -a "$REPO/topology/out/$TAG/." "$OUTDIR/"
echo
echo "raw streams written to $OUTDIR"
find "$OUTDIR" -type f | sort | sed 's|^|  |'

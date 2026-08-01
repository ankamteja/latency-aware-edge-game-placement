#!/usr/bin/env bash
# Metric collection driver.
#
# Walks a grid of (placement target x player count). For each cell it:
#   1. waits until the target server has ZERO players left from the last cell
#   2. starts the probes and lets them run alone for a while - that idle window
#      is the network-only baseline for this exact cell
#   3. starts N bots, holds the load steady for the run duration
#   4. samples the server's own load counters the whole time
#   5. stops everything and writes the raw streams to one directory per cell
#
# It deliberately does NOT aggregate, join or label anything. Four independent
# raw streams per cell, plus a meta.json saying how they were produced.
#
# Usage:
#   ./collect.sh                                   # full grid
#   ./collect.sh --targets edge --loads 5 --duration 60   # one smoke cell
#
# Options:
#   --targets   comma list of edge,cloud            (default edge,cloud)
#   --loads     comma list of bot counts            (default 1,5,10,20,30,40)
#   --duration  seconds of steady load per cell     (default 120)
#   --idle      seconds of probe-only baseline      (default 20)
#   --settle    seconds of recovery between cells   (default 30)
#   --tag       name for the output directory       (default: UTC timestamp)
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd .. && pwd)"

TARGETS=edge,cloud
LOADS=1,5,10,20,30,40
DURATION=120
IDLE=20
SETTLE=30
TAG="$(date -u +%Y%m%dT%H%M%SZ)"

while [ $# -gt 0 ]; do
  case "$1" in
    --targets)  TARGETS="$2"; shift 2;;
    --loads)    LOADS="$2";   shift 2;;
    --duration) DURATION="$2";shift 2;;
    --idle)     IDLE="$2";    shift 2;;
    --settle)   SETTLE="$2";  shift 2;;
    --tag)      TAG="$2";     shift 2;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done

CLIENT=clab-edgegame-client
ip_of() { case "$1" in edge) echo 10.0.1.2;; cloud) echo 10.0.2.2;; *) echo "unknown target $1" >&2; exit 2;; esac; }

OUTDIR="$REPO/results/raw/$TAG"          # final home, on the host
CONTAINER_OUT="/out/$TAG"                # same place as seen from the client
mkdir -p "$REPO/topology/out/$TAG"

# ---------------------------------------------------------------------------
# Pre-flight. Refuse to collect against a testbed that is not verified good.
# ---------------------------------------------------------------------------
"$REPO/topology/verify.sh" || { echo "pre-flight failed, aborting"; exit 1; }

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

# Ask the server itself how many players it has. rcon is an admin console over
# TCP; `list` answers "There are 3 of a max of 100 players online: ...".
online() {
  docker exec "clab-edgegame-$1" rcon-cli list 2>/dev/null \
    | tr -d '\r' | grep -oE 'are [0-9]+' | grep -oE '[0-9]+' | head -1
}

# Nothing from the previous cell may still be attached, or the load in this
# cell is not N. Reused usernames also collide as "duplicate_login" kicks.
wait_empty() {
  for _ in $(seq 1 45); do
    [ "$(online "$1" || echo x)" = "0" ] && return 0
    sleep 2
  done
  echo "  WARNING: $1 still reports $(online "$1") players after 90s"
}

# The bracket in bot[.]js stops the pattern matching the pkill command line
# itself - without it pkill happily kills its own shell.
stop_client_procs() {
  docker exec "$CLIENT" pkill -f 'bot[.]js'   2>/dev/null || true
  docker exec "$CLIENT" pkill -f 'probe[.]js' 2>/dev/null || true
  docker exec "$CLIENT" pkill -f 'ping'       2>/dev/null || true
}

# Server-side load counters, sampled on the host. Written as one CSV row per
# sample. mspt/tps come back with Minecraft colour codes (section sign plus a
# character); strip them or the CSV is unreadable.
strip() { sed -e 's/\xc2\xa7.//g' -e 's/\x1b\[[0-9;]*m//g' | tr -d '\r' | tr ',' ';' | tr -d '\n'; }

sample_server() {  # node outfile
  local node="$1" out="$2" c
  echo "epoch_ms,players,cpu_percent,mem_usage,mspt_raw,tps_raw" > "$out"
  while :; do
    c=$(docker stats --no-stream --format '{{.CPUPerc}},{{.MemUsage}}' "clab-edgegame-$node" 2>/dev/null | tr -d '%' | tr -d '\r')
    printf '%s,%s,%s,"%s","%s"\n' \
      "$(date +%s%3N)" \
      "$(online "$node" || echo -1)" \
      "${c:-,}" \
      "$(docker exec "clab-edgegame-$node" rcon-cli mspt 2>/dev/null | strip)" \
      "$(docker exec "clab-edgegame-$node" rcon-cli tps  2>/dev/null | strip)" \
      >> "$out"
    sleep 5
  done
}

# ---------------------------------------------------------------------------
# the grid
# ---------------------------------------------------------------------------
echo
echo "collection tag : $TAG"
echo "targets        : $TARGETS"
echo "loads          : $LOADS"
echo "per cell        : ${SETTLE}s settle + ${IDLE}s idle baseline + ${DURATION}s steady load"
echo

for target in ${TARGETS//,/ }; do
  IP="$(ip_of "$target")"
  for N in ${LOADS//,/ }; do
    CELL="$target-${N}bots"
    HOST_CELL="$REPO/topology/out/$TAG/$CELL"
    mkdir -p "$HOST_CELL"
    echo "=== $CELL  (target $IP)"

    stop_client_procs
    wait_empty "$target"
    # Let the server settle before the idle baseline starts. After a heavy cell
    # the game thread is still catching up, and a baseline measured during that
    # recovery is not a baseline.
    echo "    settling ${SETTLE}s"
    sleep "$SETTLE"

    # -- server-side sampler (host side, background)
    sample_server "$target" "$HOST_CELL/server.csv" &
    SAMPLER=$!

    # -- probes: start first so the idle window is captured
    docker exec -d "$CLIENT" sh -c \
      "node /bots/probe.js $IP 25565 1000 > $CONTAINER_OUT/$CELL/probe.csv 2>&1"
    docker exec -d "$CLIENT" sh -c \
      "ping -D -i 1 -n $IP > $CONTAINER_OUT/$CELL/icmp.txt 2>&1"

    echo "    idle baseline ${IDLE}s"
    sleep "$IDLE"

    BOTS_START=$(date +%s%3N)
    docker exec -d "$CLIENT" sh -c \
      "node /bots/bot.js $N $IP 25565 > $CONTAINER_OUT/$CELL/bot.csv 2>&1"

    # Bots join staggered at 500 ms each, so the load is not steady until they
    # are all in. Wait that out, then hold for the full duration.
    JOIN_WAIT=$(( N / 2 + 10 ))
    sleep "$JOIN_WAIT"
    STEADY_START=$(date +%s%3N)
    echo "    steady load ${DURATION}s ($(online "$target") players attached)"
    sleep "$DURATION"
    STEADY_END=$(date +%s%3N)
    HELD=$(online "$target" || echo -1)

    kill "$SAMPLER" 2>/dev/null || true
    stop_client_procs

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
  "cpu_max": "$(docker exec "clab-edgegame-$target" cat /sys/fs/cgroup/cpu.max | tr -d '\r')",
  "cpuset": "$(docker inspect -f '{{.HostConfig.CpusetCpus}}' "clab-edgegame-$target")",
  "netem_delay": "$(docker exec "clab-edgegame-$target" tc qdisc show dev eth1 2>/dev/null | grep -o 'delay [^ ]*' | head -1)"
}
EOF
    KICKS=$(grep -c ',kicked' "$HOST_CELL/bot.csv" 2>/dev/null) || KICKS=0
    echo "    held $HELD players, $KICKS kicks, $(grep -c ',rtt,' "$HOST_CELL/bot.csv" 2>/dev/null || true) rtt samples"
  done
done

# The client wrote into the bind mount; move the whole tree to its final home.
mkdir -p "$REPO/results/raw"
cp -a "$REPO/topology/out/$TAG" "$OUTDIR"
echo
echo "raw streams written to $OUTDIR"
find "$OUTDIR" -type f | sort | sed 's|^|  |'

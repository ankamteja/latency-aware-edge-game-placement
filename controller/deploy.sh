#!/usr/bin/env bash
# Deploy ONE placement for real and measure it.
#
# collect.sh loads one node at a time, which is how the load->latency curve of
# each node is learned. A placement algorithm's output is different: it splits
# a batch of players across several nodes AT ONCE. This script takes such a
# split, loads every node in it concurrently, and measures every node with the
# same four streams collect.sh records - so "which model's placement was right"
# is answered by a clock, not by the model that made the placement.
#
# Per deployment:
#   1. stop all load, wait until EVERY node reports zero players
#   2. settle, then probes alone on every loaded node (idle baseline)
#   3. start each node's bots at the same instant (each node's bots still join
#      500 ms apart), wait for the largest group to finish joining
#   4. hold the full load for the steady window, sampling server counters
#
# Usage:
#   ./deploy.sh --placement edge1=40,edge2=40,edge3=20,cloud=0 \
#               --name p100-mm1-greedy --tag place1 [--duration 90]
#
# Output: results/raw/<tag>/<name>/<node>/{bot,probe,server}.csv, icmp.txt,
# meta.json - the same layout as a collect.sh cell, one per loaded node - plus
# <name>/placement.json.
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd .. && pwd)"
source "$REPO/topology/nodes.env"

PLACEMENT=""
NAME=""
TAG="$(date -u +%Y%m%dT%H%M%SZ)"
DURATION=90
IDLE=15
SETTLE=20
MIN_AVAIL=1500

while [ $# -gt 0 ]; do
  case "$1" in
    --placement) PLACEMENT="$2"; shift 2;;
    --name)      NAME="$2";      shift 2;;
    --tag)       TAG="$2";       shift 2;;
    --duration)  DURATION="$2";  shift 2;;
    --idle)      IDLE="$2";      shift 2;;
    --settle)    SETTLE="$2";    shift 2;;
    --min-avail) MIN_AVAIL="$2"; shift 2;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done
[ -n "$PLACEMENT" ] && [ -n "$NAME" ] || { echo "need --placement and --name" >&2; exit 2; }

CLIENT_CTR="$(ctr "$CLIENT")"
source ./lib.sh

# Parse "edge1=40,edge2=0,..." into the list of nodes that get players.
declare -A COUNT
LOADED=""
MAXN=0
for kv in ${PLACEMENT//,/ }; do
  n="${kv%%=*}"; c="${kv##*=}"
  node_ip "$n" >/dev/null                      # dies on an unknown node name
  COUNT[$n]=$c
  if [ "$c" -gt 0 ]; then
    LOADED="$LOADED $n"
    [ "$c" -gt "$MAXN" ] && MAXN=$c
  fi
done

HOST_DIR="$REPO/topology/out/$TAG/$NAME"
CONTAINER_DIR="/out/$TAG/$NAME"
mkdir -p "$HOST_DIR"

echo "=== $NAME  ($PLACEMENT)"
for n in $NODES; do stop_target "$n" "$(node_ip "$n")"; done
for n in $NODES; do wait_empty "$n"; done
wait_mem
echo "    settling ${SETTLE}s"
sleep "$SETTLE"

SAMPLERS=""
for n in $LOADED; do
  ip="$(node_ip "$n")"
  mkdir -p "$HOST_DIR/$n"
  sample_server "$n" "$HOST_DIR/$n/server.csv" &
  SAMPLERS="$SAMPLERS $!"
  docker exec -d "$CLIENT_CTR" sh -c \
    "node /bots/probe.js $ip 25565 1000 --tag=$n > $CONTAINER_DIR/$n/probe.csv 2>&1"
  docker exec -d "$CLIENT_CTR" sh -c \
    "ping -D -i 1 -n $ip > $CONTAINER_DIR/$n/icmp.txt 2>&1"
done
echo "    idle baseline ${IDLE}s"
sleep "$IDLE"

BOTS_START=$(date +%s%3N)
for n in $LOADED; do
  docker exec -d "$CLIENT_CTR" sh -c \
    "node /bots/bot.js ${COUNT[$n]} $(node_ip "$n") 25565 --tag=$n > $CONTAINER_DIR/$n/bot.csv 2>&1"
done
sleep $(( MAXN / 2 + 10 ))
STEADY_START=$(date +%s%3N)
printf '    steady load %ss:' "$DURATION"
for n in $LOADED; do printf ' %s=%s' "$n" "$(online "$n")"; done; echo
sleep "$DURATION"
STEADY_END=$(date +%s%3N)

MEM_AVAIL_END=$(mem_avail_mb)
for n in $LOADED; do
  held=$(online "$n" || echo -1)
  cat > "$HOST_DIR/$n/meta.json" <<EOF
{
  "tag": "$TAG",
  "deployment": "$NAME",
  "placement": "$PLACEMENT",
  "target": "$n",
  "target_ip": "$(node_ip "$n")",
  "bots": ${COUNT[$n]},
  "players_held": $held,
  "idle_seconds": $IDLE,
  "duration_seconds": $DURATION,
  "bots_start_ms": $BOTS_START,
  "steady_start_ms": $STEADY_START,
  "steady_end_ms": $STEADY_END,
  "cpu_max": "$(docker exec "$(ctr "$n")" cat /sys/fs/cgroup/cpu.max | tr -d '\r')",
  "cpuset": "$(docker inspect -f '{{.HostConfig.CpusetCpus}}' "$(ctr "$n")")",
  "host_mem_available_mb_end": $MEM_AVAIL_END,
  "server_swap_mb_end": $(swap_mb "$n"),
  "netem_delay": "$(docker exec "$(ctr "$n")" tc qdisc show dev eth1 2>/dev/null | grep -o 'delay [^ ]*' | head -1)"
}
EOF
done

for p in $SAMPLERS; do kill "$p" 2>/dev/null || true; done
for n in $LOADED; do stop_target "$n" "$(node_ip "$n")"; done

{
  printf '{"name": "%s", "placement": {' "$NAME"
  first=1
  for n in $NODES; do
    [ "$first" = 1 ] || printf ', '; first=0
    printf '"%s": %s' "$n" "${COUNT[$n]:-0}"
  done
  printf '}}\n'
} > "$HOST_DIR/placement.json"

for n in $LOADED; do
  KICKS=$(grep -c ',kicked' "$HOST_DIR/$n/bot.csv" 2>/dev/null) || KICKS=0
  RTTS=$(grep -c ',rtt,' "$HOST_DIR/$n/bot.csv" 2>/dev/null) || RTTS=0
  printf '    %-6s %3s bots  %s kicks  %s rtt samples\n' "$n" "${COUNT[$n]}" "$KICKS" "$RTTS"
done

mkdir -p "$REPO/results/raw/$TAG/$NAME"
cp -a "$HOST_DIR/." "$REPO/results/raw/$TAG/$NAME/"

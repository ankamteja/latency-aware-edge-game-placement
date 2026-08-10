#!/usr/bin/env bash
# Generate the world around spawn on every node, before any measurement.
#
# WHY THIS EXISTS
#
# Each node boots from a fresh copy of the same server directory. The world in
# it is generated, but only the chunks a previous session actually visited. The
# first time bots walk outward from spawn, the server has to *generate* new
# terrain - and world generation is far more expensive than simulating an
# already-generated chunk.
#
# On a node capped at 0.5 core that difference is not subtle. Same node, same
# 5 bots, same 60 s window:
#
#            p50    p95    p99   cpu%   mspt
#   cold      43    474    819     50   66.0     <- saturated, ticks over budget
#   warm       7     60     73     21    5.1     <- healthy
#
# A cold first cell therefore looks like an overloaded node when it is really
# just a busy one, and it biases the WEAKEST node hardest - which is exactly
# where the interesting result lives. Ramping a grid from N=1 upward hides this
# by accident (the early cells do the warming), but that only works if cells
# always run in increasing order and never in isolation.
#
# So: warm every node explicitly, discard the data, then measure.
#
# All four nodes are warmed AT THE SAME TIME. Their cpu-sets are disjoint, so
# they do not compete, and it turns a 10-minute job into a 3-minute one. It
# also doubles as an early check that concurrent multi-node load works, which
# scenario S4 depends on.
#
# Usage: ./warmup.sh [bots] [seconds]        default: 20 bots, 150 s
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd .. && pwd)"
source "$REPO/topology/nodes.env"

BOTS="${1:-20}"
SECS="${2:-150}"
CLIENT_CTR="$(ctr "$CLIENT")"

online() {
  docker exec "$(ctr "$1")" rcon-cli list 2>/dev/null \
    | tr -d '\r' | grep -oE 'are [0-9]+' | grep -oE '[0-9]+' | head -1
}

echo "==> warming $NODES with $BOTS bots for ${SECS}s (data discarded)"

for node in $NODES; do
  ip="$(node_ip "$node")"
  docker exec "$CLIENT_CTR" pkill -f "bot[.]js.*--tag=$node" 2>/dev/null || true
  docker exec -d "$CLIENT_CTR" sh -c \
    "node /bots/bot.js $BOTS $ip 25565 --tag=$node > /dev/null 2>&1"
done

sleep "$((BOTS / 2 + 10))"
printf '    attached:'; for n in $NODES; do printf ' %s=%s' "$n" "$(online "$n")"; done; echo
sleep "$SECS"

echo "==> stopping warm-up load"
for node in $NODES; do
  docker exec "$CLIENT_CTR" pkill -f "bot[.]js.*--tag=$node" 2>/dev/null || true
done

# Flush the generated chunks to disk so a later restart does not have to
# regenerate them. save-all is the server's own "write the world out now".
for node in $NODES; do
  docker exec "$(ctr "$node")" rcon-cli save-all >/dev/null 2>&1 || true
done

echo "==> waiting for every node to report zero players"
for node in $NODES; do
  for _ in $(seq 1 45); do
    [ "$(online "$node" || echo x)" = "0" ] && break
    sleep 2
  done
  printf '    %-6s %s\n' "$node" "$(docker exec "$(ctr "$node")" rcon-cli list 2>/dev/null | tr -d '\r')"
done

echo "==> warm. Now safe to collect in any cell order."

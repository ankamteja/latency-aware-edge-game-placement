#!/usr/bin/env bash
# Bring the whole testbed up: node data dirs, containerlab deploy, network
# impairment, then wait until both game servers are actually serving.
#
# Usage: ./up.sh [edge_rtt_ms] [cloud_rtt_ms]
set -euo pipefail
cd "$(dirname "$0")"

EDGE_RTT_MS="${1:-5}"
CLOUD_RTT_MS="${2:-40}"

[ -d nodes/edge ] && [ -d nodes/cloud ] || ./prepare.sh
mkdir -p out

echo "==> building the client image (node + iproute2 + ping)"
docker build -q -f Dockerfile.client -t edgegame-client:1 .

echo "==> containerlab deploy"
containerlab deploy -t edge-cloud.clab.yml --reconfigure

echo "==> waiting for both servers to answer a status ping (up to 5 min)"
# mc-monitor ships inside the itzg image. It speaks the Minecraft server-list
# protocol, so a success means the server finished loading the world and is
# accepting connections - much more reliable than grepping the log for
# "Done (", which can match a line left over from a previous boot.
for node in edge cloud; do
  for i in $(seq 1 150); do
    if docker exec "clab-edgegame-$node" mc-monitor status --host 127.0.0.1 >/dev/null 2>&1; then
      echo "    $node ready after $((i*2))s"
      break
    fi
    [ "$i" = 150 ] && { echo "    $node NEVER became ready"; docker logs --tail 30 "clab-edgegame-$node"; exit 1; }
    sleep 2
  done
done

echo "==> applying netem"
./netem.sh "$EDGE_RTT_MS" "$CLOUD_RTT_MS"

echo
./verify.sh

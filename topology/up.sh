#!/usr/bin/env bash
# Bring the whole testbed up: node data dirs, containerlab deploy, network
# impairment, then wait until every game server is actually serving.
#
# Usage: ./up.sh [netem-profile]      default: ladder
set -euo pipefail
cd "$(dirname "$0")"
source ./nodes.env

PROFILE="${1:-ladder}"

missing=0
for n in $NODES; do [ -d "nodes/$n" ] || missing=1; done
[ "$missing" = 0 ] || ./prepare.sh
mkdir -p out

echo "==> building the client image (node + iproute2 + ping + procps)"
docker build -q -f Dockerfile.client -t edgegame-client:1 .

echo "==> containerlab deploy"
containerlab deploy -t edge-cloud.clab.yml --reconfigure

echo "==> waiting for every server to answer a status ping (up to 5 min each)"
# mc-monitor ships inside the itzg image. It speaks the Minecraft server-list
# protocol, so a success means the server finished loading the world and is
# accepting connections - much more reliable than grepping the log for
# "Done (", which can match a line left over from a previous boot.
for node in $NODES; do
  for i in $(seq 1 150); do
    if docker exec "$(ctr "$node")" mc-monitor status --host 127.0.0.1 >/dev/null 2>&1; then
      echo "    $node ready after $((i*2))s"
      break
    fi
    if [ "$i" = 150 ]; then
      echo "    $node NEVER became ready"
      docker logs --tail 30 "$(ctr "$node")"
      exit 1
    fi
    sleep 2
  done
done

echo "==> applying netem"
./netem.sh "$PROFILE"

echo
./verify.sh

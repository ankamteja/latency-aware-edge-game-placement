#!/usr/bin/env bash
# Build the per-node /data directories the two game servers boot from.
#
# Why this exists: a Minecraft server needs a jar, a generated world and a pile
# of config files. Generating a world on a 0.5-CPU node takes minutes and can
# trip the server's own "can't keep up" watchdog, and downloading the jar needs
# papermc.io to be reachable (it was not, during earlier runs). So we copy one
# known-good server directory - the "golden" volume left over from the
# single-node experiments - into a fresh directory per node.
#
# The result is ~255 MB per node and is git-ignored (topology/nodes/).
#
# Usage: ./prepare.sh [source-volume-name]
set -euo pipefail
cd "$(dirname "$0")"

# Docker named volume holding the known-good server directory.
GOLDEN="${1:-4dbb72a1a6b48fe0193126694b19415ab2d8f8d44f61ca31d8a5686dbf40c3b4}"

if ! docker volume inspect "$GOLDEN" >/dev/null 2>&1; then
  echo "error: docker volume '$GOLDEN' not found." >&2
  echo "       run: docker volume ls   and pass the right name as \$1" >&2
  exit 1
fi

for node in edge cloud; do
  echo "==> building nodes/$node from volume $GOLDEN"
  rm -rf "nodes/$node"
  mkdir -p "nodes/$node"
  # A throwaway alpine container is the only thing that can read a named
  # volume without root on the host. -a preserves ownership (uid 1000), which
  # the server process needs.
  docker run --rm \
    -v "$GOLDEN":/src:ro \
    -v "$PWD/nodes/$node":/dst \
    alpine sh -c 'cp -a /src/. /dst/'
  # Old logs and stale session state would only confuse the next run.
  rm -rf "nodes/$node/logs" "nodes/$node/crash-reports"
  # Each node keeps its own copy of the world; identical starting state means
  # the only difference between edge and cloud is CPU and network delay.
done

mkdir -p out
echo "==> done"
du -sh nodes/edge nodes/cloud

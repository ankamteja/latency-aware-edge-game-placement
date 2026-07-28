#!/usr/bin/env bash
# Tear the lab down. Leaves topology/nodes/ (the server data) in place so the
# next ./up.sh does not have to re-copy 500 MB; pass --clean to wipe it too.
set -euo pipefail
cd "$(dirname "$0")"

containerlab destroy -t edge-cloud.clab.yml --cleanup || true

if [ "${1:-}" = "--clean" ]; then
  echo "==> removing per-node server data"
  rm -rf nodes
fi

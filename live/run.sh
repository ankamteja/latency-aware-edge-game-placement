#!/usr/bin/env bash
# Start the live placement console: checks the testbed, then serves the
# dashboard on http://127.0.0.1:8090. Ctrl-C stops it and disconnects every
# match the controller started.
#
# Usage: live/run.sh
set -euo pipefail
cd "$(dirname "$0")/.."
topology/verify.sh >/dev/null || { echo "testbed pre-flight failed: run topology/up.sh"; exit 1; }
[ -f data/dataset.csv ] || { echo "no dataset: build it first (docs/08-results.md 8.7)"; exit 1; }
echo "dashboard: http://127.0.0.1:8090"
# cores 24-27 are outside every server (0-7) and the client (8-23): the
# controller must not compete with the servers it measures
exec taskset -c 24-27 python3 -m live.server

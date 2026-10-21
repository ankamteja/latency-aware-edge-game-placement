#!/usr/bin/env bash
# The old model against ours, live: run the same scenario once under each
# controller, one after the other, through the running dashboard so both can
# be watched. Results land in results/live/ and on the Compare runs page.
#
# Usage: live/ab.sh [scenario] [arrival]      defaults: standard nearest
set -euo pipefail
SC="${1:-standard}"; AR="${2:-nearest}"
API=http://127.0.0.1:8090
curl -sf "$API/api/options" >/dev/null || { echo "dashboard not running: start live/run.sh first"; exit 1; }
for POL in analytical learned; do
  echo "== $POL controller, scenario $SC, arrival $AR"
  curl -sf -X POST "$API/api/run" -H 'content-type: application/json' \
       -d "{\"policy\":\"$POL\",\"scenario\":\"$SC\",\"arrival\":\"$AR\"}"
  echo
  sleep 5
  while curl -sf "$API/api/options" | grep -q '"running":true'; do sleep 10; done
  echo "   finished"
  sleep 30     # let every server drain its players before the next run
done
curl -sf "$API/api/runs" | python3 -c '
import json,sys
for r in json.load(sys.stdin)[:2]:
    print(f"{r[\"policy\"]:10s} worst p95 median {r[\"worst_p95_median_ms\"]} ms, max {r[\"worst_p95_max_ms\"]} ms, "
          f"time over budget {r[\"time_over_budget_share\"]}, migrations {r[\"migrations\"]}")'

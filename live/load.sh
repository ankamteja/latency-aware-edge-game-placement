#!/usr/bin/env bash
# Operator load from a terminal, for a running live session. Bots join in
# matches of 10 (one game session each), so counts round up to a multiple of
# 10. Every command shows up on the dashboard within one tick (2 s), tagged
# as coming from the terminal.
#
#   live/load.sh add edge1 40       40 bots (4 matches) straight onto edge1
#   live/load.sh remove 20          take 20 bots (the 2 newest matches) off
#   live/load.sh remove 20 edge2    take 20 bots off edge2
#   live/load.sh throttle edge1 0.25  cut edge1's CPU to 0.25 cores, tell no model
#   live/load.sh restore edge1      give edge1 its own CPU back
#   live/load.sh status             players, tick time and p95 per node, now
#   live/load.sh start [model]      start a manual session (model: learned-live,
#                                   learned, queueing or analytical; default learned)
#   live/load.sh stop               end the session, disconnect every bot
set -euo pipefail
API=http://127.0.0.1:8090
matches() { echo $(( (${1:?bot count} + 9) / 10 )); }
case "${1:-}" in
  add)    n=$(matches "${3:-10}"); node="${2:?node: edge1 edge2 edge3 cloud}"
          body="{\"action\":\"add\",\"node\":\"$node\",\"matches\":$n,\"source\":\"terminal\"}"
          echo "adding $((n*10)) bots ($n matches) on $node" ;;
  remove) n=$(matches "${2:-10}")
          body="{\"action\":\"remove\",\"matches\":$n${3:+,\"node\":\"$3\"},\"source\":\"terminal\"}"
          echo "removing $((n*10)) bots ($n matches)${3:+ from $3}" ;;
  throttle) body="{\"action\":\"throttle\",\"node\":\"${2:?node}\",\"cores\":${3:?cores},\"source\":\"terminal\"}"
          echo "throttling $2 to $3 cores" ;;
  restore) body="{\"action\":\"restore\",\"node\":\"${2:?node}\",\"source\":\"terminal\"}"
          echo "restoring $2" ;;
  start)  curl -sS -X POST "$API/api/run" -H 'content-type: application/json' \
               -d "{\"policy\":\"${2:-learned}\",\"scenario\":\"manual\",\"arrival\":\"nearest\"}"; echo; exit ;;
  stop)   curl -sS -X POST "$API/api/stop"; echo; exit ;;
  status) cd "$(dirname "$0")/.." && exec python3 -m live.status ;;
  *) sed -n '2,18p' "$0"; exit 1 ;;
esac
curl -sS -X POST "$API/api/load" -H 'content-type: application/json' -d "$body"; echo

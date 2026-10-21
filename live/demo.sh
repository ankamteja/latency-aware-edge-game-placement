#!/usr/bin/env bash
# A guided live demo on the real testbed, driven from this terminal.
#
#   live/demo.sh            the load-aware model, then the load-blind formula
#   live/demo.sh ours       only the load-aware part
#   live/demo.sh formula    only the load-blind part
#
# Before: Performance power mode, charger in, topology/verify.sh passed,
# live/run.sh running in another terminal, dashboard open on
# http://127.0.0.1:8090. Each step prints the command, waits for Enter, runs
# it, then shows the live table for a while. Ctrl-C at any point; run
# live/load.sh stop afterwards to disconnect every bot.
set -uo pipefail
cd "$(dirname "$0")/.."
API=http://127.0.0.1:8090
PART="${1:-both}"

say()  { printf '\n\033[1;36m%s\033[0m\n' "$*"; }
note() { printf '\033[2m%s\033[0m\n' "$*"; }
step() {                               # step "<command>" <seconds to watch> "<what to point at>"
  printf '\n\033[1m$ %s\033[0m' "$1"; read -r -p "   [Enter to run] " _
  eval "$1"
  [ -n "${3:-}" ] && note "watch: $3"
  local end=$(( SECONDS + $2 ))
  while [ $SECONDS -lt $end ]; do
    sleep 4
    printf '\033[2J\033[H'; note "$1   (live, $(( end - SECONDS )) s left; Ctrl-C to stop watching)"
    python3 -m live.status 2>/dev/null || echo "no run in progress"
  done
}

# ---- pre-flight -------------------------------------------------------------
curl -sf "$API/api/options" >/dev/null || { echo "dashboard not running: start live/run.sh in another terminal"; exit 1; }
prof=$(tuned-adm active 2>/dev/null | awk '{print $NF}')
[ "$prof" = "throughput-performance" ] || echo "WARNING: power mode is '$prof', not Performance: every node will be 2-3x slower than the models expect"
if curl -sf "$API/api/options" | grep -q '"running":true'; then
  echo "a run is already in progress: live/load.sh stop, then run this again"; exit 1
fi

if [ "$PART" = "both" ] || [ "$PART" = "ours" ]; then
  say "PART 1: our controller (learned model, corrected from live measurements)"
  step "live/load.sh start learned-live" 6 "a new session, no players yet"
  say "Players arrive. The model predicts every node's p95 for the new match and picks the best."
  step "live/load.sh join 40" 50 "event log: one match every 5 s, each placed by the model with every node's prediction; edge1 is closest and still fast. 40 is edge1's knee: if the fourth match tips it over while players log in, the live model notices and moves one off"
  step "live/load.sh join 30" 45 "edge1 is predicted past its knee now, so the model sends these to edge2 (and edge3)"
  say "A flash crowd: 30 players forced onto edge1, the way a distance-only matchmaker would put them."
  step "live/load.sh add edge1 30" 75 "edge1's p95 climbs into the seconds; every 10 s the controller moves one match off it"
  say "edge1 silently loses half its CPU. No model is told."
  step "live/load.sh throttle edge1 0.25" 90 "edge1 slows down; the live model raises its cost factor and moves players away"
  step "live/load.sh restore edge1" 5 ""
  step "live/load.sh stop" 3 "every bot disconnects"
  sleep 20
fi

if [ "$PART" = "both" ] || [ "$PART" = "formula" ]; then
  say "PART 2: the load-blind formula in control (latency = distance + size/bandwidth)"
  step "live/load.sh start analytical" 6 ""
  say "The same arrivals. The formula predicts about 5 ms for edge1 at any load, so it always picks edge1."
  step "live/load.sh join 70" 80 "one match every 5 s: all 70 players go to edge1; its p95 goes to seconds; the formula still says 5 ms and never moves anyone"
  step "live/load.sh stop" 3 ""
fi

say "Done. Results of every run: results/live/  (python3 -m live.summarize)"

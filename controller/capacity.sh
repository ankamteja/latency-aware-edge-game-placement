#!/usr/bin/env bash
# S0 - discover each node's capacity, in players.
#
# WHY THIS RUNS FIRST
#
# "0.5 core" is not a portable unit. Half a core of an i7-14700HX does far more
# work per second than half a core of a small edge box, so a curve plotted
# against CPU quota only describes this laptop. The unit that travels is
# UTILIZATION - the fraction of a node's own capacity in use, 0 to 1 - which is
# also the unit the queueing law is written in:
#
#     queueing delay  is proportional to  1 / (1 - utilization)
#
# To divide by capacity you first have to measure it. This script does that:
# it ramps players on a node until the server can no longer hold its tick rate,
# and calls the last level it *could* hold that node's N_max.
#
# The threshold is the game's own, not the hardware's: a Minecraft server
# advances the world 20 times a second, so a tick has a 50 ms budget. Sustained
# MSPT above 50 ms means the server is falling behind and every player action
# is queueing. That budget comes from the game's design, so it means the same
# thing on any CPU - which is what makes N_max comparable across nodes.
#
# Server-side counters only. Latency curves are S1's job; this is just the
# denominator.
#
# Usage: ./capacity.sh [--targets edge1,edge2] [--hold 60] [--levels 1,2,4,...]
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd .. && pwd)"
source "$REPO/topology/nodes.env"

TARGETS="${NODES// /,}"
LEVELS="1,2,4,8,12,16,24,32,40"     # 40 is the ceiling: bot0..bot39 are opped
HOLD=60                              # seconds of steady load per level
SETTLE=15
BUDGET=50                            # ms per tick, from the game's 20 Hz design

while [ $# -gt 0 ]; do
  case "$1" in
    --targets) TARGETS="$2"; shift 2;;
    --levels)  LEVELS="$2";  shift 2;;
    --hold)    HOLD="$2";    shift 2;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done

CLIENT_CTR="$(ctr "$CLIENT")"
OUT="$REPO/results/raw/capacity"
mkdir -p "$OUT"

online() {
  docker exec "$(ctr "$1")" rcon-cli list 2>/dev/null \
    | tr -d '\r' | grep -oE 'are [0-9]+' | grep -oE '[0-9]+' | head -1
}
wait_empty() {
  for _ in $(seq 1 45); do [ "$(online "$1" || echo x)" = "0" ] && return 0; sleep 2; done
}

# The 5-second average tick time, pulled out of the server's own /mspt output.
# That output needs three separate pieces of cleanup before a number falls out:
#
#   1. it is drenched in ANSI colour codes  ->  strip them, or nothing matches
#   2. it spans TWO lines - the header ending in "1m:" and then the values, so
#      the lines must be joined before any pattern can span both
#   3. the label "1m:" itself contains a digit, so a naive "first number after
#      1m:" grabs the 1 from "1m" - cut the string at the label instead
#
# Joined and cleaned it reads:
#   Server tick times (avg/min/max) from last 5s, 10s, 1m: 22.2/3.8/95.9, ...
# and the first triple is the 5 s window, whose avg is what we want.
mspt5s() {
  docker exec "$(ctr "$1")" rcon-cli mspt 2>/dev/null \
    | sed -e 's/\x1b\[[0-9;]*m//g' -e 's/\xc2\xa7.//g' | tr -d '\r' | tr -d '\n' \
    | sed 's/.*1m:[^0-9]*//' | grep -oE '^[0-9.]+'
}
cpu_pct() {
  docker stats --no-stream --format '{{.CPUPerc}}' "$(ctr "$1")" 2>/dev/null | tr -d '%\r'
}

median() { sort -n | awk '{a[NR]=$1} END{if(NR==0){print "nan"; exit} print (NR%2)?a[(NR+1)/2]:(a[NR/2]+a[NR/2+1])/2}'; }

echo
echo "capacity discovery - tick budget ${BUDGET} ms, ${HOLD}s per level"
echo

SUMMARY="$OUT/summary.csv"
echo "node,cpu_max,cores,n_max,mspt_at_n_max,first_breach_n,mspt_at_breach" > "$SUMMARY"

for node in ${TARGETS//,/ }; do
  ip="$(node_ip "$node")"
  cpumax=$(docker exec "$(ctr "$node")" cat /sys/fs/cgroup/cpu.max | tr -d '\r')
  cores=$(awk -v s="$cpumax" 'BEGIN{split(s,a," "); printf "%.2f", a[1]/a[2]}')
  f="$OUT/$node.csv"
  echo "bots,players_held,mspt5s_median,mspt5s_max,cpu_percent_median,over_budget" > "$f"
  echo "=== $node  ($cores cores, $ip)"

  nmax=0; mspt_nmax=""; breach=""; mspt_breach=""
  for N in ${LEVELS//,/ }; do
    docker exec "$CLIENT_CTR" pkill -f "bot[.]js.*--tag=$node" 2>/dev/null || true
    wait_empty "$node"
    sleep "$SETTLE"

    docker exec -d "$CLIENT_CTR" sh -c \
      "node /bots/bot.js $N $ip 25565 --tag=$node > /dev/null 2>&1"
    sleep "$(( N / 2 + 10 ))"

    ms=(); cp=()
    for _ in $(seq 1 $(( HOLD / 5 ))); do
      v=$(mspt5s "$node"); [ -n "$v" ] && ms+=("$v")
      c=$(cpu_pct "$node"); [ -n "$c" ] && cp+=("$c")
      sleep 5
    done
    held=$(online "$node" || echo -1)
    docker exec "$CLIENT_CTR" pkill -f "bot[.]js.*--tag=$node" 2>/dev/null || true

    med=$(printf '%s\n' "${ms[@]}" | median)
    mx=$(printf '%s\n' "${ms[@]}" | sort -n | tail -1)
    cmed=$(printf '%s\n' "${cp[@]}" | median)
    over=$(awk -v m="$med" -v b="$BUDGET" 'BEGIN{print (m>b)?"yes":"no"}')

    printf '%s,%s,%s,%s,%s,%s\n' "$N" "$held" "$med" "$mx" "$cmed" "$over" >> "$f"
    printf '    %3d bots  held %-3s  mspt5s med %-7s max %-8s cpu %-6s %s\n' \
      "$N" "$held" "$med" "$mx" "$cmed" "$([ "$over" = yes ] && echo 'OVER BUDGET' || echo '')"

    if [ "$over" = yes ]; then
      breach="$N"; mspt_breach="$med"
      break                       # first level it cannot hold; stop here
    fi
    nmax="$N"; mspt_nmax="$med"
  done

  printf '%s,"%s",%s,%s,%s,%s,%s\n' \
    "$node" "$cpumax" "$cores" "$nmax" "$mspt_nmax" "${breach:-none}" "${mspt_breach:-}" >> "$SUMMARY"
  echo "    -> N_max = $nmax players (first breach at ${breach:-none})"
  echo
done

echo "== summary"
column -s, -t < "$SUMMARY"
echo
echo "written to $OUT/"

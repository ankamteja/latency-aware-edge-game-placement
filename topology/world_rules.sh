#!/usr/bin/env bash
# Freeze everything in the world that changes on its own, so the only thing
# that varies between cells is the number of players.
#
# Each server runs its own 20-minute day/night cycle. At night hostile mobs
# spawn around every player and path-find toward them, which on a 0.5-core node
# costs more than the players themselves: one bot at night put edge1 14 s
# behind on ticks, the same bot by day ran it at 10% CPU. Because the four
# clocks drift independently, a cell landed in day or night by chance. So:
#   permanent noon, no weather, peaceful (no hostile mobs at all).
# Game rules are saved in the world, so this survives a restart; up.sh runs it
# anyway and verify.sh checks it.
set -euo pipefail
cd "$(dirname "$0")"
source ./nodes.env

for n in $NODES; do
  for cmd in "difficulty peaceful" "gamerule doDaylightCycle false" "time set noon" \
             "gamerule doWeatherCycle false" "weather clear" "kill @e[type=!minecraft:player]"; do
    docker exec "$(ctr "$n")" rcon-cli "$cmd" >/dev/null
  done
  echo "    $n: peaceful, noon, clear, no mobs"
done

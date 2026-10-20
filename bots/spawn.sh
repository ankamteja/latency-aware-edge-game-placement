#!/bin/sh
# Run N bots against one server as several bot.js processes of at most PER
# bots each, so no single Node event loop has to absorb the whole N^2 chat
# broadcast (see the note in bot.js). Bot k still joins at k * 500 ms, exactly
# as when one process ran them all; all processes write to this script's
# stdout, one CSV line per event.
#
# Runs inside the client container:
#   /bots/spawn.sh <N> <host> <port> <tag> [PER]       default PER: 10
set -eu
N="$1"; HOST="$2"; PORT="$3"; TAG="$4"; PER="${5:-10}"

from=0
while [ "$from" -lt "$N" ]; do
  n=$(( N - from )); [ "$n" -gt "$PER" ] && n="$PER"
  node /bots/bot.js "$n" "$HOST" "$PORT" "--tag=$TAG" \
       "--from=$from" "--offset=$(( from * 500 ))" --every=500 &
  from=$(( from + n ))
done
wait

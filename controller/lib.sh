# Shared helpers for the measurement drivers (collect.sh, deploy.sh).
#
# Sourced, not executed. Expects nodes.env to be sourced first (for ctr) and
# CLIENT_CTR and MIN_AVAIL to be set by the caller.

# Ask the server itself how many players it has. rcon is an admin console over
# TCP; `list` answers "There are 3 of a max of 100 players online: ...".
online() {
  docker exec "$(ctr "$1")" rcon-cli list 2>/dev/null \
    | tr -d '\r' | grep -oE 'are [0-9]+' | grep -oE '[0-9]+' | head -1
}

# Nothing from the previous cell may still be attached, or the load in this
# cell is not N. Reused usernames also collide as "duplicate_login" kicks.
wait_empty() {
  for _ in $(seq 1 45); do
    [ "$(online "$1" || echo x)" = "0" ] && return 0
    sleep 2
  done
  echo "  WARNING: $1 still reports $(online "$1") players after 90s"
}

# Stop the load and probes for ONE target.
# The bracket in bot[.]js stops the pattern matching the pkill command line
# itself - without it pkill happily kills its own shell. The --tag marker is
# what makes this per-target instead of "kill every bot on the client", which
# matters as soon as two nodes are loaded at the same time.
stop_target() {  # node ip
  docker exec "$CLIENT_CTR" pkill -f "bot[.]js.*--tag=$1"   2>/dev/null || true
  docker exec "$CLIENT_CTR" pkill -f "probe[.]js.*--tag=$1" 2>/dev/null || true
  docker exec "$CLIENT_CTR" pkill -f "[p]ing .*$2"          2>/dev/null || true
}

# Host memory is part of the experiment. Four JVMs and up to 100+ bots share a
# 16 GB laptop; once the host runs short, the kernel pages server heap out to
# swap and the next tick that touches it stalls on a disk read - latency the
# data would wrongly blame on player load. So: refuse to start a cell until
# enough memory is free, and record what was free and how much of the server's
# memory sat in swap, next to every cell's results.
mem_avail_mb() { awk '/^MemAvailable:/{print int($2/1024)}' /proc/meminfo; }
swap_mb() {  # node
  local b; b=$(docker exec "$(ctr "$1")" cat /sys/fs/cgroup/memory.swap.current 2>/dev/null | tr -d '\r')
  echo $(( ${b:-0} / 1048576 ))
}
wait_mem() {
  for _ in $(seq 1 60); do
    [ "$(mem_avail_mb)" -ge "$MIN_AVAIL" ] && return 0
    echo "    waiting: only $(mem_avail_mb) MB available (want $MIN_AVAIL)"
    sleep 10
  done
  echo "  WARNING: starting with only $(mem_avail_mb) MB available"
}

# Server-side load counters, sampled on the host. Written as one CSV row per
# sample. mspt/tps come back with Minecraft colour codes (section sign plus a
# character); strip them or the CSV is unreadable.
strip() { sed -e 's/\xc2\xa7.//g' -e 's/\x1b\[[0-9;]*m//g' | tr -d '\r' | tr ',' ';' | tr -d '\n'; }

sample_server() {  # node outfile
  local node="$1" out="$2" c
  echo "epoch_ms,players,cpu_percent,mem_usage,mspt_raw,tps_raw" > "$out"
  while :; do
    c=$(docker stats --no-stream --format '{{.CPUPerc}},{{.MemUsage}}' "$(ctr "$node")" 2>/dev/null | tr -d '%' | tr -d '\r')
    printf '%s,%s,%s,"%s","%s"\n' \
      "$(date +%s%3N)" \
      "$(online "$node" || echo -1)" \
      "${c:-,}" \
      "$(docker exec "$(ctr "$node")" rcon-cli mspt 2>/dev/null | strip)" \
      "$(docker exec "$(ctr "$node")" rcon-cli tps  2>/dev/null | strip)" \
      >> "$out"
    sleep 5
  done
}

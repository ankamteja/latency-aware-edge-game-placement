#!/usr/bin/env bash
# Pre-flight check. Run this before EVERY collection run.
#
# Every check here guards a failure mode that produces plausible-looking but
# worthless numbers:
#   * a `cpu:` limit that silently did not apply -> the edge node quietly has 28
#     cores, the load effect disappears, and the results table just looks flat
#   * netem that did not attach -> "near" and "far" are the same distance
#   * a server that is up but not accepting players -> zero samples
#   * players left over from a previous run -> the load is not what you think
#
# Exits non-zero if anything is wrong.
set -uo pipefail
cd "$(dirname "$0")"

FAIL=0
ok()   { printf '  \033[32mok\033[0m   %s\n' "$1"; }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAIL=1; }

echo "== containers"
for n in client edge cloud; do
  s=$(docker inspect -f '{{.State.Status}}' "clab-edgegame-$n" 2>/dev/null || echo missing)
  [ "$s" = running ] && ok "clab-edgegame-$n running" || bad "clab-edgegame-$n is '$s'"
done

echo "== cpu limits (read from the kernel, not from the YAML)"
# The `cpu:` field in the topology becomes a Linux CFS bandwidth limit, which
# cgroup v2 exposes as /sys/fs/cgroup/cpu.max = "<quota_us> <period_us>":
# "the processes in this container may use <quota> microseconds of CPU time in
# every <period> microseconds", summed across all cores. So
#   50000 100000  = 0.5 cores      400000 100000 = 4 cores      max = no limit
# If this reads "max", the cap silently did not apply, the node has all 28 host
# cores, and the whole experiment measures nothing.
check_cpu() { # node expected-cpu-max
  v=$(docker exec "clab-edgegame-$1" cat /sys/fs/cgroup/cpu.max 2>/dev/null | tr -d '\r')
  c=$(docker inspect -f '{{.HostConfig.CpusetCpus}}' "clab-edgegame-$1" 2>/dev/null)
  cores=$(awk -v s="$v" 'BEGIN{split(s,a," "); if(a[1]=="max") print "unlimited"; else printf "%.2f", a[1]/a[2]}')
  [ "$v" = "$2" ] && ok "$1 cpu.max='$v' (= $cores cores) cpuset=${c:-<none>}" \
                  || bad "$1 cpu.max='$v' (expected '$2') cpuset=${c:-<none>}"
}
check_cpu edge  "50000 100000"
check_cpu cloud "400000 100000"

echo "== data-plane addressing"
for spec in "client eth1 10.0.1.1" "client eth2 10.0.2.1" "edge eth1 10.0.1.2" "cloud eth1 10.0.2.2"; do
  set -- $spec
  if docker exec "clab-edgegame-$1" ip -4 addr show "$2" 2>/dev/null | grep -q "$3"; then
    ok "$1 $2 = $3"
  else
    bad "$1 $2 is not $3"
  fi
done

echo "== netem qdiscs"
for spec in "client eth1" "client eth2" "edge eth1" "cloud eth1"; do
  set -- $spec
  q=$(docker exec "clab-edgegame-$1" tc qdisc show dev "$2" 2>/dev/null | grep -o 'delay [^ ]*' | head -1)
  [ -n "$q" ] && ok "$1 $2 $q" || bad "$1 $2 has no netem delay"
done

echo "== measured RTT (this is the number that goes in the write-up)"
# Configured delay is an intention; what the kernel delivers is the fact.
for spec in "10.0.1.2 edge" "10.0.2.2 cloud"; do
  set -- $spec
  out=$(docker exec clab-edgegame-client ping -c 20 -i 0.2 -q "$1" 2>/dev/null | tail -2)
  rtt=$(echo "$out" | grep -o 'min/avg/[^ ]* = [^ ]*' | awk '{print $3}')
  loss=$(echo "$out" | grep -o '[0-9.]*% packet loss')
  [ -n "$rtt" ] && ok "$2 ($1) min/avg/max/mdev = $rtt ms, $loss" \
                || bad "$2 ($1) unreachable"
done

echo "== game servers"
for n in edge cloud; do
  if docker exec "clab-edgegame-$n" mc-monitor status --host 127.0.0.1 >/dev/null 2>&1; then
    online=$(docker exec "clab-edgegame-$n" rcon-cli list 2>/dev/null | tr -d '\r')
    ok "$n accepting connections | $online"
    case "$online" in *"are 0 "*) ;; *) bad "$n still has players from a previous run";; esac
  else
    bad "$n not answering a status ping"
  fi
done

echo
[ "$FAIL" = 0 ] && echo "ALL CHECKS PASSED" || echo "SOMETHING IS WRONG - do not collect data yet"
exit "$FAIL"

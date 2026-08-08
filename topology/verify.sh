#!/usr/bin/env bash
# Pre-flight check. Run this before EVERY collection run.
#
# Every check here guards a failure mode that produces plausible-looking but
# worthless numbers:
#   * a `cpu:` limit that silently did not apply -> the edge node quietly has 28
#     cores, the load effect disappears, and the results table just looks flat
#   * netem that did not attach -> "near" and "far" are the same distance
#   * traffic on the management interface -> every node measures identically
#   * a server that is up but not accepting players -> zero samples
#   * players left over from a previous run -> the load is not what you think
#
# Exits non-zero if anything is wrong.
set -uo pipefail
cd "$(dirname "$0")"
source ./nodes.env

FAIL=0
ok()   { printf '  \033[32mok\033[0m   %s\n' "$1"; }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAIL=1; }

echo "== containers"
for n in $CLIENT $NODES; do
  s=$(docker inspect -f '{{.State.Status}}' "$(ctr "$n")" 2>/dev/null || echo missing)
  [ "$s" = running ] && ok "$(ctr "$n") running" || bad "$(ctr "$n") is '$s'"
done

echo "== cpu limits (read from the kernel, not from the YAML)"
# The `cpu:` field in the topology becomes a Linux CFS bandwidth limit, which
# cgroup v2 exposes as /sys/fs/cgroup/cpu.max = "<quota_us> <period_us>":
# "the processes in this container may use <quota> microseconds of CPU time in
# every <period> microseconds", summed across all cores. So
#   50000 100000  = 0.5 cores      400000 100000 = 4 cores      max = no limit
# If this reads "max", the cap silently did not apply, the node has all 28 host
# cores, and the whole experiment measures nothing.
for n in $NODES; do
  want="$(node_cpumax "$n")"
  v=$(docker exec "$(ctr "$n")" cat /sys/fs/cgroup/cpu.max 2>/dev/null | tr -d '\r')
  c=$(docker inspect -f '{{.HostConfig.CpusetCpus}}' "$(ctr "$n")" 2>/dev/null)
  cores=$(awk -v s="$v" 'BEGIN{split(s,a," "); if(a[1]=="max") print "unlimited"; else printf "%.2f", a[1]/a[2]}')
  [ "$v" = "$want" ] && ok "$n cpu.max='$v' (= $cores cores) cpuset=${c:-<none>}" \
                     || bad "$n cpu.max='$v' (expected '$want') cpuset=${c:-<none>}"
done

echo "== cpuset ranges are disjoint"
# Overlapping cpusets mean nodes compete for the same physical cores, so a
# "0.5 core" node's latency depends on what the others are doing.
seen=""; overlap=""
for n in $CLIENT $NODES; do
  r=$(docker inspect -f '{{.HostConfig.CpusetCpus}}' "$(ctr "$n")" 2>/dev/null)
  [ -z "$r" ] && continue
  # expand "4-6,9" into "4 5 6 9"
  for part in ${r//,/ }; do
    case "$part" in
      *-*) for i in $(seq "${part%-*}" "${part#*-}"); do
             case " $seen " in *" $i "*) overlap="$overlap $i";; esac; seen="$seen $i"; done ;;
      *)   case " $seen " in *" $part "*) overlap="$overlap $part";; esac; seen="$seen $part" ;;
    esac
  done
done
[ -z "$overlap" ] && ok "no core shared between containers" \
                  || bad "cores shared by more than one container:$overlap"

echo "== data-plane addressing"
for n in $NODES; do
  cif="$(node_client_if "$n")"; cip="$(node_client_ip "$n")"; nip="$(node_ip "$n")"
  if docker exec "$(ctr "$CLIENT")" ip -4 addr show "$cif" 2>/dev/null | grep -q "$cip"; then
    ok "client $cif = $cip"
  else
    bad "client $cif is not $cip"
  fi
  if docker exec "$(ctr "$n")" ip -4 addr show eth1 2>/dev/null | grep -q "$nip"; then
    ok "$n eth1 = $nip"
  else
    bad "$n eth1 is not $nip"
  fi
done

echo "== netem qdiscs"
for n in $NODES; do
  cif="$(node_client_if "$n")"
  q1=$(docker exec "$(ctr "$CLIENT")" tc qdisc show dev "$cif" 2>/dev/null | grep -o 'delay [^ ]*' | head -1)
  q2=$(docker exec "$(ctr "$n")"      tc qdisc show dev eth1  2>/dev/null | grep -o 'delay [^ ]*' | head -1)
  [ -n "$q1" ] && [ -n "$q2" ] && ok "$n  client:$cif $q1  |  $n:eth1 $q2" \
                               || bad "$n missing netem (client:$cif '${q1:-none}', $n:eth1 '${q2:-none}')"
done

echo "== measured RTT (this is the number that goes in the write-up)"
# Configured delay is an intention; what the kernel delivers is the fact.
for n in $NODES; do
  ip="$(node_ip "$n")"
  out=$(docker exec "$(ctr "$CLIENT")" ping -c 20 -i 0.2 -q "$ip" 2>/dev/null | tail -2)
  rtt=$(echo "$out" | grep -o 'min/avg/[^ ]* = [^ ]*' | awk '{print $3}')
  loss=$(echo "$out" | grep -o '[0-9.]*% packet loss')
  [ -n "$rtt" ] && ok "$n ($ip) min/avg/max/mdev = $rtt ms, $loss" \
                || bad "$n ($ip) unreachable"
done

echo "== game servers"
for n in $NODES; do
  if docker exec "$(ctr "$n")" mc-monitor status --host 127.0.0.1 >/dev/null 2>&1; then
    online=$(docker exec "$(ctr "$n")" rcon-cli list 2>/dev/null | tr -d '\r')
    ok "$n accepting connections | $online"
    case "$online" in *"are 0 "*) ;; *) bad "$n still has players from a previous run";; esac
  else
    bad "$n not answering a status ping"
  fi
done

echo "== host headroom"
# Memory, not CPU, is the binding constraint with four servers.
avail=$(free -m | awk '/^Mem:/{print $7}')
swap=$(free -m | awk '/^Swap:/{print $3}')
[ "$avail" -ge 2048 ] && ok "${avail}M available, ${swap}M swap in use" \
                      || bad "only ${avail}M available (${swap}M swap in use) - close other apps before collecting"

echo "== server swap (a swapped-out heap page faulting mid-tick inflates MSPT)"
# The servers are Java processes with multi-hundred-MB heaps. If the host runs
# short of memory the kernel pages parts of that heap to disk, and the next
# tick that touches one stalls on a disk read. That shows up as latency the
# experiment would wrongly attribute to server load.
for n in $NODES; do
  sw=$(docker exec "$(ctr "$n")" cat /sys/fs/cgroup/memory.swap.current 2>/dev/null | tr -d '\r')
  swm=$(( ${sw:-0} / 1048576 ))
  if [ "$swm" -lt 64 ]; then ok "$n ${swm}M swapped"
  else bad "$n has ${swm}M of its heap swapped out - free host memory and restart the node"
  fi
done

echo
[ "$FAIL" = 0 ] && echo "ALL CHECKS PASSED" || echo "SOMETHING IS WRONG - do not collect data yet"
exit "$FAIL"

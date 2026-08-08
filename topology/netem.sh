#!/usr/bin/env bash
# Apply the emulated network distance to the data-plane links.
#
# netem is a Linux queueing discipline that holds outgoing packets for a fixed
# time before releasing them. It only delays traffic LEAVING the interface it is
# attached to, so a one-sided rule gives a one-way delay. To get a symmetric
# round trip we attach half the target RTT to each end of the link:
#
#   client:eth1 --2.5ms-->  <--2.5ms-- edge1:eth1    => ~5 ms RTT
#
# Distance is deliberately a RUNTIME knob rather than part of the topology.
# Switching profile takes seconds and needs no redeploy, which is what makes it
# possible to separate the effect of distance from the effect of capacity.
#
#   ladder   the realistic tradeoff: the closer a node is, the weaker it is.
#            This is the placement dilemma. edge1 5 / edge2 15 / edge3 30 /
#            cloud 40 ms. Chosen so that edge1 and cloud match the two-node
#            run1 exactly, keeping that data comparable.
#
#   flat     every edge at the same 5 ms, cloud still at 40. Distance is now
#            constant across the three edges, so any difference between them is
#            capacity alone - the control for "you just picked a convenient
#            capacity gap".
#
#   near     everything close (2 ms edges, 5 ms cloud). Removes distance from
#            the picture almost entirely; useful for isolating server effects.
#
# These numbers are the experiment's definition of "near" and "far". They are a
# design parameter, not a measurement. verify.sh checks what the network
# actually delivers, which is the number that goes in the write-up.
#
# Usage: ./netem.sh [profile]        default: ladder
#        ./netem.sh ladder
#        ./netem.sh flat
set -euo pipefail
cd "$(dirname "$0")"
source ./nodes.env

PROFILE="${1:-ladder}"

# Target round-trip time in ms per node, per profile.
case "$PROFILE" in
  ladder) RTT_edge1=5  RTT_edge2=15 RTT_edge3=30 RTT_cloud=40 ;;
  flat)   RTT_edge1=5  RTT_edge2=5  RTT_edge3=5  RTT_cloud=40 ;;
  near)   RTT_edge1=2  RTT_edge2=2  RTT_edge3=2  RTT_cloud=5  ;;
  *) echo "unknown profile '$PROFILE' (want: ladder | flat | near)" >&2; exit 2 ;;
esac

# bash has no floating point, so work it out with awk.
half() { awk -v r="$1" 'BEGIN{printf "%.3fms", r/2}'; }

set_delay() {  # container interface delay
  containerlab tools netem set -n "$1" -i "$2" --delay "$3" >/dev/null
}

echo "==> netem profile: $PROFILE"
printf '    %-8s %-9s %-9s %s\n' node "target" "per side" "interfaces"
for node in $NODES; do
  v="RTT_$node"; rtt="${!v}"
  h="$(half "$rtt")"
  cif="$(node_client_if "$node")"
  set_delay "$(ctr "$CLIENT")" "$cif"  "$h"   # client -> node
  set_delay "$(ctr "$node")"   eth1    "$h"   # node -> client
  printf '    %-8s %-9s %-9s %s\n' "$node" "${rtt}ms RTT" "$h" "client:$cif + $node:eth1"
done

echo "==> verify what the network actually delivers with ./verify.sh"

#!/usr/bin/env bash
# Apply the emulated network distance to the two data-plane links.
#
# netem is a Linux queueing discipline that holds outgoing packets for a fixed
# time before releasing them. It only delays traffic LEAVING the interface it is
# attached to, so a one-sided rule gives a one-way delay. To get a symmetric
# round trip we attach half the target RTT to each end of the link:
#
#   client:eth1 --2.5ms-->  <--2.5ms-- edge:eth1     => ~5 ms RTT
#   client:eth2 -- 20ms-->  <-- 20ms-- cloud:eth1    => ~40 ms RTT
#
# These numbers are the experiment's definition of "near" and "far". They are a
# design parameter, not a measurement. verify.sh checks what the network
# actually delivers, which is the number that goes in the write-up.
#
# Usage: ./netem.sh [edge_rtt_ms] [cloud_rtt_ms]
set -euo pipefail
cd "$(dirname "$0")"

EDGE_RTT_MS="${1:-5}"
CLOUD_RTT_MS="${2:-40}"

# bash has no floating point, so work in microseconds and print with awk.
half() { awk -v r="$1" 'BEGIN{printf "%.3fms", r/2}'; }
EDGE_HALF="$(half "$EDGE_RTT_MS")"
CLOUD_HALF="$(half "$CLOUD_RTT_MS")"

set_delay() {  # node interface delay
  echo "    $1 $2  delay $3"
  containerlab tools netem set -n "$1" -i "$2" --delay "$3" >/dev/null
}

echo "==> edge path: target ${EDGE_RTT_MS} ms RTT ($EDGE_HALF each direction)"
set_delay clab-edgegame-client eth1 "$EDGE_HALF"
set_delay clab-edgegame-edge   eth1 "$EDGE_HALF"

echo "==> cloud path: target ${CLOUD_RTT_MS} ms RTT ($CLOUD_HALF each direction)"
set_delay clab-edgegame-client eth2 "$CLOUD_HALF"
set_delay clab-edgegame-cloud  eth1 "$CLOUD_HALF"

echo "==> current impairments"
containerlab tools netem show -n clab-edgegame-client 2>/dev/null || true

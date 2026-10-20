#!/usr/bin/env bash
# The load->latency grid the dataset is built from.
#
# Each node is swept on its own ladder, sized to its measured capacity
# (docs/07-capacity.md) so every node is seen from idle to past - or as close
# as the 100-player ceiling allows - its knee. edge1 holds ~50 players, so its
# ladder is finer and stops at 60; the others run to the 100-player ceiling.
#
# Run once per replicate. Replicate b walks the nodes in reverse order, so a
# slow drift of the host over the run (thermal, memory) does not line up with
# node identity in both replicates.
#
# Usage: ./grid.sh <tag> [reverse]
#   ./grid.sh grid-a
#   ./grid.sh grid-b reverse
set -euo pipefail
cd "$(dirname "$0")"

TAG="${1:?usage: ./grid.sh <tag> [reverse]}"
ORDER="edge1 edge2 edge3 cloud"
[ "${2:-}" = reverse ] && ORDER="cloud edge3 edge2 edge1"

declare -A LOADS=(
  [edge1]=1,10,20,30,40,50,60
  [edge2]=1,20,40,60,80,100
  [edge3]=1,20,40,60,80,100
  [cloud]=1,20,40,60,80,100
)

VERIFY=""
for n in $ORDER; do
  ./collect.sh --targets "$n" --loads "${LOADS[$n]}" \
               --duration 90 --idle 15 --settle 20 --tag "$TAG" $VERIFY
  VERIFY=--no-verify          # pre-flight once per replicate, not per node
done

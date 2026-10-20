#!/usr/bin/env bash
# Deploy every distinct placement in results/placement/plan.json, one after
# another, under one tag. Order is shuffled with a fixed seed so the scenario
# size does not line up with time-of-run.
#
# Usage: ./deploy_plan.sh <tag> [seed]
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd .. && pwd)"
TAG="${1:?usage: ./deploy_plan.sh <tag> [seed]}"
SEED="${2:-1}"

"$REPO/topology/verify.sh" >/dev/null || { echo "pre-flight failed, aborting"; exit 1; }

python3 - "$REPO/results/placement/plan.json" "$SEED" <<'EOF' |
import json, random, sys
d = json.load(open(sys.argv[1]))["deployments"]
items = sorted(d.items())
random.Random(int(sys.argv[2])).shuffle(items)
for name, arg in items:
    print(name, arg)
EOF
while read -r name arg; do
  ./deploy.sh --tag "$TAG" --name "$name" --placement "$arg" </dev/null
done

#!/usr/bin/env bash
# Rebuild every derived artefact from the raw measurements, in order.
#
#   ./rebuild.sh            data, scores, figures, report and guide PDFs
#   ./rebuild.sh --site     also the static replay of the dashboard (site/)
#
# Needs no testbed: everything here reads results/raw/ and results/live/.
# The PDFs need tectonic (https://tectonic-typesetting.github.io); the step is
# skipped with a note if it is not installed. git diff afterwards shows what,
# if anything, changed.
set -euo pipefail
cd "$(dirname "$0")"

runs=$(ls results/raw | grep -xE 'grid[1-9]|place[1-9]' | paste -sd, -)
echo "== dataset from: $runs"
python3 dataset/build_dataset.py --tags "$runs"

echo "== model scores"
python3 -m model.evaluate > /dev/null
python3 -m model.metrics > /dev/null
python3 -m model.uncertainty > /dev/null

echo "== deployed placements"
for t in $(ls results/raw | grep -xE 'place[1-9]'); do
  python3 -m placement.experiment score --tag "$t" > /dev/null
done

echo "== live runs"
python3 -m live.summarize > /dev/null

echo "== figures"
python3 -m model.figures > /dev/null
python3 -m live.figures > /dev/null

TECTONIC=$(command -v tectonic || echo "$HOME/tools/tectonic/tectonic")
if [ -x "$TECTONIC" ]; then
  echo "== report and demo guide PDFs"
  "$TECTONIC" -X compile report/main.tex --outdir report > /dev/null
  (cd docs/demo-guide && "$TECTONIC" -X compile guide.tex > /dev/null)
else
  echo "== PDFs skipped: tectonic not installed"
fi

if [ "${1:-}" = "--site" ]; then
  echo "== replay site"
  python3 -m live.build_site > /dev/null
fi

echo "== tests"
python3 -m pytest -q | tail -1
echo "done; git status shows what changed"

#!/usr/bin/env bash
# Rebuild the presentation from the figures in figures/.
#   deck/build.sh   -> deck/latency_edge_placement.pptx (16 slides)
# latency_edge_placement_v2.pptx is the team's hand-made deck; build_v3.py
# brings its text and figures up to date with the results, build_v4.py
# arranges it in the report's sections (Abstract ... Conclusion and Future
# Work). topology_diagram.py draws slide 5's topology from the /30 subnets the
# containerlab file configures.
set -euo pipefail
cd "$(dirname "$0")"
python3 -I topology_diagram.py assets/topology_30.png
python3 -I build_v3.py latency_edge_placement_v2.pptx /tmp/deck_v3.$$.pptx ../figures
python3 -I build_v4.py /tmp/deck_v3.$$.pptx latency_edge_placement.pptx
rm -f /tmp/deck_v3.$$.pptx

"""Print the live state of every node, as the dashboard has it now.

    python3 -m live.status          (live/load.sh status calls this)
"""
import json
import sys
import urllib.request


def ms(v):
    if v is None:
        return "-"
    return f"{v / 1000:.1f} s" if v >= 1000 else f"{v:.0f} ms"


def main():
    with urllib.request.urlopen("http://127.0.0.1:8090/api/state", timeout=5) as r:
        s = json.load(r)
    if "nodes" not in s:
        sys.exit("no run in progress")
    print(f"run {s['run']}  t={s['t']:.0f}s  controller={s['policy']}  status={s['status']}")
    print(f"{'node':6} {'players':>7} {'tick':>8} {'p95':>8} {'learned':>9} {'formula':>9}  matches")
    for n, d in s["nodes"].items():
        tick = "-" if d["mspt_ms"] is None else f"{d['mspt_ms']:.1f} ms"
        p = d["predicted"]
        print(f"{n:6} {d['players']:>7} {tick:>8} {ms(d['p95_ms']):>8} {ms(p.get('learned')):>9} "
              f"{ms(p.get('analytical')):>9}  {' '.join(f'm{m:02d}' for m in d['matches'])}")
    for e in s.get("log", [])[:5]:
        print(f"  t={e['t']:>6.0f}s  {e['text']}")


if __name__ == "__main__":
    main()

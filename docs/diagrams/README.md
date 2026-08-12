# Diagrams

Figures are generated, not drawn by hand, so they can be regenerated when the
testbed changes rather than going quietly stale.

```bash
cd docs/diagrams
python3 architecture.py     # -> architecture.png
python3 code_map.py         # -> code-map.png
```

Only `matplotlib` is needed. The scripts look for JetBrains Mono in
`~/.local/share/fonts/` and fall back to the default monospace face if it is
not installed, so they run anywhere.

| File | What it shows | Source of its numbers |
|---|---|---|
| `architecture.png` | the lab (client, four candidates, emulated links) and how deep into a node each of the four probes reaches | RTTs from [05-runbook.md](../05-runbook.md), `N_max` from [07-capacity.md](../07-capacity.md), quotas and cpusets from `topology/nodes.env` |
| `code-map.png` | every source file, what it does, and the order they run in | `wc -l` over the tracked source files |

**Both carry hard-coded numbers.** If the node table, the netem profile or the
measured capacities change, edit the tables at the top of the relevant script
and re-run it — nothing here reads the testbed live.

# Documentation

Written for someone who has never touched containerlab, Minecraft servers, or
Linux traffic control. Every concept is explained once, in the file where it
first matters, and every command is spelled out flag by flag.

## Read in this order

| # | File | What it answers |
|---|---|---|
| 1 | [01-concepts.md](01-concepts.md) | What all the words mean. Latency, RTT, queueing delay, tail percentiles, MSPT, CFS quota, netem, emulation vs simulation. |
| 2 | [02-topology.md](02-topology.md) | What the testbed is, why it has these five nodes, and what every line of the topology file does. |
| 3 | [03-commands.md](03-commands.md) | Every shell command in the project, explained flag by flag. Use as a reference. |
| 4 | [04-metrics.md](04-metrics.md) | What we measure, why there are four different latency numbers, and the exact format of every output file. |
| 5 | [05-runbook.md](05-runbook.md) | The step-by-step procedure to run a collection from a cold machine. |
| 6 | [06-troubleshooting.md](06-troubleshooting.md) | Every failure hit so far and the fix. Read this when something breaks. |
| 7 | [07-capacity.md](07-capacity.md) | How each node's capacity is measured, why utilization is the portable unit, and the numbers it produced. |

[HANDOFF.md](HANDOFF.md) is the one-file summary of the whole project — what
exists, what it showed, what will bite you, and the standing constraints.
Start there if you are picking this up cold.

## Where the project currently stands

```
done      single-node baseline                     results/derisk.md, results/sweep.md  (SUPERSEDED)
done      two-node testbed, first collection       results/raw/run1/                    (SUPERSEDED)
done      four-candidate testbed, capacity ladder  topology/
done      four-way latency measurement             bots/probe.js, bots/bot.js
done      metric collection driver                 controller/collect.sh
done      world warm-up, a required pre-step       controller/warmup.sh
done      per-node capacity measured               results/raw/capacity/
NOW       warm re-run of the placement grid
next      analysis of the collected streams
later     labelled dataset
later     load-aware latency model
later     substitute the model into a placement algorithm
```

Two earlier results are marked SUPERSEDED because they were measured on freshly
copied worlds. The server was *generating* terrain as well as simulating
players, and because those grids ramped the player count upward, generation
load rose together with player load and cannot be separated after the fact.
The effect and its mechanism survive; the magnitudes do not. See
[06-troubleshooting.md §6.2b](06-troubleshooting.md).

The line between "metric collection" and "dataset" matters and is deliberate.
Collection produces *raw observations* - one file per measurement stream, with
timestamps, untouched. A dataset is what you get after joining those streams,
choosing features and attaching labels. That join throws information away, and
it is much easier to do it correctly once you can see all the raw streams side
by side. So: collect first, keep everything, decide later.

## Repository map

```
bots/          bot.js      load generator + in-game latency measurement
               probe.js    network / TCP / server-status latency probes
topology/      *.clab.yml  the containerlab testbed definition
               nodes.env   the node table every script reads
               up.sh down.sh prepare.sh netem.sh verify.sh
controller/    warmup.sh   generate terrain before measuring (required)
               capacity.sh measure each node's N_max
               collect.sh  the metric collection driver
results/       derisk.md sweep.md   write-ups of the single-node experiments
               raw/                 raw measurement streams, one dir per run
docs/          this documentation
```

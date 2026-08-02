# Documentation

Written for someone who has never touched containerlab, Minecraft servers, or
Linux traffic control. Every concept is explained once, in the file where it
first matters, and every command is spelled out flag by flag.

## Read in this order

| # | File | What it answers |
|---|---|---|
| 1 | [01-concepts.md](01-concepts.md) | What all the words mean. Latency, RTT, queueing delay, tail percentiles, MSPT, CFS quota, netem, emulation vs simulation. |
| 2 | [02-topology.md](02-topology.md) | What the testbed is, why it has exactly these three nodes, and what every line of the topology file does. |
| 3 | [03-commands.md](03-commands.md) | Every shell command in the project, explained flag by flag. Use as a reference. |
| 4 | [04-metrics.md](04-metrics.md) | What we measure, why there are four different latency numbers, and the exact format of every output file. |
| 5 | [05-runbook.md](05-runbook.md) | The step-by-step procedure to run a collection from a cold machine. |
| 6 | [06-troubleshooting.md](06-troubleshooting.md) | Every failure hit so far and the fix. Read this when something breaks. |

## Where the project currently stands

```
done      single-node baseline experiment          results/derisk.md, results/sweep.md
done      edge-cloud topology                      topology/
done      four-way latency measurement             bots/probe.js, bots/bot.js
done      metric collection driver                 controller/collect.sh
NOW       first full collection pass               results/raw/run1/
next      analysis of the collected streams
later     labelled dataset
later     load-aware latency model
later     substitute the model into a placement algorithm
```

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
               up.sh down.sh prepare.sh netem.sh verify.sh
controller/    collect.sh  the metric collection driver
results/       derisk.md sweep.md   write-ups of the single-node experiments
               raw/                 raw measurement streams, one dir per run
docs/          this documentation
```

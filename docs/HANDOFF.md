# Handoff

State of the project as of **2026-08-03**, HEAD `dd1cdca`. Written so a fresh
session can pick this up without re-deriving anything.

Read [README.md](README.md) for the doc index. This file is the summary of
*what exists*, *what it showed*, and *what will bite you*.

---

## 1. The thesis

Edge placement algorithms pick a node with an analytical latency model:

```
latency = propagation_delay + data_size / bandwidth
```

It has a term for distance and a term for bandwidth, and **no term for server
load**. Edge nodes are small and cannot scale out, so once one is crowded the
queueing delay inside the server can exceed the network delay that edge
placement was supposed to save. The error is invisible in the literature
because placement algorithms are evaluated in simulators (iFogSim,
EdgeCloudSim, YAFS, PureEdgeSim) built on the same load-blind formula - the
algorithm is graded by the assumption it is built on.

**Novelty, stated narrowly:** learn the load→latency curve *empirically* from a
real interactive workload and use it as the latency term that *ranks* candidate
nodes. The claim is not "nobody uses load" - autoscalers, load balancers, cost
models and queueing-aware placement all read it. The claim is that nobody
*measures* the load→latency relationship for a tail-sensitive interactive
workload and puts it into the placement ranking. See the **Positioning** table
in the README.

**End goal:** show the model mispredicts badly enough to pick the wrong node,
then replace it with a latency predictor trained on measured data and compare
node rankings.

---

## 2. What is built

```
bots/
  bot.js         mineflayer load generator + in-game RTT (chat echo)
  probe.js       TCP-handshake and Minecraft-status-ping probes
topology/
  edge-cloud.clab.yml   containerlab: client + edge + cloud, two links
  Dockerfile.client     node:22-bookworm + iproute2 + iputils-ping + procps
  prepare.sh     build per-node /data from a known-good Docker volume
  up.sh          build image, deploy, wait for readiness, apply netem, verify
  netem.sh       apply the emulated distance (half the RTT on each end)
  verify.sh      pre-flight; exits non-zero if anything is off
  down.sh        teardown (--clean also deletes the ~510 MB of node data)
controller/
  collect.sh     the metric collection driver
results/
  derisk.md sweep.md    write-ups of the single-node phase
  raw/*.log             single-node logs (older "<i> RTT: <ms>" format)
  raw/run1/             two-node testbed, 12 cells, 4 streams each
docs/                   01-concepts .. 06-troubleshooting, plus this file
```

Not present, deliberately: `data/` (no dataset), no model, no analysis scripts.

### The testbed

```
                       netem 2.5 ms each way        cpu.max = 0.5 core
   client ──eth1── 10.0.1.0/30 ──────────────────── edge   10.0.1.2
     bots                                                  cores 0-1
   probes ──eth2── 10.0.2.0/30 ──────────────────── cloud  10.0.2.2
   cores 8-23          netem 20 ms each way         cpu.max = 4 cores
                                                           cores 2-7
```

Containers are `clab-edgegame-{client,edge,cloud}`. **Pointing the bots at
`10.0.1.2` rather than `10.0.2.2` is the placement decision.**

Measured RTT (not assumed - `ping`, 20 packets, 0% loss):
**edge 5.11 ms**, **cloud 40.14 ms**, mdev < 0.1 ms on both.

Edge and cloud are otherwise identical: same jar, same world, same config,
copied from the same source. CPU and network delay are the only differences.

The three core ranges are disjoint so the load generator cannot steal CPU from
the servers it measures.

### The measurement ladder

The same path measured at four depths, concurrently, under the same load:

| rung | tool | path it exercises |
|---|---|---|
| ICMP | `ping -D` in the client | network only - what the analytical model predicts |
| TCP handshake | `probe.js` | + the server host's accept path |
| status ping | `probe.js` (`minecraft-protocol.ping`) | + the server *process* |
| in-game RTT | `bot.js` chat echo | + the server's single main game thread |

Reading them together attributes the delay to a layer instead of guessing.
Server-side counters (`rcon-cli mspt` / `tps`, `docker stats`, `rcon-cli list`)
are sampled every 5 s so the cause is recorded next to the effect.

**Caution:** a status ping is a TCP handshake plus a handshake packet plus a
status request, so its absolute value is ~3.4x the ICMP RTT (17.5 ms on the
5.1 ms link, 123 ms on the 40.1 ms link). Compare it to *its own idle
baseline*, which every cell records - never to the other rungs.

### The collection driver

`controller/collect.sh` walks a grid of (placement target x player count).
Per cell:

```
  settle 30s     no players; let the previous cell's damage drain
  idle   20s     probes only, zero players -> network-only baseline for THIS cell
  join   N/2+10s bots log in staggered 500 ms apart; load not yet steady
  steady 120s    full load held; the measurement window
```

Every phase boundary is written to `meta.json` in milliseconds. Each cell is
gated on `rcon list` reporting **0** players before it starts.

Output: `results/raw/<tag>/<target>-<N>bots/` containing `bot.csv`,
`probe.csv`, `icmp.txt`, `server.csv`, `meta.json`. Four independent raw
streams. Nothing joined, aggregated or labelled.

---

## 3. What the data shows

### Phase 1 - single node, localhost, zero network distance

`results/derisk.md` (1 vs 25 bots) and `results/sweep.md` (1-40 bots). Tail RTT
grew ~15x at p95 while the analytical model's prediction stayed constant. MSPT
74 ms against a 50 ms budget; CPU pinned at the 0.5 cap. Proved the model is
*incomplete*. Did **not** prove it picks the wrong node - that needs two nodes.

### Phase 2 - two nodes, run `run1`, 12 cells

All 12 cells held their full player count with **zero kicks**. All times ms.

```
                icmp     tcp    status    in-game RTT              server
cell             p50     p50    p50  p95   p50    p95    p99    cpu%  mspt
edge-1          5.10    5.43   17.5   22     7     11     60      12   6.2
edge-5          5.09    5.41   17.2   20     7     18     40      20   8.8
edge-10         5.08    5.46   17.7   66     8     71   2517      27  12.7
edge-20         5.08    5.48   20.1   91    20   3753   6271      45  28.6
edge-30         5.06    5.45   33.6  641    44   3942   5243      50  40.0
edge-40         5.07    5.45   62.5  454   166   6248   8638      50  72.8
cloud-1        40.10   40.53  123.0  124    42     43     44      17   3.4
cloud-5        40.10   40.49  122.7  123    42     43     45      20   4.0
cloud-10       40.10   40.53  122.8  124    42     44     48      23   4.8
cloud-20       40.10   40.51  123.0  124    49     82    101      35   6.3
cloud-30       40.10   40.53  122.8  124    67    138    549      43   7.5
cloud-40       40.10   40.52  122.9  125   123    310    709      67   9.3
```

`cpu%` is median container CPU (100% = one core, so the 0.5-core edge saturates
at 50). `mspt` is the median 5-second average tick time; budget is 50 ms.

**Established:**

1. **The omitted term dominates.** Edge p95 goes 11 → 6248 ms, a factor of 570,
   while the analytical prediction is a flat line.
2. **It is not the network and not the load generator.** ICMP on the edge link
   read 5.06-5.10 ms in *every* cell, idle or saturated, p95 within 0.1 ms of
   p50. The link moved by 0.03 ms while in-game latency moved 570x.
3. **It is specifically the game thread.** TCP handshake 5.43 → 5.48 ms across
   the whole sweep; the status ping moves partially (17.5 → 62.5); only the
   in-game RTT explodes.
4. **Mechanism recorded, not assumed.** Edge CPU pins at its cap from 30 bots
   and MSPT crosses the 50 ms tick budget between 30 and 40 - exactly where
   latency becomes seconds.

**The headline - rank inversion.** The model ranks by distance alone, so it
picks edge at every load, by a fixed 35 ms. Measured p95:

| bots | 1 | 5 | 10 | 20 | 30 | 40 |
|---|---|---|---|---|---|---|
| edge p95 | 11 | 18 | 71 | 3753 | 3942 | 6248 |
| cloud p95 | 43 | 43 | 44 | 82 | 138 | 310 |
| measured winner | edge | edge | **cloud** | **cloud** | **cloud** | **cloud** |

From 10 players on the model picks the worse node, by 45x at 20 players.

**The sharpest finding - the crossover depends on the percentile:**

| percentile | edge stops winning at |
|---|---|
| p50 | between **30 and 40** players |
| p95 | between **5 and 10** players |

Same nodes, same run, same instant. A model predicting *average* latency would
call edge correct up to ~35 players; the tail says it stopped being correct at
10. That is a 4x difference in capacity planning from the choice of statistic
alone, and it is the strongest support the project has produced for its own
tail-focused framing.

**Not established:**

- **Replication.** n = 1 run, no variance estimate.
- **Generality of the crossover.** Where it sits depends on the capacity ratio
  (0.5 vs 4 cores) and the distance gap (5 vs 40 ms), both *chosen*, not
  discovered. Defensible claim: "an inversion exists and is large" - not "it
  happens at 10 players".
- **Respawn contribution.** Bots walk forward forever and eventually fall or
  drown; 3-9 respawns per cell are logged but not separated from steady-state
  queueing in the tail.
- **Shared-host confound** is *bounded* by the flat ICMP, not eliminated -
  memory bandwidth and caches are still shared across the pinned cores.
- **The actual thesis.** Nothing trained. No evidence yet that a learned model
  ranks better than the analytical one.

---

## 4. Hard-won gotchas - read before touching anything

Full detail in [06-troubleshooting.md](06-troubleshooting.md). The ones that
produce *plausible but worthless* data:

| Trap | Why it hides | Guard |
|---|---|---|
| `docker inspect .HostConfig.NanoCpus` reads **0** on a correctly-capped container - containerlab uses `CpuQuota`/`CpuPeriod` | trusting it means chasing a phantom bug; trusting the YAML means shipping a real one | read `/sys/fs/cgroup/cpu.max` from inside the container |
| `docker logs \| grep 'Done ('` matches a line from a **previous boot** | the readiness wait returns instantly against a dead server | `mc-monitor status --host 127.0.0.1` |
| `pkill -f "bot.js"` matches its own command line and kills the calling shell | script dies silently, exit 144 | `pkill -f 'bot[.]js'` |
| `grep -c` exits **non-zero when the count is zero** | under `set -e` a *clean* run kills the script | `X=$(grep -c ... ) \|\| X=0`, not `\|\| echo 0` |
| Log lines carry ANSI codes; rcon output carries `§`+char | regexes silently match nothing, percentiles come back `NaN` | strip `\x1b\[[0-9;]*m` and `\xc2\xa7.` before parsing |
| `TYPE=PAPER` contacts api.papermc.io on **every** start; `SKIP_UPDATE=TRUE` does not stop it | one network hiccup and nothing boots, despite the jar being present | `TYPE=CUSTOM` + `CUSTOM_SERVER=/data/paper-1.21.4-232.jar` |
| Previous cell's sessions linger on a CPU-starved server | reused usernames produce `duplicate_login` kicks that look like an overload symptom | gate every cell on `rcon list` = 0 |
| netem only delays **egress** | a one-sided rule gives half the RTT you configured | half the target on each end, then verify with `ping` |
| Bots dialling the management IP (`172.20.20.x`) | the emulated links are never touched; near and far measure identically | data-plane IPs only: `10.0.1.2` / `10.0.2.2` |
| **mineflayer re-emits `spawn` on every respawn** | listeners and intervals registered per spawn stack up; one bot sent 3 msg/s and counted each 3x - 530 samples in 130 s instead of 130 | register once (`bot.js` guards with a `spawns` counter); sanity-check `grep -c ',rtt,'` against `N x duration` |

That last one was live in the original `bot.js`, so **the July single-node
sweep numbers carry it**. Flagged, not silently patched.

---

## 5. Conventions and standing constraints

- **No Claude attribution in commits.** No `Co-Authored-By: Claude`, no
  `Claude-Session:` trailer. Author stays `charan
  <ankamcharantejaa@gmail.com>`. History was rewritten once to strip these;
  don't reintroduce them.
- **Do not build a dataset or train a model yet.** Stated twice, explicitly.
  Collection keeps everything and decides nothing; joining, feature selection
  and labelling are the next phase, not this one.
- **Do not write a `results/run1.md`.** The numbers are already framed
  correctly in `docs/04-metrics.md §4.1` and the README as a sanity check that
  the instrument works - not as the analysis.
- **Docs are for a beginner.** Every concept explained where it first matters,
  every command flag by flag. Keep that register.
- **Claims are stated with their limits.** "Capacities were chosen, not
  discovered" and "one run, one host" belong next to the crossover result every
  time it is quoted.
- `.gitignore` intentionally ignores `docs/edge-game-placement-project.md`
  (personal working notes), `topology/nodes/` (~510 MB of server data) and
  `topology/out/` (collector scratch). Everything else in `docs/` is tracked.

---

## 6. Environment

| | |
|---|---|
| host | Fedora, i7-14700HX, 28 cores, 16 GB RAM |
| containerlab | 0.76.1, runs non-root (user in `docker` + `clab_admins`) |
| node | v22.22.2 (host), v22.23.2 (client container) |
| server | Paper 1.21.4 (`itzg/minecraft-server`), booted from cached jar |
| mineflayer | 4.37.1 |

No passwordless sudo on this host - everything must work as an unprivileged
user in the `docker` group.

Another containerlab lab (`chunk3`, FRR routers) shares the management bridge.
It is unrelated and must not be disturbed.

**The lab is currently up.** `topology/down.sh` to remove it.

---

## 7. Reproducing from cold

```bash
cd topology && ./prepare.sh && ./up.sh    # ends with ALL CHECKS PASSED or exits
cd ../controller
./collect.sh --targets edge --loads 5 --duration 60 --tag smoke   # smoke first
./collect.sh --tag run2                                           # ~40 min
```

`up.sh` refuses to hand over a testbed that does not verify. Always smoke-test
one cell before a 40-minute unattended grid - this rig has historically failed
in ways that leave a directory full of empty files.

Full procedure: [05-runbook.md](05-runbook.md).

---

## 8. Next steps, roughly in order

1. **Analysis of `run1`** - locate the crossover precisely per percentile,
   separate respawn bursts from steady-state queueing in the tail, relate MSPT
   to in-game RTT.
2. **Replication** - re-run the grid at least twice for a variance estimate.
   The crossover cell is currently a single observation.
3. **Sweep the design parameters** - capacity ratio (edge at 0.25 / 0.5 / 1
   core) and distance gap, to show *how* the crossover moves rather than that
   it exists at one point.
4. **Richer impairment** - `containerlab tools netem set` also takes
   `--jitter`, `--loss` and `--rate`. A bandwidth cap would finally make the
   formula's `data_size / bandwidth` term non-trivial instead of negligible.
5. **Then** the dataset, then the predictor, then substituting it into a
   placement algorithm and comparing node rankings against the analytical
   baseline. Not before.

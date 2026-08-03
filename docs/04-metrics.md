# 4. What is measured, and why

The core measurement idea, and the exact format of every file a collection run
produces.

---

## 4.1 One latency number is not enough

If you only measure "how long did the player's action take", you get a number
that mixes the network, the operating system, and the game together, and you
cannot say which one got slower. The whole argument of this project is *which
layer* the extra delay lives in - so the measurement has to separate them.

So the same path is measured at four depths, **simultaneously**, on the same
link, during the same load:

| # | Probe | Path it exercises | Tool |
|---|---|---|---|
| 1 | **ICMP ping** | kernel to kernel. Network only. No application involved. | `ping -D` inside the client |
| 2 | **TCP handshake** | network + the server host's TCP accept path | `probe.js`, `net.connect` |
| 3 | **Server status ping** | network + the server *process* answering a request | `probe.js`, `minecraft-protocol.ping` |
| 4 | **In-game action RTT** | network + the server's **main game thread** | `bot.js`, chat echo |

Read the four together and the delay is decomposed:

- If **all four** rise, the network got slower.
- If **1 and 2 stay flat** but **3 and 4 rise**, the network is fine and the
  server process is the bottleneck.
- If **1, 2 and 3 stay flat** but **4 rises**, the delay is specifically in the
  game thread - the tick loop - which is the queueing term the analytical
  placement model omits.

**Probe 1 is also the number the analytical model predicts.** The formula
`propagation + size/bandwidth` describes network transit and nothing else, so
ICMP RTT is very close to what the model would output. Every millisecond
between probe 1 and probe 4 is model error.

### One caution on the status probe's absolute value

A server-list ping is not a single round trip - it is a TCP handshake plus a
handshake packet plus a status request. Idle, it measures about 3.4x the ICMP
RTT on both paths (17.5 ms on a 5.1 ms link, 123 ms on a 40.1 ms link). So do
not compare its absolute value against the others; compare it **against its own
idle baseline**, which is exactly why every cell records one.

### What the first collection pass shows

Median (p50) of each probe during the steady window, run `run1`, 12 cells.
All times in ms.

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

`cpu%` is the median container CPU (100% = one core, so the 0.5-core edge node
saturates at 50). `mspt` is the median 5-second average tick time; the budget
is 50 ms. Every cell held its full player count with zero kicks.

The ladder does its job:

1. **The network never moves.** ICMP sits at 5.07-5.10 ms on the edge path and
   40.10 ms on the cloud path in *every* cell, idle or saturated, with p95
   within 0.1 ms of p50. So nothing in the rest of the table is the emulated
   link - and it is not the load generator either, since that would show up
   here too.
2. **The TCP handshake barely moves** - 5.43 to 5.48 ms across the whole edge
   sweep. Accepting a connection stays cheap even while the game is collapsing.
3. **The status ping does move**, from 17.5 to 62.5 ms on the edge. So the
   server-list ping is *not* fully insulated from load, and probe 3 is honestly
   labelled "network + server process" rather than "network only". This was an
   open question, deliberately left to the data rather than assumed.
4. **The in-game RTT moves enormously** - p95 from 11 ms to 6248 ms on the edge
   node, a factor of 570, while ICMP on the same link changed by 0.03 ms.

And the cause is recorded next to the effect: edge CPU pins at its 0.5-core cap
from 30 bots on, and MSPT crosses the 50 ms tick budget between 30 and 40 bots -
exactly where in-game latency becomes seconds. The cloud node, with 4 cores,
never gets near the budget (9.3 ms at 40 bots).

### The observation worth flagging

The analytical model ranks these two nodes by network distance alone, so it
predicts edge (5 ms) beats cloud (40 ms) at every load, by 35 ms. Measured p95
in-game RTT:

| bots | edge | cloud | model's pick | measured winner |
|---|---|---|---|---|
| 1 | 11 | 43 | edge | edge |
| 5 | 18 | 43 | edge | edge |
| 10 | 71 | 44 | edge | **cloud** |
| 20 | 3753 | 82 | edge | **cloud** |
| 30 | 3942 | 138 | edge | **cloud** |
| 40 | 6248 | 310 | edge | **cloud** |

From 10 players on, the node the model ranks best is the worse one - by a
factor of 45 at 20 players. That is the rank inversion the project set out to
find, and it appears in the very first collection pass.

Stated carefully: this is **one run**, on **one host**, with edge and cloud
capacities that were *chosen* (0.5 vs 4 cores) rather than discovered. The
numbers above are a sanity check that the instrument works and that the effect
is present and large - not the analysis. Establishing where the crossover sits,
how it moves with the capacity ratio and the distance gap, and how much of the
tail is respawn bursts rather than steady-state queueing, is the next phase.

---

## 4.2 Server-side load signals

Latency is the effect. These are the cause, sampled every 5 seconds from the
host:

| Signal | Source | Meaning |
|---|---|---|
| `players` | `rcon-cli list` | how many bots are actually attached. Confirms the offered load is really N. |
| `cpu_percent` | `docker stats` | 100% = one full core. A 0.5-core node reading ~50% is saturated. |
| `mem_usage` | `docker stats` | rules out swapping/GC pressure as an alternative explanation |
| `mspt_raw` | `rcon-cli mspt` | tick times, avg/min/max over 5 s, 10 s and 1 m windows. **Over 50 ms means the server cannot hold 20 ticks per second.** |
| `tps_raw` | `rcon-cli tps` | achieved ticks per second over 1 m, 5 m, 15 m. 20.0 is healthy. |

MSPT is the single most important one. It is the server saying, in its own
units, how far behind it is - and its 50 ms budget comes from the game's
design, not from the hardware, so it means the same thing on a laptop and on a
small edge box. That makes it the natural input feature for a load-aware
latency model that has to generalise across different nodes.

---

## 4.3 The shape of a collection run

`controller/collect.sh` walks a grid of **(placement target) x (player count)**.
Default grid: `{edge, cloud} x {1, 5, 10, 20, 30, 40}` = 12 cells.

Each cell runs four phases:

```
  settle 30s        no players; let the previous cell's damage drain away
  idle   20s        probes only, zero players -> the network-only baseline
                    for this exact cell, measured not assumed
  join   N/2+10s    bots log in staggered 500 ms apart; load is not steady yet
  steady 120s       full load held; this is the measurement window
```

Every phase boundary is written into `meta.json` as a millisecond timestamp, so
analysis can slice out exactly the steady window later without re-running
anything.

Between cells the driver **waits until the server reports zero players**
before starting the next one. Skipping this was the cause of a real failure:
the previous cell's sessions lingered on a CPU-starved server, and reusing the
usernames produced `multiplayer.disconnect.duplicate_login` kicks that looked
like an overload symptom but were not.

---

## 4.4 Output layout

```
results/raw/<tag>/
  edge-1bots/
    bot.csv        in-game latency samples + join/kick/respawn events
    probe.csv      TCP and status-ping samples
    icmp.txt       raw ping output, timestamped
    server.csv     server-side load counters, every 5 s
    meta.json      how this cell was produced
  edge-5bots/
  ...
  cloud-40bots/
```

Four independent raw streams per cell. Nothing is joined, averaged or labelled;
that is deliberate - see [README.md](README.md).

### `bot.csv`

```
epoch_ms,botN,rtt,<ms>        one in-game latency sample
epoch_ms,botN,spawn           bot joined for the first time
epoch_ms,botN,respawn         bot died and came back
epoch_ms,botN,kicked,"why"    server removed the bot
epoch_ms,botN,error,"why"     client-side failure
```

Example:
```
1785732733847,bot0,spawn
1785732734857,bot0,rtt,9
```

The bots walk forward continuously, so over a couple of minutes each one
usually falls or drowns at least once and respawns. That is logged rather than
suppressed: a respawn is a burst of server work and shows up in the tail.

**Any cell containing `kicked` lines is not clean and should be excluded** -
kicks mean the load was not N for the whole window.

### `probe.csv`

```
epoch_ms,tcp,<ms>
epoch_ms,status,<ms>
```
One of each per second. `-1` means the probe failed (timeout or refused), which
is itself a measurement: past a certain load the server stops answering.

Durations are measured with `process.hrtime.bigint()`, a monotonic nanosecond
clock, rather than `Date.now()`, which can jump if the system clock is
adjusted.

### `icmp.txt`

Raw `ping -D` output:
```
[1785732206.604756] 64 bytes from 10.0.1.2: icmp_seq=1 ttl=64 time=5.08 ms
```
The bracketed unix timestamp is what lets ICMP samples be lined up with the
other three streams.

### `server.csv`

```
epoch_ms,players,cpu_percent,mem_usage,mspt_raw,tps_raw
1785732288157,5,50.22,1.023GiB / 1.863GiB,"Server tick times (avg/min/max) from last 5s; 10s; 1m:  22.2/3.8/95.9; 23.9/2.6/105.2; 39.3/0.2/1508.1","TPS from last 1m; 5m; 15m: 13.82; 18.36; 19.42"
```

`mspt_raw` and `tps_raw` are kept as the server's own text, quoted, with commas
turned into semicolons so the CSV stays parseable and colour codes stripped.
They are deliberately **not** parsed at collection time: parsing is a decision
about which of the three time windows matters, and that decision belongs to
analysis, not to collection.

### `meta.json`

```json
{
  "tag": "run1",
  "target": "edge",
  "target_ip": "10.0.1.2",
  "bots": 5,
  "players_held": 5,
  "idle_seconds": 20,
  "duration_seconds": 120,
  "bots_start_ms": 1785732229000,
  "steady_start_ms": 1785732242000,
  "steady_end_ms": 1785732362000,
  "cpu_max": "50000 100000",
  "cpuset": "0-1",
  "netem_delay": "delay 2.5ms"
}
```

`players_held` is the server's own count at the end of the steady window. If it
does not equal `bots`, the cell did not hold its load and should be treated
with suspicion.

---

## 4.5 How to read a run without any analysis code

```bash
cd results/raw/run1/edge-20bots

# did the cell hold its load, and was it clean?
cat meta.json
grep -c ',kicked' bot.csv

# in-game latency, sorted - eyeball the tail
grep ',rtt,' bot.csv | cut -d, -f4 | sort -n | tail -20

# did the network move at all?
grep -o 'time=[0-9.]*' icmp.txt | cut -d= -f2 | sort -n | tail -5

# was the server saturated?
cut -d, -f3 server.csv | tail -20
```

If the last four ICMP numbers are still ~5 ms while the last twenty in-game
numbers are in the hundreds, that gap is the term the analytical model does not
have.

---

## 4.6 What is deliberately not done yet

- No joining of the four streams into one table.
- No percentile tables across the grid.
- No feature selection, no labels, no model.

Collection keeps everything and decides nothing. Every aggregation throws
information away, and it is far cheaper to choose the aggregation once the raw
streams can be inspected side by side than to re-run 40 minutes of experiment
because the wrong summary was stored.

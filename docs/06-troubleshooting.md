# 6. Troubleshooting

Every failure this project has actually hit, what it looked like, and the fix.
Most of them are dangerous specifically because they do **not** look like
failures - the run completes and produces a file full of numbers that mean
nothing.

---

## 6.1 The CPU cap silently did not apply

**Symptom.** Everything deploys, servers respond, but the results table is
suspiciously flat - adding players barely changes latency.

**Cause.** The container has no CPU limit and is quietly using all the host's
cores, so there is nothing to saturate.

**Why it hides.** The obvious check reports the wrong thing:

```bash
docker inspect clab-edgegame-edge --format '{{.HostConfig.NanoCpus}}'
# -> 0     ... which reads as "no limit"
```

containerlab expresses `cpu: 0.5` as `CpuQuota`/`CpuPeriod`, not `NanoCpus`,
so `NanoCpus` is `0` on a container that *is* correctly limited. Trusting that
field would send you chasing a non-existent bug; trusting the YAML would let a
real one through.

**Fix.** Ask the kernel what is actually enforced:

```bash
docker exec clab-edgegame-edge cat /sys/fs/cgroup/cpu.max
# 50000 100000   = 50 ms of CPU time per 100 ms window = 0.5 core
# max 100000     = NO LIMIT - this is the failure
```

`topology/verify.sh` does this on every run.

---

## 6.2 The bots were sending several messages a second

**Symptom.** A single bot produced 530 latency samples in a 130-second window.
It should produce about 130 - one per second.

**Cause.** `bot.js` attached its chat listener and its two `setInterval`s
inside a `bot.on('spawn', ...)` handler. mineflayer emits `spawn` **again after
every respawn**, and a bot that walks forward forever eventually falls or
drowns. Each death therefore added another chat listener *and* another pair of
intervals. After three spawns the bot was sending three messages a second and
counting each one three times.

**Why it matters.** Both the offered load and the sample count were wrong: a
"20-bot" cell was really generating the traffic of many more, and the extra
samples were duplicates rather than independent observations.

**Fix.** Set everything up exactly once, and log respawns separately so they
stay visible:

```js
let spawns = 0
bot.on('spawn', () => {
  if (++spawns > 1) { log(i, 'respawn'); return }
  ...
})
```

**How to catch it.** Sample count should be about
`bots x steady-window seconds`. Several times that means this bug.

---

## 6.2b A cold world makes a healthy node look saturated

**Symptom.** The first cell run against a freshly-deployed node shows a
saturated server - CPU pinned at the cap, MSPT over the 50 ms budget, tail
latency in the hundreds of ms. Re-running the *same cell* a few minutes later
shows a comfortable server.

Same node, same 5 bots, same 60 s window, on a 0.5-core node:

| | p50 | p95 | p99 | cpu% | mspt |
|---|---|---|---|---|---|
| cold world | 43 | 474 | 819 | 50 (capped) | 66.0 |
| warm world | 7 | 60 | 73 | 21 | 5.1 |

**Cause.** Each node boots from a copy of the same server directory. The world
in it is generated only where a previous session actually went. The first time
bots walk outward from spawn, the server has to **generate** new terrain, and
world generation is far more expensive than simulating an already-generated
chunk.

**Why this is dangerous rather than merely annoying.** It does not just add
noise - it adds *correlated* noise:

- It hits the **weakest node hardest**, which is exactly the node the
  experiment's conclusion rests on.
- In a grid that ramps `1, 5, 10, 20, 30, 40`, each cell pushes bots into
  terrain the previous cells never reached. So chunk generation **rises
  together with player count**, and the two are confounded. A curve that looks
  like "queueing delay vs load" is partly "world generation vs load".

**Fix.** Warm every node before collecting, and discard that data:

```bash
cd controller && ./warmup.sh 20 150
```

`warmup.sh` runs bots on all nodes simultaneously (their cpu-sets are disjoint,
so they do not compete), then `save-all`s the generated chunks to disk. After
it, cells can be run in any order and in isolation.

**How to detect it after the fact.** Compare the first cell of a run against a
repeat of that same cell later in the run. If the repeat is dramatically
healthier, the first one was measuring terrain generation.

---

## 6.3 Kicked bots: `multiplayer.disconnect.duplicate_login`

**Symptom.** Bots disconnect mid-run. Easy to misread as an overload symptom.

**Cause.** The *previous* run's sessions were still attached. A CPU-starved
server is slow to notice a dropped client, and the next run reuses the same
usernames (`bot0`..`bot39`), so the server sees a second login for a name that
is still online and kicks one of them.

**Fix.** Gate every run on the server reporting zero players before it starts:

```bash
docker exec clab-edgegame-edge rcon-cli list
# There are 0 of a max of 100 players online:
```

`collect.sh` does this in `wait_empty()` and will not start a cell until it
sees zero.

**Not to be confused with** the vanilla anti-spam kick, which fires on chatting
once per second and gets *more* aggressive when the server is already behind.
The fix for that one is opping the bots, which the prepared server data already
does for `bot0`..`bot39`.

---

## 6.4 Server will not start: `Failed to download paper`

**Symptom.**

```
[init] [ERROR] Failed to download paper
io.netty.channel.unix.Errors$NativeIoException: recvAddress(..) failed with
error(-104): Connection reset by peer
```

**Cause.** With `TYPE=PAPER` the `itzg` image contacts `api.papermc.io` on
every start to check for updates. If that host is unreachable - which it was,
while Docker Hub worked fine - the container will not boot even though the jar
is already sitting in `/data`. `SKIP_UPDATE=TRUE` does not prevent it.

**Fix.** Run the cached jar directly and remove the network dependency:

```yaml
env:
  TYPE: CUSTOM
  CUSTOM_SERVER: /data/paper-1.21.4-232.jar
```

This is why the topology uses `TYPE: CUSTOM`.

---

## 6.5 "Server is ready" when it is not

**Symptom.** A readiness loop returns instantly, then everything downstream
fails because nothing is listening.

**Cause.**

```bash
until docker logs mc1 2>&1 | grep -q 'Done ('; do sleep 2; done
```

`docker logs` returns the container's whole history. With a persistent data
directory, a `Done (` line from a boot two days ago is still in there, so the
loop exits immediately.

**Fix.** Use a real readiness probe that asks the running server:

```bash
docker exec clab-edgegame-edge mc-monitor status --host 127.0.0.1
```

Exit status 0 means the world finished loading and connections are accepted.
Docker's own health status (`docker inspect -f '{{.State.Health.Status}}'`)
works too.

---

## 6.6 `pkill` kills the script that ran it

**Symptom.** The driver script dies silently, often with exit code 144.

**Cause.**

```bash
pkill -f "bot.js"
```

`-f` matches the full command line - including `pkill`'s own, which contains
the string `bot.js`. So `pkill` matches itself and its parent shell.

**Fix.** Break the literal match with a bracket expression:

```bash
pkill -f 'bot[.]js'
```

`bot[.]js` still matches the text `bot.js`, but the pattern itself no longer
contains that text.

---

## 6.7 Parsing returns `NaN` for everything

**Symptom.** An analysis script reports `NaN` for every percentile even though
the log file is clearly full of numbers.

**Cause.** The lines start with invisible ANSI colour codes, so
`/^(\d+) RTT: (\d+)/` never matches:

```
\x1b[33m0\x1b[39m RTT: 47
```

Minecraft's own output adds a second layer: the section sign `§` (UTF-8
`c2 a7`) followed by one character.

**Fix.** Strip both before parsing:

```js
const line = raw.replace(/\x1b\[[0-9;]*m/g, '')
```
```bash
sed -e 's/\x1b\[[0-9;]*m//g' -e 's/\xc2\xa7.//g'
```

---

## 6.8 `grep -c` aborts the script

**Symptom.** The driver exits right after a cell finishes, with no error.

**Cause.** `grep -c` **exits non-zero when the count is zero**. Under
`set -e`, counting kicks in a clean run therefore kills the script - the better
the run went, the more reliably it broke.

**Fix.**

```bash
KICKS=$(grep -c ',kicked' bot.csv 2>/dev/null) || KICKS=0
```

Note `|| echo 0` is *not* the fix: `grep -c` already printed its own `0` before
failing, so you get two.

---

## 6.9 Nothing shows any difference between "near" and "far"

**Symptom.** Edge and cloud measure identically.

**Likely causes, in order of likelihood.**

1. **The traffic is on the management network.** Every containerlab node has an
   `eth0` on a plain Docker bridge with no impairment. If the bots dial the
   management IP (`172.20.20.x`) instead of the data-plane IP (`10.0.1.2` /
   `10.0.2.2`), the emulated links are never touched.
2. **netem did not attach.** Check:
   ```bash
   docker exec clab-edgegame-edge tc qdisc show dev eth1
   ```
   It must mention `netem` and a delay. `noqueue` or `pfifo_fast` alone means
   there is no impairment.
3. **The delay is on one side only.** netem delays *egress*. One-sided rules
   give one-way delay, so the RTT is half what you configured.

Always confirm with the measurement, never the configuration:

```bash
docker exec clab-edgegame-client ping -c 20 -q 10.0.1.2
```

---

## 6.10 `containerlab deploy` fails on a name that already exists

**Fix.** `--reconfigure` destroys the previous instance of the lab first:

```bash
containerlab deploy -t edge-cloud.clab.yml --reconfigure
```

Other labs on the same host are unaffected; `containerlab inspect --all` lists
them if you need to be sure.

---

## 6.11 `ip: not found` when containerlab runs the node's `exec` commands

**Cause.** The data-plane addresses are assigned with `ip addr add` after boot,
and the stock `node:22-bookworm` image contains neither `ip` nor `ping`.

**Fix.** `topology/Dockerfile.client` adds `iproute2`, `iputils-ping` and
`procps` on top of the Node image; `up.sh` builds it as `edgegame-client:1`.
The `itzg/minecraft-server` image already has all three.

---

## 6.12 The server crashed mid-experiment

**Symptom.** In the log:

```
Can't keep up! Is the server overloaded? Running 4298ms or 85 ticks behind
```
followed by the container in state `Exited (255)`.

**Cause.** Paper's watchdog kills a server that falls far enough behind. Under
a deliberate overload this is a real possibility, not a bug in the testbed -
but it invalidates the cell.

**How to tell it happened.** `players_held` in `meta.json` will not equal
`bots`, and `bot.csv` will contain `error` or `kicked` lines. Check the
container is still up:

```bash
docker ps --filter name=clab-edgegame --format '{{.Names}}\t{{.Status}}'
```

**Fix.** Re-run that cell with a lower player count, or accept the crash as the
result for that point and record it as such. Do not silently keep a partial
cell.

---

## 6.13 `containerlab tools netem set` fails: `unsupported kind: netem`

**Symptom.** `up.sh` stops right after "applying netem":

```
ERROR  Could not get all qdiscs: extractXStats(): unsupported kind: netem.
```

**Cause.** On newer kernels containerlab installs the qdisc correctly and then
fails reading its statistics back. Under `set -e` the script dies after the
first link, so only one link has a delay.

**Fix.** `netem.sh` now applies the qdisc with `tc` inside each container:

```bash
docker exec <container> tc qdisc replace dev eth1 root netem delay 2.5ms limit 10000
```

`limit 10000` is the queue length containerlab used, so nothing else changes.
`verify.sh` still measures the delay that results.

---

## 6.14 A server restarted by itself during warm-up

**Symptom.** In the server log:

```
The server has not responded for 10 seconds! Creating thread dump
...
Minecraft server failed. ... {"exitCode": 70}
```

and `rcon-cli` refuses connections for a minute while the container restarts.

**Cause.** The main thread stalled for over 60 s - Paper's watchdog limit -
while doing ordinary work. The host was paging: `free -m` showed 6.5 GB of
swap in use and `memory.swap.current` showed hundreds of MB of each server's
heap swapped out. A tick that touches a swapped page waits for the disk.

**Why it matters even without a crash.** A shorter stall does not restart
anything; it just shows up as latency, which the data would blame on player
load. This is the most dangerous kind of artefact: plausible numbers.

**Fix.** Two parts, both in place:

1. `up.sh` sets `--memory-swap` equal to `--memory` on every server right
   after deploy, which forbids that container from swapping. Under memory
   pressure the kernel now has to reclaim from other processes. It must run
   before the heaps grow: pages already in swap stay there.
2. The cloud heap was cut from 2G to 1G (all four servers now use 1G), which
   is plenty for 100 players.

`verify.sh` fails if any server has more than 64 MB in swap, and every cell's
`meta.json` records `server_swap_mb_end` and `host_mem_available_mb_end`.

---

## 6.15 The bots used 47 MB each

**Symptom.** 30 bots in one process: 1.4 GB resident. 100 bots would not fit
next to four JVMs on a 16 GB host.

**Cause.** The server sends each player all 441 chunk columns within view
distance 10, and mineflayer keeps a private parsed copy per bot. It is live
data, not garbage: capping the V8 heap makes the process die with an
out-of-memory error.

**Fix.** `bot.js` shares parsed columns between the bots of one process.
Every bot still receives and parses every column - server work and wire
traffic are unchanged - and a column another bot already holds replaces the
fresh copy. Same 30 bots on edge3: 1430 MB -> 235 MB, with server CPU (~35% vs
~37%), MSPT (6.4 vs 6.5 ms) and sample count unchanged.

The tempting alternative, dropping chunks far from the bot, was rejected: the
server only sends *new* chunks at the edge of view distance, so a bot that
walks would soon stand in a chunk it had thrown away, and its movement - part
of the load - would change.

---

## 6.16 The load generator was measuring itself

**Symptom.** On the strong nodes, latency at 60-100 players was far higher
than their CPU or MSPT could explain: cloud at 80 players, p95 278 ms, with
the server using 0.6 of its 4 cores and ticking in 7 ms.

**Cause.** Every chat message is broadcast to every player, so N bots receive
N^2 messages a second - 6,400 at 80 bots - and one Node process handled all of
them on a single thread. `top` in the client showed it at 70-100% of a core.
A message that arrived while the event loop was busy waited, and that wait
was recorded as round-trip time. Real players are separate machines; this
delay exists only in the testbed.

**Fix.** `bots/spawn.sh` runs at most 10 bots per process (same overall join
schedule, one join every 500 ms), and each process logs its own event-loop
delay p99 every 5 s as `epoch,proc<K>,loop,<ms>` lines in `bot.csv`. Same
cell, cloud at 80 players:

| bots per process | p50 | p95 | p99 |
|---|---|---|---|
| 80 (one process) | 125 ms | 278 ms | 324 ms |
| 20 | 44 ms | 56 ms | 63 ms |
| 10 | 43 ms | 56 ms | 63 ms |

20 and 10 agree, so the client is no longer in the measurement. The grid
measured with one process is kept as `results/raw/grid-a` as evidence of the
artefact; nothing is trained on it. The earlier two-node `run1` and the
single-node sweeps also used one process - their high-load cells carry the
same inflation.

**How to check a run.** The `loop` lines should stay in the tens of ms. If they
climb toward the RTT values, the client is saturated again.

---

## 6.17 After a host reboot the lab looks up but nothing is reachable

**Symptom.** After the host crashed and came back, `docker ps` listed every
`clab-edgegame-*` container as `Up (healthy)` and every server answered
`mc-monitor` from inside its own container, but `verify.sh` failed on every
network check:

```
FAIL client eth1 is not 10.0.1.1
FAIL edge1 missing netem (client:eth1 'none', edge1:eth1 'none')
FAIL edge1 (10.0.1.2) unreachable
```

**Cause.** Docker restarts the containers on boot (restart policy), but the
veth pairs between them are created by `containerlab deploy`, not by Docker.
They live in the containers' network namespaces and die with them. A restarted
container comes back with only its management interface: no `eth1..eth4`, no
data-plane addresses, and therefore no netem qdiscs either. The servers are
healthy - they simply have no link to the client.

**Fix.** Run `topology/up.sh` again. It redeploys with `--reconfigure`
(the node data in `topology/nodes/` is bind-mounted and survives, so the worlds
stay warm), re-forbids swap, reapplies netem and ends with `verify.sh`.

**What it did to the data.** Nothing that was kept: the crash interrupted
`grid1` after its last edge1 cell, so `results/raw/grid1/` held edge1 only.
The remaining nodes were collected after the redeploy under the same tag;
every cell's `meta.json` records its own time, and the idle-baseline RTT
recorded per cell (`net_rtt_idle_ms`) confirms the links came back at the same
values (5.06 / 15.08 / 30.04 / 40.07 ms minimum RTT).

**Rule.** After any reboot, `verify.sh` before anything else. A healthy
container is not a connected one.

---

## 6.18 The same cell measured 10x worse in the second replicate

**Symptom.** The two grid replicates agreed on edge2, edge3 and cloud, but not
on edge1. With a single player, edge1 measured p95 7 ms in the first replicate
and 84 ms in the second, at 9% vs 46% CPU; at 20 players, 19 ms vs 2134 ms.
The idle baseline (0 players) was 2% CPU in both, so the server was not busy
on its own - one player made it busy.

**Cause.** The game's day/night cycle. Each server runs its own 20-minute
clock, and at night hostile mobs spawn around every player and path-find
toward them. The edge1 log for the bad cell:

```
bot0 logged in ... at ([world]0.65, 62.0, 14.2)
Can't keep up! Is the server overloaded? Running 2558ms or 51 ticks behind
bot0 was shot by Skeleton
Can't keep up! Is the server overloaded? Running 13993ms or 279 ticks behind
bot0 was slain by Zombie
```

One bot at night put a 0.5-core server 14 s behind; the same bot, minutes
later by daylight, ran it at 10% CPU with p95 7 ms. The four clocks drift
independently, so whether a cell landed in day or night was chance - an
uncontrolled variable larger than the one being measured, and worst on the
smallest node, exactly where the knee is.

Ruled out on the way: bot positions (every bot's saved position is within
35 blocks of spawn on every node, so they are not wandering into unwarmed
terrain), entity build-up (`paper entity list * world` showed under 100
entities per world), and host memory (no server swap, 2.5-3 GB available).

**Fix.** `topology/world_rules.sh`: peaceful difficulty, permanent noon, no
weather, all non-player entities removed. `up.sh` runs it and `verify.sh`
fails if `doDaylightCycle` is not `false` or the difficulty is not peaceful.
The workload is now players only; the earlier replicates are kept as
`results/raw/grid1-daynight` and `grid2-daynight` and are not trained on.

**Why this matters beyond the testbed.** It is a real effect - mob AI is
server work that scales with players - but it is a second load source the
experiment does not control. Freezing it keeps "players" the only variable.

## 6.19 A whole replicate measured 2-3x slower, on an idle host

**Symptom.** The third grid replicate (`grid3`, morning of 2026-10-21) cost
two to three times the CPU per player on every node and every cell: edge1
with 20 players used 43.7% of a core where `grid1` and `grid2` used 14-15%,
and its p95 was 5.5 s instead of 8 ms. The knee moved from 50-60 players to
under 20. `verify.sh` passed.

**Ruled out, in order.** Host activity (re-probed with the host idle: still
42%); JVM age (the servers had run for 11 hours; a fresh `up.sh` and warm-up
gave 42.4%); new operator entries (bot0-bot99 were already ops in `grid1`);
bots wandering (all within 30 blocks of spawn); memory, swap and IO pressure
(all zero); CPU frequency caps (none, turbo on).

**Cause.** The laptop's power mode. `/var/log/tuned/tuned.log` shows
`throughput-performance` (GNOME's Performance mode) from 23:56 the night
before, then `balanced-battery` at 07:52 and `balanced` at 08:00: the charger
was unplugged briefly and GNOME left Performance mode, and plugging back in
does not restore it. A node capped at half a core runs in short bursts, so
under `balanced` the governor saw a mostly idle core and kept it at
0.8-2 GHz (5.3 GHz possible), and the same work took 2-3x the CPU time. The
same edge1 cell, minutes apart, one per mode: 42.4% vs 17.8%
(`results/raw/probe-balanced`, `probe-performance`).

It also explains `grid1-edge1-contended` (08 §8.6): `grid1` started at
23:43 in Balanced mode and the switch to Performance came 13 minutes in,
during the edge1 cells. It had been blamed on interactive use of the laptop.

**Fix.** Set Performance mode (GNOME menu, or without the GUI:
`gdbus call --system --dest org.freedesktop.UPower.PowerProfiles
--object-path /org/freedesktop/UPower/PowerProfiles --method
org.freedesktop.DBus.Properties.Set org.freedesktop.UPower.PowerProfiles
ActiveProfile "<'performance'>"`). `verify.sh` now fails unless
`tuned-adm active` reports `throughput-performance`, and every live run
records the mode in its `meta.json` and warns in its event log. The bad
replicate is kept as `results/raw/grid3-balanced`; `grid3` was re-measured.

**Why this matters beyond the testbed.** Nothing about the network, the
players or the server changed, and the smallest node's capacity fell
threefold. A latency formula cannot see it; a model fitted on measurements
taken in one mode is wrong in the other. It is the same blind spot the
project is about, found in the measurement rig itself.

## 6.20 Part of a replicate cost 1.3-1.6x the CPU, in Performance mode

**Symptom.** `grid4` (2026-10-21 17:54) passed `verify.sh`, power mode was
`throughput-performance` and the charger was in, yet edge1 used 20.2 / 33.6 /
41.1% CPU at 20 / 30 / 40 players against 14-15 / 21-22 / 30-31% in grids 1-3,
and edge2 54 / 96% at 60 / 80 against 41-47 / 74-78%. edge3 and cloud,
measured later in the same replicate, matched the earlier grids.

**Diagnosis.** Compare every cell's CPU at a fixed player count with the
earlier replicates (the median `cpu_percent` of `server.csv` rows at full
load). `top` during the run showed a browser at about 40% CPU and `kswapd0`
active, and analysis scripts (figures, deck builds) had been run during the
edge1 and edge2 cells. The servers sit on their own cores, but the client
generating the load and the host's memory do not.

**Fix.** The contended cells were moved to `results/raw/grid4-contended`
(kept as evidence) and edge1 and edge2 re-measured on an idle host with the
browser closed: `NODES="edge1 edge2" controller/grid.sh grid4`
(`grid.sh` now takes a `NODES` override). The re-measured edge1 is within
about 10-15% of grids 1-3, edge2 matches them. Rule: nothing heavier than a
text editor runs on the host while a grid, a deployment or a live run is
measuring, and each new replicate is checked cell by cell against the
earlier ones before it enters the dataset.

## 6.21 The live model learned from players logging in

**Symptom.** In two of three capacity-drop runs the live-corrected model
had already rated edge1 2.2-3.1 times slower than the grid before its CPU
was cut, and had moved almost every match off it, so those runs could not
show the cut being noticed.

**Diagnosis.** The cost factor `c` in `timeline.jsonl` jumped from 1.0 to
1.9 at t = 12 s, with only the first 10 players on edge1 and their p95 at
16-69 ms. A window was used 10 s after the node's load last changed, but a
match takes about 6 s to log in and its first 10-25 s are join spikes, so
the model learned from logins. Every later arrival landed on edge1 (the
nearest node) and repeated it.

**Fix.** The live model now learns only from windows at least 30 s after the
node's load last changed (`OBSERVE_SETTLE_S` in `live/controller.py`,
recorded as `observe_settle_s` in every run's `meta.json`). Shadow scoring
of every model still uses every 10 s window, so it stays comparable with the
earlier runs. Runs before the change are reported as their own versions
(`live/summarize.py` `label`): "first version" (no violation memory),
"before the settle rule", and the current one.

## 6.22 A night of runs on a host that had slowed down

**Symptom.** Live runs from 21:21 to 23:54 on 2026-10-21 (all four
controllers) and the third deployment round `place3` (23:54 - 00:20) were
worse than the same runs in the afternoon: queueing's median worst p95 0.8
and 1.1 s instead of 72-166 ms, edge1 at 40 players backlogged at 1.1-1.8 s.
`place3` repeats placements already measured twice, and the same
placements cost more CPU on every node: edge1 at 40 players 42-49% against
28-38% in `place1`, edge2 at 80 91-99% against 75-81%, edge3 at 40 36%
against 29-30%.

**Diagnosis.** `verify.sh` passed and the power mode was Performance in
every run. `top` afterwards showed a browser running (about 65 CPU-minutes)
and 5.2 GB of swap in use with 3.4 GB of memory available: the same
contention as 6.20, for hours. The servers have their own cores, but the
client that generates the load and the host's memory are shared.

**Fix.** The runs are kept as evidence in `results/live-contended/` and
`results/raw/place3-contended/` and are in no table. Clean results stay as
they were. Measure only with the browser closed and swap use low, and
compare a repeated cell's CPU with its earlier measurements before trusting
a new round.

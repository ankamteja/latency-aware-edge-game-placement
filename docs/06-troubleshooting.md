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

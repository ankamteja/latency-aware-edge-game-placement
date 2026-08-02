# 3. Every command, explained

A reference. Each command is one that actually appears in the project's
scripts, with every flag spelled out.

---

## 3.1 containerlab

### Deploy the lab

```bash
containerlab deploy -t edge-cloud.clab.yml --reconfigure
```
| Part | Meaning |
|---|---|
| `deploy` | read the topology, create containers and veth links |
| `-t <file>` | which topology file (`--topo`) |
| `--reconfigure` | destroy any existing lab of this name first, then deploy clean. Without it, deploying over a running lab errors out. |

Containers come up named `clab-<labname>-<nodename>`, e.g.
`clab-edgegame-edge`.

### Destroy the lab

```bash
containerlab destroy -t edge-cloud.clab.yml --cleanup
```
| Part | Meaning |
|---|---|
| `destroy` | stop and remove the containers and links |
| `--cleanup` | also delete the `clab-<labname>/` directory containing generated config |

### List running labs

```bash
containerlab inspect --all
```
Shows every lab on the machine, each node's kind, image, state and management
IP. Use it to confirm you are looking at the right lab - other labs on the same
host are unaffected by yours, but they do share the management bridge.

### Apply network impairment

```bash
containerlab tools netem set -n clab-edgegame-edge -i eth1 --delay 2.5ms
```
| Flag | Meaning |
|---|---|
| `-n` | node (container) to act on |
| `-i` | interface inside that node |
| `--delay` | hold outgoing packets this long |
| `--jitter` | random variation around the delay |
| `--loss` | drop this percentage of packets |
| `--rate` | cap throughput, in kbit |
| `--corruption` | flip a bit in this percentage of packets |

Applies to **egress only**. See [02-topology.md §2.5](02-topology.md).

```bash
containerlab tools netem show -n clab-edgegame-client
```
Prints the current impairment on every interface of that node.

---

## 3.2 Docker

### Inspect a container's configuration

```bash
docker inspect -f '{{.State.Status}}' clab-edgegame-edge
docker inspect -f '{{.HostConfig.CpusetCpus}}' clab-edgegame-edge
```
`-f` (`--format`) takes a Go template and prints one field instead of the whole
JSON blob. Useful fields: `.State.Status`, `.State.Health.Status`,
`.HostConfig.CpuQuota`, `.HostConfig.CpuPeriod`, `.HostConfig.CpusetCpus`,
`.HostConfig.Memory`, `.Mounts`.

Note `.HostConfig.NanoCpus` reads `0` here even though the CPU *is* limited -
containerlab expresses the limit as `CpuQuota`/`CpuPeriod` instead. Ask the
kernel rather than the daemon:

```bash
docker exec clab-edgegame-edge cat /sys/fs/cgroup/cpu.max
# -> 50000 100000    i.e. 50 ms of CPU time per 100 ms window = 0.5 core
```

### Run a command inside a container

```bash
docker exec clab-edgegame-edge rcon-cli list
docker exec -d clab-edgegame-client sh -c "node /bots/bot.js 20 10.0.1.2 > /out/x.csv 2>&1"
```
| Flag | Meaning |
|---|---|
| `-d` | detached - start it and return immediately. Used for the bots and probes, which must keep running while the driver does other things. |
| `-it` | interactive terminal - for poking around by hand, never in scripts |

`sh -c "..."` is needed whenever the command involves a redirect or a pipe:
without it, `>` would be interpreted by *your* shell on the host, not inside
the container.

### Live resource usage

```bash
docker stats --no-stream --format '{{.CPUPerc}},{{.MemUsage}}' clab-edgegame-edge
```
| Flag | Meaning |
|---|---|
| `--no-stream` | take one sample and exit, instead of refreshing forever |
| `--format` | print only the fields we want, comma separated |

**`CPUPerc` is scaled so 100% = one whole core.** A container capped at 0.5
reads about 50% when saturated; one capped at 4 can read up to 400%.

### Volumes

```bash
docker volume ls
docker run --rm -v <volume>:/src:ro -v "$PWD/dst":/dst alpine sh -c 'cp -a /src/. /dst/'
```
The second command is how `prepare.sh` copies the prepared server directory out
of a Docker named volume without needing root on the host: a throwaway
container mounts the volume and copies its contents to a bind-mounted host
directory.

| Part | Meaning |
|---|---|
| `--rm` | delete the container when it exits |
| `-v vol:/src:ro` | mount the named volume read-only, so the source cannot be damaged |
| `-v "$PWD/dst":/dst` | bind mount a host directory (absolute path required) |
| `cp -a /src/. /dst/` | `-a` preserves permissions and timestamps; the `/.` copies the *contents* rather than the directory itself |

### Logs

```bash
docker logs --tail 30 clab-edgegame-edge
docker logs -f clab-edgegame-edge
```
`--tail N` shows the last N lines, `-f` follows. Useful when a server refuses
to start.

**Do not use `docker logs | grep 'Done ('` to decide a server is ready.** With
a persistent data directory the log can contain a `Done (` line from a previous
boot and the check passes instantly against a server that is not up. Use a real
readiness probe instead (§3.4).

---

## 3.3 Linux networking inside the containers

```bash
ip addr add 10.0.1.1/30 dev eth1     # give the interface an address
ip link set eth1 up                  # bring the interface up
ip -4 addr show eth1                 # show IPv4 addresses on eth1
```
`/30` is a four-address subnet: network, two usable hosts, broadcast. Exactly
right for a point-to-point link, and it makes the routing table trivial - each
link is its own subnet, so the kernel already knows which interface to use.

```bash
tc qdisc show dev eth1
```
Prints the queueing discipline attached to the interface. After `netem.sh` it
shows `netem ... delay 2.5ms`. If it shows only `noqueue` or `pfifo_fast`, the
impairment is not there.

```bash
ping -c 20 -i 0.2 -q 10.0.1.2
```
| Flag | Meaning |
|---|---|
| `-c 20` | send 20 packets and stop |
| `-i 0.2` | 0.2 s between packets (intervals below 0.2 s need root) |
| `-q` | quiet - print only the summary line |
| `-D` | prefix each reply with a unix timestamp (used during collection so ICMP samples can be lined up with everything else) |
| `-n` | do not do reverse DNS on addresses |

The summary line is
`rtt min/avg/max/mdev = 5.051/5.113/5.186/0.038 ms`. `mdev` is mean deviation -
a jitter measure. Near zero means netem is delivering a very steady delay.

---

## 3.4 The Minecraft server

```bash
docker exec clab-edgegame-edge mc-monitor status --host 127.0.0.1
```
`mc-monitor` ships inside the `itzg/minecraft-server` image and speaks the
Minecraft server-list protocol. A zero exit status means the server has
finished loading the world and is accepting connections. This is the correct
readiness check - unlike a log grep, it cannot be fooled by an old log line.

```bash
docker exec clab-edgegame-edge rcon-cli list
docker exec clab-edgegame-edge rcon-cli mspt
docker exec clab-edgegame-edge rcon-cli tps
docker exec clab-edgegame-edge rcon-cli op bot0
```
`rcon-cli` is an admin console client, also bundled in the image. It reads the
password from `/data/.rcon-cli.env`, so no credentials appear on the command
line.

| Command | Output | Use |
|---|---|---|
| `list` | `There are 5 of a max of 100 players online: bot0, ...` | confirm the load is actually N, and that the previous run has fully disconnected |
| `mspt` | `Server tick times (avg/min/max) from last 5s, 10s, 1m: 22.2/3.8/95.9; ...` | the primary server-load signal. Above 50 ms means the server cannot hold 20 ticks per second. |
| `tps` | `TPS from last 1m, 5m, 15m: 13.82, 18.36, 19.42` | achieved tick rate; 20.0 is healthy |
| `op <name>` | grants operator | operators are exempt from the chat spam kick, which would otherwise remove chatting bots |

The output carries Minecraft colour codes - a section sign `§` followed by one
character. Strip them before parsing:

```bash
sed 's/\xc2\xa7.//g'          # section sign is UTF-8 c2 a7
sed 's/\x1b\[[0-9;]*m//g'     # and ANSI escape codes, for good measure
```

Forgetting this is a real, silent failure: an earlier analysis script matched
`/^(\d+) RTT: (\d+)/` against lines that actually began with an invisible ANSI
colour sequence, matched nothing, and returned `NaN` for every percentile.

---

## 3.5 The bots and probes

```bash
node bot.js 20 10.0.1.2 25565
```
20 bots against the edge node. Each prints CSV lines to stdout; the collector
redirects that to `bot.csv`. Usernames are `bot0`..`bot19`, which must be opped
server-side.

```bash
node probe.js 10.0.1.2 25565 1000
```
Host, port, and sample interval in milliseconds. Prints a TCP-handshake sample
and a server-status sample every second.

Both are stopped with:

```bash
pkill -f 'bot[.]js'
```
`-f` matches against the whole command line, not just the process name (which
would be `node`). **The brackets are load-bearing**: `pkill -f 'bot.js'` also
matches the `pkill` command's own command line, so the shell running it kills
itself. Writing `bot[.]js` matches the literal string `bot.js` but the pattern
text itself no longer matches, so `pkill` survives.

---

## 3.6 Bash idioms used in the scripts

```bash
set -euo pipefail
```
| Part | Effect |
|---|---|
| `-e` | exit immediately if any command fails |
| `-u` | error on use of an undefined variable (catches typos) |
| `-o pipefail` | a pipeline fails if *any* stage fails, not just the last |

```bash
cd "$(dirname "$0")"
```
Make the script work regardless of where it was called from, by moving to the
directory the script itself lives in.

```bash
date +%s%3N
```
Current time in milliseconds since the epoch. `%s` is seconds, `%3N` is the
first three digits of the nanoseconds field. Every measurement line is stamped
this way so the four streams can be lined up afterwards.

```bash
for target in ${TARGETS//,/ }; do
```
`${VAR//a/b}` replaces every `a` with `b`. Turning `edge,cloud` into
`edge cloud` lets the `for` loop split it into words.

```bash
sample_server edge out.csv &
SAMPLER=$!
...
kill "$SAMPLER"
```
`&` runs it in the background, `$!` is the PID of that background job, and
`kill` stops it later. This is how the server sampler runs concurrently with
the load.

```bash
grep -c ',kicked' bot.csv 2>/dev/null || true
```
`grep -c` counts matching lines but **exits non-zero when the count is zero**,
which under `set -e` would abort the script. The `|| true` makes "no kicks" a
success. (An earlier version used `|| echo 0` and printed a stray `0`, because
`grep -c` had already printed its own `0` before failing.)

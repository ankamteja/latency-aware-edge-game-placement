# 2. The topology

What the testbed is, why it looks like this, and what every line of
`topology/edge-cloud.clab.yml` does.

---

## 2.1 The shape

```
                          netem 2.5 ms each way          cpu.max = 0.5 core
   ┌────────┐  eth1   ┌───────────────────────┐  eth1   ┌──────────────┐
   │        ├─────────┤   10.0.1.0/30 link    ├─────────┤  edge  .1.2  │
   │ client │         └───────────────────────┘         └──────────────┘
   │        │
   │  bots  │  eth2   ┌───────────────────────┐  eth1   ┌──────────────┐
   │ probes ├─────────┤   10.0.2.0/30 link    ├─────────┤ cloud  .2.2  │
   └────────┘         └───────────────────────┘         └──────────────┘
                          netem 20 ms each way            cpu.max = 4 cores
```

Three nodes, two point-to-point links, and that is the whole experiment.

| Node | Role | CPU | Network distance |
|---|---|---|---|
| `client` | runs the bots and the probes | uncapped, pinned to cores 8-23 | - |
| `edge` | the near, small server | 0.5 core, cores 0-1 | 5 ms RTT |
| `cloud` | the far, large server | 4 cores, cores 2-7 | 40 ms RTT |

**Pointing the bots at `10.0.1.2` instead of `10.0.2.2` *is* the placement
decision.** Everything downstream is measuring the consequence of that choice.

---

## 2.2 Why these particular numbers

These are **design parameters, chosen before any data was collected**, not
values discovered from results. Stating that plainly matters, because "edge is
small and near, cloud is big and far" is precisely the premise the experiment
is built to test - so it has to be declared as a premise.

- **edge = 0.5 core.** An edge site is a cheap box in a cabinet with a power
  and cooling budget. Small is the defining property of an edge node; if it
  were large there would be no placement problem.
- **cloud = 4 cores.** A regional datacentre has compute to spare. What it does
  not have is proximity.
- **5 ms vs 40 ms RTT.** Roughly a metro-area hop versus a cross-country one.
  The 35 ms gap is the *entire budget the analytical model thinks it is
  saving* by choosing edge. The interesting question is at what player count
  the edge's queueing delay eats more than 35 ms - at that point the model's
  ranking is inverted and it is picking the wrong node.
- **Load grid stops at 40 bots** because `bot0`..`bot39` are the usernames
  opped in the prepared server data. More bots means opping more usernames.

The two servers are otherwise identical: same jar, same world, same config,
copied from the same source. CPU and network delay are the only differences.

---

## 2.3 The topology file, line by line

`topology/edge-cloud.clab.yml`

```yaml
name: edgegame
```
The lab name. containerlab prefixes every container with it, so the nodes
become `clab-edgegame-client`, `clab-edgegame-edge`, `clab-edgegame-cloud`.
Every script refers to nodes by those full names.

```yaml
topology:
  nodes:
    client:
      kind: linux
      image: edgegame-client:1
```
`kind: linux` means "an ordinary container, do not try to configure it as a
router". `image` is built by `up.sh` from `Dockerfile.client` - the stock Node
image has no `ip` and no `ping`, and we need both.

```yaml
      cpu-set: "8-23"
```
Pins the load generator to host cores 8-23. The servers are pinned to 0-1 and
2-7. Disjoint sets, so the instrument cannot compete for CPU with the thing it
measures. This does not remove the shared-host caveat entirely (memory
bandwidth and caches are still shared) but it removes the largest part of it.

```yaml
      cmd: sleep infinity
```
The Node image would otherwise start a REPL and exit. We want an idle container
we can `docker exec` into.

```yaml
      binds:
        - ../bots:/bots
        - ./out:/out
```
Bind mounts: a host directory appearing inside the container. Paths are
relative to the topology file. `../bots` gives the container `bot.js`,
`probe.js` and the already-installed `node_modules`; `./out` is where the
container writes its measurements so the host can read them.

```yaml
      exec:
        - ip addr add 10.0.1.1/30 dev eth1
        - ip link set eth1 up
```
containerlab wires the veth cable but does not assign addresses on the data
plane, so we do it ourselves after boot. `/30` is a 4-address subnet - two
usable addresses, exactly enough for a point-to-point link. Each link is its
own subnet, so the client's routing table sends `10.0.1.2` out `eth1` and
`10.0.2.2` out `eth2` with no routing configuration at all.

```yaml
    edge:
      image: itzg/minecraft-server
      cpu: 0.5
      cpu-set: "0-1"
      memory: 2G
```
`cpu: 0.5` becomes the CFS quota described in
[01-concepts.md §1.8](01-concepts.md). **Verify it applied rather than trusting
it** - see §2.6.

```yaml
      env:
        EULA: "TRUE"
        ONLINE_MODE: "FALSE"
        TYPE: CUSTOM
        CUSTOM_SERVER: /data/paper-1.21.4-232.jar
        MEMORY: 1G
```
- `EULA` - the server refuses to start without it.
- `ONLINE_MODE: FALSE` - do not check logins against Mojang's auth servers. The
  bots have no accounts, so this is mandatory.
- `TYPE: CUSTOM` + `CUSTOM_SERVER` - run this exact jar. The default
  (`TYPE: PAPER`) contacts `api.papermc.io` on *every* start to check for
  updates, and a single network hiccup then stops the whole testbed booting.
  This happened; see [06-troubleshooting.md](06-troubleshooting.md).
- `MEMORY: 1G` - the Java heap, separate from the container's `memory: 2G`
  limit. The heap must stay comfortably below the container limit or the kernel
  kills the process instead of Java garbage-collecting.

```yaml
  links:
    - endpoints: ["client:eth1", "edge:eth1"]
    - endpoints: ["client:eth2", "cloud:eth1"]
```
Two veth pairs. This is the cabling.

---

## 2.4 Bringing it up

```bash
cd topology
./prepare.sh     # build the two server data directories (only needed once)
./up.sh          # build image, deploy, wait for both servers, apply netem, verify
```

`./up.sh` accepts the two RTT targets: `./up.sh 5 40` is the default,
`./up.sh 10 60` would make the paths further apart.

Tear down with `./down.sh`, or `./down.sh --clean` to also delete the ~500 MB
of server data.

### What `prepare.sh` is for

A Minecraft server needs a jar, a generated world and about thirty config
files. Generating a world on a node capped at 0.5 CPU takes minutes and can
trip the server's own "can't keep up" watchdog. So instead of generating, we
**copy a known-good server directory** - the one left over from the earlier
single-node experiments, still sitting in a Docker volume - into
`topology/nodes/edge` and `topology/nodes/cloud`.

That copied directory already carries the settings the experiment needs:

| Setting | Value | Why |
|---|---|---|
| `max-players` | 100 | the default 20 would cap the load grid |
| `connection-throttle` (bukkit.yml) | -1 | the default 4000 ms rejects staggered bot joins |
| `online-mode` | false | bots have no Mojang accounts |
| `enable-rcon` | true | how the collector reads MSPT/TPS/player count |
| ops.json | bot0..bot39 | operators are exempt from the chat spam kick |

`topology/nodes/` is git-ignored (255 MB per node). `prepare.sh` rebuilds it.

---

## 2.5 Applying the network distance

`topology/netem.sh` attaches a netem qdisc to **both ends** of each link, each
carrying half the target RTT:

```
client:eth1  2.5ms  ─────  2.5ms  edge:eth1     => ~5 ms RTT
client:eth2   20ms  ─────   20ms  cloud:eth1    => ~40 ms RTT
```

Both ends, because netem only delays packets *leaving* an interface - a
one-sided rule gives a one-way delay and therefore half the RTT you wanted.

It is applied through containerlab rather than by running `tc` inside the
containers:

```bash
containerlab tools netem set -n clab-edgegame-edge -i eth1 --delay 2.5ms
```

`netem set` also takes `--jitter`, `--loss`, `--rate` and `--corruption`. Only
`--delay` is used so far; the rest are the obvious next knobs to turn once
delay alone has been characterised.

---

## 2.6 Verification is not optional

`topology/verify.sh` runs before every collection and refuses to continue if
anything is off. Each check exists because the corresponding failure produces
**plausible-looking but worthless data**:

| Check | What it catches | Why it is silent otherwise |
|---|---|---|
| containers running | a crashed server | bots simply collect nothing |
| `cpu.max` read from the kernel | a CPU cap that did not apply | the "edge" node quietly has all 28 host cores and the load effect vanishes - the results table just looks flat |
| data-plane addresses | traffic escaping via the management interface | every path measures the same, near and far look identical |
| netem qdisc present | delay never attached | same as above |
| **measured ping RTT** | configured delay differing from delivered delay | you would quote a number you never observed |
| server answering | server up but not accepting players | zero samples |
| zero players online | leftovers from the previous cell | the load is not N, and reused usernames get kicked as `duplicate_login` |

A real example of why the CPU check reads the kernel and not the YAML: this
project's first deployment looked entirely healthy, but

```
docker inspect ... --format '{{.HostConfig.NanoCpus}}'   ->  0
```

containerlab sets the limit through `CpuQuota`/`CpuPeriod`, not `NanoCpus`, so
the obvious check reports "no limit" on a container that is in fact correctly
limited. Reading `/sys/fs/cgroup/cpu.max` from inside the container asks the
kernel what is actually enforced, which is the only answer that matters.

### Verified state of the testbed

```
edge  cpu.max = 50000 100000   (0.50 cores)   cpuset 0-1
cloud cpu.max = 400000 100000  (4.00 cores)   cpuset 2-7
edge  ping min/avg/max/mdev = 5.051/5.113/5.186/0.038 ms, 0% loss
cloud ping min/avg/max/mdev = 40.081/40.144/40.331/0.059 ms, 0% loss
```

Measured RTT is within 0.4% of both targets, with a standard deviation under
0.1 ms. **5.11 ms and 40.14 ms are the numbers that belong in the write-up**,
not 5 and 40.

---

## 2.7 Known limits of this testbed

- **One physical host.** Bots, both servers and the emulated network all share
  one machine's memory bandwidth and caches. Core pinning removes the CPU part
  of that contention but not all of it. The probe ladder in
  [04-metrics.md](04-metrics.md) exists partly to bound how much this matters:
  if ICMP RTT stays flat while in-game RTT explodes, the explosion is not the
  load generator.
- **netem delay is constant.** No jitter, no loss, no bandwidth cap yet. Real
  paths have all three.
- **Two nodes, one client.** Enough to test the ranking between two candidates,
  not enough for a placement algorithm choosing among many.
- **The world is identical on both nodes and the bots all spawn together**, so
  chunk loading is concentrated in one area. That is a harsher load than
  players spread across a map - consistent across cells, but not general.

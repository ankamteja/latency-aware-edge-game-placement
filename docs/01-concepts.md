# 1. Concepts

Everything you need to understand before reading any other file. No prior
knowledge assumed.

---

## 1.1 The problem in one picture

A maps app that knows road distance but cannot see traffic:

- Restaurant A is 2 km away. The app says "obviously go here". It is through a
  traffic jam. Real journey: 50 minutes.
- Restaurant B is 20 km away. The app says "too far". Empty highway. Real
  journey: 15 minutes.

The app picked wrong, confidently, because one of the two things that decide
journey time is invisible to it.

Now swap the words:

| Maps app | This project |
|---|---|
| Restaurant A - close, jammed | Edge server - close, weak CPU, crowded |
| Restaurant B - far, empty | Cloud server - far, strong CPU, idle |
| Traffic | Server load |
| Distance-only routing | The analytical latency formula |
| Journey time | End-to-end player latency |

The formula that edge placement algorithms use is:

```
latency = propagation_delay + data_size / bandwidth
```

`propagation_delay` is distance. `data_size / bandwidth` is transmission time.
There is no term anywhere in it for *how busy the server is*. That is the
missing term this project measures.

---

## 1.2 Latency and RTT

**Latency** is how long something takes to arrive.

**RTT** (round-trip time) is how long a message takes to go to the server and
come back. It is what you can actually measure from one machine, because you
only need one clock: note the time, send, wait for the reply, note the time
again, subtract. Measuring one-way delay properly needs two clocks that agree
with each other to sub-millisecond precision, which is hard. So everything in
this project is RTT.

For a game, RTT is what a player feels. You press forward, the server decides
where you actually ended up, and the screen updates. If that loop takes 200 ms,
the game feels broken, no matter what caused the 200 ms.

**Where RTT comes from** - four places, and only the first two are in the
analytical formula:

1. **Propagation** - the signal physically travelling. Fixed by distance.
   Roughly 5 microseconds per km of fibre. Nothing can reduce it.
2. **Transmission** - pushing the bits onto the wire. `size / bandwidth`.
3. **Network queueing** - packets waiting in router buffers.
4. **Server-side processing and queueing** - the server has to actually *do*
   something with the request, and if it is busy the request waits its turn.

Item 4 is the whole subject of this project.

---

## 1.3 Queueing delay, and why it is not gentle

A queue at one counter. If customers arrive slower than the clerk serves them,
nobody waits long. As the arrival rate creeps up toward the service rate, the
wait does not grow gently - it explodes. The standard result from queueing
theory:

```
average wait  is proportional to  1 / (1 - utilization)
```

where utilization is "fraction of capacity in use", 0 to 1.

| Utilization | 1/(1-u) | Meaning |
|---|---|---|
| 0.50 | 2 | fine |
| 0.80 | 5 | noticeable |
| 0.90 | 10 | bad |
| 0.95 | 20 | unusable |
| 0.99 | 100 | falling over |

Two consequences that shape this entire project:

- **The curve is flat then vertical.** A node at 50% load and a node at 80%
  load look almost the same. A node at 95% is a completely different machine.
  You cannot see this coming from a linear model.
- **It is why cloud people rarely notice.** In a datacentre you autoscale long
  before 90%. At the edge you *cannot* - the edge site is one small box, there
  is nothing to scale out to. So the queueing term that stays hidden in the
  cloud becomes the dominant term at the edge.

---

## 1.4 Averages lie: p50, p95, p99

Sort every measurement from smallest to largest. The **pNN** value is the one
NN% of the way along.

- **p50** (median) - half the samples are faster than this.
- **p95** - 95% are faster; 1 in 20 is worse than this.
- **p99** - 99% are faster; 1 in 100 is worse than this.

Example, 100 samples: ninety at 5 ms, ten at 500 ms.

```
mean = 54.5 ms   -> sounds okay-ish
p50  = 5 ms      -> sounds great
p95  = 500 ms    -> the truth
```

For a game, the mean is close to meaningless. A player who stutters once every
twenty seconds quits. So **the tail is the metric**, and every result in this
project is reported as p50/p95/p99/max, never as a bare average.

This also matters for the argument: server load barely moves the median but
moves the tail enormously. A model that only predicts an average would miss the
effect even if it *did* know about load.

---

## 1.5 Emulation vs simulation

- **Simulation** - a program that pretends. You write the maths for how a
  network and a server behave, and the program plays out that maths. Fast, but
  it can only tell you what your own assumptions imply.
- **Emulation** - a real but small system. Real Linux kernels, real TCP, real
  packets, real server software, artificially constrained. Slow, but it can
  surprise you.

This distinction is the reason the project exists. Placement research is
evaluated almost entirely in simulators (iFogSim, EdgeCloudSim, YAFS,
PureEdgeSim), and those simulators model latency with the same load-blind
formula that the placement algorithm uses. The algorithm is graded by the same
assumption it is built on, so the error can never appear. Emulation breaks that
loop: the server is real, so it can be slow for reasons nobody modelled.

In this testbed exactly one thing is fake - the network delay, which is
injected with netem. Everything else is genuine.

---

## 1.6 Containers, containerlab, and the network plumbing

**Container** - a process on your machine with its own filesystem, its own
process list, and its own network stack (interfaces, addresses, routing table,
firewall). It is not a virtual machine; it shares the host kernel. That is why
it is cheap enough to run a whole network of them on a laptop.

**veth pair** - a virtual Ethernet cable. Two interfaces created together;
anything sent into one comes out of the other. Put one end inside container A
and the other inside container B, and they are cabled together.

**containerlab** (`containerlab` / `clab`) - a tool that reads a YAML file
describing nodes and links, starts the containers, and creates the veth pairs
between them. It is normally used for network-equipment labs; here it is doing
the same job for an edge-cloud topology.

Every containerlab node ends up with two kinds of interface:

- `eth0` - the **management** interface, on a normal Docker bridge. This is how
  `docker exec` and image pulls work. **No experiment traffic uses it.**
- `eth1`, `eth2`, ... - the **data plane**, the veth links you declared. All
  measured traffic goes here, and this is where the emulated delay lives.

Mixing these up is the classic way to accidentally measure nothing: if the bots
dial the management IP, the packets never touch the emulated links and every
"near" and "far" result comes back identical.

---

## 1.7 netem: the one fake thing

**tc** (traffic control) is the Linux subsystem that decides how packets leave
an interface. A **qdisc** (queueing discipline) is the algorithm it uses.
**netem** is a qdisc that holds each outgoing packet for a set time before
releasing it, and can also add jitter, loss, reordering and a rate cap.

Two things about netem that will bite you if you forget them:

1. **It only affects packets leaving the interface it is attached to.** Attach
   it to one side of a link and you have delayed one direction only. To get a
   symmetric round trip, attach half the target RTT to *each* end. That is
   exactly what `topology/netem.sh` does.
2. **Configured delay is an intention, not a fact.** Always measure the
   resulting RTT with `ping` and use the measured number in the write-up.
   `topology/verify.sh` does this on every run.

---

## 1.8 How the server's capacity is limited (and what a "core" is worth)

**cgroups** are the kernel feature that limits what a group of processes may
consume. For CPU, cgroup v2 exposes a single file:

```
/sys/fs/cgroup/cpu.max     ->     "50000 100000"
                                     |      |
                                     |      +-- period, microseconds
                                     +--------- quota, microseconds
```

Read it as: *the processes in this container may use 50000 microseconds of CPU
time in every 100000 microsecond window*. 50 ms out of every 100 ms = 0.5 of a
CPU. The value `max` means no limit at all.

This is a **time budget, not a pinned core**. A container with `0.5` can run on
any core, or briefly on several at once; it just cannot accumulate more than
50 ms of CPU time per 100 ms. When it runs out it is *throttled* - descheduled
until the next window opens. That throttling is a large part of where the
latency tail comes from.

`docker stats` reports CPU as a percentage where **100% = one full core**. So a
container capped at 0.5 pinned at the limit reads ~50%, and a container capped
at 4 could read up to 400%.

**cpuset** is a different knob: it says *which* cores the container may run on.
In this testbed the edge node, the cloud node and the load generator are each
pinned to disjoint core ranges, so the measuring instrument cannot steal CPU
from the thing it is measuring.

**Caution on portability.** "0.5 CPU" is not a portable unit of capacity.
Half a core of a fast laptop CPU does far more work per second than half a core
of a small edge box. So capacity should eventually be expressed as
*utilization* (0 to 1 of whatever that node can do), which is the quantity the
`1/(1-u)` law is written in, or measured directly through a
hardware-independent signal like MSPT (next section).

---

## 1.9 Minecraft server internals worth knowing

The game server is not a web server, and the difference is what makes it a good
subject.

- **Tick** - the server advances the whole world in discrete steps, 20 times a
  second. Everything - physics, mobs, player movement, chat - happens inside a
  tick, on **one main thread**.
- **Tick budget** - 1 second / 20 = **50 ms**. A tick must finish inside 50 ms
  or the server falls behind.
- **MSPT** (milliseconds per tick) - how long ticks are actually taking. Under
  50 ms is healthy. Over 50 ms means the server cannot keep up, and every
  player action queues behind the overrun.
- **TPS** (ticks per second) - the achieved rate. 20.0 is healthy; anything
  lower means ticks are being dropped.

Why this matters: **MSPT is a hardware-independent load signal.** The 50 ms
budget comes from the game's design, not from the CPU. A node whose MSPT is
60 ms is in trouble whether it is a laptop or a Raspberry Pi. That makes MSPT
the natural feature for a load-aware latency model that has to work across
heterogeneous nodes.

- **rcon** - a small admin protocol over TCP. It lets us ask the running server
  questions from outside (`list`, `mspt`, `tps`) without touching the game.
- **Paper** - a performance-oriented build of the Minecraft server. Used here
  because it exposes `/mspt` and `/tps`.

---

## 1.10 The bots

**mineflayer** is a Node.js library that speaks the Minecraft protocol. A bot
is a real client: it logs in, receives chunks, sends movement packets. The
server cannot tell it apart from a person, which is the point - the load is
genuine, not synthetic packets.

Each bot does two jobs:

- **load**: walks and turns continuously, forcing movement, collision and chunk
  work every tick;
- **measurement**: once a second it sends a chat message containing the current
  timestamp and waits for the server to echo it back. That round trip must be
  handled by the main game thread, so it contains the server-side queueing
  delay. Subtract the sent timestamp from the arrival time and you have the
  in-game RTT.

Bots must be **opped** (given operator status) or the vanilla anti-spam filter
kicks them for chatting once a second. The prepared server data has `bot0`
through `bot39` already opped, which is why the load grid stops at 40.

---

## 1.11 Vocabulary quick reference

| Term | Meaning |
|---|---|
| Service placement | Deciding which node a service runs on |
| Analytical model | A closed-form formula that *predicts* latency. Blind to load. |
| Rank inversion | The option the model ranked best turns out to be the worst. The result this project is hunting. |
| Utilization | Fraction of a node's capacity in use, 0 to 1 |
| Tail latency | p95/p99/max, as opposed to mean or median |
| netem | Linux qdisc that injects delay. The only fake thing here. |
| cgroup / CFS quota | Kernel mechanism that caps CPU time |
| MSPT / TPS | Milliseconds per tick / ticks per second. The server's own load counters. |
| rcon | Remote admin console for the Minecraft server |
| Data plane | The emulated links (`eth1`, `eth2`). Where measured traffic goes. |
| Management plane | `eth0`. Control only, never measured. |

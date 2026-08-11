# 7. Capacity, and why utilization is the unit that travels

Everything else in this project measures *latency*. This chapter measures
*capacity* — how much load a node can absorb before latency starts to matter —
because without it none of the other numbers can be compared across nodes.

---

## 7.1 The problem with "0.5 core"

The testbed caps `edge1` at half a CPU. That is a precise statement about this
laptop and almost meaningless anywhere else: half a core of an i7-14700HX does
far more work per second than half a core of a small edge box. A curve plotted
against *CPU quota* only describes the machine it was measured on.

The unit that travels is **utilization** — the fraction of a node's own
capacity currently in use, 0 to 1. It is also the unit the queueing law is
written in:

```
queueing delay  is proportional to  1 / (1 - utilization)
```

At u = 0.5 the factor is 2. At u = 0.9 it is 10. At u = 0.99 it is 100. Two
nodes at the same utilization sit at the same point on that curve regardless of
how fast their CPUs are — which is exactly the property a placement model needs
if it is going to rank heterogeneous nodes.

To divide by capacity, you first have to measure capacity. That is what
`controller/capacity.sh` does, and it is why it runs before anything else.

---

## 7.2 The threshold is the game's, not the hardware's

A Minecraft server advances the world in discrete **ticks**, 20 times a second.
That gives every tick a budget of

```
1 second / 20 = 50 ms
```

MSPT (milliseconds per tick) is how long ticks actually take. Under 50 ms the
server is keeping up. Over 50 ms it is falling behind, and every player action
queues behind the overrun.

The important part: **50 ms comes from the game's design, not from the CPU.**
A node whose MSPT is 60 ms is in trouble whether it is a laptop, a Raspberry Pi
or a rack server. That makes "players held before MSPT exceeds 50 ms" —
call it **N_max** — a capacity number that means the same thing everywhere, and
`players / N_max` a utilization estimate that is comparable across nodes.

---

## 7.3 How the measurement works

```bash
cd controller
./warmup.sh              # REQUIRED first - see §7.6
./capacity.sh            # all nodes
./capacity.sh --targets edge1 --levels 8,16,24,32,40,50,60 --hold 60
```

For each node, `capacity.sh` ramps the player count through a ladder. At each
level it:

1. stops any previous load and waits until the server reports **zero** players,
2. settles for 15 s, joins N bots, waits out the staggered join,
3. samples the **5-second average MSPT** every 5 s for the hold window,
4. takes the median of those samples,
5. stops at the first level whose median exceeds 50 ms.

`N_max` is the last level the node *did* hold. The first level it failed is
recorded too, so the knee is bracketed rather than guessed.

Only server-side counters are recorded. Latency curves are the collector's job;
this script exists to produce the denominator.

### Parsing MSPT is fiddlier than it looks

The server's `/mspt` output needs three separate pieces of cleanup before a
number falls out:

```
1. it is drenched in ANSI colour codes            -> strip them
2. it spans TWO lines, header then values         -> join the lines first
3. the label "1m:" itself contains a digit        -> cut at the label, do not
                                                     grab "the first number"
```

Cleaned and joined it reads:

```
Server tick times (avg/min/max) from last 5s, 10s, 1m: 22.2/3.8/95.9, ...
```

and the first triple is the 5-second window. The one-liner that survives all
three:

```bash
docker exec clab-edgegame-edge1 rcon-cli mspt \
  | sed -e 's/\x1b\[[0-9;]*m//g' -e 's/\xc2\xa7.//g' | tr -d '\r' | tr -d '\n' \
  | sed 's/.*1m:[^0-9]*//' | grep -oE '^[0-9.]+'
```

---

## 7.4 Results

Measured 2026-08-11 on warm worlds, 60 s per level.

| node | CPU quota | N_max | MSPT at N_max | first breach |
|---|---|---|---|---|
| `edge1` | 0.5 core | **50** | 44.5 ms | 60 players → 69.1 ms |
| `edge2` | 1 core | **100** | 44.7 ms | none at ≤ 100 |
| `edge3` | 2 cores | > 100 | 11.1 ms | none at ≤ 100 |
| `cloud` | 4 cores | > 100 | 9.3 ms | none at ≤ 100 |

The full ladders are in `results/raw/capacity/<node>.csv`. `edge1`:

| players | 8 | 16 | 24 | 32 | 40 | 50 | 60 |
|---|---|---|---|---|---|---|---|
| MSPT (ms) | 6.9 | 8.9 | 9.8 | 11.8 | 16.5 | 44.5 | **69.1** |
| CPU % | 26 | 34 | 39 | 44 | 47 | 50 | 50 |

Three things worth reading off this:

- **The shape is flat, then vertical.** Going from 8 to 40 players — a 5×
  increase in load — moves tick time by under 10 ms. Going from 40 to 60 moves
  it by 52 ms. This is `1/(1 − u)` behaviour, and it is why a linear or
  closed-form model fitted to the comfortable region predicts nothing useful
  about the region that actually matters.
- **The knee is where the CPU cap is.** `edge1` reaches 50% — one half of one
  core, exactly its quota — between 40 and 50 players, and that is precisely
  where MSPT turns. Cause and effect, recorded side by side.
- **Capacity scales roughly linearly with CPU**: about **100 players per core**
  for this workload. `edge1` at 0.5 core holds 50; `edge2` at 1 core holds 100.

### The ceiling is ours, not theirs

`edge3` and `cloud` never breached. That is a limit of the testbed, not a
property of those nodes:

- `server.properties` sets `max-players=100`;
- only `bot0`..`bot99` are opped, and un-opped bots get removed by the chat
  spam filter;
- the load generator and four servers share one 16 GB host, which is already
  the binding constraint.

So their entries read "> 100" and should be quoted that way. The
100-players-per-core relationship suggests ~200 and ~400 respectively, but that
is extrapolation and is not claimed as measured.

---

## 7.5 Turning a player count into utilization

```
utilization ≈ players / N_max
```

30 players on `edge1` is u ≈ 0.60. The same 30 players on `edge2` is u ≈ 0.30,
and on `cloud` below 0.10. Same offered load, three very different places on
the queueing curve — which is the whole point: **a placement model that ranks
by distance sees these three as identical, and they are not.**

A second, continuous estimate is available for free in every collection run,
and does not depend on having found a knee at all:

```
utilization ≈ container CPU% / (100 × cores)
```

`docker stats` reports CPU where 100% is one full core, so a 4-core node
reading 240% is at u = 0.60. This is the better feature for a model, because it
is sampled every 5 seconds throughout a run rather than being one number per
node.

---

## 7.6 Warm the world first, or measure the wrong thing

**`capacity.sh` results are meaningless on a cold world.** Every node boots from
a copy of the same server directory, whose world is only generated where an
earlier session actually walked. The first bots to head outward make the server
*generate* terrain, which costs far more than simulating an existing chunk.

Same node, same 5 players, same window:

| | p50 | p95 | CPU % | MSPT |
|---|---|---|---|---|
| cold world | 43 ms | 474 ms | 50 (capped) | 66.0 ms |
| warm world | 7 ms | 60 ms | 21 | 5.1 ms |

A cold node looks saturated when it is merely busy, and the error lands hardest
on the weakest node — the one the conclusion depends on. Run `./warmup.sh`
first. Details in [06-troubleshooting.md §6.2b](06-troubleshooting.md).

---

## 7.7 What this does not establish

- **Single run per level.** No variance estimate; the knee is bracketed to
  within one ladder step, not measured with error bars.
- **One workload.** Bots walk and turn continuously and are clustered near
  spawn. Real players spread across a map and do more varied work, so `N_max`
  is specific to this load pattern.
- **Capacity was configured, then measured.** The 0.5 / 1 / 2 / 4 ladder is a
  design parameter we chose. What is measured is the *response* to it.
- **The strong nodes were never pushed to their knee**, so the
  100-players-per-core figure rests on two points, not four.

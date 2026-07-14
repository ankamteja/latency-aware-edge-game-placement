# Load sweep: RTT vs bot count at zero network distance

Follow-up to [derisk.md](derisk.md). Same idea, more points: one server on
localhost, network distance fixed at zero, only the bot count changes. The
analytical model (`latency = propagation + size/bandwidth`) predicts an
identical RTT for every row below, because nothing on its right-hand side
moves. Everything that does move is server-side queueing.

## Setup

- Paper 1.21.4 (`itzg/minecraft-server`), `--cpus=0.5`, localhost
- Server booted from the cached jar via `TYPE=CUSTOM` /
  `CUSTOM_SERVER=/data/paper-1.21.4-232.jar` — `papermc.io` was returning
  connection resets, and the default PAPER type re-checks the download API on
  every start. CUSTOM runs the existing jar with no network dependency.
- `connection-throttle: -1`, `max-players=100`, bots `bot0..bot39` opped
  (spam-kick exemption), all carried over on the same `/data` volume.
- Each run is gated on `rcon list` reporting **0** players before it starts, so
  a previous run's sessions can't linger and trigger
  `multiplayer.disconnect.duplicate_login` on reused usernames. Concurrent
  player count is sampled mid-run to confirm the load actually held at N.
- First 5 samples per bot discarded (cold start). RTT = chat echo round-trip
  per bot (`bots/bot.js`).

## Results (2026-07-14)

| N bots | samples | kicks | players held | median | mean | p95 | p99 | max | container CPU |
|---|---|---|---|---|---|---|---|---|---|
| 1  | 62   | 0 | 1  | 2  | 6  | 15  | 81   | 81   | 14–50% |
| 5  | 435  | 0 | 5  | 3  | 9  | 51  | 75   | 133  | 20–51% |
| 10 | 796  | 0 | 10 | 3  | 29 | 54  | 929* | 1306*| ~26%   |
| 20 | 1509 | 0 | 20 | 4  | 15 | 63  | 274  | 603  | ~38%   |
| 30 | 2181 | 0 | 30 | 8  | 25 | 95  | 398  | 704  | 40–47% |
| 40 | 3029 | 0 | 40 | 40 | 69 | 224 | 583  | 1241 | ~50% (capped) |

All times in ms. `players held` is the live server-reported count during the
run — the load was sustained at N in every row, no dropouts.

## Reading it

- **Median** climbs 2 → 40 ms (≈20×) and **p95** climbs 15 → 224 ms (≈15×) as
  bot count goes 1 → 40. Both are monotonic. The analytical model's prediction
  is a flat line across this whole range.
- The damage is worst in the tail — the metric that matters for placement is
  the worst player, not the average one.
- **CPU** pins at the 0.5-core cap (49.8–50.2%) at N=40. The server is
  compute-starved exactly where RTT blows up, which is the causal link: no
  spare CPU → ticks run long → actions queue → RTT rises. Nothing here is
  visible to a model that only knows distance and bandwidth.

## Caveats

- `*` N=10 tail is non-monotonic (p99 929, max 1306 — above N=20). This is a
  transient: 38 of 796 samples (~5%) landed in a single 400–1300 ms burst,
  i.e. one multi-second server hitch that hit all 10 bots at once, not a steady
  state. Median and p95 for N=10 sit on the trend; the tail for that one run
  caught a stall. Worth a re-run to confirm, but it does not change the
  direction of the curve.
- Bots and server share one host. Some fraction of the tail could be
  client-side scheduling on the load generator rather than server queueing.
  Isolating this needs a concurrent network-only probe (probe RTT), which
  `bot.js` does not yet emit — the next real gap to close.

## Conclusion

Confirms and extends the de-risk result across a full load sweep: at fixed
(zero) network distance, tail RTT grows ~15× while the analytical model's
prediction stays constant. This is the first evidence for the claim in the
README's Positioning section — that the term placement models omit (measured
load→latency) is not a rounding error but the dominant one under load: p95 up
~15×, and container CPU pinned at the 0.5-core cap exactly where it explodes,
which is the causal link (no spare compute → ticks run long → actions queue).

Scope, stated precisely. This proves the model is *incomplete* — it omits a
term that moves latency by ~15× at a single node. It does **not** yet prove the
model picks the *wrong node*: that needs two nodes where the model ranks
near-and-loaded above far-and-idle while measured RTT ranks them the other way
(the crossover). And it does not yet isolate how much of the tail is server
queueing versus load-generator contention, since bot and server share a host —
that needs the concurrent probe-RTT baseline. Both are the remaining work
before the wrong-node claim can be made.

# 9. The live controller and its dashboard

Chapters 1 to 8 measure the testbed and grade three latency models. This one
closes the loop: a controller reads the testbed in real time, asks a latency
model where each match should be, moves matches between nodes, and a
dashboard shows every step as it happens. It is a digital twin in the
practical sense: a live model of the four nodes, fed by measurements every
two seconds, that the controller acts on.

![workflow](diagrams/workflow.svg)

---

## 9.1 What runs

```
live/
  testbed.py    start and stop matches, read server counters, tail latency CSVs
  policy.py     where a match should be, according to one latency model
  controller.py the real-time loop, the scenarios, the run logs
  server.py     FastAPI: dashboard, WebSocket state, run and load control
  static/       the dashboard (one HTML page, no external scripts)
  run.sh        start the console          live/run.sh
  load.sh       operator load from a shell live/load.sh add edge1 40
  ab.sh         old model against ours     live/ab.sh standard
  status.py     the live state as a table  live/load.sh status
```

**A match** is ten bots in one `bot.js` process in the client container,
tagged `live-mNN` on its command line. Match `N` uses usernames
`bot<10N>` to `bot<10N+9>`; bot0 to bot159 are opped on every server, so up
to 16 matches can run at once.

**A migration** stops that process, waits until it has exited, and starts it
again pointed at the other node. The ten players disconnect from one server
and log in to the other, the same cost a real session move has. The
controller measures it: the reconnect time of a move is from the stop until
the last of the ten players sends its first latency sample on the new node.

**The controller's model** is one of four, chosen per run:

| policy | what it predicts a node's p95 from |
|---|---|
| `analytical` | distance only: the load-blind formula of chapter 8 |
| `queueing` | the fitted M/M/1 form: distance + s / (1 - u) |
| `learned` | the gradient-boosted trees fitted on `grid1` and `grid2` |
| `learned-live` | `learned`, corrected while it runs: each steady 10 s window is compared with the prediction and updates a per-node cost factor c (the node at P players behaves like the grid's node at c x P), and a window measured over 100 ms is remembered for 5 minutes as a floor for that node at that load or more |

All four are evaluated in the background on every run (*every model in
shadow*), whichever one is in control.

## 9.2 One tick, every 2 seconds

1. **Demand.** Apply the scenario: matches arrive and leave on a fixed
   schedule, identical for every run, or, in a manual session, whatever the
   operator queued with `live/load.sh` or the dashboard.
2. **Telemetry.** Read every bot's new latency samples (one chat echo per bot
   per second, written as CSV by `bot.js`). Every 5 s also read every server's
   player count (`rcon list`), tick time (`rcon mspt`) and CPU (the
   container's own cgroup counter).
3. **Measure.** Per node, p50 and p95 of the last 10 s of samples. The worst
   node's p95 is the worst-off players' latency, the number the controller
   tries to keep low.
4. **Predict.** Every model (analytical, queueing, learned) predicts p95 for
   every node at its current player count. Only the model in control acts;
   the other two are scored in shadow.
5. **Decide** (every 10 s). Consider moving each match to each other node.
   Take the single best move if it lowers the predicted worst p95 by at least
   10 ms and by 20 %, or, with the worst unchanged, lowers the players'
   average predicted p95 by 3 ms. A match that just moved stays put for 60 s.
6. **Migrate.** Stop the match on node A, start it on node B.
7. **Publish.** The state goes to the dashboard over a WebSocket once a second
   and to `results/live/<run>/` on disk.

The three gains in step 5 are hysteresis: without them a match would bounce
between two nodes on noise. They are in `live/policy.py` (`Gains`) and every
run records the values it used in `meta.json`.

## 9.3 Why the analytical controller never moves a match off a crowded node

The analytical model predicts a node's latency as its network round trip,
whatever the load. To it, edge1 is 5 ms at 1 player and at 100. A move off a
crowded node can never lower its prediction, so it never makes one; the only
moves it ever makes are toward a nearer node. This is not a setting, it is
what the formula implies, and it is exactly the behaviour of a placement
algorithm built on it.

## 9.4 Fair comparison

- **Same demand.** Every scenario is a fixed, seeded schedule.
- **Same starting point.** By default every new match lands on the nearest
  node with room (`arrival: nearest`), the way a distance-based matchmaker
  places it. Runs then differ only in the controller's model.
  `arrival: model` lets the model place new matches too.
- **Same gate.** A run starts only when every server reports zero players,
  the same rule every grid cell uses.
- **No contention.** `live/run.sh` pins the controller to cores 24 to 27,
  which no server (0 to 7) or the client (8 to 23) uses. Keep the host
  otherwise idle during a run (docs/08-results.md 8.6).
- **Scored the same way.** Shadow scores count one row per node per 10 s
  window, and only windows in which that node's load did not change, so a
  prediction is never graded against samples taken at a different load.

## 9.5 Running it

```bash
topology/up.sh                  # if the lab is not up; ends with ALL CHECKS PASSED
live/run.sh                     # dashboard on http://127.0.0.1:8090
```

**Watch the twin react to load you add from a terminal.** Everything is
driven from a shell; the dashboard only shows:

```bash
live/load.sh start learned      # a manual session, the learned model in control
live/load.sh add edge1 60       # 60 real bots straight onto the 0.5-core edge
live/load.sh status             # what the twin shows, as a table
live/load.sh remove 20          # take 20 bots off again
live/load.sh stop               # end the session, disconnect every bot
```

The dashboard's *Raw telemetry* panel prints what the numbers are made of as
it reads them: latency lines from named bots (`bot23 rtt 7 ms`) and each
server's own console output (`rcon list: There are 40 of a max of 100 players
online: bot0, bot1, ...`). Each node card lists the usernames the server
itself reports online, next to the controller's own count.

Within one tick the twin shows edge1's player count jump; within a few
seconds its p95 rises and its link turns amber or red; within 10 s the
controller moves a match to edge2, drawn as a dot travelling along the links,
and the event log names the terminal as the source of the load. Run the same
commands with controller *Analytical* to see the formula leave everything
where it is.

**The old model against ours, on the same schedule:**

```bash
live/ab.sh standard             # about 30 minutes: analytical, then learned
```

Both runs appear on the *Compare runs* page.

## 9.6 Results

All runs on 2026-10-21, host in Performance power mode, logs in
`results/live/<run>/`. `python3 -m live.summarize` rebuilds every number
below into `results/live/summary.md`; `python3 -m live.figures` draws
figures 6 and 7.

### The standard schedule under each controller

`live/ab.sh standard` and a third run with `queueing`: the same arrivals and
departures (a match of 10 every 25 s up to 140 players, held 150 s, then down
to 60), new matches landing on the nearest node with room (a distance-based
matchmaker), each controller free to move one match every 10 s. One run each.

| controller | worst node's p95, median | worst p95, max | time over 100 ms | samples over 100 ms | all samples' p95 | migrations | mean reconnect |
|---|---|---|---|---|---|---|---|
| analytical (load-blind) | 1 058 ms | 19.6 s | 53% | 35.6% | 12.8 s | 0 | - |
| queueing (M/M/1) | 166 ms | 5.7 s | 53% | 25.7% | 1.8 s | 11 | 6.3 s |
| learned | **33 ms** | **817 ms** | **18%** | **2.0%** | **35 ms** | 10 | 5.9 s |

![worst p95 over time under each controller](../figures/fig6_live_ab.png)

- **The analytical controller never moves a match.** edge1 fills to 100
  players, its p95 goes past 10 s and stays there until departures empty it:
  the offline placement result, reproduced in closed loop.
- **Queueing moves as often as learned but to the wrong place, once.** Its
  curve depends on utilization alone, so it rates edge2 at 80 players
  (u = 0.8) at 27 ms. edge2's measured knee is between 80 and 100 players;
  live it sat at 1.8-3.4 s for about 200 s. The learned model predicts 65 ms
  for edge2 at 80, so it stopped edge2 at 70 and sent the overflow to edge3.
  This is the "one curve is not enough" effect of 08 §8.2 deciding a
  placement. Offline, at the four deployed scenarios, the two models placed
  almost the same; here they do not.
- **Part of the gap is the knee itself.** Both runs held edge1 at 40 players,
  exactly at its knee. In the queueing run edge1 stayed backlogged after
  arrival spikes (0.5-5.7 s); in the learned run it recovered (about 12 ms).
  That difference is chance at the knee, not the model. One run per
  controller cannot separate the two effects; the edge2 decision is
  systematic, the edge1 one is not.
- **The learned controller's remaining 18% over budget** is one transient
  repeated: a new match lands on edge1 (the matchmaker puts it there), edge1
  goes past its knee for the 10-25 s it takes the controller to move a match
  away. With matches placed by the model itself (`arrival=model`) it would
  not exist; the nearest arrival is kept so that the runs differ only in the
  controller.

**Every model in shadow.** Each 10 s window of steady load on a node is also
scored against every model's prediction for it, made before the window was
seen. F1 for "this node is over 100 ms":

| run (windows, of them over 100 ms) | analytical | queueing | learned | learned, corrected live |
|---|---|---|---|---|
| analytical in control (91, 28) | 0.00 | 0.87 | 0.87 | **0.95** |
| queueing in control (127, 36) | 0.00 | 0.00 | 0.00 | **0.78** |

In the queueing run the windows over budget are edge1 backlogged at 40 and
edge2 at 80: places where every offline model predicts a healthy node. Only
the model that corrects itself from the measurements catches them. (In the
learned run only 7 of 137 windows break 100 ms, all arrival transients; every
model's F1 there is 0 to 0.25 and is not a meaningful comparison.)

### A node gets slower and no model is told

`capacity-drop`: 8 matches arrive on the nearest node and stay; at 220 s
edge1's CPU quota is cut from 0.5 to 0.25 cores (`docker update`, the change a
noisy neighbour or a smaller VM makes) and nothing tells any model. 9 minutes
per run.

| controller | runs | time over 100 ms, whole run | after the cut: time over 100 ms | after the cut: worst p95, median | edge1 after the cut |
|---|---|---|---|---|---|
| queueing | 1 | 83% | 100% | 7.1 s | keeps 40 players |
| learned (offline) | 2 | 74%, 82% | 99%, 99% | 670 ms, 13.8 s | keeps 40 players |
| learned, corrected live, first version | 1 | 20% | 21% | 30 ms | 40, then 20, then back to 30 |
| learned, corrected live, with violation memory | 2 | **2%, 14%** | **4%, 13%** | **24 ms, 43 ms** | 20 or fewer within 30 s |

![edge1 under the CPU cut](../figures/fig7_live_capacity_drop.png)

- **Neither offline model notices.** Both keep using the curve measured at
  0.5 cores: 40 players still look healthy, edge1's p95 sits at 0.2 s to
  tens of seconds for the last five minutes, and the controller never acts.
- **The first live-corrected version noticed, then forgot.** Its cost factor
  rose to 1.65 within 80 s of the cut and it moved two matches off. With
  edge1 down to 20 players the windows looked healthy (20 players on a
  quarter core are still below the new knee), the factor decayed back to
  0.9, and at 440 s it moved a match back, which saw 3.9 s for about 20 s.
  One scale factor cannot hold what it learned at the knee once the load is
  below it.
- **The fix.** A window measured over 100 ms is remembered: for 5 minutes
  the live model predicts at least that latency for that node at that load
  or more (`LivePolicy.broke`, tested in `tests/test_live.py`). Windows in
  which no cost factor can change the prediction by 1.5x no longer move the
  factor.
- **Two runs of the fixed version: 2% and 14% over budget.** Both keep
  edge1 light after the cut and are an order of magnitude better than the
  offline models (74-83%). The spread between them is the honest result.
  The second run's over-budget time came from three places: arrival spikes
  before the cut, as in every run; its own moves (four matches moved within
  40 s around the cut, and each reconnect briefly loads the node it lands
  on); and the memory expiring at 500 s, after which it moved one match
  back to the throttled edge1, where the ten rejoining players saw 3-4 s.
  Moves are not free and a memory that expires means probing again; the
  controller models neither.
- **Read with care.** The memory was designed after the first run, and each
  configuration ran once or twice. This shows the mechanism, not a tuned or
  validated result.

## 9.7 Limits

- A migration here is a disconnect and reconnect of ten bots. A production
  system would hand state over first; the reconnect time measured here is an
  upper bound on what a player sees.
- The controller moves at most one match every 10 s. A flash crowd larger
  than that drains slowly; the rate is a choice, recorded in `meta.json`.
- `learned` is fitted offline on the grid and never updated during a run.
  `learned-live` corrects it from measured windows, but only through one
  number per node (how much more each player costs) bounded to 0.5-4x, plus
  a 5-minute memory of loads measured over budget; a change that alters the
  curve's shape rather than its scale is fitted only approximately (9.6).
  Neither sees tick time or CPU directly.
- The models were fitted with the host in Performance power mode. Run the live
  system in the same mode (`topology/verify.sh` checks it); in Balanced mode
  every node is 2-3x slower than every offline model believes (08 §8.6).
- One host. Everything in docs/08-results.md 8.6 applies.

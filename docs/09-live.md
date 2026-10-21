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

TODO after the live runs.

## 9.7 Limits

- A migration here is a disconnect and reconnect of ten bots. A production
  system would hand state over first; the reconnect time measured here is an
  upper bound on what a player sees.
- The controller moves at most one match every 10 s. A flash crowd larger
  than that drains slowly; the rate is a choice, recorded in `meta.json`.
- `learned` is fitted offline on the grid and never updated during a run.
  `learned-live` corrects it from measured windows, but only through one
  number per node (how much more each player costs) bounded to 0.5-4x; a
  change that alters the curve's shape rather than its scale is fitted only
  approximately. Neither sees tick time or CPU directly.
- The models were fitted with the host in Performance power mode. Run the live
  system in the same mode (`topology/verify.sh` checks it); in Balanced mode
  every node is 2-3x slower than every offline model believes (08 §8.6).
- One host. Everything in docs/08-results.md 8.6 applies.

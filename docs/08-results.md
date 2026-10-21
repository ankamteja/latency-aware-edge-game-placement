# 8. Results: the grid, the models, and the deployed placements

This chapter is the analysis. Everything before it built the instrument; this
is what the instrument measured, on the four-node testbed, with every known
artefact removed. Every number below can be regenerated from the files under
`results/` with the commands in §8.7.

Read the limits in §8.6 before quoting anything.

---

## 8.1 What was run

| run | what | cells | when |
|---|---|---|---|
| `grid1` | every node swept on its own load ladder, edge1 → cloud | 25 | 2026-10-20 23:43 – 2026-10-21 00:48, edge1 re-run 02:30 – 02:47 |
| `grid2` | the same ladder, nodes in reverse order | 25 | 2026-10-21 00:48 – 01:54 |
| `grid3` | a third replicate, edge1 → cloud, held out from every fit | 25 | 2026-10-21 09:16 – 10:22 |
| `grid4` | a fourth replicate, edge1 → cloud, held out from every fit | 25 | 2026-10-21 17:54 – 19:00; edge1 and edge2 re-measured 20:11 – 20:45 |
| `place1` | each model's optimal placement deployed for real, all nodes loaded at once | 14 placements, 31 node-cells | 2026-10-21 01:54 – 02:28, 02:47 – 02:53 |
| `place2` | the 9 distinct optimal placements deployed again, a second round | 9 placements, 19 node-cells | 2026-10-21 19:00 – 19:27 |

Ladders: edge1 at 1, 10, 20, 30, 40, 50, 60 players; edge2, edge3 and cloud at
1, 20, 40, 60, 80, 100. Each cell: 20 s settle, 15 s idle baseline (probes
only), staggered join, 90 s steady window. Only the steady window is analysed.

Conditions, all checked by `topology/verify.sh` before each run:

- RTT 5.2 / 15.2 / 30.3 / 40.2 ms (edge1 / edge2 / edge3 / cloud), measured with
  ping at bring-up (`placement/nodes.json`); within 0.3 ms of that in every cell
- CPU quota 0.5 / 1 / 2 / 4 cores on disjoint cpusets
- warm worlds, server heaps unable to swap
- bots split 10 per process, so the client is not in the measurement (§6.16)
- **time of day frozen at noon, peaceful, no weather** (§6.18)

Discarded, and kept only as evidence of the artefact that spoiled them:

| kept as | why it is not used |
|---|---|
| `grid1-daynight`, `grid2-daynight` | measured with the day/night cycle running: hostile mobs at night (§6.18) |
| `grid1-edge1-contended` | edge1 measured with the laptop's power mode on Balanced (it was switched to Performance 13 minutes into the run) and the host in interactive use: 2.4x the CPU per player of every other edge1 measurement (§8.6) |
| `grid3-balanced` | a full third replicate measured after the power mode fell back to Balanced: 2-3x the CPU per player on every node, edge1 collapsing at 20 players instead of 50-60 (§8.6) |
| `grid4-contended` | grid4's first edge1 and edge2 cells, measured while the host was in use (a browser and analysis scripts): edge1 1.3-1.6x and edge2 1.2-1.3x the CPU per player of grids 1-3; both nodes re-measured on an idle host |
| `probe-balanced`, `probe-performance` | the same edge1 20-player cell, minutes apart, in each power mode: 42.4% vs 17.8% CPU (§8.6) |
| `grid-a` | one bot process for all bots: the client's event loop was measured (§6.16) |

The dataset (`data/dataset.csv`, `data/cells.csv`) is built from `grid1`-`grid4`,
`place1` and `place2` only: 150 cells, 450 rows of 30 s windows. Every
model is fitted on `grid1` and `grid2`; `grid3` and `grid4` are used only as
a test set. In `grid4` edge1 still costs about 10-15% more CPU per player at
30-50 players than in grids 1-3 (20 players: 16%, inside the 14-18% of a clean
run), the drift between replicates of one host.

---

## 8.2 The network is flat; the game thread is not

p95 in-game round-trip time, ms, both replicates (`grid1 / grid2`). The network
round trip the analytical model predicts is in the header.

| players | edge1 (5.2 ms) | edge2 (15.2 ms) | edge3 (30.3 ms) | cloud (40.2 ms) |
|---|---|---|---|---|
| 1 | 6 / 6 | 17 / 16 | 31 / 31 | 41 / 41 |
| 10 | 6 / 8 | | | |
| 20 | 9 / 8 | 18 / 17 | 32 / 32 | 42 / 42 |
| 30 | 10 / 11 | | | |
| 40 | 14 / 15 | 21 / 21 | 33 / 33 | 44 / 43 |
| 50 | 47 / 308 | | | |
| 60 | **8 623 / 6 738** | 23 / 23 | 38 / 39 | 48 / 48 |
| 80 | | 34 / **2 661** | 46 / 45 | 53 / 60 |
| 100 | | **14 431 / 5 341** | 62 / 54 | 56 / 59 |

Over the same cells, ICMP p95 never moved by more than 0.3 ms from the link's
configured value - saturated or idle. Every millisecond above the header is
server-side, and the analytical model has no term for it.

The shape, on every node that reaches it, is flat, then a cliff:

- **edge1** stays within 10 ms of its network RTT up to 40 players. At 60 it
  is 8.6 s. Tick time (MSPT): 4.2-5.0 ms at 40, 6.5-6.7 ms at 50, **46 ms at 60**.
- **edge2** is flat to 60 players (23 ms); its knee is at 80, and every
  replicate breaks by 100. At 80
  the replicates disagree by 80x (34 vs 2 661 ms) - that is the knee itself, the
  load at which the tail is unstable from one run to the next.
- **edge3 and cloud** never reach a knee within the 100-player ceiling. Their
  p95 rises 31 → 62 ms and 41 → 59 ms.

**The tail breaks before the average tick time does.** At edge1, 50 players,
MSPT is 6.6 ms (mean of the two replicates) - an eighth of the 50 ms budget - while p95 has already left the
flat region (47 and 308 ms). Mean tick time is not an early warning.

Figures: `figures/fig1_p95_vs_players.png` (this table, with the analytical
model drawn flat beside each node), `figures/fig3_layers_edge1.png` (the four
probe rungs on edge1).

---

## 8.3 Rank inversion, and where it happens

For one match at a time, which node should host it? Measured p95, averaged over
both replicates, and the node each model picks
(`results/model/ranking.csv`):

| players | edge1 | edge2 | edge3 | cloud | measured best | analytical picks | regret |
|---|---|---|---|---|---|---|---|
| 1 | 6.0 | 16.3 | 31.0 | 41.0 | edge1 | edge1 | 0 |
| 20 | 8.5 | 17.5 | 32.0 | 42.0 | edge1 | edge1 | 0 |
| 40 | 14.5 | 21.0 | 33.0 | 43.5 | edge1 | edge1 | 0 |
| 60 | 7 680 | 23.0 | 38.5 | 48.0 | **edge2** | edge1 | **7 657 ms** |

The analytical model ranks by distance alone, so it always picks edge1. That
is right up to 40 players and wrong at 60, by a factor of 330 on the worst
player's latency. The queueing and learned models both switch to edge2 at 60
and have zero regret at every load.

This is a narrower and more honest version of the inversion than the
superseded two-node run claimed (that run had cold worlds, a saturated load
generator and night-time mobs, all of which made the edge look worse sooner).

---

## 8.4 How well each model predicts latency

Three models, one interface: `predict(node, players) -> p95 ms`
(`placement/models.py`).

- **analytical**: network RTT + 100 B / 1 Gb/s. No load term.
- **queueing (M/M/1)**: RTT + s / (1 - u), u = players / (100 x cores). Its one
  parameter s is the median of `delay x (1 - u)` over stable training cells:
  2.4 ms on this data. (A least-squares fit was tried first; a few multi-second
  tails dragged s to 1.4 s, so the model predicted 1.4 s on an idle node. The
  median is the most favourable fit of the form.)
- **learned**: RTT + server delay predicted by gradient-boosted trees on
  (utilization, players, cores). No assumed shape.

`results/model/summary.md`, three tests:

**Cross-replicate** - fit on one grid replicate, predict the other, all 50
cells:

| model | median abs error | typical factor off | MAE |
|---|---|---|---|
| analytical | 5.8 ms | 2.82x | 768 ms |
| queueing | 1.8 ms | 1.85x | 6 547 ms |
| learned | **0.9 ms** | **1.28x** | **469 ms** |

The queueing model is good in the flat region and badly wrong near the knee:
its 1/(1 - u) term explodes to its cap where the measured latency, though
large, is finite - hence the 6.5 s mean error.

**Leave one node out** - fit on three nodes, predict the fourth, which the
model has never seen (median abs error / typical factor off):

| held out | analytical | queueing | learned |
|---|---|---|---|
| edge1 | 5.3 / 6.5x | 2.6 / 3.86x | **1.3 / 1.96x** |
| edge2 | 6.8 / 5.56x | **1.8 / 2.16x** | 4.7 / 3.18x |
| edge3 | 5.3 / 1.28x | 3.0 / 1.18x | **1.5 / 1.06x** |
| cloud | 5.8 / 1.18x | 3.3 / 1.13x | **1.6 / 1.05x** |

The learned model transfers to an unseen node size best on three of four
nodes; on edge2 the closed form transfers better.

**Held-out replicates** - fit on `grid1` and `grid2`, predict `grid3` and
`grid4`, replicates measured hours later on a restarted testbed and never
used in any fit (50 cells; `results/model/held_out.csv`):

| model | median abs error | typical factor off | MAE | R² (log10) | Spearman ρ | F1, p95 > 50 ms | F1, p95 > 100 ms |
|---|---|---|---|---|---|---|---|
| analytical | 6.9 ms | 2.94x | 1 377 ms | -0.52 | 0.47 | 0.00 | 0.00 |
| queueing | 2.2 ms | 1.57x | 5 835 ms | 0.70 | 0.94 | 0.60 | **1.00** |
| learned | **1.1 ms** | 1.29x | **968 ms** | **0.89** | 0.94 | **0.86** | 0.80 |

The same pattern as cross-replicate, on data no model has seen: the learned
model is the most accurate and catches 12 of the 14 cells that break
50 ms (two false alarms); the queueing model catches 6 of them (no false
alarm) but gets all six 100 ms violations exactly. With 14 and 6 positive
cells these F1 scores move by about 0.05-0.15 per cell. Both held-out
replicates reproduce the knees: edge1 between 40 (15-16 ms) and 50 players
(409 ms and 1.8 s), edge2 between 80 (34-44 ms) and 100 (3.3-25.8 s), edge3
and cloud none up to 100.

**How sure are these?** `python -m model.uncertainty` resamples the test
cells with replacement 2000 times and scores every model on the same
resample (`results/model/uncertainty.md`). Median absolute error, 95%
interval:

| test | analytical | queueing | learned | learned better than queueing in |
|---|---|---|---|---|
| cross-replicate, 50 cells | 5.8 [2.9, 8.9] ms | 1.8 [1.6, 5.0] ms | **0.9 [0.3, 1.5] ms** | 100% of resamples, difference -0.9 [-3.7, -0.6] ms |
| held-out grid3 + grid4, 50 cells | 6.9 [3.2, 11.7] ms | 2.2 [1.5, 6.5] ms | **1.1 [0.8, 2.8] ms** | 96%, difference -1.1 [-4.2, +0.1] ms |

The learned model's lead in accuracy holds across resamples; on the smaller
held-out set its interval against queueing still just includes zero, so
there the gap is not significant. The F1
intervals are wide (cross-replicate F1 at 50 ms: learned 0.83 [0.62, 0.97],
queueing 0.56 [0.20, 0.80]) because only 3-12 cells break a budget, which is
why the F1 comparisons below are called indicative. Cells on one node's
ladder are not independent, so the true intervals are wider still.

**Every standard score.** The models are regressors, so accuracy and F1 only
exist once the prediction is turned into a decision. The decision placement
makes is "will this node break a latency budget at this load?" - positive =
measured p95 above the threshold. `python -m model.metrics` writes all of it
to `results/model/metrics.md` and `metrics.csv`; cross-replicate, 50 cells,
all out of sample:

| model | MAE | RMSE | MAPE | R² (log10) | Spearman ρ |
|---|---|---|---|---|---|
| analytical | 768 ms | 2 694 ms | 34% | -0.48 | 0.46 |
| queueing | 6 547 ms | 18 818 ms | 3 006% | 0.28 | 0.93 |
| learned | **469 ms** | **1 762 ms** | **18%** | **0.84** | **0.94** |

| budget | model | accuracy | precision | recall | F1 | balanced acc. |
|---|---|---|---|---|---|---|
| p95 > 50 ms (12 of 50 cells) | analytical | 0.76 | 0.00 | 0.00 | 0.00 | 0.50 |
| | queueing | 0.84 | 0.83 | 0.42 | 0.56 | 0.70 |
| | learned | **0.92** | 0.83 | **0.83** | **0.83** | **0.89** |
| p95 > 100 ms (6 of 50 cells) | analytical | 0.88 | 0.00 | 0.00 | 0.00 | 0.50 |
| | queueing | **0.96** | 0.83 | **0.83** | **0.83** | **0.91** |
| | learned | 0.94 | 0.80 | 0.67 | 0.73 | 0.82 |

Ranking (one match, four load levels): top-1 accuracy analytical 0.75,
queueing 1.00, learned 1.00.

How to read this:

- **The analytical model's 76-88% accuracy is the accuracy paradox.** It
  never predicts a violation - it has no load term - so it is "right" on
  every healthy cell and catches none of the 12 that break the budget:
  recall 0, F1 0. Accuracy alone would make it look acceptable; F1 and
  balanced accuracy (0.50, a coin flip) show it is useless for this
  decision.
- **Neither load-aware model wins everywhere.** The learned model detects
  the 50 ms violations far better (F1 0.83 vs 0.56: the queueing model
  misses cells that are slow but not yet near u = 1). At 100 ms the queueing
  model is slightly better (F1 0.83 vs 0.73). With 6 and 12 positive cells,
  a difference of one or two cells moves these numbers by 0.1-0.2: treat
  them as indicative, not as a ranking.
- **The thresholds are our choice.** 50 ms is one tick of the game's 20 Hz
  loop; 100 ms is a common playability limit. Neither is in the data.
- **The queueing model's huge MAE and MAPE** come from its capped prediction
  (60 s) near u = 1 where measured latency, though large, is finite. Its
  median error (1.8 ms) and Spearman ρ (0.93) show it orders cells well. Figure:
`figures/fig4_predicted_vs_measured.png`.

---

## 8.5 The end-to-end test: deploy each model's placement

The question a placement algorithm is actually asked: split a batch of players
(matches of 10) across all four nodes at once, minimising the worst player's
p95. For each total and each model, the brute-force optimum under that model
was computed (`placement/experiment.py plan`), then **deployed for real** with
all loaded nodes running concurrently (`controller/deploy.sh`), and measured.
Nobody's prediction is used to grade anybody: the clock decides.

Every placement was deployed twice, in two rounds hours apart (`place1`,
`place2`). `results/placement/deployments.csv`, worst node's measured p95 in
ms, round 1 / round 2:

| players | analytical | queueing | learned |
|---|---|---|---|
| 40 | 26 / 16 (edge1=40) | 26 / 16 (edge1=40) | 26 / 16 (edge1=40) |
| 80 | **29 897 / 28 244** (edge1=80) | 20 / 20 (40/40/0/0) | 20 / 20 (40/40/0/0) |
| 120 | **17 758 / 18 658** (edge1=100, edge2=20) | 31 / 37 (40/80/0/0) | 32 / 32 (40/70/10/0) |
| 160 | **19 990 / 28 251** (edge1=100, edge2=60) | 35 / 40 (40/80/40/0) | 39 / 55 (40/70/50/0) |

Placements are written edge1/edge2/edge3/cloud and count players assigned.
Zero kicks in every deployment, but the overloaded edge1 under the analytical
placement held only 66, 63 and 71 (round 1) and 52, 52 and 43 (round 2) of
its 80, 100 and 100 players; the others timed out (keepalive) and are not in
its p95. In round 2 edge1 cost about 15% more CPU at 40 players than in round
1 (32-45% against 28-38%), the same drift as in `grid4`.

What this shows:

0. **In a simulator it would have won.** Graded by its own formula, the way
   a simulator built on it grades it, the load-blind placement is the best of
   the three at every size: predicted worst 5.2 / 5.2 / 15.2 / 15.2 ms at
   40 / 80 / 120 / 160 players, against 14.0 / 20.9 / 31.6 / 33.2 ms for the
   learned placement, which pays for the distance of the nodes it spreads to.
   Deployed, the learned placement measured 26 / 20 / 32 / 39 ms and the
   load-blind one 26 / 29 897 / 17 758 / 19 990 ms in round 1, and
   16 / 20 / 32 / 55 against 16 / 28 244 / 18 658 / 28 251 ms in round 2. This is the error a
   simulator cannot show.
1. **The load-blind placement fails catastrophically, and confidently.** It
   predicts 5-15 ms for every scenario and fills the nearest node to its
   100-player cap before using the next. From 80 players the worst-off players
   wait 18-30 seconds in both rounds - about 500-1500x worse
   than either load-aware placement, on the same hardware, the same links and
   the same players.
2. **Both load-aware models fix it, and by about the same amount.** Their
   placements are nearly identical (both keep edge1 at 40) and measure within
   15 ms of each other with neither consistently ahead: queueing is 5 ms worse
   at 120 in round 2, learned 4 and 15 ms worse at 160. The largest gap,
   learned 55 ms at 160 players in round 2, is edge1 at 40 players, just
   below its knee, again. The learned model predicted its own deployments to
   within 22 ms (14.0 → 26 / 16, 20.9 → 20 / 20, 31.6 → 32 / 32, 33.2 → 39 /
   55); the analytical model predicted 5-15 ms for deployments that measured
   18-30 s.
3. **The learned model's advantage is in prediction, not in this decision.**
   It is the better predictor (§8.4), but for this testbed's ranking question a
   correctly fitted closed form reaches the same placement. A claim that the
   learned model *places* better is not supported by these four scenarios.

Figure: `figures/fig5_deployments.png`.

Four earlier learned-model placements are also in `place1`
(`p40-20-20-0-0`, `p80-20-60-0-0`, `p120-20-60-40-0`, `p160-30-60-70-0`). They
were planned from data that still contained the contended edge1 cells (§8.6),
which made edge1 look smaller than it is. They are valid measurements - worst
p95 17, 22, 35 and 45 ms - and they are in the dataset, but they are not the
learned model's answer on clean data, so they are not in the table above.

---

## 8.6 Limits - quote these with the results

- **One host, four replicates.** Every node is a container on one laptop.
  The bootstrap intervals (8.4) cover the variation between cells, not between
  whole replicates, of which there are four. At the knees (edge1 at
  50, edge2 at 80) the replicates disagree by 6-80x, so the exact player count
  of a knee is not established; that a knee exists, and roughly where, is.
- **The host's power mode sets the servers' capacity.** A node capped at
  half a core runs in short bursts, so the CPU governor sees a mostly idle
  core and keeps its clock low. Every clean run was measured with the laptop
  in Performance mode (tuned `throughput-performance`). In Balanced mode
  edge1's cores sat at 0.8-2 GHz under load (5.3 GHz maximum) and the same
  work cost 2-3x the CPU: edge1 with 20 players used 42.4% of a core instead
  of 14-18%, and its knee moved from 50-60 players to under 20. This is what
  spoiled the first edge1 pass of `grid1` (the mode was switched to
  Performance 13 minutes into it; it was first blamed on interactive use of
  the laptop, which was also happening) and a whole third replicate
  (`grid3-balanced`, measured after the charger was unplugged and the mode
  fell back to Balanced). Two probes minutes apart, same cell, one per mode,
  confirm it. `topology/verify.sh` now fails unless the mode is Performance.
  It is also evidence for the main claim: the same node, same players, same
  network, and a change no latency formula sees moved the knee by 3x.
- **Capacities were chosen, not discovered.** 0.5 / 1 / 2 / 4 cores and 5 / 15
  / 30 / 40 ms were picked to make the trade-off exist. The claim is "an
  inversion exists, is large, and a load-aware model avoids it", not "edge
  nodes break at 60 players".
- **Capacity does not scale linearly with cores at the top.** The queueing
  model assumes 100 players per core. edge1 and edge2 fit that; edge3 and
  cloud were never pushed past their knee (100-player ceiling), so the
  assumption is untested there.
- **The workload is synthetic.** Bots walk, turn and chat once a second.
  Peaceful mode removes mob AI, which is real server work in a real game.
  Chat is broadcast to every player, so per-player cost grows with N.
- **Four scenarios.** The placement result rests on 40-160 players in matches
  of 10 across four nodes. Larger, more crowded problems are where the models
  could disagree.

---

## 8.7 Reproducing these numbers

```bash
cd topology && ./up.sh                      # ends with ALL CHECKS PASSED
cd ../controller
./grid.sh grid1 && ./grid.sh grid2 reverse  # ~2 h, keep the host idle
./grid.sh grid3 && ./grid.sh grid4         # held-out replicates, ~1 h each
cd ..
python3 dataset/build_dataset.py --tags grid1,grid2
python3 -m placement.experiment plan --players 40,80,120,160
controller/deploy_plan.sh place1            # ~40 min
(cd controller && ./deploy_plan.sh place2 2)  # second round, ~30 min
./rebuild.sh                                # dataset, scores, figures, PDFs
python3 -m model.evaluate                   # results/model/
python3 -m model.metrics                    # results/model/metrics.md
python3 -m model.uncertainty                # results/model/uncertainty.md
python3 -m model.figures                    # figures/
```

Set the laptop's power mode to Performance and keep the host idle while the
grids run (§8.6) - close browsers, do not
compile, do not watch video.

# Latency model evaluation

Queueing model fitted service term s = 2.40 ms (capacity 100 players/core).

## Cross-replicate (fit one grid replicate, predict the other)

| model | cells | MAE (ms) | median abs err (ms) | typical factor off |
|---|---|---|---|---|
| analytical | 50 | 767.7 | 5.8 | 2.82x |
| queueing | 50 | 6546.6 | 1.8 | 1.85x |
| learned | 50 | 468.7 | 0.9 | 1.28x |

## Held-out replicate (fit on grid1+grid2, predict grid3+grid4)

| model | cells | MAE (ms) | median abs err (ms) | typical factor off |
|---|---|---|---|---|
| analytical | 50 | 1376.9 | 6.9 | 2.94x |
| queueing | 50 | 5834.8 | 2.2 | 1.57x |
| learned | 50 | 968.2 | 1.1 | 1.29x |

## Leave one node out (median abs err ms / typical factor off)

| held-out node | analytical | queueing | learned |
|---|---|---|---|
| edge1 | 5.3 / 6.5x | 2.6 / 3.86x | 1.3 / 1.96x |
| edge2 | 6.8 / 5.56x | 1.8 / 2.16x | 4.7 / 3.18x |
| edge3 | 5.3 / 1.28x | 3.0 / 1.18x | 1.5 / 1.06x |
| cloud | 5.8 / 1.18x | 3.3 / 1.13x | 1.6 / 1.05x |

## Node ranking at each load (measured p95 ms; pick and regret per model)

| players | edge1 | edge2 | edge3 | cloud | best | analytical pick (regret) | queueing pick (regret) | learned pick (regret) |
|---|---|---|---|---|---|---|---|---|
| 1 | 6.0 | 16.3 | 31.0 | 41.0 | edge1 | edge1 (0.0) | edge1 (0.0) | edge1 (0.0) |
| 20 | 8.5 | 17.5 | 32.0 | 42.0 | edge1 | edge1 (0.0) | edge1 (0.0) | edge1 (0.0) |
| 40 | 14.5 | 21.0 | 33.0 | 43.5 | edge1 | edge1 (0.0) | edge1 (0.0) | edge1 (0.0) |
| 60 | 7680.4 | 23.0 | 38.5 | 48.0 | edge2 | edge1 (7657.4) | edge2 (0.0) | edge2 (0.0) |

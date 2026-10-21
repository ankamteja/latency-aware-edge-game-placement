# Latency model metrics

All predictions are out of sample. Positive class = measured p95 above the threshold (the node violates the latency budget at that load). See model/metrics.py for definitions.

## Cross-replicate (fit one grid replicate, predict the other)

### Regression

| model | n | MAE ms | RMSE ms | median abs err ms | MAPE % | R² (log10) | Spearman ρ |
|---|---|---|---|---|---|---|---|
| analytical | 50 | 767.7 | 2694.0 | 5.8 | 34.1 | -0.48 | 0.46 |
| queueing | 50 | 6546.6 | 18817.6 | 1.8 | 3006.0 | 0.28 | 0.93 |
| learned | 50 | 468.7 | 1762.2 | 0.9 | 18.3 | 0.84 | 0.94 |

### Classification: does p95 exceed 50 ms? (12 of 50 cells do)

| model | accuracy | precision | recall | F1 | balanced acc. | TP | FP | FN | TN |
|---|---|---|---|---|---|---|---|---|---|
| analytical | 0.76 | 0.00 | 0.00 | 0.00 | 0.50 | 0 | 0 | 12 | 38 |
| queueing | 0.84 | 0.83 | 0.42 | 0.56 | 0.70 | 5 | 1 | 7 | 37 |
| learned | 0.92 | 0.83 | 0.83 | 0.83 | 0.89 | 10 | 2 | 2 | 36 |

### Classification: does p95 exceed 100 ms? (6 of 50 cells do)

| model | accuracy | precision | recall | F1 | balanced acc. | TP | FP | FN | TN |
|---|---|---|---|---|---|---|---|---|---|
| analytical | 0.88 | 0.00 | 0.00 | 0.00 | 0.50 | 0 | 0 | 6 | 44 |
| queueing | 0.96 | 0.83 | 0.83 | 0.83 | 0.91 | 5 | 1 | 1 | 43 |
| learned | 0.94 | 0.80 | 0.67 | 0.73 | 0.82 | 4 | 1 | 2 | 43 |

## Held-out replicate (fit on grid1+grid2, predict grid3+grid4)

### Regression

| model | n | MAE ms | RMSE ms | median abs err ms | MAPE % | R² (log10) | Spearman ρ |
|---|---|---|---|---|---|---|---|
| analytical | 50 | 1376.9 | 5750.4 | 6.9 | 34.9 | -0.52 | 0.47 |
| queueing | 50 | 5834.8 | 17339.7 | 2.2 | 426.0 | 0.70 | 0.94 |
| learned | 50 | 968.2 | 4198.4 | 1.1 | 17.9 | 0.89 | 0.94 |

### Classification: does p95 exceed 50 ms? (14 of 50 cells do)

| model | accuracy | precision | recall | F1 | balanced acc. | TP | FP | FN | TN |
|---|---|---|---|---|---|---|---|---|---|
| analytical | 0.72 | 0.00 | 0.00 | 0.00 | 0.50 | 0 | 0 | 14 | 36 |
| queueing | 0.84 | 1.00 | 0.43 | 0.60 | 0.71 | 6 | 0 | 8 | 36 |
| learned | 0.92 | 0.86 | 0.86 | 0.86 | 0.90 | 12 | 2 | 2 | 34 |

### Classification: does p95 exceed 100 ms? (6 of 50 cells do)

| model | accuracy | precision | recall | F1 | balanced acc. | TP | FP | FN | TN |
|---|---|---|---|---|---|---|---|---|---|
| analytical | 0.88 | 0.00 | 0.00 | 0.00 | 0.50 | 0 | 0 | 6 | 44 |
| queueing | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 6 | 0 | 0 | 44 |
| learned | 0.96 | 1.00 | 0.67 | 0.80 | 0.83 | 4 | 0 | 2 | 44 |

## Ranking: does the model pick the measured-best node for one match?

| model | load levels | top-1 accuracy | mean regret ms |
|---|---|---|---|
| analytical | 4 | 0.75 | 1914.3 |
| queueing | 4 | 1.00 | 0.0 |
| learned | 4 | 1.00 | 0.0 |

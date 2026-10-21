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

## Ranking: does the model pick the measured-best node for one match?

| model | load levels | top-1 accuracy | mean regret ms |
|---|---|---|---|
| analytical | 4 | 0.75 | 1914.3 |
| queueing | 4 | 1.00 | 0.0 |
| learned | 4 | 1.00 | 0.0 |

# Uncertainty of the model scores

Paired bootstrap over cells; see model/uncertainty.py for the method
and why the intervals are optimistic.

## Cross-replicate (50 cells, 2000 paired resamples)

| model | median abs error, ms [95% CI] | F1, p95 > 50 ms [95% CI] | F1, p95 > 100 ms [95% CI] |
|---|---|---|---|
| analytical | 5.8 [2.9, 8.9] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| queueing | 1.8 [1.6, 5.0] | 0.56 [0.20, 0.80] | 0.83 [0.50, 1.00] |
| learned | 0.9 [0.3, 1.5] | 0.83 [0.62, 0.97] | 0.73 [0.29, 1.00] |

| difference in median error | ms [95% CI] | first model better in |
|---|---|---|
| learned - queueing | -0.9 [-3.7, -0.6] | 100% of resamples |
| learned - analytical | -5.0 [-7.6, -2.3] | 100% of resamples |
| queueing - analytical | -4.0 [-6.0, -1.2] | 100% of resamples |

## Held-out replicates (grid3+grid4) (50 cells, 2000 paired resamples)

| model | median abs error, ms [95% CI] | F1, p95 > 50 ms [95% CI] | F1, p95 > 100 ms [95% CI] |
|---|---|---|---|
| analytical | 6.9 [3.2, 11.7] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| queueing | 2.2 [1.5, 6.5] | 0.60 [0.27, 0.83] | 1.00 [1.00, 1.00] |
| learned | 1.1 [0.8, 2.8] | 0.86 [0.69, 0.97] | 0.80 [0.36, 1.00] |

| difference in median error | ms [95% CI] | first model better in |
|---|---|---|
| learned - queueing | -1.1 [-4.2, +0.1] | 96% of resamples |
| learned - analytical | -5.8 [-9.5, -2.1] | 100% of resamples |
| queueing - analytical | -4.7 [-7.5, -1.4] | 100% of resamples |

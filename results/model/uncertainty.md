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

## Held-out replicates (grid3) (25 cells, 2000 paired resamples)

| model | median abs error, ms [95% CI] | F1, p95 > 50 ms [95% CI] | F1, p95 > 100 ms [95% CI] |
|---|---|---|---|
| analytical | 6.9 [2.6, 15.7] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| queueing | 2.3 [1.3, 12.5] | 0.67 [0.00, 1.00] | 1.00 [1.00, 1.00] |
| learned | 1.2 [0.8, 3.7] | 0.92 [0.67, 1.00] | 0.80 [0.00, 1.00] |

| difference in median error | ms [95% CI] | first model better in |
|---|---|---|
| learned - queueing | -1.1 [-9.6, +0.3] | 95% of resamples |
| learned - analytical | -5.7 [-12.8, -1.7] | 100% of resamples |
| queueing - analytical | -4.6 [-7.5, -0.9] | 100% of resamples |

# Live runs

Every finished run in results/live/, from its own logs.
Worst = the worst node's p95 over the last 10 s, sampled every tick.

## capacity-drop

| run | controller | worst p95, median | time over 100 ms | worst, max | moves | mean reconnect | after the cut (220 s): median / over 100 ms / max |
|---|---|---|---|---|---|---|---|
| 20261021-110303007-learned-capacity-drop-nearest | learned | 528 ms | 74% | 2.6 s | 4 | 5.9 s | 670 ms / 99% / 2.6 s |
| 20261021-145704362-learned-capacity-drop-nearest | learned | 7.7 s | 82% | 31.1 s | 4 | 6.0 s | 13.8 s / 99% / 31.1 s |
| 20261021-112507411-learned-live-capacity-drop-nearest | learned-live | 24 ms | 2% | 222 ms | 8 | 5.9 s | 24 ms / 4% / 222 ms |
| 20261021-150643068-learned-live-capacity-drop-nearest | learned-live | 43 ms | 14% | 4.5 s | 12 | 6.3 s | 43 ms / 13% / 4.5 s |
| 20261021-163331922-learned-live-capacity-drop-nearest | learned-live | 43 ms | 9% | 1.1 s | 12 | 6.1 s | 43 ms / 6% / 1.1 s |
| 20261021-111240742-learned-live-capacity-drop-nearest | learned-live, first version | 31 ms | 20% | 4.1 s | 9 | 6.2 s | 30 ms / 21% / 4.1 s |
| 20261021-144725694-queueing-capacity-drop-nearest | queueing | 2.6 s | 83% | 33.1 s | 4 | 6.0 s | 7.1 s / 100% / 33.1 s |

## standard

| run | controller | worst p95, median | time over 100 ms | worst, max | moves | mean reconnect |
|---|---|---|---|---|---|---|
| 20261021-103501780-analytical-standard-nearest | analytical | 1.1 s | 53% | 19.6 s | 0 | - |
| 20261021-161941626-analytical-standard-nearest | analytical | 4.5 s | 62% | 29.8 s | 0 | - |
| 20261021-104850714-learned-standard-nearest | learned | 33 ms | 18% | 817 ms | 10 | 5.9 s |
| 20261021-154235986-learned-standard-nearest | learned | 47 ms | 41% | 5.8 s | 10 | 6.2 s |
| 20261021-143333558-queueing-standard-nearest | queueing | 166 ms | 53% | 5.7 s | 11 | 6.3 s |
| 20261021-155627132-queueing-standard-nearest | queueing | 72 ms | 46% | 3.5 s | 11 | 6.3 s |

## By configuration

Median over runs, with [lowest, highest] when there is more than one.

| scenario | controller | runs | worst p95, median | time over 100 ms | moves | after the cut: time over 100 ms |
|---|---|---|---|---|---|---|
| capacity-drop | learned | 2 | 4.1 s [528 ms, 7.7 s] | 78% [74%, 82%] | 4 [4, 4] | 99% [99%, 99%] |
| capacity-drop | learned-live | 3 | 43 ms [24 ms, 43 ms] | 9% [2%, 14%] | 12 [8, 12] | 6% [4%, 13%] |
| capacity-drop | learned-live, first version | 1 | 31 ms | 20% | 9 | 21% |
| capacity-drop | queueing | 1 | 2.6 s | 83% | 4 | 100% |

| scenario | controller | runs | worst p95, median | time over 100 ms | moves |
|---|---|---|---|---|---|
| standard | analytical | 2 | 2.8 s [1.1 s, 4.5 s] | 58% [53%, 62%] | 0 [0, 0] |
| standard | learned | 2 | 40 ms [33 ms, 47 ms] | 29% [18%, 41%] | 10 [10, 10] |
| standard | queueing | 2 | 119 ms [72 ms, 166 ms] | 49% [46%, 53%] | 11 [11, 11] |

# Live runs

Every finished run in results/live/, from its own logs.
Worst = the worst node's p95 over the last 10 s, sampled every tick.

## capacity-drop

| run | controller | worst p95, median | time over 100 ms | worst, max | moves | mean reconnect | after the cut (220 s): median / over 100 ms / max |
|---|---|---|---|---|---|---|---|
| 20261021-110303007-learned-capacity-drop-nearest | learned | 528 ms | 74% | 2.6 s | 4 | 5.9 s | 670 ms / 99% / 2.6 s |
| 20261021-145704362-learned-capacity-drop-nearest | learned | 7.7 s | 82% | 31.1 s | 4 | 6.0 s | 13.8 s / 99% / 31.1 s |
| 20261021-111240742-learned-live-capacity-drop-nearest | learned-live | 31 ms | 20% | 4.1 s | 9 | 6.2 s | 30 ms / 21% / 4.1 s |
| 20261021-112507411-learned-live-capacity-drop-nearest | learned-live | 24 ms | 2% | 222 ms | 8 | 5.9 s | 24 ms / 4% / 222 ms |
| 20261021-150643068-learned-live-capacity-drop-nearest | learned-live | 43 ms | 14% | 4.5 s | 12 | 6.3 s | 43 ms / 13% / 4.5 s |
| 20261021-144725694-queueing-capacity-drop-nearest | queueing | 2.6 s | 83% | 33.1 s | 4 | 6.0 s | 7.1 s / 100% / 33.1 s |

## standard

| run | controller | worst p95, median | time over 100 ms | worst, max | moves | mean reconnect |
|---|---|---|---|---|---|---|
| 20261021-103501780-analytical-standard-nearest | analytical | 1.1 s | 53% | 19.6 s | 0 | - |
| 20261021-104850714-learned-standard-nearest | learned | 33 ms | 18% | 817 ms | 10 | 5.9 s |
| 20261021-143333558-queueing-standard-nearest | queueing | 166 ms | 53% | 5.7 s | 11 | 6.3 s |

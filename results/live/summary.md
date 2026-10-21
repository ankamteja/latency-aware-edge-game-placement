# Live runs

Every finished run in results/live/, from its own logs.
Worst = the worst node's p95 over the last 10 s, sampled every tick.

## capacity-drop

| run | controller | worst p95, median | time over 100 ms | worst, max | moves | mean reconnect | after the cut (220 s): median / over 100 ms / max |
|---|---|---|---|---|---|---|---|
| 20261021-110303007-learned-capacity-drop-nearest | learned | 528 ms | 74% | 2.6 s | 4 | 5.9 s | 670 ms / 99% / 2.6 s |
| 20261021-111240742-learned-live-capacity-drop-nearest | learned-live | 31 ms | 20% | 4.1 s | 9 | 6.2 s | 30 ms / 21% / 4.1 s |
| 20261021-112507411-learned-live-capacity-drop-nearest | learned-live | 24 ms | 2% | 222 ms | 8 | 5.9 s | 24 ms / 4% / 222 ms |

## standard

| run | controller | worst p95, median | time over 100 ms | worst, max | moves | mean reconnect |
|---|---|---|---|---|---|---|
| 20261021-103501780-analytical-standard-nearest | analytical | 1.1 s | 53% | 19.6 s | 0 | - |
| 20261021-104850714-learned-standard-nearest | learned | 33 ms | 18% | 817 ms | 10 | 5.9 s |

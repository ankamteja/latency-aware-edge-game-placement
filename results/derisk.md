# De-risk experiment: RTT vs load at zero network distance

Same server, same localhost, zero network change — only the number of bots
changes. Any RTT increase is invisible to the analytical model
(`latency = propagation + size/bandwidth`), which predicts identical latency
for both runs.

## Setup

- Paper 1.21.4 (`itzg/minecraft-server`), `--cpus=0.5`, localhost
- `connection-throttle: -1` (bukkit.yml) — default 4000 ms kicks staggered bot joins
- bots opped — vanilla spam-kick (`disconnect.spam`) fires on 1 msg/s chat once the
  server falls behind on ticks; ops are exempt
- `max-players=100` (default 20 caps the experiment)
- First 5 samples per run discarded (cold start)
- RTT = chat echo round-trip measured by each bot (`bots/bot.js`)

## Results (2026-07-11)

| Metric (ms) | 1 bot | 25 bots | change |
|---|---|---|---|
| samples | 34 | 1,962 | |
| median | 80 | 48 | |
| mean | 45 | 80 | ~1.8× |
| p95 | ~89 | 326 | **~3.7×** |
| p99 | ~89 | 770 | **~8.7×** |
| max | 89 | 1,159 | **~13×** |

Mid-run server state at 25 bots:

- MSPT avg/max (10 s window): **74.0 / 202.0 ms** — tick budget is 50 ms, the
  server cannot hold 20 Hz (1-minute max: 1,397 ms)
- Container CPU: **49.86%** — pinned exactly at the 0.5-CPU cap (compute-starved,
  not idle)
- Zero kicks, all 25 bots reporting

## Notes

- Network distance was zero and unchanged in both runs. Everything above the
  1-bot distribution is server-side queueing delay, the component the
  analytical placement model cannot see.
- The damage concentrates in the tail (p95/p99/max), which is also the metric
  that matters for game placement (worst player, not mean player). The
  single-bot distribution is bimodal (a few ms vs ~85 ms, tick/chat-phase
  alignment), which drags the medians around; tail percentiles are the honest
  comparison.
- MSPT above the 50 ms budget is the direct server-load signal and moves
  together with tail RTT. This is the main feature the learned predictor
  should pick up.

## Conclusion

Effect demonstrated: at fixed (zero) network distance, tail RTT grows ~4–13×
under load while the analytical model's prediction stays constant. The project
is de-risked; proceed to the full load sweep (1, 5, 10, 20, 30, 40 bots).

// Multi-bot load generator + in-game latency measurement.
//
// Each bot is a real Minecraft client speaking the real protocol. It does two
// things at once:
//   1. generates load - walks forward and turns constantly, which forces the
//      server to run movement, collision and chunk logic for it every tick
//   2. measures latency - sends a chat message containing the current time and
//      waits for the server to echo it back. That round trip has to be handled
//      by the server's single main game thread, so it includes queueing delay
//      inside the server, which is exactly the term the analytical placement
//      model cannot see.
//
// Usage: node bot.js [N] [host] [port]
//   N    number of bots (default 1; usernames bot0..bot(N-1) must be opped
//        server-side or the vanilla chat spam filter kicks them)
//   host server to dial - THIS is the placement decision (default localhost)
//   port server port (default 25565)
//
// Output: one CSV line per event on stdout
//   epoch_ms,bot<i>,rtt,<ms>      a latency sample
//   epoch_ms,bot<i>,spawn         bot joined the world (first time only)
//   epoch_ms,bot<i>,respawn       bot died and came back - it walks forward
//                                 forever, so it eventually falls or drowns
//   epoch_ms,bot<i>,kicked,<why>  server removed the bot - a run with kicks is
//   epoch_ms,bot<i>,error,<why>   not clean and should be discarded
//
// (Logs under results/raw/ from before 2026-08-03 use the older
//  "<i> RTT: <ms>" format instead.)
const mineflayer = require('mineflayer')

const N = parseInt(process.argv[2]) || 1
const HOST = process.argv[3] || 'localhost'
const PORT = parseInt(process.argv[4]) || 25565

const log = (i, ...rest) => console.log([Date.now(), 'bot' + i, ...rest].join(','))

function makeBot(i) {
  const bot = mineflayer.createBot({
    host: HOST, port: PORT,
    username: 'bot' + i, auth: 'offline', version: '1.21.4'
  })
  // mineflayer emits 'spawn' again after every respawn, and a bot that walks
  // forward forever does eventually fall or drown. Everything below must be
  // set up EXACTLY ONCE: attaching the chat listener and the intervals per
  // spawn made the bot send several messages per second and count each one
  // several times, inflating both the offered load and the sample count.
  let spawns = 0
  bot.on('spawn', () => {
    if (++spawns > 1) { log(i, 'respawn'); return }
    log(i, 'spawn')
    const prefix = 'p' + i + '_'
    // persistent listener: with many bots, a once('chat') would usually fire
    // on ANOTHER bot's message and silently drop the sample
    bot.on('chat', (u, m) => {
      if (u === bot.username && m.startsWith(prefix)) {
        log(i, 'rtt', Date.now() - parseInt(m.slice(prefix.length)))
      }
    })
    setInterval(() => {                       // keep the bot busy = real server load
      bot.setControlState('forward', true)
      bot.look(Math.random() * 6, 0)
    }, 100)
    setInterval(() => bot.chat(prefix + Date.now()), 1000)  // measure RTT
  })
  bot.on('error', e => log(i, 'error', JSON.stringify(e.message)))
  bot.on('kicked', r => log(i, 'kicked', JSON.stringify(String(r))))
}
// Stagger the joins: N clients logging in at the same instant is a chunk-load
// spike, not the steady-state load we want to measure.
for (let i = 0; i < N; i++) setTimeout(() => makeBot(i), i * 500)

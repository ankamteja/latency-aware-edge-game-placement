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
// Usage: node bot.js [N] [host] [port] [--tag=<name>] [--from=K]
//                    [--offset=<ms>] [--every=<ms>]
//   N     number of bots (default 1; usernames bot0..bot(N-1) must be opped
//         server-side or the vanilla chat spam filter kicks them)
//   host  server to dial - THIS is the placement decision (default localhost)
//   port  server port (default 25565)
//   --tag a marker that does nothing except appear in this process's command
//         line, so a driver loading several nodes at once can stop the bots
//         for ONE target with `pkill -f 'bot[.]js.*--tag=edge1'` instead of
//         killing every bot on the client
//   --from    first bot number (default 0): this process runs botK..bot(K+N-1)
//   --offset  ms before this process's first join (default 0)
//   --every   ms between this process's joins (default 500)
//
// One process should not run many bots. Every chat message is broadcast to
// every player, so N bots receive N^2 messages a second, and a single Node
// process handles all of them on one thread: at 60 bots it sat at 70-100% of
// a core and its event-loop delay was being measured as server latency.
// bots/spawn.sh splits a load across processes with these three flags so the
// joins still arrive one every 500 ms overall.
//
// Output: one CSV line per event on stdout
//   epoch_ms,bot<i>,rtt,<ms>      a latency sample
//   epoch_ms,bot<i>,spawn         bot joined the world (first time only)
//   epoch_ms,bot<i>,respawn       bot died and came back - it walks forward
//                                 forever, so it eventually falls or drowns
//   epoch_ms,bot<i>,kicked,<why>  server removed the bot - a run with kicks is
//   epoch_ms,bot<i>,error,<why>   not clean and should be discarded
//   epoch_ms,proc<K>,loop,<p99>   this process's event-loop delay p99 over the
//                                 last 5 s, in ms - if it is not small, the
//                                 client, not the server, is adding latency
//
// (Logs under results/raw/ from before 2026-08-03 use the older
//  "<i> RTT: <ms>" format instead.)
const mineflayer = require('mineflayer')

// Options are --name=value; everything else is positional. --tag is only a
// process-line marker and is not read.
const opt = Object.fromEntries(process.argv.slice(2)
  .filter(a => a.startsWith('--')).map(a => a.slice(2).split('=')))
const argv = process.argv.slice(2).filter(a => !a.startsWith('--'))
const FROM = parseInt(opt.from) || 0
const OFFSET = parseInt(opt.offset) || 0
const EVERY = parseInt(opt.every) || 500
const N = parseInt(argv[0]) || 1
const HOST = argv[1] || 'localhost'
const PORT = parseInt(argv[2]) || 25565

const log = (i, ...rest) => console.log([Date.now(), 'bot' + i, ...rest].join(','))

// Share chunk columns between the bots of this process.
//
// The server sends every player the 21x21 chunk columns inside its view
// distance, and mineflayer keeps a private parsed copy of each one - about
// 47 MB per bot, so 100 bots need ~4.7 GB on a 16 GB host that also runs four
// JVMs. Once the host runs short, the kernel swaps server heap out and ticks
// stall on page faults: latency the experiment would blame on player load.
//
// All bots of one process dial the same server and stand in the same world,
// so they receive the same columns. Each bot still receives and parses every
// column, exactly as before - the server's work and the bytes on the wire are
// unchanged - but after parsing, a column some other bot already holds is
// replaced by that bot's copy, and the duplicate is garbage. Block updates
// are applied by every holder to the one shared copy, which is idempotent.
// A column is dropped from the cache when its last holder unloads it.
//
// Assumes one dimension (bots never leave the overworld), so a column is
// identified by its x,z alone.
const World = require('prismarine-world')('1.21.4')
const shared = new Map()                    // "x,z" -> { column, refs }
const origSet = World.prototype.setLoadedColumn
const origUnload = World.prototype.forceUnloadColumn
const release = key => {
  const s = shared.get(key)
  if (s && --s.refs <= 0) shared.delete(key)
}
World.prototype.setLoadedColumn = function (chunkX, chunkZ, chunk, save) {
  const key = chunkX + ',' + chunkZ
  if (this.columns[key]) release(key)       // a re-sent column replaces our hold
  let s = shared.get(key)
  if (s) s.refs++
  else shared.set(key, (s = { column: chunk, refs: 1 }))
  return origSet.call(this, chunkX, chunkZ, s.column, save)
}
World.prototype.forceUnloadColumn = function (key, chunkX, chunkZ) {
  if (this.columns[key]) release(chunkX + ',' + chunkZ)
  return origUnload.call(this, key, chunkX, chunkZ)
}

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
for (let j = 0; j < N; j++) setTimeout(() => makeBot(FROM + j), OFFSET + j * EVERY)

const { monitorEventLoopDelay } = require('perf_hooks')
const loop = monitorEventLoopDelay({ resolution: 10 })
loop.enable()
setInterval(() => {
  console.log([Date.now(), 'proc' + FROM, 'loop', (loop.percentile(99) / 1e6).toFixed(1)].join(','))
  loop.reset()
}, 5000)

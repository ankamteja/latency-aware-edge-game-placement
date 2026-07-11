// Multi-bot load generator + RTT measurement rig.
// Usage: node bot.js [N] [host] [port]
//   N    number of bots (default 1)
//   host server to dial — THIS is the placement decision (default localhost)
//   port server port (default 25565)
const mineflayer = require('mineflayer')

const N = parseInt(process.argv[2]) || 1
const HOST = process.argv[3] || 'localhost'
const PORT = parseInt(process.argv[4]) || 25565

function makeBot(i) {
  const bot = mineflayer.createBot({
    host: HOST, port: PORT,
    username: 'bot' + i, auth: 'offline', version: '1.21.4'
  })
  bot.on('spawn', () => {
    const prefix = 'p' + i + '_'
    // persistent listener: with many bots, a once('chat') would usually fire
    // on ANOTHER bot's message and silently drop the sample
    bot.on('chat', (u, m) => {
      if (u === bot.username && m.startsWith(prefix)) {
        console.log(i, 'RTT:', Date.now() - parseInt(m.slice(prefix.length)))
      }
    })
    setInterval(() => {                       // keep the bot busy = real server load
      bot.setControlState('forward', true)
      bot.look(Math.random() * 6, 0)
    }, 100)
    setInterval(() => bot.chat(prefix + Date.now()), 1000)  // measure RTT
  })
  bot.on('error', e => console.log(i, 'ERR', e.message))
  bot.on('kicked', r => console.log(i, 'KICKED', r))
}
for (let i = 0; i < N; i++) setTimeout(() => makeBot(i), i * 500)

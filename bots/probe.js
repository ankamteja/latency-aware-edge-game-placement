// Latency probe ladder.
//
// The point of this file: a single "latency" number hides where the delay came
// from. So we measure the same path at three depths, at the same time, and let
// the difference between them say which layer the delay lives in.
//
//   tcp     open a TCP connection to the game port and time the handshake.
//           Touches the network and the server's accept queue. No game logic.
//   status  the Minecraft server-list ping (what your client shows in the
//           server browser). Network + the server process answering a request.
//           Whether this is affected by game-thread load is an EMPIRICAL
//           question - we do not assume it, we read it off the data.
//   (ICMP ping is the fourth, purest rung; it is collected separately by the
//    `ping` binary in controller/collect.sh.)
//
// In-game action latency - the thing a player actually feels - is measured by
// bot.js instead, because it has to ride the game thread.
//
// Usage: node probe.js <host> [port] [interval_ms]
// Output: one CSV line per sample on stdout
//   epoch_ms,kind,rtt_ms          rtt_ms is -1 when the probe failed
const net = require('net')
const mc = require('minecraft-protocol')

const HOST = process.argv[2] || '127.0.0.1'
const PORT = parseInt(process.argv[3]) || 25565
const EVERY = parseInt(process.argv[4]) || 1000

function emit(kind, ms) {
  console.log(`${Date.now()},${kind},${ms}`)
}

// --- rung 1: TCP handshake ------------------------------------------------
// process.hrtime.bigint() is a monotonic nanosecond clock. Date.now() can jump
// if the system clock is adjusted; for measuring a duration you want the clock
// that only ever moves forward.
function tcpProbe() {
  const t0 = process.hrtime.bigint()
  const s = net.connect({ host: HOST, port: PORT })
  let done = false
  const finish = ok => {
    if (done) return
    done = true
    emit('tcp', ok ? Number(process.hrtime.bigint() - t0) / 1e6 : -1)
    s.destroy()
  }
  s.setTimeout(5000)
  s.on('connect', () => finish(true))
  s.on('timeout', () => finish(false))
  s.on('error', () => finish(false))
}

// --- rung 2: Minecraft server-list ping -----------------------------------
function statusProbe() {
  const t0 = process.hrtime.bigint()
  let done = false
  const finish = ok => {
    if (done) return
    done = true
    emit('status', ok ? Number(process.hrtime.bigint() - t0) / 1e6 : -1)
  }
  const timer = setTimeout(() => finish(false), 5000)
  mc.ping({ host: HOST, port: PORT, closeTimeout: 4000 }, err => {
    clearTimeout(timer)
    finish(!err)
  })
}

setInterval(tcpProbe, EVERY)
setInterval(statusProbe, EVERY)
tcpProbe()
statusProbe()

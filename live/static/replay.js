/* Replay mode for the hosted copy of the dashboard (built by live/build_site.py).

   The page talks to /api/* and /ws. Here those are answered from files: the
   offline data and run list as recorded, and a "live" state stream rebuilt,
   tick by tick, from one recorded run's frames. Start run picks the newest
   recorded run of the chosen controller and scenario and plays it back on
   its own clock, faster if asked. Nothing is simulated. */
(function () {
  "use strict";
  const DATA = "data/";
  const cache = {};
  const getj = p => cache[p] || (cache[p] = fetch(DATA + p).then(r => {
    if (!r.ok) throw new Error(p);
    return r.json();
  }));
  const realFetch = window.fetch.bind(window);
  let replay = null;           // {d, i, status, timer}
  let speed = 4;
  let runsIndex = [];

  const json = (o, status = 200) =>
    new Response(JSON.stringify(o), {status, headers: {"content-type": "application/json"}});

  function state() {
    if (!replay) return {status: "idle", last: runsIndex[0] || null};
    const d = replay.d, i = replay.i, f = d.frames[i], t = f.t;
    const upto = d.timeline.slice(0, i + 1);
    const worst = upto.map(r => r.worst_p95_ms).filter(v => v != null);
    const mig = d.migrations.filter(m => m.t <= t);
    const summary = Object.assign({}, d.summary, {
      status: replay.status,
      duration_s: t,
      migrations: mig.length,
      time_over_budget_share: worst.length ? worst.filter(v => v > 100).length / worst.length : 0,
      // the logs keep each model's score for the whole run only, so the
      // table appears when the playback reaches the end
      shadow: replay.status === "finished" ? d.summary.shadow : {},
    });
    return {
      run: d.summary.run, policy: d.meta.policy, scenario: d.meta.scenario, arrival: d.meta.arrival,
      status: replay.status, t, length_s: d.meta.length_s, updated: Date.now() / 1000,
      budget_ms: 100, nodes: f.nodes, series: upto.slice(-450), migrations: mig.slice(-50),
      log: d.events.filter(e => e.t <= t).slice(-60).reverse(), raw: [], summary,
    };
  }

  function step() {
    if (!replay || replay.status !== "running") return;
    const d = replay.d;
    if (replay.i >= d.frames.length - 1) { replay.status = "finished"; return; }
    const dt = d.frames[replay.i + 1].t - d.frames[replay.i].t;
    replay.i += 1;
    replay.timer = setTimeout(step, Math.max(50, dt * 1000 / speed));
  }

  async function start(runId) {
    if (replay && replay.timer) clearTimeout(replay.timer);
    const d = await getj("runs/" + runId + ".json");
    replay = {d, i: 0, status: "running", timer: null};
    step();
    return d;
  }

  window.fetch = async (url, opt = {}) => {
    const u = typeof url === "string" ? url : url.url;
    if (!u.startsWith("/api/")) return realFetch(url, opt);
    if (u === "/api/options") {
      const o = await getj("options.json");
      return json(Object.assign({}, o, {running: !!(replay && replay.status === "running")}));
    }
    if (u === "/api/runs") return json(await getj("runs.json"));
    if (u.startsWith("/api/runs/")) {
      try {
        const d = await getj("runs/" + u.slice(10) + ".json");
        return json({summary: d.summary, timeline: d.timeline, migrations: d.migrations});
      } catch (e) { return json({detail: "no such run"}, 404); }
    }
    if (u === "/api/offline") return json(await getj("offline.json"));
    if (u === "/api/run") {
      const req = JSON.parse(opt.body || "{}");
      const r = runsIndex.find(x => x.policy === req.policy && x.scenario === req.scenario);
      if (!r) return json({detail: "no recorded run of this controller in this scenario"}, 409);
      const d = await start(r.run);
      return json({run: r.run, length_s: d.meta.length_s / speed});
    }
    if (u === "/api/stop") {
      if (replay && replay.status === "running") { replay.status = "stopped"; clearTimeout(replay.timer); }
      return json({ok: true});
    }
    if (u === "/api/load") return json({detail: "a replay plays a recorded run; load is added from a terminal on the testbed"}, 409);
    return json({detail: "not available in the replay"}, 404);
  };

  const RealWS = window.WebSocket;
  window.WebSocket = function (url, protocols) {
    if (!/\/ws$/.test(url)) return new RealWS(url, protocols);
    const sock = {readyState: 1, close() { clearInterval(iv); }};
    const iv = setInterval(() => { if (sock.onmessage) sock.onmessage({data: JSON.stringify(state())}); }, 500);
    setTimeout(() => sock.onopen && sock.onopen(), 0);
    return sock;
  };

  document.addEventListener("DOMContentLoaded", async () => {
    runsIndex = await getj("runs.json");
    const recorded = new Set(runsIndex.map(r => r.scenario));
    // only scenarios with a recorded run can be replayed
    const sc = document.getElementById("f-sc");
    [...sc.options].forEach(o => { if (!recorded.has(o.value)) o.remove(); });
    const ar = document.getElementById("f-ar");
    [...ar.options].forEach(o => { if (o.value !== "nearest") o.remove(); });
    // the logs keep no raw telemetry and no terminal: hide those panels
    const raw = document.getElementById("raw");
    if (raw) raw.closest(".card").style.display = "none";
    const term = document.querySelector(".term");
    if (term) {
      const card = term.closest(".card");
      card.parentElement.style.gridTemplateColumns = "1fr";
      card.style.display = "none";
    }
    const bar = document.createElement("div");
    bar.id = "replay-bar";
    bar.innerHTML = `<span><b>Replay.</b> Runs recorded on the real testbed on 2026-10-21, played back from their logs:
      every player count, latency, tick time and migration is as measured. The live system needs the testbed;
      see <a href="https://github.com/ankamteja/latency-aware-edge-game-placement">the repository</a>.</span>
      <label for="replay-speed">replay speed <select id="replay-speed"><option value="1">1x</option><option value="2">2x</option><option value="4" selected>4x</option><option value="10">10x</option></select></label>`;
    const hdr = document.getElementById("hdr");
    hdr.parentNode.insertBefore(bar, hdr.nextSibling);
    document.getElementById("replay-speed").addEventListener("change", e => { speed = +e.target.value; });
    const style = document.createElement("style");
    style.textContent = `#replay-bar{display:flex;gap:16px;align-items:center;justify-content:space-between;
      padding:8px 16px;font-size:12px;color:var(--muted);border-bottom:1px solid var(--line);background:var(--bg)}
      #replay-bar a{color:var(--blue)}
      #replay-bar label{display:flex;align-items:center;gap:6px;white-space:nowrap;margin:0;
        font-size:12px;text-transform:none;letter-spacing:0}
      #replay-bar select{width:auto;min-width:0;padding:2px 6px;height:auto}`;
    document.head.appendChild(style);
    // open on the comparison that makes the point: a node slows down mid-run
    const pick = runsIndex.find(r => r.policy === "learned-live" && r.scenario === "capacity-drop")
              || runsIndex[0];
    if (pick) {
      document.getElementById("f-pol").value = pick.policy;
      sc.value = pick.scenario;
      start(pick.run);
    }
  });
})();

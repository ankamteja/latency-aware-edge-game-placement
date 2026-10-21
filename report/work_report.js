// Plain-language work report (report/work_report.docx), same sections as the
// paper. Every number is in N below; update it from results/ and rebuild:
//   node report/work_report.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, ShadingType, AlignmentType, ImageRun, LevelFormat, BorderStyle,
  PageBreak, Footer, PageNumber,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(__dirname, "work_report.docx");

// ---- numbers (all measured; sources in brackets) ---------------------------
const N = {
  date: "22 October 2026",
  cells: 150, rows: 450,                                   // data/cells.csv, dataset.csv
  heldOut: { cells: 50, analytical: "6.9", queueing: "2.2", learned: "1.1" },
  cross: { analytical: "5.8", queueing: "1.8", learned: "0.9" },
  f1HeldOut: { analytical: "0.00", queueing: "0.60", learned: "0.86" },
  deployRounds: 2,                                         // results/placement/deployments.csv
  deploy: [                                                // players, analytical, queueing, learned
    ["40", "26 / 16 ms", "26 / 16 ms", "26 / 16 ms"],
    ["80", "29.9 / 28.2 s", "20 / 20 ms", "20 / 20 ms"],
    ["120", "17.8 / 18.7 s", "31 / 37 ms", "32 / 32 ms"],
    ["160", "20.0 / 28.3 s", "35 / 40 ms", "39 / 55 ms"],
  ],
  loadAware: "16-55 ms",
  live: {                                                  // results/live/summary.md
    runs: "3",
    rows: [
      ["Formula (load-blind)", "1.1 s (76 ms to 4.5 s)", "53%", "0"],
      ["Queueing (M/M/1)", "99 ms (72 to 166 ms)", "50%", "11"],
      ["Learned model", "39 ms (33 to 47 ms)", "33%", "10"],
      ["Learned, corrected live", "33 ms (32 to 34 ms)", "8%", "15"],
    ],
  },
  drop: {
    offline: "99-100%",
    liveText: "In the runs made with the final version of the live model, it noticed the cut from the measurements alone and moved players off the slowed node.",
  },
};

// ---- helpers ------------------------------------------------------------------
const FONT = "Calibri";
const p = (text, opts = {}) => new Paragraph({
  spacing: { after: 120, line: 300 },
  ...opts,
  children: Array.isArray(text) ? text : [new TextRun({ text, font: FONT, size: 23 })],
});
const b = (text) => new TextRun({ text, bold: true, font: FONT, size: 23 });
const t = (text) => new TextRun({ text, font: FONT, size: 23 });
const h1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 160 }, children: [new TextRun({ text, font: FONT })] });
const h2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 240, after: 120 }, children: [new TextRun({ text, font: FONT })] });
const bullet = (runs) => new Paragraph({
  numbering: { reference: "bullets", level: 0 }, spacing: { after: 80, line: 290 },
  children: typeof runs === "string" ? [t(runs)] : runs,
});
let listNo = 0;                 // each numbered list restarts at 1
const newList = () => { listNo += 1; };
const num = (runs) => new Paragraph({
  numbering: { reference: "steps", level: 0, instance: listNo }, spacing: { after: 80, line: 290 },
  children: typeof runs === "string" ? [t(runs)] : runs,
});

const W = 9026;   // A4 text width with 1-inch margins, in DXA
function table(header, rows, widths) {
  const sum = widths.reduce((a, x) => a + x, 0);
  const scaled = widths.map((x) => Math.round((x * W) / sum));
  scaled[scaled.length - 1] += W - scaled.reduce((a, x) => a + x, 0);
  const border = { style: BorderStyle.SINGLE, size: 4, color: "B7C4CF" };
  const borders = { top: border, bottom: border, left: border, right: border };
  const cell = (text, i, head) => new TableCell({
    width: { size: scaled[i], type: WidthType.DXA },
    borders,
    shading: head ? { type: ShadingType.CLEAR, color: "auto", fill: "DCEFEE" } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({ children: [new TextRun({ text, bold: head, font: FONT, size: 21 })] })],
  });
  return new Table({
    width: { size: W, type: WidthType.DXA },
    columnWidths: scaled,
    rows: [new TableRow({ tableHeader: true, children: header.map((x, i) => cell(x, i, true)) }),
      ...rows.map((r) => new TableRow({ children: r.map((x, i) => cell(x, i, false)) }))],
  });
}
function figure(file, caption, w, h) {
  const width = 560, height = Math.round((560 * h) / w);
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(path.join(ROOT, "figures", file)),
        transformation: { width, height } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
      children: [new TextRun({ text: caption, italics: true, font: FONT, size: 20, color: "4A5560" })] }),
  ];
}
const gap = () => new Paragraph({ spacing: { after: 80 }, children: [] });

// ---- content ------------------------------------------------------------------
const body = [
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 1800, after: 200 },
    children: [new TextRun({ text: "Latency-Aware Edge Game Server Placement", bold: true, font: FONT, size: 44 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 },
    children: [new TextRun({ text: "Work report", font: FONT, size: 30, color: "0B7F78" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 },
    children: [new TextRun({ text: "Ankam Charan Teja, Aranya Roy, Nikhil Kumar Reddy, Yashvardhan Deep, Akshit Singh", font: FONT, size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 },
    children: [new TextRun({ text: N.date, font: FONT, size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "Code, data and the full paper: github.com/ankamteja/latency-aware-edge-game-placement", font: FONT, size: 21, color: "4A5560" })] }),
  new Paragraph({ children: [new PageBreak()] }),

  h1("Abstract"),
  p("Online games feel smooth only when the game server answers quickly. To make that happen, game servers are often placed on small \"edge\" servers close to the players. The programs that decide which server a group of players should use usually estimate the delay with a simple formula: the time a message takes to travel over the network, plus the time to send its data. That formula ignores one thing: how busy the server already is."),
  p("We built a small but real test system on one laptop, with four game servers of different sizes and distances, and filled them with automated players. We measured what the players actually experienced and compared it with what the formula and two better models predicted."),
  p([b("Main finding. "), t(`When the nearest server gets crowded, the simple formula still calls it the best choice, and its players end up waiting 18 to 30 seconds for a reply. Models that take server load into account keep the same players at ${N.loadAware}. A model trained on our measurements predicts the delay best, and a version that keeps learning while the system runs handled a server that suddenly slowed down.`)]),

  h1("1. Introduction"),
  h2("1.1 The problem in simple words"),
  p("Think of a map app that always sends you down the shortest road, without looking at traffic. Usually that works. When the short road is jammed, you arrive later than if you had taken a longer, empty road. Edge placement has the same problem: the nearest server is picked because it is close, even when it is already full."),
  p("Edge servers are small, so they fill up fast. When a game server is overloaded it falls behind on its \"ticks\" (the game updates the world 20 times a second), and every player on it starts to lag. The usual formula has no term for this, and because most research tests placement ideas in simulators that use the same formula, the mistake never shows up."),
  h2("1.2 What we wanted to find out"), (newList(), gap()),
  num("How wrong is the simple formula when a nearby server is busy?"),
  num("Can a model that learns from real measurements predict the delay better?"),
  num("Does a better model actually lead to better decisions about where to put players, both in a one-time plan and in a system that keeps adjusting while the game runs?"),
  h2("1.3 Words used in this report"),
  table(["Term", "Meaning"], [
    ["RTT (round-trip time)", "The time for a message to reach the server and come back."],
    ["p95", "The 95th percentile: 95% of messages are faster than this. It shows what the unluckiest players feel, not the average."],
    ["Tick and MSPT", "The game updates 20 times a second, so each update has 50 ms. MSPT is how long one update really takes."],
    ["Load / utilization", "How many players a server has compared with what it can handle (we use 100 players per CPU core)."],
    ["Knee", "The player count at which a server's delay suddenly shoots up."],
    ["Median error", "Half the predictions are closer to the truth than this."],
    ["F1 score", "How well a model answers \"will this server be too slow?\" 1 is perfect, 0 means it never catches a problem."],
  ], [2600, 6400]),

  h1("2. Methodology"),
  h2("2.1 The test system"),
  p("Everything runs on one laptop as five small virtual machines (containers): one \"client\" that plays the role of the players, and four game servers. We made the nearest server the weakest on purpose, so that \"close\" and \"powerful\" pull in opposite directions."),
  table(["Server", "CPU", "Network delay (RTT)", "Role"], [
    ["edge1", "0.5 core", "5 ms", "nearest, weakest"],
    ["edge2", "1 core", "15 ms", "edge"],
    ["edge3", "2 cores", "30 ms", "edge"],
    ["cloud", "4 cores", "40 ms", "farthest, strongest"],
  ], [1800, 1600, 2400, 3200]),
  gap(),
  p("Each server runs a real Minecraft server (Paper 1.21.4). The players are bots that use the real game protocol: they walk, turn and send one chat message every second. The time until that message comes back is the in-game delay a player feels."),
  h2("2.2 Measuring at four depths at once"),
  p("To find out where delay comes from, we measure four things at the same time on the same server:"),
  bullet([b("Ping: "), t("only the network. This is what the formula predicts.")]),
  bullet([b("TCP connection: "), t("network plus the operating system.")]),
  bullet([b("Server status request: "), t("adds the server program itself.")]),
  bullet([b("In-game chat echo: "), t("adds the game's main loop, which is where overload shows up.")]),
  h2("2.3 The measurement grid"),
  p("Each server was tested at a ladder of player counts (edge1 at 1 to 60 players, the others at 1 to 100). Each step lasts 90 seconds after the players settle in. The whole ladder was run four times: two runs were used to build the models and two runs, measured hours later, were kept aside only for testing them."),
  h2("2.4 Three ways to predict delay"),
  bullet([b("Formula (load-blind): "), t("network delay plus data size divided by bandwidth. No load at all.")]),
  bullet([b("Queueing model (M/M/1): "), t("a classic textbook formula where delay grows as a server fills up. We fitted its one number to our data.")]),
  bullet([b("Learned model: "), t("a machine-learning model (gradient-boosted trees) trained on our measurements, using the server size, player count and load.")]),
  p("A fourth version of the learned model keeps correcting itself while the system runs, by comparing what it predicted with what it measured."),
  h2("2.5 Three tests"), (newList(), gap()),
  num([b("Deploy the plan: "), t("for 40, 80, 120 and 160 players, each model chose how to split the players over the four servers. We then actually ran each plan and measured it, twice.")]),
  num([b("Live controller: "), t("a program that watches the servers every 2 seconds and may move one group of 10 players every 10 seconds. The same 13-minute schedule of players arriving and leaving was run with each model in charge, several times each.")]),
  num([b("A server gets slower: "), t("halfway through a run we cut edge1's CPU in half without telling any model, to see which one notices.")]),
  h2("2.6 Keeping the tests fair"),
  bullet("The game's day and night cycle, weather and monsters were switched off, because night-time monsters made one player as costly as forty."),
  bullet("The laptop had to be on charge and in Performance power mode. In the normal power mode the same work cost two to three times more CPU."),
  bullet("Nothing else heavy ran on the laptop during a measurement. A checking script refuses to start if any of these conditions is wrong."),

  h1("3. Implementation"),
  h2("3.1 Tools"),
  table(["Part", "What we used"], [
    ["Virtual network and servers", "containerlab, Linux netem (network delay), Linux cgroups (CPU limits), Docker"],
    ["Game servers", "Paper 1.21.4 Minecraft server"],
    ["Players and probes", "Node.js bots using the mineflayer library; ping, TCP and status probes"],
    ["Data and models", "Python, pandas, scikit-learn"],
    ["Live controller and dashboard", "Python, FastAPI, a web dashboard updated live"],
    ["Paper and slides", "LaTeX (IEEE format), python-pptx"],
  ], [3200, 5800]),
  h2("3.2 How the pieces fit together"), (newList(), gap()),
  num("Bring up the test system and check it (network delays, CPU limits, power mode)."),
  num("Run the measurement grid: bots join each server step by step, every sample is saved."),
  num(`Build the dataset: ${N.cells} measured cells, ${N.rows} rows of 30-second windows.`),
  num("Fit the three models and score them on data they have never seen."),
  num("Compute each model's best plan, deploy it for real and measure it."),
  num("Run the live controller with each model in charge, record every move and every sample."),
  num("One command (rebuild.sh) recreates every table and figure from the raw data."),
  p("Everything, including the raw measurements, the runs that went wrong, 29 automated tests and a replay of the live dashboard, is in the GitHub repository."),

  h1("4. Results"),
  h2("4.1 The network stays the same, the server does not"),
  p("On edge1, the ping time stayed within 0.3 ms of 5 ms no matter how many players joined. The delay players actually felt stayed low up to 40 players and then jumped to 6.7 to 8.6 seconds at 60 players. All of the extra delay came from the busy game server, which is exactly the part the formula leaves out."),
  ...figure("fig1_p95_vs_players.png", "Figure 1. Measured delay (p95) on each server as players are added, compared with the formula's prediction (dashed).", 1260, 774),
  h2("4.2 How well each model predicts"),
  table(["Model", "Median error, tested on other runs", "Median error, on the two held-out runs", "F1 for \"too slow?\" (held-out)"], [
    ["Formula", `${N.cross.analytical} ms`, `${N.heldOut.analytical} ms`, N.f1HeldOut.analytical],
    ["Queueing", `${N.cross.queueing} ms`, `${N.heldOut.queueing} ms`, N.f1HeldOut.queueing],
    ["Learned", `${N.cross.learned} ms`, `${N.heldOut.learned} ms`, N.f1HeldOut.learned],
  ], [1800, 2500, 2500, 2200]),
  gap(),
  p("The learned model predicts best. On the held-out runs its lead over the queueing model is small enough that it could be chance. The formula never predicts that a server will be too slow, so it never catches a problem."),
  h2("4.3 Putting each model's plan into practice"),
  p(`Worst player's delay when each model's plan was actually run (round 1 / round ${N.deployRounds}):`),
  table(["Players", "Formula", "Queueing", "Learned"], N.deploy, [1500, 2600, 2450, 2450]),
  gap(),
  p("From 80 players on, the formula puts too many players on the nearest server and its worst players wait 18 to 30 seconds, about 500 to 1500 times longer than with either load-aware model. In a simulator built on the formula, the same plan would have looked like the best one. The learned and queueing models made almost the same plans here, so in these one-time plans the learned model did not choose better, it only predicted better."),
  ...figure("fig5_deployments.png", "Figure 2. Each model's plan, deployed and measured (log scale). Bars: median of the rounds; dots: each round.", 1260, 774),
  h2("4.4 The live controller"),
  p(`Same 13-minute schedule of players with each model in charge, ${N.live.runs} or more runs each. Worst players' delay, median over the runs (lowest to highest run):`),
  table(["Model in charge", "Worst players' delay", "Time over 100 ms", "Moves"], N.live.rows, [2600, 2800, 1800, 1300]),
  gap(),
  p("The formula never moves anyone, because to it a crowded server looks exactly as fast as an empty one. The queueing model moves players but overloads edge2, because it judges servers only by how full they are. The learned model avoids that, and the self-correcting version keeps the worst players lowest."),
  ...figure("fig6_live_ab.png", "Figure 3. Worst players' delay over time with each model in charge (one typical run each); players arriving and leaving below.", 1280, 832),
  h2("4.5 A server suddenly gets slower"),
  p(`When edge1 lost half its CPU in the middle of a run, the formula, the queueing model and the trained-once learned model kept their players on it, and those players were over 100 ms ${N.drop.offline} of the time afterwards. ${N.drop.liveText}`),
  ...figure("fig7_live_capacity_drop.png", "Figure 4. edge1's CPU is cut at 220 s (dotted line). Top: edge1's delay; middle: players left on edge1; bottom: how much slower the live model thinks edge1 has become.", 1280, 1024),
  h2("4.6 Problems we hit and how we fixed them"),
  table(["Problem", "What we found", "Fix"], [
    ["One player cost as much as forty", "At night the game spawns monsters around every player", "Froze the time at noon, switched monsters off"],
    ["The player program measured itself", "One program running all bots overloaded the client", "At most ten bots per program"],
    ["A whole test run was 2-3x slower", "The laptop had dropped out of Performance power mode", "Checked automatically before every run"],
    ["Some steps cost 1.3-1.6x more CPU", "A browser and analysis scripts were running during the test", "Re-measured on an idle laptop; old data kept as evidence"],
    ["The live model distrusted a healthy server", "It learned from the seconds when players were still logging in", "It now waits 30 s after any change before learning"],
  ], [2500, 3500, 3000]),

  h1("5. Conclusion and Future Work"),
  h2("5.1 Conclusion"),
  bullet("The common placement formula is only right while servers are lightly loaded. Once the nearest server is busy, it is wrong by seconds, not milliseconds."),
  bullet(`Any model that looks at server load avoids the problem: ${N.loadAware} instead of 18 to 30 seconds for the same players on the same hardware.`),
  bullet("A model learned from measurements predicts delay best. In live operation it also chose better than the textbook queueing model, which overloaded a server it judged to be fine."),
  bullet("Server capacity is not fixed: a power setting or a CPU cut can change it while the system runs. Only a model that keeps learning from measurements can follow that."),
  h2("5.2 Limitations"),
  bullet("Everything ran on one laptop, and we chose the server sizes to create the trade-off."),
  bullet("Players are bots, not people, and game monsters were switched off."),
  bullet("Moving players means they disconnect and reconnect (about 6 seconds); real systems would hand over the game state."),
  bullet("Each live test was repeated only a few times, so the exact numbers vary from run to run; the direction of the results is clear."),
  h2("5.3 Future work"),
  bullet("Repeat the tests on separate machines and with more repetitions."),
  bullet("Move a game without disconnecting its players."),
  bullet("Let the model place new players directly instead of only correcting later."),
  bullet("Add other network problems (jitter, packet loss) and real game monsters as extra load."),
];

const doc = new Document({
  creator: "Ankam Charan Teja",
  title: "Latency-Aware Edge Game Server Placement: Work Report",
  styles: {
    default: { document: { run: { font: FONT, size: 23 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, color: "0B4F6C", font: FONT }, paragraph: { outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, color: "0B7F78", font: FONT }, paragraph: { outlineLevel: 1 } },
    ],
  },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
    { reference: "steps", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] },
  ] },
  sections: [{
    properties: { page: { margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18, color: "6B7680" })] })] }) },
    children: body,
  }],
});

Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUT, buf); console.log("wrote", OUT); });

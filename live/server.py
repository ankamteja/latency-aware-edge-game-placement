"""Dashboard and control API for the live placement controller.

    python -m live.server            # http://127.0.0.1:8090

  GET  /                    the dashboard
  GET  /api/state           the current (or last) run's live state
  WS   /ws                  the same state, pushed once a second
  POST /api/run             start a run: {"policy", "scenario", "arrival"}
  POST /api/stop            stop the current run (matches are disconnected)
  POST /api/load            operator load: {"action": "add", "node", "matches"}
                            or {"action": "remove", "matches"[, "node"]}
                            or {"action": "throttle", "node", "cores"} / "restore"
                            or {"action": "join", "matches"}: the model places them
  GET  /api/runs            summaries of every finished run
  GET  /api/runs/{id}       one run's summary, timeline and migrations
  GET  /api/offline         grid curves, deployed placements, model metrics

Only one run at a time, and none while a grid or deployment script is using
the testbed: two load generators on one testbed would measure each other.
"""
import asyncio
import atexit
import csv
import json
import subprocess
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from live import testbed as tb
from live.controller import ARRIVALS, RESULTS, SCENARIOS, Run
from live.policy import POLICIES

REPO = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Edge placement console")
app.mount("/diagrams", StaticFiles(directory=REPO / "docs" / "diagrams"), name="diagrams")
current: dict = {"run": None, "thread": None}
start_lock = threading.Lock()       # check-and-start must be one step


class LoadRequest(BaseModel):
    action: str = "add"          # add | join | remove | throttle | restore
    node: str | None = None
    matches: int = 1
    cores: float | None = None   # throttle: the node's new CPU quota
    source: str = "dashboard"    # dashboard | terminal, shown in the event log


class RunRequest(BaseModel):
    policy: str = "learned"
    scenario: str = "standard"
    arrival: str = "nearest"


def testbed_busy():
    r = subprocess.run(["pgrep", "-f", r"(collect|deploy|grid|capacity|warmup)[.]sh"],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def running():
    t = current["thread"]
    return t is not None and t.is_alive()


def state():
    r = current["run"]
    if r is None:
        last = latest_run()
        return {"status": "idle", "last": last}
    with r.lock:
        s = dict(r.state) if r.state else {"status": r.status, "run": r.id}
    s["status"] = r.status
    return s


def latest_run():
    runs = list_runs()
    return runs[0] if runs else None


def list_runs():
    out = []
    for p in sorted(RESULTS.glob("*/summary.json"), reverse=True):
        try:
            out.append(json.loads(p.read_text()))
        except json.JSONDecodeError:
            continue
    return out


@app.on_event("shutdown")
def shutdown():
    # the run thread is a daemon: without this, stopping the server would
    # leave every match's bots connected to the testbed
    r, t = current["run"], current["thread"]
    if r is not None:
        r.stop_flag.set()
        if t is not None:
            t.join(timeout=10)       # lets the run write its summary
    tb.stop_all()


atexit.register(tb.stop_all)        # last resort if the process dies otherwise


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def api_state():
    return state()


@app.get("/api/options")
def api_options():
    return {"policies": list(POLICIES), "scenarios": SCENARIOS, "arrivals": list(ARRIVALS),
            "busy": testbed_busy(), "running": running()}


@app.post("/api/run")
def api_run(req: RunRequest):
    if req.policy not in POLICIES or req.scenario not in SCENARIOS or req.arrival not in ARRIVALS:
        raise HTTPException(400, "unknown policy, scenario or arrival mode")
    with start_lock:
        if running():
            raise HTTPException(409, "a run is already in progress")
        if testbed_busy():
            raise HTTPException(409, "a grid or deployment script is using the testbed")
        r = Run(req.policy, req.scenario, req.arrival)
        t = threading.Thread(target=r.run, daemon=True, name=r.id)
        current.update(run=r, thread=t)
        t.start()
    return {"run": r.id, "length_s": r.length}


@app.post("/api/stop")
def api_stop():
    r = current["run"]
    if not r or not running():
        raise HTTPException(409, "nothing is running")
    r.stop_flag.set()
    return {"run": r.id, "stopping": True}


@app.post("/api/load")
def api_load(req: LoadRequest):
    r = current["run"]
    if not r or not running():
        raise HTTPException(409, "no run in progress: start one (manual scenario for operator load)")
    if req.action not in ("add", "join", "remove", "throttle", "restore") or not 1 <= req.matches <= 16:
        raise HTTPException(400, "action must be add, join, remove, throttle or restore; matches 1 to 16")
    if req.action not in ("remove", "join") and req.node not in r.nodes:
        raise HTTPException(400, "needs a node: edge1, edge2, edge3 or cloud")
    if req.action == "throttle" and not (req.cores and 0.05 <= req.cores <= r.nodes[req.node]["cores"]):
        raise HTTPException(400, "throttle needs cores between 0.05 and the node's own cores")
    r.commands.put(req.model_dump())
    return {"queued": req.model_dump(), "run": r.id}


@app.get("/api/runs")
def api_runs():
    return list_runs()


@app.get("/api/runs/{run_id}")
def api_run_detail(run_id: str):
    d = RESULTS / run_id
    if not d.is_dir() or "/" in run_id or ".." in run_id:
        raise HTTPException(404, "no such run")
    return {"summary": read_json(d / "summary.json"), "timeline": read_jsonl(d / "timeline.jsonl"),
            "migrations": read_jsonl(d / "migrations.jsonl")}


def read_jsonl(path):
    """Lines of a file that may still be growing: a torn last line is skipped."""
    out = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None



def deployments_by_placement(rows):
    """One row per deployed placement: the median over deployment rounds."""
    groups = {}
    for d in rows:
        groups.setdefault((d["deployment"], d["model"], d["players"]), []).append(d)
    out = []
    for g in groups.values():
        vals = sorted(float(d["measured_worst_p95_ms"]) for d in g)
        r = dict(g[0])
        r["measured_worst_p95_ms"] = str(vals[len(vals) // 2] if len(vals) % 2
                                         else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2)
        r["rounds"] = str(len(g))
        out.append(r)
    return out

def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


@app.get("/api/offline")
def api_offline():
    cells = [r for r in read_csv(REPO / "data" / "cells.csv") if r["run"] in ("grid1", "grid2")]
    curves = {}
    for r in cells:
        curves.setdefault(r["node"], {}).setdefault(int(r["bots"]), []).append(float(r["rtt_p95_ms"]))
    curves = {n: sorted((k, sum(v) / len(v)) for k, v in d.items()) for n, d in curves.items()}
    deploy = read_csv(REPO / "results" / "placement" / "deployments.csv")
    plan = json.loads((REPO / "results" / "placement" / "plan.json").read_text())
    chosen = {e["deployment"] for e in plan["entries"]}
    deploy = deployments_by_placement([d for d in deploy if d["deployment"] in chosen])
    metrics = read_csv(REPO / "results" / "model" / "metrics.csv")
    return {"curves": curves, "deployments": deploy, "metrics": metrics}


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    try:
        while True:
            await sock.send_text(json.dumps(state(), default=str))
            await asyncio.sleep(1.0)
    except (WebSocketDisconnect, RuntimeError):
        return


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8090, log_level="warning")

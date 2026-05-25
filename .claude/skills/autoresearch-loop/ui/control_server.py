"""
Run Control Panel server for autoresearch (shared by /autoresearch-setup and
/autoresearch-loop).

A tiny stdlib-only local web server that acts as a file-based message bus between
the browser control panel and Claude Code (the agent). No third-party deps.

The panel shows one results table (read live from the project's results.tsv, so
the baseline row and every loop iteration appear in the SAME table), with three
buttons:
  • Execute   — run the baseline (setup + first run).      Disabled once a baseline exists.
  • Run loop  — iterate autonomously.                       Enabled after the baseline.
  • Stop      — stop the loop after the current iteration.  Enabled while looping.

Protocol (control files live in --workdir; results.tsv lives in --project-root):
  state.json       written by Claude  {phase, name, branch, metric, direction,
                                        setup_done, baseline_done, loop_running,
                                        best, message}
  execute.json     written by server  {"go": true}        (Execute clicked)
  loop_start.json  written by server  {"go": true}        (Run loop clicked)
  stop.json        written by server  {"stop": true}      (Stop clicked)

Endpoints:
  GET  /            -> index.html
  GET  /state       -> state.json                 (UI polls this)
  GET  /table       -> {header:[...], rows:[[...]]} parsed from results.tsv
  GET  /log         -> tail of run.log (text)
  POST /execute     -> write execute.json,    phase=executing
  POST /loop/start  -> write loop_start.json,  phase=looping (optimistic)
  POST /loop/stop   -> write stop.json,        phase=stopping

Usage:
  python control_server.py --port 8770 --workdir /run/dir --project-root /proj
"""

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
WORKDIR = None
PROJECT_ROOT = None
_lock = threading.Lock()

LOG_TAIL_LINES = 80
MAX_TABLE_BYTES = 2_000_000


def _path(name):
    return os.path.join(WORKDIR, name)


def _read_json(name, default):
    try:
        with open(_path(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(name, obj):
    with _lock:
        with open(_path(name), "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)


def _patch_state(**kw):
    state = _read_json("state.json", {})
    state.update(kw)
    _write_json("state.json", state)


def _read_table():
    path = os.path.join(PROJECT_ROOT, "results.tsv")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(MAX_TABLE_BYTES)
    except (FileNotFoundError, IsADirectoryError):
        return {"header": [], "rows": []}
    lines = [ln for ln in text.splitlines() if ln.strip() != ""]
    if not lines:
        return {"header": [], "rows": []}
    header = lines[0].split("\t")
    rows = [ln.split("\t") for ln in lines[1:]]
    return {"header": header, "rows": rows}


def _read_log_tail():
    state = _read_json("state.json", {})
    log_name = state.get("log_file", "run.log")
    path = os.path.join(PROJECT_ROOT, log_name)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except (FileNotFoundError, IsADirectoryError):
        return ""
    return "\n".join(lines[-LOG_TAIL_LINES:])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            try:
                with open(os.path.join(HERE, "index.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(404, {"error": "index.html not found"})
        elif path == "/state":
            self._send(200, _read_json("state.json", {"phase": "idle"}))
        elif path == "/table":
            self._send(200, _read_table())
        elif path == "/log":
            self._send(200, _read_log_tail(), "text/plain; charset=utf-8")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/execute":
            _write_json("execute.json", {"go": True})
            _patch_state(phase="executing", message="Running the baseline…")
            self._send(200, {"ok": True})
        elif path == "/loop/start":
            # clear any stale stop signal before starting
            try:
                os.remove(_path("stop.json"))
            except FileNotFoundError:
                pass
            _write_json("loop_start.json", {"go": True})
            _patch_state(phase="looping", loop_running=True, message="Starting the loop…")
            self._send(200, {"ok": True})
        elif path == "/loop/stop":
            _write_json("stop.json", {"stop": True})
            _patch_state(phase="stopping", message="Stopping after the current iteration…")
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})


def main():
    global WORKDIR, PROJECT_ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--project-root", required=True)
    args = ap.parse_args()

    WORKDIR = os.path.abspath(args.workdir)
    PROJECT_ROOT = os.path.abspath(args.project_root)
    os.makedirs(WORKDIR, exist_ok=True)
    if not os.path.exists(_path("state.json")):
        _write_json("state.json", {"phase": "idle", "setup_done": False,
                                   "baseline_done": False, "loop_running": False})

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"autoresearch control panel: http://127.0.0.1:{args.port}  "
          f"(workdir={WORKDIR}, project={PROJECT_ROOT})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

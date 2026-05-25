"""
Report viewer server for autoresearch-analyze.

A tiny stdlib-only local web server that acts as a file-based message bus between
the browser report viewer and Claude Code (the agent). No third-party deps.

The viewer shows an Execute button; on click the agent generates the report
(report.py), then the page shows the summary, embeds report.pdf inline, and
offers a Download button.

Protocol (control files live in --workdir; report files live in --project-root):
  state.json     written by Claude  {phase, name, metric, summary, has_report,
                                      report_rev, message}
                 phase: idle | generating | ready | empty | error
  summary.json   written by Claude  the `report.py --json` object (stats)
  execute.json   written by server  {"go": true}     (Execute clicked)

Endpoints:
  GET  /             -> index.html
  GET  /state        -> state.json            (UI polls this)
  GET  /summary      -> summary.json
  GET  /report.pdf   -> PROJECT_ROOT/report.pdf   (application/pdf)
  GET  /progress.png -> PROJECT_ROOT/progress.png (image/png)
  POST /execute      -> write execute.json, phase=generating

Usage:
  python report_server.py --port 8772 --workdir /run/dir --project-root /proj
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

# Only these project-root files may be served (no arbitrary path access).
ALLOWED_FILES = {
    "/report.pdf": ("report.pdf", "application/pdf"),
    "/progress.png": ("progress.png", "image/png"),
}


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
        elif path == "/summary":
            self._send(200, _read_json("summary.json", {}))
        elif path in ALLOWED_FILES:
            fname, ctype = ALLOWED_FILES[path]
            full = os.path.join(PROJECT_ROOT, fname)
            try:
                with open(full, "rb") as f:
                    self._send(200, f.read(), ctype)
            except (FileNotFoundError, IsADirectoryError):
                self._send(404, "not generated yet", "text/plain")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/execute":
            _write_json("execute.json", {"go": True})
            _patch_state(phase="generating", message="Generating the report…")
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})


def main():
    global WORKDIR, PROJECT_ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8772)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--project-root", required=True)
    args = ap.parse_args()

    WORKDIR = os.path.abspath(args.workdir)
    PROJECT_ROOT = os.path.abspath(args.project_root)
    os.makedirs(WORKDIR, exist_ok=True)
    if not os.path.exists(_path("state.json")):
        _write_json("state.json", {"phase": "idle", "has_report": False})

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"autoresearch report viewer: http://127.0.0.1:{args.port}  "
          f"(workdir={WORKDIR}, project={PROJECT_ROOT})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

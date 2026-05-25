"""
Local UI server for autoresearch-generate.

A tiny stdlib-only web server that acts as a file-based message bus between the
browser UI and Claude Code (the agent). No third-party dependencies.

It shows the build plan, an Execute button, the generated files (click each to
read it), the validation result, and a chat box where the user asks for changes
that Claude applies to the files (and to spec.md).

Protocol (control files live in --workdir; generated files live in --project-root):
  state.json     {"phase": "...", "message": "..."}
                 phase: ready | generating | review | working | done
  plan.json      written by Claude    {name, goal, measure, direction,
                                        compute_seconds, kill_seconds, data,
                                        runner, files:[...]}
  manifest.json  written by Claude     {rev, validation:{ok,summary,lines[]},
                                        files:[{path,label,note}], chat:[{role,text}]}
  execute.json   written by server     {"go": true}
  chat.json      written by server     {"text": "..."}
  done.json      written by server     {"done": true}

Endpoints:
  GET  /                 -> index.html
  GET  /state           -> state.json     (UI polls this)
  GET  /plan            -> plan.json
  GET  /manifest        -> manifest.json
  GET  /file?path=REL   -> contents of PROJECT_ROOT/REL  (whitelisted by manifest)
  POST /execute         -> save execute.json, phase=generating
  POST /chat            -> save chat.json,    phase=working
  POST /done            -> phase=done

Usage:
  python generate_server.py --port 8766 --workdir /run/dir --project-root /proj
"""

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
WORKDIR = None
PROJECT_ROOT = None
_lock = threading.Lock()

MAX_FILE_BYTES = 400_000


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


def _set_phase(phase, message=""):
    state = _read_json("state.json", {})
    state["phase"] = phase
    state["message"] = message
    _write_json("state.json", state)


def _manifest_paths():
    """The set of relative paths the UI is allowed to read (the whitelist)."""
    manifest = _read_json("manifest.json", {"files": []})
    return {f.get("path") for f in manifest.get("files", []) if f.get("path")}


def _resolve_in_root(rel):
    """Resolve REL under PROJECT_ROOT, refusing anything that escapes it."""
    if rel not in _manifest_paths():
        return None
    full = os.path.realpath(os.path.join(PROJECT_ROOT, rel))
    root = os.path.realpath(PROJECT_ROOT)
    if full == root or full.startswith(root + os.sep):
        return full
    return None


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

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path, qs = parsed.path, parse_qs(parsed.query)
        if path in ("/", "/index.html"):
            try:
                with open(os.path.join(HERE, "index.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(404, {"error": "index.html not found"})
        elif path == "/state":
            self._send(200, _read_json("state.json", {"phase": "ready"}))
        elif path == "/plan":
            self._send(200, _read_json("plan.json", {}))
        elif path == "/manifest":
            self._send(200, _read_json("manifest.json",
                                       {"rev": 0, "validation": {}, "files": [], "chat": []}))
        elif path == "/file":
            rel = (qs.get("path", [""])[0] or "").strip()
            full = _resolve_in_root(rel)
            if not full:
                return self._send(403, "not allowed", "text/plain")
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    self._send(200, f.read(MAX_FILE_BYTES), "text/plain; charset=utf-8")
            except (FileNotFoundError, IsADirectoryError):
                self._send(404, "not found", "text/plain")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/execute":
            _write_json("execute.json", {"go": True})
            _set_phase("generating", "Generating the experiment…")
            self._send(200, {"ok": True})
        elif path == "/chat":
            _write_json("chat.json", self._body())
            _set_phase("working", "Applying your change…")
            self._send(200, {"ok": True})
        elif path == "/done":
            _set_phase("done")
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})


def main():
    global WORKDIR, PROJECT_ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--project-root", required=True)
    args = ap.parse_args()

    WORKDIR = os.path.abspath(args.workdir)
    PROJECT_ROOT = os.path.abspath(args.project_root)
    os.makedirs(WORKDIR, exist_ok=True)
    if not os.path.exists(_path("state.json")):
        _write_json("state.json", {"phase": "ready"})

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"autoresearch generate UI: http://127.0.0.1:{args.port}  "
          f"(workdir={WORKDIR}, project={PROJECT_ROOT})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

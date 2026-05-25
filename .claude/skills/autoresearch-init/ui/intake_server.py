"""
Local intake UI server for autoresearch-init.

A tiny stdlib-only web server that acts as a file-based message bus between the
browser UI and Claude Code (the agent). No third-party dependencies.

Protocol (all files live in --workdir):
  state.json          {"phase": "...", "message": "..."}
                      phase: intake | processing | questions | review | confirmed | closed
  intake.json         written by server on form submit   {idea, name?, code?, code_path?, domain?}
  questions.json      written by Claude                   {"intro"?, "questions":[{"id","text","hint"}]}
  answers.json        written by server on chat submit    {"answers": {id: text}}
  variations.json     written by Claude                   {"selected":N, "variations":[{"id","label","note"}]}
  spec_<N>.md         written by Claude                   full spec text for variation N (review)
  change_request.json written by server                   {"text": "...", "base_id": N}
  confirm.json        written by server                   {"id": N}

Endpoints:
  GET  /                 -> index.html
  GET  /state           -> state.json            (UI polls this)
  GET  /questions       -> questions.json
  GET  /variations      -> variations.json
  GET  /variation?id=N  -> spec_<N>.md (text/markdown)
  POST /intake          -> save intake.json,  phase=processing
  POST /answers         -> save answers.json, phase=processing
  POST /change          -> save change_request.json, phase=processing
  POST /confirm         -> save confirm.json, phase=confirmed
  POST /done            -> phase=closed

Usage:
  python intake_server.py --port 8765 --workdir /path/to/runtime
"""

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
WORKDIR = None
_lock = threading.Lock()


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


def _safe_id(raw):
    """Only allow integer ids -> spec_<n>.md (no path traversal)."""
    try:
        return str(int(raw))
    except (TypeError, ValueError):
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
            self._send(200, _read_json("state.json", {"phase": "intake"}))
        elif path == "/questions":
            self._send(200, _read_json("questions.json", {"questions": []}))
        elif path == "/variations":
            self._send(200, _read_json("variations.json", {"selected": None, "variations": []}))
        elif path == "/variation":
            vid = _safe_id(qs.get("id", [None])[0])
            if vid is None:
                return self._send(400, "bad id", "text/plain")
            try:
                with open(_path(f"spec_{vid}.md"), "r", encoding="utf-8") as f:
                    self._send(200, f.read(), "text/markdown; charset=utf-8")
            except FileNotFoundError:
                self._send(404, "variation not ready", "text/plain")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/intake":
            _write_json("intake.json", self._body())
            _set_phase("processing", "Analyzing your idea...")
            self._send(200, {"ok": True})
        elif path == "/answers":
            _write_json("answers.json", self._body())
            _set_phase("processing", "Updating the setup...")
            self._send(200, {"ok": True})
        elif path == "/change":
            _write_json("change_request.json", self._body())
            _set_phase("processing", "Creating a new variation...")
            self._send(200, {"ok": True})
        elif path == "/confirm":
            _write_json("confirm.json", self._body())
            _set_phase("confirmed", "Confirmed. Finishing up...")
            self._send(200, {"ok": True})
        elif path == "/done":
            _set_phase("closed")
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})


def main():
    global WORKDIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--workdir", required=True)
    args = ap.parse_args()

    WORKDIR = os.path.abspath(args.workdir)
    os.makedirs(WORKDIR, exist_ok=True)
    if not os.path.exists(_path("state.json")):
        _write_json("state.json", {"phase": "intake"})

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"autoresearch intake UI: http://127.0.0.1:{args.port}  (workdir={WORKDIR})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

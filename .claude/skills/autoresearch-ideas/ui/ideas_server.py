"""
Idea-basket viewer server for autoresearch-ideas.

A stdlib-only local web server acting as a file-based message bus between the
browser and Claude Code (the agent). It shows the spec goal, the live basket
(read from idea.md), the documents in idea_basket/ with their visited status,
and lets the user:

  • set a paper limit and Execute → the agent collects (<10) goal-aligned ideas
    from up to N papers and the dropped documents, marking each used file visited;
  • Upload documents straight into idea_basket/;
  • propose their own idea → the agent fixes the grammar (3-4 sentences), judges
    alignment with the goal, and returns an opinion; the user then Adds it (or
    Force-adds it even if it doesn't align);
  • view idea.md.

Idea collection / proposal review need judgement, so the AGENT does them via the
bus; uploads and reads are handled directly by the server.

Protocol (control files in --workdir; idea.md / idea_basket in --project-root):
  state.json     written by Claude  {phase, name, goal, paper_limit, message}
                 phase: idle | collecting | thinking | ready
  execute.json   written by server  {"paper_limit": N}
  propose.json   written by server  {"text": "<user's raw idea>"}
  proposal.json  written by Claude   {pending, original, cleaned, aligned, opinion}
  confirm.json   written by server  {"accept": bool, "force": bool}

Endpoints:
  GET  /            -> index.html
  GET  /state       -> state.json
  GET  /ideas       -> {ideas:[...], counts:{...}, files:[{name,status,ideas}]}
  GET  /idea_md     -> raw idea.md text
  GET  /proposal    -> proposal.json
  POST /execute     -> write execute.json,  phase=collecting
  POST /upload?name=F -> save raw body bytes into idea_basket/F
  POST /propose     -> write propose.json,  phase=thinking
  POST /confirm     -> write confirm.json

Usage:
  python ideas_server.py --port 8774 --workdir /run/dir --project-root /proj
"""

import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # import idea_lib from the skill dir
import idea_lib as L  # noqa: E402

WORKDIR = None
PROJECT_ROOT = None
_lock = threading.Lock()
MAX_UPLOAD = 30 * 1024 * 1024  # 30 MB


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
    s = _read_json("state.json", {})
    s.update(kw)
    _write_json("state.json", s)


def _ideas_payload():
    try:
        ideas = L.read_ideas(PROJECT_ROOT)
    except Exception:
        ideas = []
    for i in ideas:
        i["source_cat"] = L.classify_source(i.get("source", ""))
    return {"ideas": ideas, "counts": L.counts(ideas),
            "files": L.file_statuses(PROJECT_ROOT)}


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

    def _json_body(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            return {}

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
        elif path == "/ideas":
            self._send(200, _ideas_payload())
        elif path == "/idea_md":
            p = L.idea_path(PROJECT_ROOT)
            try:
                with open(p, encoding="utf-8") as f:
                    self._send(200, f.read(), "text/plain; charset=utf-8")
            except FileNotFoundError:
                self._send(200, "(idea.md not created yet)", "text/plain; charset=utf-8")
        elif path == "/proposal":
            self._send(200, _read_json("proposal.json", {"pending": False}))
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path, qs = parsed.path, parse_qs(parsed.query)
        if path == "/execute":
            body = self._json_body()
            try:
                limit = max(1, min(100, int(body.get("paper_limit", 10))))
            except (TypeError, ValueError):
                limit = 10
            _write_json("execute.json", {"paper_limit": limit})
            _patch_state(phase="collecting", paper_limit=limit,
                         message=f"Collecting up to ~9 ideas from ≤{limit} papers + your files…")
            self._send(200, {"ok": True})
        elif path == "/upload":
            name = (qs.get("name", [""])[0] or "").strip()
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0 or n > MAX_UPLOAD:
                return self._send(400, {"error": "empty or too-large file"})
            data = self.rfile.read(n)
            try:
                saved = L.save_upload(PROJECT_ROOT, name, data)
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            self._send(200, {"ok": True, "saved": saved})
        elif path == "/propose":
            body = self._json_body()
            text = (body.get("text") or "").strip()
            if not text:
                return self._send(400, {"error": "empty idea"})
            _write_json("propose.json", {"text": text})
            try:
                os.remove(_path("proposal.json"))
            except FileNotFoundError:
                pass
            _patch_state(phase="thinking", message="Reviewing your idea against the goal…")
            self._send(200, {"ok": True})
        elif path == "/confirm":
            self._write_confirm(self._json_body())
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})

    def _write_confirm(self, body):
        _write_json("confirm.json", {"accept": bool(body.get("accept")),
                                     "force": bool(body.get("force"))})
        _patch_state(phase="collecting" if body.get("accept") else "idle",
                     message="Adding your idea…" if body.get("accept") else "Discarded the proposed idea.")


def main():
    global WORKDIR, PROJECT_ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8774)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--project-root", required=True)
    args = ap.parse_args()

    WORKDIR = os.path.abspath(args.workdir)
    PROJECT_ROOT = os.path.abspath(args.project_root)
    os.makedirs(WORKDIR, exist_ok=True)
    if not os.path.exists(_path("state.json")):
        _write_json("state.json", {"phase": "idle", "paper_limit": 10})

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"autoresearch ideas UI: http://127.0.0.1:{args.port}  "
          f"(workdir={WORKDIR}, project={PROJECT_ROOT})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

"""
Conductor server — the single UI that drives the WHOLE pipeline and embeds every
stage's UI functions (init intake, generate build+chat, setup, ideas, loop,
analyze) scoped per project.

stdlib-only file-bus between the browser dashboard and Claude Code (the agent).
Reads (project lists, results, idea.md, generated files, report, summaries) are
served directly; anything that needs the model (intake Q&A, generate fill/chat,
idea collection / grammar+alignment review, loop iterations, report narratives)
is requested via control files the agent watches.

Control files live under  <workdir>/<slug>/  (and  <workdir>/_new/  for the
new-project intake, before a slug exists).  Projects live under <workspace>.

Run:
  python conductor_server.py --port 8780 --workdir /run --workspace /projects
"""

import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import conductor_lib as C  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "autoresearch-ideas"))
try:
    import idea_lib as I  # noqa: E402
except Exception:
    I = None

WORKDIR = None
WORKSPACE = None
_lock = threading.Lock()
MAX_UPLOAD = 30 * 1024 * 1024


# --------------------------- control-file helpers ---------------------------

def _dir(slug):
    d = os.path.join(WORKDIR, slug)
    os.makedirs(d, exist_ok=True)
    return d


def _rj(slug, name, default):
    try:
        with open(os.path.join(_dir(slug), name), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _wj(slug, name, obj):
    with _lock:
        with open(os.path.join(_dir(slug), name), "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)


def _rtext(slug, name, default=""):
    try:
        with open(os.path.join(_dir(slug), name), encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return default


def _task_read():
    try:
        with open(os.path.join(WORKDIR, "task.json"), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"active": False, "phase": "idle", "steps": []}


def _task_busy():
    t = _task_read()
    return bool(t.get("active")) and t.get("phase") in ("queued", "running")


def _task_set(slug, stage, message):
    import time as _t
    with _lock:
        with open(os.path.join(WORKDIR, "task.json"), "w", encoding="utf-8") as f:
            json.dump({"active": True, "slug": slug, "stage": stage, "phase": "queued",
                       "message": message, "steps": [], "started": _t.strftime("%H:%M:%S"),
                       "updated": _t.strftime("%H:%M:%S")}, f, indent=2)


def _safe_root(slug):
    slug = os.path.basename((slug or "").strip())
    if not slug:
        return None
    root = os.path.realpath(os.path.join(WORKSPACE, slug))
    base = os.path.realpath(WORKSPACE)
    if root == base or root.startswith(base + os.sep):
        return root if os.path.isdir(root) else None
    return None


# ------------------------------- reads --------------------------------------

def _project_detail(root):
    stages, spec, d, running = C.stage_status(root)
    meta = C.read_conductor_json(root)
    return dict(
        slug=os.path.basename(root),
        name=(spec["name"] if spec else os.path.basename(root)),
        description=(meta.get("description") or (spec["description"] if spec else "")),
        metric=(spec["metric"] if spec else ""), direction=(spec["direction"] if spec else ""),
        run_tag=meta.get("run_tag", ""), loop_running=running,
        has_report=os.path.isfile(os.path.join(root, "report.pdf")),
        stages=stages, summary=(C.results_summary(root, spec) if spec else {}),
    )


def _ideas_payload(root):
    if not I:
        return {"ideas": [], "counts": {}, "files": []}
    ideas = I.read_ideas(root)
    for i in ideas:
        i["source_cat"] = I.classify_source(i.get("source", ""))
    return {"ideas": ideas, "counts": I.counts(ideas), "files": I.file_statuses(root)}


def _gen_file(root, slug, rel):
    manifest = _rj(slug, "gen_manifest.json", {"files": []})
    allowed = {f.get("path") for f in manifest.get("files", []) if f.get("path")}
    if rel not in allowed:
        return None
    full = os.path.realpath(os.path.join(root, rel))
    if full == os.path.realpath(root) or full.startswith(os.path.realpath(root) + os.sep):
        return full
    return None


# ------------------------------- HTTP ---------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
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
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            return {}

    # ----- GET -----
    def do_GET(self):
        u = urlparse(self.path)
        p, qs = u.path, parse_qs(u.query)
        slug = qs.get("slug", [""])[0]

        if p in ("/", "/index.html"):
            try:
                with open(os.path.join(HERE, "ui", "index.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            except FileNotFoundError:
                return self._send(404, {"error": "index.html missing"})
        if p == "/api/state":
            return self._send(200, _rj("", "state.json", {"phase": "idle"}))
        if p == "/api/task":
            return self._send(200, _task_read())
        if p == "/api/projects":
            return self._send(200, {"projects": [C.project_card(r) for r in C.find_projects(WORKSPACE)]})

        # --- new-project intake (no slug yet) ---
        if p == "/api/new/state":
            return self._send(200, _rj("_new", "state.json", {"phase": "idle"}))
        if p == "/api/new/questions":
            return self._send(200, _rj("_new", "questions.json", {}))
        if p == "/api/new/variations":
            return self._send(200, _rj("_new", "variations.json", {"variations": []}))
        if p == "/api/new/spec":
            return self._send(200, _rtext("_new", f"spec_{qs.get('id',['1'])[0]}.md",
                                          "(spec not rendered yet)"), "text/plain; charset=utf-8")

        # everything below needs a real project
        root = _safe_root(slug)
        if p.startswith("/api/") and p not in ("/api/new",) and root is None and p != "/api/report":
            return self._send(404, {"error": "no such project"})

        if p == "/api/project":
            return self._send(200, _project_detail(root))
        if p == "/api/results":
            h, rows = C.read_results(root)
            return self._send(200, {"header": h, "rows": rows})
        if p == "/api/spec":
            return self._send(200, _rtext_proj(os.path.join(root, ".autoresearch"), "spec.md",
                                               "(no spec yet)"), "text/plain; charset=utf-8")
        if p == "/api/report":
            root = _safe_root(slug)
            try:
                with open(os.path.join(root, "report.pdf"), "rb") as f:
                    return self._send(200, f.read(), "application/pdf")
            except (FileNotFoundError, TypeError, IsADirectoryError):
                return self._send(404, "no report", "text/plain")
        if p == "/api/gen/plan":
            return self._send(200, _rj(slug, "gen_plan.json", {}))
        if p == "/api/gen/manifest":
            return self._send(200, _rj(slug, "gen_manifest.json", {"rev": 0, "files": [], "validation": {}, "chat": []}))
        if p == "/api/gen/file":
            full = _gen_file(root, slug, (qs.get("path", [""])[0] or "").strip())
            if not full:
                return self._send(403, "not allowed", "text/plain")
            try:
                with open(full, encoding="utf-8", errors="replace") as f:
                    return self._send(200, f.read(400_000), "text/plain; charset=utf-8")
            except (FileNotFoundError, IsADirectoryError):
                return self._send(404, "not found", "text/plain")
        if p == "/api/setup/result":
            return self._send(200, _rj(slug, "setup_result.json", {}))
        if p == "/api/run/state":
            return self._send(200, _rj(slug, "run_state.json", {"phase": "idle"}))
        if p == "/api/run/log":
            return self._send(200, _rtext_proj(root, "run.log"), "text/plain; charset=utf-8")
        if p == "/api/ideas/list":
            return self._send(200, _ideas_payload(root))
        if p == "/api/ideas/idea_md":
            return self._send(200, _rtext_proj(root, "idea.md", "(no idea.md yet)"), "text/plain; charset=utf-8")
        if p == "/api/ideas/proposal":
            return self._send(200, _rj(slug, "ideas_proposal.json", {"pending": False}))
        if p == "/api/analyze/summary":
            return self._send(200, _rj(slug, "analyze_summary.json", {}))
        return self._send(404, {"error": "not found"})

    # ----- POST -----
    def do_POST(self):
        u = urlparse(self.path)
        p, qs = u.path, parse_qs(u.query)
        slug = qs.get("slug", [""])[0]

        # uploads read raw bytes (not JSON)
        if p == "/api/ideas/upload":
            root = _safe_root(slug)
            if not root or not I:
                return self._send(404, {"error": "no such project"})
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0 or n > MAX_UPLOAD:
                return self._send(400, {"error": "empty or too-large file"})
            data = self.rfile.read(n)
            try:
                saved = I.save_upload(root, (qs.get("name", [""])[0] or "").strip(), data)
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            return self._send(200, {"ok": True, "saved": saved})

        b = self._body()

        # --- new-project intake ---
        if p == "/api/new/start":
            if not (b.get("idea") or "").strip():
                return self._send(400, {"error": "an idea is required"})
            if _task_busy():
                return self._send(409, {"error": "Claude is busy — one task at a time"})
            _task_set("(new)", "init", "Creating the project…")
            _wj("_new", "intake.json", {"idea": b.get("idea", "").strip(),
                                        "name": (b.get("name") or "").strip(),
                                        "domain": (b.get("domain") or "").strip()})
            _wj("_new", "state.json", {"phase": "thinking", "message": "Reading your idea…"})
            return self._send(200, {"ok": True})
        if p == "/api/new/answers":
            _wj("_new", "answers.json", {"answers": b.get("answers", {})})
            _wj("_new", "state.json", {"phase": "thinking", "message": "Applying your answers…"})
            return self._send(200, {"ok": True})
        if p == "/api/new/change":
            _wj("_new", "change_request.json", {"text": (b.get("text") or "").strip(),
                                                "base_id": b.get("base_id", 1)})
            _wj("_new", "state.json", {"phase": "thinking", "message": "Revising the spec…"})
            return self._send(200, {"ok": True})
        if p == "/api/new/confirm":
            _wj("_new", "confirm.json", {"id": b.get("id", 1)})
            _wj("_new", "state.json", {"phase": "confirming", "message": "Creating the project…"})
            return self._send(200, {"ok": True})

        # --- per-project stages ---
        root = _safe_root(slug)
        if root is None:
            return self._send(404, {"error": "no such project"})

        # gating check for the discrete stage runs
        stages, _, _, running = C.stage_status(root)
        sd = {s["key"]: s for s in stages}

        def gated(stage):
            return stage in sd and sd[stage]["enabled"]

        if p == "/api/gen/execute":
            if not gated("generate"):
                return self._send(409, {"error": "generate is locked"})
            if _task_busy():
                return self._send(409, {"error": "Claude is busy — one task at a time"})
            _task_set(os.path.basename(root), "generate", "Generating the experiment…")
            _wj(slug, "gen_execute.json", {"go": True}); return self._send(200, {"ok": True})
        if p == "/api/gen/chat":
            _wj(slug, "gen_chat.json", {"text": (b.get("text") or "").strip()}); return self._send(200, {"ok": True})
        if p == "/api/gen/done":
            _wj(slug, "gen_done.json", {"done": True}); return self._send(200, {"ok": True})
        if p == "/api/setup/execute":
            if not gated("setup"):
                return self._send(409, {"error": "setup is locked"})
            if _task_busy():
                return self._send(409, {"error": "Claude is busy — one task at a time"})
            _task_set(os.path.basename(root), "setup", "Preparing the run…")
            _wj(slug, "setup_execute.json", {"go": True}); return self._send(200, {"ok": True})
        if p == "/api/ideas/execute":
            if not gated("ideas"):
                return self._send(409, {"error": "ideas is locked"})
            if _task_busy():
                return self._send(409, {"error": "Claude is busy — one task at a time"})
            try:
                lim = max(1, min(100, int(b.get("paper_limit", 10))))
            except (TypeError, ValueError):
                lim = 10
            _task_set(os.path.basename(root), "ideas", f"Collecting ideas from ≤{lim} papers…")
            _wj(slug, "ideas_execute.json", {"paper_limit": lim}); return self._send(200, {"ok": True})
        if p == "/api/ideas/propose":
            _wj(slug, "ideas_propose.json", {"text": (b.get("text") or "").strip()})
            try:
                os.remove(os.path.join(_dir(slug), "ideas_proposal.json"))
            except FileNotFoundError:
                pass
            return self._send(200, {"ok": True})
        if p == "/api/ideas/confirm":
            _wj(slug, "ideas_confirm.json", {"accept": bool(b.get("accept")), "force": bool(b.get("force"))})
            return self._send(200, {"ok": True})
        if p == "/api/run/loop/start":
            if running:
                return self._send(409, {"error": "loop already running"})
            if not gated("loop"):
                return self._send(409, {"error": "loop is locked"})
            if _task_busy():
                return self._send(409, {"error": "Claude is busy — one task at a time"})
            try:
                os.remove(os.path.join(_dir(slug), "loop_stop.json"))
            except FileNotFoundError:
                pass
            _task_set(os.path.basename(root), "loop", "Starting the loop…")
            _wj(slug, "loop_start.json", {"go": True})
            _wj(slug, "run_state.json", {"phase": "looping", "loop_running": True, "message": "Starting the loop…"})
            return self._send(200, {"ok": True})
        if p == "/api/run/loop/stop":
            _wj(slug, "loop_stop.json", {"stop": True})
            _wj(slug, "run_state.json", {"phase": "stopping", "loop_running": True, "message": "Stopping after the current iteration…"})
            return self._send(200, {"ok": True})
        if p == "/api/analyze/execute":
            if not gated("analyze"):
                return self._send(409, {"error": "analyze is locked (need a kept run)"})
            if _task_busy():
                return self._send(409, {"error": "Claude is busy — one task at a time"})
            _task_set(os.path.basename(root), "analyze", "Generating the report…")
            _wj(slug, "analyze_execute.json", {"go": True}); return self._send(200, {"ok": True})
        return self._send(404, {"error": "not found"})


def _rtext_proj(root, name, default=""):
    try:
        with open(os.path.join(root, name), encoding="utf-8", errors="replace") as f:
            txt = f.read()
        if name == "run.log":
            txt = "\n".join(txt.splitlines()[-80:])
        return txt
    except (FileNotFoundError, TypeError, IsADirectoryError):
        return default


def main():
    global WORKDIR, WORKSPACE
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8780)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--workspace", required=True)
    a = ap.parse_args()
    WORKDIR = os.path.abspath(a.workdir)
    WORKSPACE = os.path.abspath(a.workspace)
    os.makedirs(WORKDIR, exist_ok=True)
    os.makedirs(WORKSPACE, exist_ok=True)
    if not os.path.exists(os.path.join(_dir(""), "state.json")):
        _wj("", "state.json", {"phase": "idle"})
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"autoresearch conductor: http://127.0.0.1:{a.port}  (workdir={WORKDIR}, workspace={WORKSPACE})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""OpenClaw bridge for the autoresearch conductor.

Replaces Claude Code's `Monitor` tool. Watches the conductor WORKDIR for request
files the dashboard writes (see conductor_server.py do_POST) and dispatches each,
one at a time, to the OpenClaw agent (which has the autoresearch-conductor skill).
Per-request model: each request -> one short agent session -> writes results ->
deletes the request file. The loop stage is bridge-controlled (one iteration per
dispatch) so no single agent session has to run indefinitely.
"""
import argparse
import json
import os
import subprocess
import time

# Request files the dashboard writes that need an agent to act.
REQUESTS = {
    "intake.json", "answers.json", "change_request.json", "confirm.json",
    "gen_execute.json", "gen_chat.json", "gen_chat_confirm.json",
    "setup_execute.json",
    "ideas_execute.json", "ideas_propose.json", "ideas_confirm.json",
    "analyze_execute.json",
}
# gen_done.json is a no-op handler -> just delete it, don't spend an agent call.
NOOP = {"gen_done.json"}

AGENT_CMD_DEFAULT = "node /app/dist/index.js"


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def write_json(path, obj):
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
    except OSError:
        pass


def dispatch(agent_cmd, agent_id, workdir, workspace, req_path, basename, content, timeout):
    rel = os.path.relpath(req_path, workdir)
    slug = os.path.dirname(rel) or "(root)"
    msg = (
        "You are the autoresearch-conductor running under OpenClaw in PER-REQUEST mode "
        "(do NOT monitor or loop; handle exactly one request, then stop).\n"
        f"Conductor WORKDIR={workdir}\n"
        f"Workspace (holds project folders; skills are in {workspace}/skills)={workspace}\n"
        "A dashboard control request appeared:\n"
        f"  file: {req_path}\n"
        f"  group/slug: {slug}\n"
        f"  type: {basename}\n"
        f"  content: {json.dumps(content)}\n\n"
        "Follow the autoresearch-conductor skill's handler for THIS request type. "
        "Drive the other skills' controlled scripts as the skill specifies, write the "
        "result/manifest/state files back into WORKDIR so the dashboard can read them, "
        "keep task.json current via task.py, and DELETE this request file when done. "
        "Handle only this one request, then stop."
    )
    session = f"conductor-{basename.replace('.json', '')}-{int(time.time())}"
    cmd = agent_cmd.split() + ["agent", "--agent", agent_id, "--session-key", session, "--message", msg]
    print(f"[bridge] dispatch {basename} (slug={slug}, session={session})", flush=True)
    try:
        r = subprocess.run(cmd, timeout=timeout)
        print(f"[bridge] agent exit={r.returncode} for {basename}", flush=True)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"[bridge] TIMEOUT handling {basename}", flush=True)
        return False


def handle_loop(agent_cmd, agent_id, workdir, workspace, loop_start_path, timeout, poll):
    sdir = os.path.dirname(loop_start_path)
    slug = os.path.relpath(sdir, workdir)
    stop_path = os.path.join(sdir, "loop_stop.json")
    try:
        os.remove(loop_start_path)
    except OSError:
        pass
    print(f"[bridge] LOOP start (slug={slug})", flush=True)
    i = 0
    while True:
        if os.path.exists(stop_path):
            try:
                os.remove(stop_path)
            except OSError:
                pass
            write_json(os.path.join(sdir, "run_state.json"),
                       {"phase": "idle", "loop_running": False, "message": "Loop stopped."})
            print("[bridge] LOOP stop requested -> ending", flush=True)
            break
        i += 1
        write_json(os.path.join(sdir, "run_state.json"),
                   {"phase": "looping", "loop_running": True, "message": f"Running iteration {i}…"})
        msg = (
            "You are the autoresearch-conductor running under OpenClaw. Run EXACTLY ONE "
            "loop iteration for the project, then stop (the bridge controls the loop).\n"
            f"WORKDIR={workdir}\nWorkspace={workspace}\nProject slug={slug}\n"
            "Per the autoresearch-conductor loop handler: pick a pending idea, edit the "
            "editable file, run one iteration (run_iter.py), update the basket and "
            f"run_state.json (this is iteration {i}), and keep task.json current. "
            "Do NOT loop yourself; one iteration only, then stop."
        )
        cmd = agent_cmd.split() + ["agent", "--agent", agent_id,
                                   "--session-key", f"conductor-loop-{int(time.time())}", "--message", msg]
        print(f"[bridge] LOOP iter {i}", flush=True)
        try:
            subprocess.run(cmd, timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"[bridge] LOOP iter {i} TIMEOUT", flush=True)
        time.sleep(poll)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--agent", default="main")
    ap.add_argument("--agent-cmd", default=AGENT_CMD_DEFAULT)
    ap.add_argument("--poll", type=float, default=1.5)
    ap.add_argument("--timeout", type=int, default=3600)
    a = ap.parse_args()
    workdir = os.path.abspath(a.workdir)
    workspace = os.path.abspath(a.workspace)
    os.makedirs(workdir, exist_ok=True)
    print(f"[bridge] watching {workdir} (agent={a.agent}, cmd='{a.agent_cmd}')", flush=True)

    seen = {}  # req_path -> mtime already dispatched (dedup until file changes)
    while True:
        loop_starts, loop_stops, reqs, noops = [], [], [], []
        for root, _dirs, files in os.walk(workdir):
            for f in files:
                p = os.path.join(root, f)
                if f == "loop_start.json":
                    loop_starts.append(p)
                elif f == "loop_stop.json":
                    loop_stops.append(p)
                elif f in NOOP:
                    noops.append(p)
                elif f in REQUESTS:
                    reqs.append((p, f))

        for p in noops:
            try:
                os.remove(p)
                print(f"[bridge] removed no-op {os.path.basename(p)}", flush=True)
            except OSError:
                pass

        # Stale stop: a loop_stop with no matching loop_start -> consume and reset state
        if loop_stops and not loop_starts:
            for p in loop_stops:
                try:
                    os.remove(p)
                except OSError:
                    pass
                write_json(os.path.join(os.path.dirname(p), "run_state.json"),
                           {"phase": "idle", "loop_running": False, "message": "Loop stopped."})
                print(f"[bridge] consumed stale loop_stop ({os.path.relpath(p, workdir)})", flush=True)

        if loop_starts:
            handle_loop(a.agent_cmd, a.agent, workdir, workspace,
                        sorted(loop_starts)[0], a.timeout, a.poll)
            seen.clear()
            continue

        reqs.sort()
        dispatched = False
        for p, f in reqs:
            try:
                mt = os.path.getmtime(p)
            except OSError:
                continue
            if seen.get(p) == mt:
                continue
            ok = dispatch(a.agent_cmd, a.agent, workdir, workspace, p, f, read_json(p), a.timeout)
            if os.path.exists(p):
                seen[p] = mt
                print(f"[bridge] WARNING: {f} not deleted by agent (ok={ok}); "
                      "won't re-dispatch until it changes", flush=True)
            else:
                seen.pop(p, None)
            dispatched = True
            break  # one at a time; re-scan from the top

        if not dispatched:
            time.sleep(a.poll)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Controlled task-status updater for the conductor.

Claude runs ONE task at a time. This writes a single $WORKDIR/task.json that the
dashboard polls to show a waiting/loading/progress indicator on the active stage
(and to disable the other stages while a task runs). The conductor server sets it
to `queued` when a stage is requested; the agent moves it through `running` (with
step messages) and finally `done`/`error`/`clear`.

task.json shape:
  {active, slug, stage, phase, message, progress, steps:[{t,done}], started, updated}
  phase: queued | running | done | error

Usage:
  python task.py <WORKDIR> set   --slug S --stage G [--phase running] [--message M] [--progress 0.4]
  python task.py <WORKDIR> step  --message M [--done]      # append a step + set message
  python task.py <WORKDIR> done  [--message M]             # clears active
  python task.py <WORKDIR> error --message M               # clears active
  python task.py <WORKDIR> clear
  python task.py <WORKDIR> get
"""

import argparse
import json
import os
import time

PHASES = ("queued", "running", "done", "error")


def _path(wd):
    return os.path.join(wd, "task.json")


def read(wd):
    try:
        with open(_path(wd), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"active": False, "phase": "idle", "steps": []}


def write(wd, d):
    d["updated"] = time.strftime("%H:%M:%S")
    with open(_path(wd), "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("set")
    p.add_argument("--slug"); p.add_argument("--stage")
    p.add_argument("--phase", choices=PHASES, default="running")
    p.add_argument("--message", default=""); p.add_argument("--progress", type=float)

    p = sub.add_parser("step")
    p.add_argument("--message", required=True); p.add_argument("--done", action="store_true")

    p = sub.add_parser("done"); p.add_argument("--message", default="Done.")
    p = sub.add_parser("error"); p.add_argument("--message", required=True)
    sub.add_parser("clear")
    sub.add_parser("get")

    a = ap.parse_args()
    wd = a.workdir
    os.makedirs(wd, exist_ok=True)
    d = read(wd)

    if a.cmd == "set":
        new_task = (d.get("slug") != a.slug) or (d.get("stage") != a.stage) or not d.get("active")
        d = {"active": True, "slug": a.slug or d.get("slug"), "stage": a.stage or d.get("stage"),
             "phase": a.phase, "message": a.message,
             "progress": a.progress, "steps": [] if new_task else d.get("steps", []),
             "started": time.strftime("%H:%M:%S") if new_task else d.get("started")}
        write(wd, d)
    elif a.cmd == "step":
        d.setdefault("steps", [])
        # mark the previous step done, append the new one
        if d["steps"] and not d["steps"][-1].get("done"):
            d["steps"][-1]["done"] = True
        d["steps"].append({"t": a.message, "done": bool(a.done)})
        d["message"] = a.message
        d["active"] = True
        d["phase"] = "running"
        write(wd, d)
    elif a.cmd == "done":
        for s in d.get("steps", []):
            s["done"] = True
        d.update(active=False, phase="done", message=a.message)
        write(wd, d)
    elif a.cmd == "error":
        d.update(active=False, phase="error", message=a.message)
        write(wd, d)
    elif a.cmd == "clear":
        write(wd, {"active": False, "phase": "idle", "steps": []})
    elif a.cmd == "get":
        print(json.dumps(read(wd), indent=2))


if __name__ == "__main__":
    main()

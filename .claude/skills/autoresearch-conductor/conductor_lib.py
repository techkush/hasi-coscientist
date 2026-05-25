#!/usr/bin/env python3
"""
Shared helpers for the controlled autoresearch-conductor skill.

The conductor is the master that runs the whole pipeline through one UI. This
module discovers projects in a workspace, reads each project's metadata, and
computes the per-stage status + enable-gating that the UI renders:

    init -> generate -> setup -> ideas(optional) -> loop -> analyze

A stage is enabled only when its prerequisite is done. While the loop is running
every other stage is locked (the UI offers Stop instead).

State is derived from the real filesystem (so it always reflects reality) and a
small per-project JSON (.autoresearch/conductor.json) holds the metadata the UI
lists. conductor_server.py and the skill import from here.
"""

import json
import os
import re
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))

UNFILLED_MARKERS = (">>> GENERATE", "TODO(generate)", "NotImplementedError")
LOOP_LOCK = os.path.join(".autoresearch", "loop.lock")
CONDUCTOR_JSON = os.path.join(".autoresearch", "conductor.json")

# (key, label, optional)
STAGES = [
    ("init", "Init", False),
    ("generate", "Generate", False),
    ("setup", "Setup", False),
    ("ideas", "Ideas", True),
    ("loop", "Loop", False),
    ("analyze", "Analyze", False),
]


# ---------------------------------------------------------------------------
# spec parsing
# ---------------------------------------------------------------------------

def _section(text, name):
    m = re.search(r"^##\s+" + re.escape(name) + r"\s*$(.*?)(?=^##\s|\Z)",
                  text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _field(block, key):
    m = re.search(r"^-\s*" + re.escape(key) + r"\s*:\s*(.*)$", block, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _first_sentence(text, cap=160):
    one = " ".join((text or "").split())
    dot = one.find(". ")
    if dot != -1:
        one = one[:dot + 1]
    return one[:cap].strip()


def parse_spec(root):
    p = os.path.join(root, ".autoresearch", "spec.md")
    if not os.path.isfile(p):
        return None
    text = open(p, encoding="utf-8").read()
    name_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    name = name_m.group(1).strip() if name_m else os.path.basename(root)
    idea_m = re.search(r"^>\s*Idea:\s*(.+)$", text, re.MULTILINE)
    description = idea_m.group(1).strip() if idea_m else _first_sentence(_section(text, "Goal"))
    measure = _section(text, "Measure")
    metric = _field(measure, "name") or "score"
    direction = (_field(measure, "direction") or "higher_is_better").strip().lower()
    files = _section(text, "Files")
    editable = _field(files, "editable") or "run.py"
    readonly = _field(files, "readonly_fixed") or "prepare.py"
    return dict(name=name, description=description, metric=metric,
                direction=direction, higher=("higher" in direction),
                editable=editable, readonly=readonly)


# ---------------------------------------------------------------------------
# git + filesystem probes
# ---------------------------------------------------------------------------

def _git(root, *args):
    return subprocess.run(["git", "-C", root, *args],
                          capture_output=True, text=True, check=False)


def current_branch(root):
    r = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else ""


def tag_exists(root, name):
    return _git(root, "rev-parse", "--verify", "-q",
                f"refs/tags/{name}").returncode == 0


def _has_unfilled(path):
    if not os.path.isfile(path):
        return True
    txt = open(path, encoding="utf-8").read()
    return any(m in txt for m in UNFILLED_MARKERS)


def _ideas_count(root):
    p = os.path.join(root, "idea.md")
    if not os.path.isfile(p):
        return 0
    body = _section(open(p, encoding="utf-8").read(), "Ideas")
    return len(re.findall(r"^\s*-\s*\[", body, re.MULTILINE))


def read_results(root):
    p = os.path.join(root, "results.tsv")
    if not os.path.isfile(p):
        return [], []
    lines = [ln for ln in open(p, encoding="utf-8").read().splitlines() if ln.strip()]
    if not lines:
        return [], []
    header = lines[0].split("\t")
    rows = [ln.split("\t") for ln in lines[1:]]
    return header, rows


def results_summary(root, spec):
    header, rows = read_results(root)
    if not header:
        return dict(total=0, keep=0, discard=0, crash=0, baseline=None, best=None)
    try:
        si = header.index("status")
    except ValueError:
        si = len(header) - 2
    mi = header.index(spec["metric"]) if spec["metric"] in header else 1
    keep = discard = crash = 0
    keep_vals, first = [], None
    for r in rows:
        st = (r[si] if si < len(r) else "").lower()
        try:
            v = float(r[mi]) if mi < len(r) else None
        except ValueError:
            v = None
        if st == "keep":
            keep += 1
            if v is not None:
                keep_vals.append(v)
        elif st == "discard":
            discard += 1
        elif st == "crash":
            crash += 1
        if first is None and st != "crash" and v is not None:
            first = v
    best = None
    if keep_vals:
        best = max(keep_vals) if spec["higher"] else min(keep_vals)
    return dict(total=len(rows), keep=keep, discard=discard, crash=crash,
                baseline=first, best=best)


def loop_running(root):
    return os.path.isfile(os.path.join(root, LOOP_LOCK))


# ---------------------------------------------------------------------------
# per-project metadata json
# ---------------------------------------------------------------------------

def read_conductor_json(root):
    p = os.path.join(root, CONDUCTOR_JSON)
    try:
        return json.load(open(p, encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_conductor_json(root, **fields):
    os.makedirs(os.path.join(root, ".autoresearch"), exist_ok=True)
    data = read_conductor_json(root)
    data.update(fields)
    data.setdefault("created", time.strftime("%Y-%m-%d %H:%M"))
    data["updated"] = time.strftime("%Y-%m-%d %H:%M")
    with open(os.path.join(root, CONDUCTOR_JSON), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return data


# ---------------------------------------------------------------------------
# stage status + gating
# ---------------------------------------------------------------------------

def _done_flags(root, spec):
    init_done = spec is not None
    gen_done = (init_done
                and not _has_unfilled(os.path.join(root, spec["editable"]))
                and not _has_unfilled(os.path.join(root, spec["readonly"])))
    setup_done = (gen_done
                  and current_branch(root).startswith("autoresearch/")
                  and tag_exists(root, "ar-baseline"))
    ideas_done = setup_done and _ideas_count(root) > 0
    _, rows = read_results(root)
    has_rows = len(rows) > 0
    summ = results_summary(root, spec) if spec else {"keep": 0}
    has_keep = summ.get("keep", 0) > 0
    report_done = os.path.isfile(os.path.join(root, "report.pdf"))
    return dict(init=init_done, generate=gen_done, setup=setup_done,
                ideas=ideas_done, loop=has_rows, analyze=(has_keep and report_done),
                has_rows=has_rows, has_keep=has_keep)


def stage_status(root):
    """Return ordered stage descriptors with done/running/enabled/status."""
    spec = parse_spec(root)
    running = loop_running(root)
    d = _done_flags(root, spec)
    prereq = {
        "init": True,
        "generate": d["init"],
        "setup": d["generate"],
        "ideas": d["setup"],
        "loop": d["setup"],          # ideas is optional
        "analyze": d["has_keep"],
    }
    out = []
    for key, label, optional in STAGES:
        done = d.get(key, False)
        is_running = running and key == "loop"
        if key == "loop":
            enabled = d["setup"]  # start when ready; while running -> Stop
        else:
            enabled = prereq[key] and not running
        if is_running:
            status = "running"
        elif done:
            status = "done"
        elif enabled:
            status = "optional" if optional else "available"
        else:
            status = "locked"
        out.append(dict(key=key, label=label, optional=optional, done=done,
                        running=is_running, enabled=enabled, status=status))
    return out, spec, d, running


# ---------------------------------------------------------------------------
# project discovery
# ---------------------------------------------------------------------------

def find_projects(workspace):
    """Project roots = immediate subdirs of workspace containing .autoresearch/spec.md
    (plus workspace itself if it is a project)."""
    workspace = os.path.abspath(workspace)
    roots = []
    if os.path.isfile(os.path.join(workspace, ".autoresearch", "spec.md")):
        roots.append(workspace)
    if os.path.isdir(workspace):
        for entry in sorted(os.listdir(workspace)):
            cand = os.path.join(workspace, entry)
            if os.path.isdir(cand) and os.path.isfile(
                os.path.join(cand, ".autoresearch", "spec.md")
            ):
                roots.append(cand)
    return roots


def project_card(root):
    spec = parse_spec(root)
    meta = read_conductor_json(root)
    stages, _, d, running = stage_status(root)
    done_count = sum(1 for s in stages if s["done"])
    return dict(
        slug=os.path.basename(root),
        name=(spec["name"] if spec else os.path.basename(root)),
        description=(meta.get("description") or (spec["description"] if spec else "")),
        created=meta.get("created", ""),
        loop_running=running,
        done_count=done_count, total_stages=len(stages),
        stage_keys=[s["key"] for s in stages if s["done"]],
    )

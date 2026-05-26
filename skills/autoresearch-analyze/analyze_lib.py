#!/usr/bin/env python3
"""
Shared helpers for the controlled autoresearch-analyze skill.

report.py imports from here so the spec parsing, direction-aware statistics,
provenance lookup, and the results.tsv contract are defined once and stay
consistent with the rest of the pipeline (init/generate/loop).

Read-only: nothing here modifies the ledger, the experiment, or git state.
"""

import math
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

STD_COLUMNS = {"commit", "status", "description"}
TIME_KEYS = {"runtime_s", "elapsed_s", "wall_s", "seconds", "time_s"}


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------

def find_project_root(start):
    start = os.path.abspath(start)
    if os.path.isfile(os.path.join(start, ".autoresearch", "spec.md")):
        return start
    hits = []
    if os.path.isdir(start):
        for entry in sorted(os.listdir(start)):
            cand = os.path.join(start, entry)
            if os.path.isdir(cand) and os.path.isfile(
                os.path.join(cand, ".autoresearch", "spec.md")
            ):
                hits.append(cand)
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise SystemExit("Multiple specs found; pass PROJECT_ROOT explicitly:\n  " +
                         "\n  ".join(hits))
    raise SystemExit(f"No .autoresearch/spec.md found at or under {start}")


def section(text, name):
    m = re.search(r"^##\s+" + re.escape(name) + r"\s*$(.*?)(?=^##\s|\Z)",
                  text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def field(block, key):
    m = re.search(r"^-\s*" + re.escape(key) + r"\s*:\s*(.*)$", block, re.MULTILINE)
    return m.group(1).strip() if m else ""


def is_none(v):
    return (v or "").strip().lower() in {"", "none", "n/a", "na"}


def parse_secondary_metrics(value):
    if is_none(value):
        return []
    out = []
    for name, pat in re.findall(r"([A-Za-z_][\w]*)\s*\(([^)]*)\)", value):
        out.append(name)
    if out:
        return out
    for chunk in re.split(r"[|,]", value):
        nm = chunk.strip()
        if re.fullmatch(r"[A-Za-z_]\w*", nm):
            out.append(nm)
    return out


def parse_spec(root):
    text = open(os.path.join(root, ".autoresearch", "spec.md"), encoding="utf-8").read()
    name_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    name = name_m.group(1).strip() if name_m else "Experiment"

    measure = section(text, "Measure")
    metric = field(measure, "name") or "score"
    direction = (field(measure, "direction") or "higher_is_better").strip().lower()
    secondaries = parse_secondary_metrics(field(measure, "secondary_metrics"))

    logging = section(text, "Logging (results.tsv)")
    cols_raw = field(logging, "columns")
    columns = [c.strip() for c in cols_raw.split(",") if c.strip()]

    files = section(text, "Files")
    log_file = field(files, "log_file") or "run.log"

    goal = " ".join(section(text, "Goal").split())

    return dict(root=root, name=name, metric=metric, direction=direction,
                higher=("higher" in direction), secondaries=secondaries,
                columns=columns, log_file=log_file, goal=goal)


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

def to_float(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def read_ledger(root):
    """Return (header, rows). Each row is a dict + 'exp_n' (1-based) + 'status_l'."""
    path = os.path.join(root, "results.tsv")
    if not os.path.exists(path):
        return [], []
    lines = [ln for ln in open(path, encoding="utf-8").read().splitlines() if ln.strip()]
    if not lines:
        return [], []
    header = lines[0].split("\t")
    rows = []
    for i, ln in enumerate(lines[1:], start=1):
        cells = ln.split("\t")
        d = {header[j]: (cells[j] if j < len(cells) else "") for j in range(len(header))}
        d["exp_n"] = i
        d["status_l"] = d.get("status", "").strip().lower()
        rows.append(d)
    return header, rows


def numeric_metric_cols(spec, header):
    """Plottable metric columns: primary + declared secondaries present in the
    header, excluding std and time/elapsed columns."""
    out = []
    for c in header:
        if c.lower() in STD_COLUMNS or c.lower() in TIME_KEYS or c == "exp_n":
            continue
        if c == spec["metric"] or c in spec["secondaries"]:
            out.append(c)
    # ensure primary first
    if spec["metric"] in out:
        out.remove(spec["metric"])
        out.insert(0, spec["metric"])
    return out


def best_value(values, higher):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return max(vals) if higher else min(vals)


def stats(spec, rows):
    metric, higher = spec["metric"], spec["higher"]
    keeps = [r for r in rows if r["status_l"] == "keep"]
    disc = [r for r in rows if r["status_l"] == "discard"]
    crash = [r for r in rows if r["status_l"] == "crash"]
    noncrash = [r for r in rows if r["status_l"] != "crash"]

    baseline = None
    for r in noncrash:
        v = to_float(r.get(metric))
        if v is not None:
            baseline = v
            baseline_row = r
            break

    kvals = [to_float(r.get(metric)) for r in keeps]
    best = best_value(kvals, higher)
    best_row = None
    if best is not None:
        for r in keeps:
            if to_float(r.get(metric)) == best:
                best_row = r
                break

    abs_imp = pct = None
    if baseline is not None and best is not None:
        abs_imp = (best - baseline) if higher else (baseline - best)
        pct = (abs_imp / abs(baseline) * 100) if baseline != 0 else None

    # what stuck: keep rows with per-step delta vs previous kept measure
    stuck = []
    prev = None
    for r in keeps:
        v = to_float(r.get(metric))
        delta = None if (prev is None or v is None) else (v - prev)
        stuck.append({"row": r, "value": v, "delta": delta})
        if v is not None:
            prev = v

    kd = len(keeps) + len(disc)
    return dict(
        total=len(rows), keep=len(keeps), discard=len(disc), crash=len(crash),
        keep_rate=(len(keeps) / kd if kd else None),
        baseline=baseline, best=best, best_row=best_row,
        abs_imp=abs_imp, pct=pct, stuck=stuck, keeps=keeps,
    )


def metric_series(rows, col):
    """Non-crash (exp_n, value, status) points for a column."""
    out = []
    for r in rows:
        if r["status_l"] == "crash":
            continue
        v = to_float(r.get(col))
        if v is not None:
            out.append((r["exp_n"], v, r["status_l"]))
    return out


def total_runtime(spec, header, rows):
    tcol = next((c for c in header if c.lower() in TIME_KEYS), None)
    if not tcol:
        return None, None
    secs = sum(to_float(r.get(tcol)) or 0.0 for r in rows)
    return secs, tcol


# ---------------------------------------------------------------------------
# Provenance: findings.md + idea.md
# ---------------------------------------------------------------------------

def parse_findings(root):
    """Map short commit -> {prev, new, change, source}. Tolerant of format
    variants: an optional leading '- ', backticks around the hash, and either
    '->' or the Unicode arrow '→'."""
    path = os.path.join(root, "findings.md")
    out = {}
    if not os.path.exists(path):
        return out
    pat = re.compile(
        r"\s*-?\s*commit\s+`?(\w+)`?\s+—\s+\S+\s+(.+?)\s+(?:->|→)\s+(.+?)"
        r"\s+—\s+change:\s*(.*?)\s+—\s+source:\s*(.*)$")
    for ln in open(path, encoding="utf-8"):
        m = pat.match(ln)
        if m:
            out[m.group(1)] = dict(prev=m.group(2).strip(), new=m.group(3).strip(),
                                   change=m.group(4).strip(), source=m.group(5).strip())
    return out


def classify_source(source):
    """Bucket a free-text provenance into a display category (shared vocabulary
    with autoresearch-ideas)."""
    s = (source or "").lower()
    if not s:
        return "AI agent"
    if "basket" in s:
        return "Idea basket"
    if any(k in s for k in ("user", "human")):
        return "Human suggestion"
    if s.startswith("doc:") or " doc:" in s or "document" in s:
        return "Document"
    if any(k in s for k in ("paper", "arxiv", "doi")):
        return "Paper"
    if any(k in s for k in ("http", "www", "web")):
        return "Web"
    return "AI agent"


def parse_idea_counts(root):
    """Count basket ideas by status. New format: a '## Ideas' section with inline
    'status:' fields. Falls back to the legacy Pending/Applied sections."""
    path = os.path.join(root, "idea.md")
    if not os.path.exists(path):
        return None
    text = open(path, encoding="utf-8").read()
    if re.search(r"^##\s+Ideas\s*$", text, re.M):
        body = section(text, "Ideas")
        found = [s.lower() for s in
                 re.findall(r"status:\s*(pending|doing|selected|discarded)", body, re.I)]
        c = {s: found.count(s) for s in ("pending", "doing", "selected", "discarded")}
        c["total"] = len(found)
        return c
    applied = len(re.findall(r"^\s*-\s*\[x\]", section(text, "Applied"), re.M | re.I))
    pending = len(re.findall(r"^\s*-\s*\[ \]", section(text, "Pending"), re.M))
    return dict(pending=pending, applied=applied)


def git_commit_datetime(root, short):
    r = subprocess.run(["git", "-C", root, "show", "-s", "--format=%ci", short],
                       capture_output=True, text=True, check=False)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().splitlines()[0]
    return None

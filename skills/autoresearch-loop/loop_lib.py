#!/usr/bin/env python3
"""
Shared helpers for the controlled autoresearch-loop skill.

preflight.py (read-only gate) and run_iter.py (the per-iteration engine) import
from here so the spec parsing, measure extraction, keep/discard decision, and
results.tsv contract are defined once and stay correct.

The parsing mirrors autoresearch-generate/scaffold.py and autoresearch-init's
spec.template.md so the loop reads exactly the spec that built the experiment.
"""

import math
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

STD_COLUMNS = {"commit", "status", "description"}
TIME_KEYS = {"runtime_s", "elapsed_s", "wall_s", "seconds", "time_s"}
BASELINE_TAG = "ar-baseline"  # the rewind floor, created by autoresearch-setup


# ---------------------------------------------------------------------------
# Spec location & parsing
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
    """Return [(name, grep_pattern), ...]."""
    if is_none(value):
        return []
    out = []
    for name, pat in re.findall(r"([A-Za-z_][\w]*)\s*\(([^)]*)\)", value):
        out.append((name, pat.strip()))
    if out:
        return out
    for chunk in re.split(r"[|,]", value):
        nm = chunk.strip()
        if re.fullmatch(r"[A-Za-z_]\w*", nm):
            out.append((nm, f"^{nm}:"))
    return out


def parse_spec(root):
    path = os.path.join(root, ".autoresearch", "spec.md")
    text = open(path, encoding="utf-8").read()

    name_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    name = name_m.group(1).strip() if name_m else "Experiment"

    measure = section(text, "Measure")
    metric = field(measure, "name") or "score"
    direction = (field(measure, "direction") or "higher_is_better").strip().lower()
    grep_pattern = field(measure, "grep_pattern") or f"^{metric}:"
    extract_regex = field(measure, "extract_regex") or \
        rf"^{re.escape(metric)}:\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)"
    secondaries = parse_secondary_metrics(field(measure, "secondary_metrics"))

    files = section(text, "Files")
    editable_raw = field(files, "editable") or "run.py"
    editable = [e.strip() for e in re.split(r"[,\s]+", editable_raw) if e.strip()]
    readonly = field(files, "readonly_fixed") or "prepare.py"
    runner = field(files, "runner_command") or f"python {editable[0]}"
    log_file = field(files, "log_file") or "run.log"

    tb = section(text, "Time budget")
    tmin_raw = field(tb, "timeout_minutes") or "5"
    m = re.search(r"[0-9]*\.?[0-9]+", tmin_raw)
    timeout_minutes = float(m.group(0)) if m else 5.0

    logging = section(text, "Logging (results.tsv)")
    cols_raw = field(logging, "columns")
    columns = [c.strip() for c in cols_raw.split(",") if c.strip()] or \
              ["commit", metric, "status", "description"]

    return dict(
        root=root, name=name, metric=metric, direction=direction,
        higher=("higher" in direction), grep_pattern=grep_pattern,
        extract_regex=extract_regex, secondaries=secondaries,
        editable=editable, readonly=readonly, runner=runner,
        log_file=log_file, timeout_minutes=timeout_minutes, columns=columns,
    )


# ---------------------------------------------------------------------------
# Measure extraction — take the LAST match, preferring the final result block
# ---------------------------------------------------------------------------

def extract_one(text, grep_pattern, extract_regex):
    """Last value whose line matches grep_pattern; prefer the section after the
    last `---` separator (the scaffolded final result block). Returns float or
    None (no match, or non-finite)."""
    parts = re.split(r"(?m)^---\s*$", text)
    chunks = [parts[-1]] if len(parts) > 1 else []
    chunks.append(text)  # fall back to whole log
    for chunk in chunks:
        vals = []
        for line in chunk.splitlines():
            if re.search(grep_pattern, line):
                mm = re.search(extract_regex, line)
                if mm:
                    try:
                        v = float(mm.group(1))
                    except (ValueError, IndexError):
                        continue
                    if math.isfinite(v):
                        vals.append(v)
        if vals:
            return vals[-1]
    return None


def read_measures(spec, log_text):
    """Return {metric: value_or_None, secondary...: value_or_None}."""
    out = {spec["metric"]: extract_one(log_text, spec["grep_pattern"], spec["extract_regex"])}
    for nm, pat in spec["secondaries"]:
        rx = rf"{pat}\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)"
        out[nm] = extract_one(log_text, pat, rx)
    return out


# ---------------------------------------------------------------------------
# results.tsv ledger
# ---------------------------------------------------------------------------

def read_ledger(root):
    """Return (header_list, [row_dict, ...]). row_dict maps column->str."""
    path = os.path.join(root, "results.tsv")
    if not os.path.exists(path):
        return [], []
    lines = open(path, encoding="utf-8").read().splitlines()
    if not lines:
        return [], []
    header = lines[0].split("\t")
    rows = []
    for ln in lines[1:]:
        if not ln.strip():
            continue
        cells = ln.split("\t")
        rows.append({header[i]: (cells[i] if i < len(cells) else "")
                     for i in range(len(header))})
    return header, rows


def has_data_rows(root):
    _, rows = read_ledger(root)
    return len(rows) > 0


def current_best(spec):
    """Best measure among keep rows (direction-aware), or None."""
    _, rows = read_ledger(spec["root"])
    metric = spec["metric"]
    vals = []
    for r in rows:
        if r.get("status", "").strip().lower() != "keep":
            continue
        try:
            v = float(r.get(metric, ""))
        except (ValueError, TypeError):
            continue
        if math.isfinite(v):
            vals.append(v)
    if not vals:
        return None
    return max(vals) if spec["higher"] else min(vals)


def is_improvement(spec, value, best):
    if value is None or not math.isfinite(value):
        return False
    if best is None:
        return True
    return value > best if spec["higher"] else value < best


def sanitize(text):
    """Tabs/newlines would corrupt the TSV; collapse to spaces."""
    return re.sub(r"\s+", " ", (text or "").replace("\t", " ")).strip()


def build_row(spec, commit, measures, status, description, runtime_s):
    """Assemble the results.tsv row in the spec's column order."""
    cells = []
    for col in spec["columns"]:
        low = col.lower()
        if low == "commit":
            cells.append(commit)
        elif low == "status":
            cells.append(status)
        elif low == "description":
            cells.append(sanitize(description))
        elif low in TIME_KEYS:
            cells.append(f"{runtime_s:.2f}")
        elif col == spec["metric"] or col in dict(spec["secondaries"]):
            v = measures.get(col)
            cells.append("0" if (status == "crash" or v is None) else f"{v:.6f}")
        else:
            cells.append("0")
    return "\t".join(cells)


def append_row(root, row):
    path = os.path.join(root, "results.tsv")
    with open(path, "a", encoding="utf-8") as f:
        f.write(row + "\n")


# ---------------------------------------------------------------------------
# git plumbing
# ---------------------------------------------------------------------------

def git(root, *args, check=True):
    return subprocess.run(["git", "-C", root, *args],
                          capture_output=True, text=True, check=check)


def current_branch(root):
    return git(root, "rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.strip()


def short_head(root):
    return git(root, "rev-parse", "--short", "HEAD", check=False).stdout.strip()


def full_head(root):
    return git(root, "rev-parse", "HEAD", check=False).stdout.strip()


def is_tracked(root, path):
    return git(root, "ls-files", "--error-unmatch", path, check=False).returncode == 0


def path_has_changes(root, path):
    r = git(root, "status", "--porcelain", "--", path, check=False)
    return bool(r.stdout.strip())


def tag_exists(root, name):
    return git(root, "rev-parse", "--verify", "-q", f"refs/tags/{name}",
               check=False).returncode == 0


def is_ancestor(root, ancestor, descendant):
    return git(root, "merge-base", "--is-ancestor", ancestor, descendant,
               check=False).returncode == 0

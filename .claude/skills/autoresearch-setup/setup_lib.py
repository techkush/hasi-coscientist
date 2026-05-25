#!/usr/bin/env python3
"""
Shared helpers for the controlled autoresearch-setup skill.

Both prepare_run.py (the mutating materializer) and readiness.py (the read-only
gate) import from here so the spec parsing, git plumbing, dependency resolution,
and .gitignore / results.tsv contracts are defined once and stay consistent.

This module deliberately mirrors the parsing in
autoresearch-generate/scaffold.py so setup reads exactly the spec that generate
built from.
"""

import importlib.util
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

STD_COLUMNS = {"commit", "status", "description"}
TIME_KEYS = {"runtime_s", "elapsed_s", "wall_s", "seconds", "time_s"}

# Baseline reference: every run branch forks from this tag, never from a stray
# HEAD. prepare_run creates it at the baseline commit; the loop never moves it.
BASELINE_TAG = "ar-baseline"

# The canonical ignore set every prepared run must have. Order is preserved when
# we append missing lines. The two .autoresearch lines KEEP spec.md under version
# control (reproducible baseline) while ignoring the rest of the runtime dir.
CANONICAL_IGNORE = [
    "results.tsv",
    "run.log",
    "__pycache__/",
    "*.pyc",
    "idea.md",
    "findings.md",
    "idea_basket/",
    ".autoresearch/*",
    "!.autoresearch/spec.md",
]

# pip distribution name -> top-level import name, for the cases where they differ.
# Used so the dependency check doesn't report an installed package as missing.
PIP_TO_IMPORT = {
    "scikit-learn": "sklearn",
    "scikit-image": "skimage",
    "pillow": "PIL",
    "opencv-python": "cv2",
    "opencv-python-headless": "cv2",
    "opencv-contrib-python": "cv2",
    "pyyaml": "yaml",
    "beautifulsoup4": "bs4",
    "python-dateutil": "dateutil",
    "msgpack-python": "msgpack",
    "protobuf": "google.protobuf",
    "python-dotenv": "dotenv",
    "attrs": "attr",
    "faiss-cpu": "faiss",
    "faiss-gpu": "faiss",
    "huggingface-hub": "huggingface_hub",
    "sentence-transformers": "sentence_transformers",
}


# ---------------------------------------------------------------------------
# Spec location & parsing
# ---------------------------------------------------------------------------

def find_project_root(start):
    """Return the folder containing .autoresearch/spec.md (cwd or one level down)."""
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
        raise SystemExit(
            "Multiple specs found; pass PROJECT_ROOT explicitly:\n  " + "\n  ".join(hits)
        )
    raise SystemExit(f"No .autoresearch/spec.md found at or under {start}")


def section(text, name):
    m = re.search(
        r"^##\s+" + re.escape(name) + r"\s*$(.*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    return m.group(1).strip() if m else ""


def field(block, key):
    m = re.search(r"^-\s*" + re.escape(key) + r"\s*:\s*(.*)$", block, re.MULTILINE)
    return m.group(1).strip() if m else ""


def is_none(v):
    return (v or "").strip().lower() in {"", "none", "n/a", "na"}


def parse_spec(root):
    """Parse the spec fields setup needs. Returns a dict."""
    path = os.path.join(root, ".autoresearch", "spec.md")
    text = open(path, encoding="utf-8").read()

    name_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    name = name_m.group(1).strip() if name_m else "Experiment"

    measure = section(text, "Measure")
    metric = field(measure, "name") or "score"
    grep_pattern = field(measure, "grep_pattern") or f"^{metric}:"

    data = section(text, "Data / benchmark")
    data_field = field(data, "data")
    data_present = not is_none(data_field)
    location = field(data, "location")
    preparation = field(data, "preparation")

    files = section(text, "Files")
    editable = field(files, "editable") or "run.py"
    readonly = field(files, "readonly_fixed") or "prepare.py"
    runner = field(files, "runner_command") or f"python {editable}"
    log_file = field(files, "log_file") or "run.log"
    has_code = field(files, "has_user_code").lower().startswith("y")
    source_code = field(files, "source_code")

    deps_raw = section(text, "Dependencies")
    deps = [
        d.strip()
        for d in re.split(r"[,\n]", deps_raw)
        if d.strip() and not d.strip().lower().startswith("standard library")
    ]

    logging = section(text, "Logging (results.tsv)")
    cols_raw = field(logging, "columns")
    columns = [c.strip() for c in cols_raw.split(",") if c.strip()] or [
        "commit",
        metric,
        "status",
        "description",
    ]

    return dict(
        root=root,
        name=name,
        metric=metric,
        grep_pattern=grep_pattern,
        data_present=data_present,
        data_field=data_field,
        location=location,
        preparation=preparation,
        editable=editable,
        readonly=readonly,
        runner=runner,
        log_file=log_file,
        has_code=has_code,
        source_code=source_code,
        deps=deps,
        columns=columns,
    )


def baseline_paths(spec):
    """Files that belong in the baseline commit (explicit, never `git add -A`)."""
    root = spec["root"]
    candidates = [
        spec["editable"],
        spec["readonly"],
        "program.md",
        "README.md",
        ".gitignore",
        "requirements.txt",
        os.path.join(".autoresearch", "spec.md"),
    ]
    return [p for p in candidates if os.path.exists(os.path.join(root, p))]


# ---------------------------------------------------------------------------
# .gitignore contract
# ---------------------------------------------------------------------------

def data_ignore_entry(location):
    """The .gitignore line for the data location, or None when it cannot/should
    not be ignored (URL, absolute path, home path, or no data location)."""
    if is_none(location):
        return None
    loc = location.strip()
    if loc.lower().startswith(("http://", "https://", "s3://", "gs://")):
        return None
    if loc.startswith("~") or os.path.isabs(loc):
        return None  # lives outside the repo — nothing to ignore
    norm = loc.lstrip("./").rstrip("/")
    if not norm:
        return None
    return norm + "/"


def required_ignore_lines(spec):
    """Canonical ignore set plus the data line (if the data is in-repo)."""
    lines = list(CANONICAL_IGNORE)
    data_line = data_ignore_entry(spec["location"]) if spec["data_present"] else None
    if data_line and data_line not in lines:
        lines.append(data_line)
    return lines


def gitignore_status(spec):
    """Return (existing_lines, missing_lines, has_bare_autoresearch)."""
    path = os.path.join(spec["root"], ".gitignore")
    existing = []
    if os.path.exists(path):
        existing = [ln.rstrip("\n") for ln in open(path, encoding="utf-8")]
    existing_set = {ln.strip() for ln in existing}
    missing = [ln for ln in required_ignore_lines(spec) if ln not in existing_set]
    has_bare = ".autoresearch/" in existing_set
    return existing, missing, has_bare


# ---------------------------------------------------------------------------
# results.tsv contract
# ---------------------------------------------------------------------------

def expected_header(spec):
    return "\t".join(spec["columns"])


def results_status(spec):
    """One of: missing | ok | stale_header_only | stale_has_data."""
    path = os.path.join(spec["root"], "results.tsv")
    if not os.path.exists(path):
        return "missing"
    lines = open(path, encoding="utf-8").read().splitlines()
    if not lines:
        return "missing"
    header = lines[0].rstrip()
    has_data = any(ln.strip() for ln in lines[1:])
    if header == expected_header(spec):
        return "ok"
    return "stale_has_data" if has_data else "stale_header_only"


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def dist_to_import(dep):
    """Strip version/extras from a requirement and map to its import name."""
    base = re.split(r"[<>=!~;\[ ]", dep.strip(), 1)[0].strip().lower()
    return PIP_TO_IMPORT.get(base, base.replace("-", "_"))


def dep_available(dep):
    name = dist_to_import(dep)
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def missing_deps(spec):
    return [d for d in spec["deps"] if not dep_available(d)]


# ---------------------------------------------------------------------------
# git plumbing
# ---------------------------------------------------------------------------

def git(root, *args, check=True):
    return subprocess.run(
        ["git", "-C", root, *args],
        capture_output=True,
        text=True,
        check=check,
    )


def is_git_repo(root):
    r = git(root, "rev-parse", "--is-inside-work-tree", check=False)
    return r.returncode == 0 and r.stdout.strip() == "true"


def has_commits(root):
    return git(root, "rev-parse", "--verify", "-q", "HEAD", check=False).returncode == 0


def current_branch(root):
    r = git(root, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    return r.stdout.strip() if r.returncode == 0 else ""


def ref_exists(root, ref):
    return git(root, "rev-parse", "--verify", "-q", ref, check=False).returncode == 0


def branch_exists(root, name):
    return ref_exists(root, f"refs/heads/{name}")


def tag_exists(root, name):
    return ref_exists(root, f"refs/tags/{name}")


def tracked_dirty(root):
    """True if any TRACKED file has staged/unstaged changes (untracked ignored)."""
    r = git(root, "status", "--porcelain", "--untracked-files=no", check=False)
    return bool(r.stdout.strip())

#!/usr/bin/env python3
"""
Shared helpers for the controlled autoresearch-ideas skill.

basket.py (the CLI materializer) and ui/ideas_server.py both import from here so
the idea.md format, the status lifecycle, the source classification, and the
git-untracked contract are defined once and never drift.

idea.md uses a single `## Ideas` section with one line per idea and an inline
`status:` field (so a script can update status without moving lines between
sections):

    - [ ] <one-line idea> — status: pending — source: user
    - [~] <one-line idea> — status: doing — source: paper:"Title" <link> — commit: <hash>
    - [x] <one-line idea> — status: selected — source: doc:file.pdf — commit: <hash> — result: 18.2 -> 19.4
    - [-] <one-line idea> — status: discarded — source: agent — commit: <hash>

Status lifecycle:  pending -> doing -> selected (kept)  |  discarded (reverted).
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

STATUSES = ["pending", "doing", "selected", "discarded"]
CHECKBOX = {"pending": " ", "doing": "~", "selected": "x", "discarded": "-"}
IDEAS_SECTION = "Ideas"
BASKET_DIR = "idea_basket"
UNTRACKED = ["idea.md", "findings.md", "idea_basket/"]
DOC_EXTS = (".pdf", ".txt", ".html", ".htm", ".md")

# Canonical findings line (matches autoresearch-loop/run_iter.py + analyze parser):
#   commit <hash> — <metric> <prev> -> <new> — change: <what> — source: <where>
FINDINGS_HEADER = (
    "# Findings — new-best changes (provenance)\n\n"
    "Each line: commit <hash> — <metric> <prev> -> <new> — change: <what> — source: <where>\n\n"
)


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
    raise SystemExit("No .autoresearch/spec.md found — run /autoresearch-init first.")


def _section(text, name):
    m = re.search(r"^##\s+" + re.escape(name) + r"\s*$(.*?)(?=^##\s|\Z)",
                  text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _field(block, key):
    m = re.search(r"^-\s*" + re.escape(key) + r"\s*:\s*(.*)$", block, re.MULTILINE)
    return m.group(1).strip() if m else ""


def parse_spec(root):
    text = open(os.path.join(root, ".autoresearch", "spec.md"), encoding="utf-8").read()
    name_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    name = name_m.group(1).strip() if name_m else "Experiment"
    measure = _section(text, "Measure")
    metric = _field(measure, "name") or "score"
    direction = (_field(measure, "direction") or "higher_is_better").strip().lower()
    goal = " ".join(_section(text, "Goal").split())
    return dict(root=root, name=name, metric=metric, direction=direction, goal=goal)


# ---------------------------------------------------------------------------
# idea.md
# ---------------------------------------------------------------------------

def idea_path(root):
    return os.path.join(root, "idea.md")


def render_line(idea):
    cb = CHECKBOX.get(idea["status"], " ")
    line = f"- [{cb}] {idea['text']} — status: {idea['status']} — source: {idea.get('source','agent')}"
    if idea.get("commit"):
        line += f" — commit: {idea['commit']}"
    if idea.get("result"):
        line += f" — result: {idea['result']}"
    if idea.get("note"):
        line += f" — note: {idea['note']}"
    return line


def _parse_line(line):
    m = re.match(r"-\s*\[(.)\]\s*(.*)$", line.strip())
    if not m:
        return None
    parts = [p.strip() for p in m.group(2).split(" — ")]
    idea = {"text": parts[0], "status": "pending", "source": "", "commit": None,
            "result": None, "note": None, "raw": line.strip()}
    for p in parts[1:]:
        if ":" in p:
            k, v = p.split(":", 1)
            k = k.strip().lower()
            if k in ("status", "source", "commit", "result", "note"):
                idea[k] = v.strip()
    if idea["status"] not in STATUSES:
        idea["status"] = "pending"
    return idea


def read_ideas(root):
    """Return list of idea dicts (with 1-based 'idx')."""
    p = idea_path(root)
    if not os.path.exists(p):
        return []
    body = _section(open(p, encoding="utf-8").read(), IDEAS_SECTION)
    out = []
    for ln in body.splitlines():
        if ln.strip().startswith("- ["):
            idea = _parse_line(ln)
            if idea:
                idea["idx"] = len(out) + 1
                out.append(idea)
    return out


def counts(ideas):
    c = {s: 0 for s in STATUSES}
    for i in ideas:
        c[i["status"]] = c.get(i["status"], 0) + 1
    c["total"] = len(ideas)
    return c


def _norm(t):
    return re.sub(r"\s+", " ", (t or "").lower()).strip()


def _write_ideas(root, name, ideas):
    """Rewrite idea.md with the given ideas under ## Ideas (preserve the preamble)."""
    p = idea_path(root)
    lines = render_template(name).splitlines()
    # find the '## Ideas' header and rewrite everything after it
    out = []
    for ln in lines:
        out.append(ln)
        if ln.strip() == f"## {IDEAS_SECTION}":
            break
    out.append("")
    for idea in ideas:
        out.append(render_line(idea))
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip("\n") + "\n")


def add_idea(root, name, text, source="agent", status="pending"):
    """Append an idea (deduped on normalized text). Returns (added_bool, idea).
    If the source names a basket document (doc:<file>), that file is auto-marked
    visited."""
    ideas = read_ideas(root) if os.path.exists(idea_path(root)) else []
    if any(_norm(i["text"]) == _norm(text) for i in ideas):
        return False, None
    idea = {"text": text.strip(), "status": status if status in STATUSES else "pending",
            "source": source.strip() or "agent", "commit": None, "result": None, "note": None}
    ideas.append(idea)
    _write_ideas(root, name, ideas)
    m = re.search(r"doc:\s*([^\s—]+)", source or "")
    if m:
        mark_file_visited(root, m.group(1), add_ideas=1)
    return True, idea


def set_status(root, name, match, status, commit=None, result=None):
    """Update an idea's status. `match` is a 1-based index (str/int) or a text
    substring. Returns the updated idea or None."""
    if status not in STATUSES:
        raise SystemExit(f"status must be one of {STATUSES}")
    ideas = read_ideas(root)
    target = None
    ms = str(match).strip()
    if ms.isdigit():
        i = int(ms)
        if 1 <= i <= len(ideas):
            target = ideas[i - 1]
    if target is None:
        hits = [i for i in ideas if _norm(ms) in _norm(i["text"])]
        if len(hits) == 1:
            target = hits[0]
        elif len(hits) > 1:
            raise SystemExit(f"'{match}' matches {len(hits)} ideas; be more specific or use the index.")
    if target is None:
        raise SystemExit(f"no idea matches '{match}'.")
    target["status"] = status
    if commit:
        target["commit"] = commit
    if result:
        target["result"] = result
    _write_ideas(root, name, ideas)
    return target


# ---------------------------------------------------------------------------
# templates / basket dir / gitignore
# ---------------------------------------------------------------------------

def render_template(name):
    tmpl = os.path.join(HERE, "idea.template.md")
    if os.path.exists(tmpl):
        return open(tmpl, encoding="utf-8").read().replace("{{NAME}}", name)
    # inline fallback
    return (f"# Idea Basket — {name}\n\n"
            "Optional, git-untracked. Line format:\n"
            "  - [ ] <one-line idea> — status: pending — source: <user | paper:\"title\" link | doc:file | web link | agent>\n"
            "Status: pending -> doing -> selected | discarded.\n\n"
            f"## {IDEAS_SECTION}\n")


def ensure_basket(root, name):
    """Create idea.md (if missing), idea_basket/ (if missing), and gitignore lines."""
    created = []
    if not os.path.exists(idea_path(root)):
        with open(idea_path(root), "w", encoding="utf-8") as f:
            f.write(render_template(name))
        created.append("idea.md")
    bdir = os.path.join(root, BASKET_DIR)
    if not os.path.isdir(bdir):
        os.makedirs(bdir, exist_ok=True)
        created.append("idea_basket/")
    if ensure_gitignore(root):
        created.append(".gitignore (updated)")
    return created


def ensure_gitignore(root):
    """Ensure idea.md/findings.md/idea_basket/ are ignored. Returns True if changed."""
    p = os.path.join(root, ".gitignore")
    existing = []
    if os.path.exists(p):
        existing = [ln.rstrip("\n") for ln in open(p, encoding="utf-8")]
    present = {ln.strip() for ln in existing}
    missing = [e for e in UNTRACKED if e not in present]
    if not missing:
        return False
    lines = list(existing)
    if lines and lines[-1].strip() != "":
        lines.append("")
    lines.extend(missing)
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")
    return True


def list_basket_files(root):
    bdir = os.path.join(root, BASKET_DIR)
    if not os.path.isdir(bdir):
        return []
    return sorted(f for f in os.listdir(bdir)
                  if f.lower().endswith(DOC_EXTS) and not f.startswith("."))


# --- file visited-status (idea_basket/.status.json) ------------------------

def _status_path(root):
    return os.path.join(root, BASKET_DIR, ".status.json")


def read_file_status(root):
    try:
        with open(_status_path(root), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_file_status(root, data):
    os.makedirs(os.path.join(root, BASKET_DIR), exist_ok=True)
    with open(_status_path(root), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def mark_file_visited(root, name, add_ideas=0):
    name = os.path.basename(name)
    data = read_file_status(root)
    entry = data.get(name, {"status": "new", "ideas": 0})
    entry["status"] = "visited"
    entry["ideas"] = int(entry.get("ideas", 0)) + int(add_ideas)
    data[name] = entry
    _write_file_status(root, data)
    return entry


def file_statuses(root):
    """List basket documents with their visited status + idea count."""
    st = read_file_status(root)
    out = []
    for f in list_basket_files(root):
        e = st.get(f, {})
        out.append({"name": f, "status": e.get("status", "new"),
                    "ideas": int(e.get("ideas", 0))})
    return out


def save_upload(root, filename, data_bytes):
    """Save an uploaded document into idea_basket/. Returns the safe filename.
    Rejects unsafe names and non-document extensions."""
    base = os.path.basename(filename or "").strip().lstrip(".")
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base)
    if not base or not base.lower().endswith(DOC_EXTS):
        raise ValueError(f"unsupported file (allowed: {', '.join(DOC_EXTS)})")
    bdir = os.path.join(root, BASKET_DIR)
    os.makedirs(bdir, exist_ok=True)
    with open(os.path.join(bdir, base), "wb") as f:
        f.write(data_bytes)
    return base


def ensure_findings_header(root):
    p = os.path.join(root, "findings.md")
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as f:
            f.write(FINDINGS_HEADER)
        return True
    return False


# ---------------------------------------------------------------------------
# source classification (shared vocabulary with analyze)
# ---------------------------------------------------------------------------

def classify_source(source):
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

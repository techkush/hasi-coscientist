#!/usr/bin/env python3
"""
autoresearch-generate scaffolder (the controlled materializer).

Reads .autoresearch/spec.md and writes the experiment files from templates/ into
the project root, filling every invariant-bearing value:
  - the budget headroom (TIME_BUDGET < the loop's hard-kill timeout),
  - the exact result block + greppable lines,
  - results.tsv columns kept consistent with the measure + secondary metrics
    (every numeric column gets a printed line — no orphan columns),
  - runner command, dependencies, .gitignore.

Only the two irreducibly domain-specific bodies are left for the skill to fill,
marked as  # >>> GENERATE:... <<<  regions:
  - the measure (in the read-only file),
  - the baseline approach + how `results` is populated (in the editable file).

Usage:
    python scaffold.py [PROJECT_ROOT] [--force] [--print-plan]

If PROJECT_ROOT is omitted, the script looks for a folder containing
.autoresearch/spec.md at the cwd, then one level below it.
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "templates")

STD_COLUMNS = {"commit", "status", "description"}
TIME_KEYS = {"runtime_s", "elapsed_s", "wall_s", "seconds", "time_s"}


# ---------------------------------------------------------------------------
# Spec parsing
# ---------------------------------------------------------------------------

def find_project_root(start):
    """Return the folder containing .autoresearch/spec.md (cwd or one level down)."""
    start = os.path.abspath(start)
    if os.path.isfile(os.path.join(start, ".autoresearch", "spec.md")):
        return start
    hits = []
    for entry in sorted(os.listdir(start)):
        cand = os.path.join(start, entry)
        if os.path.isdir(cand) and os.path.isfile(os.path.join(cand, ".autoresearch", "spec.md")):
            hits.append(cand)
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise SystemExit("Multiple specs found; pass PROJECT_ROOT explicitly:\n  " +
                         "\n  ".join(hits))
    raise SystemExit(f"No .autoresearch/spec.md found at or under {start}")


def section(text, name):
    """Return the body of a '## name' section (until the next '## ')."""
    m = re.search(r"^##\s+" + re.escape(name) + r"\s*$(.*?)(?=^##\s|\Z)",
                  text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def field(block, key):
    """Return the value of a '- key: value' line within a block."""
    m = re.search(r"^-\s*" + re.escape(key) + r"\s*:\s*(.*)$", block, re.MULTILINE)
    return m.group(1).strip() if m else ""


def first_sentence(text, cap=160):
    one = " ".join(text.split())
    if not one:
        return ""
    dot = one.find(". ")
    if dot != -1:
        one = one[:dot + 1]
    return one[:cap].strip()


def is_none(v):
    return v.strip().lower() in {"", "none", "n/a", "na"}


def parse_secondary_metrics(value):
    """Return [(name, grep_pattern), ...] from the secondary_metrics field."""
    if is_none(value):
        return []
    out = []
    for name, pat in re.findall(r"([A-Za-z_][\w]*)\s*\(([^)]*)\)", value):
        out.append((name, pat.strip()))
    if out:
        return out
    # fall back: bare comma/pipe separated names, synth a line-start pattern
    for chunk in re.split(r"[|,]", value):
        nm = chunk.strip()
        if re.fullmatch(r"[A-Za-z_]\w*", nm):
            out.append((nm, f"^{nm}:"))
    return out


def parse_spec(path):
    text = open(path, encoding="utf-8").read()

    name_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    name = name_m.group(1).strip() if name_m else "Experiment"

    measure = section(text, "Measure")
    metric = field(measure, "name") or "score"
    direction = (field(measure, "direction") or "higher_is_better").strip()
    grep_pattern = field(measure, "grep_pattern") or f"^{metric}:"
    result_line = field(measure, "result_line") or f"{metric}: 0.000000"
    secondaries = parse_secondary_metrics(field(measure, "secondary_metrics"))

    data = section(text, "Data / benchmark")
    data_field = field(data, "data")
    data_present = not is_none(data_field)
    location = field(data, "location")

    files = section(text, "Files")
    editable = field(files, "editable") or "run.py"
    readonly = field(files, "readonly_fixed") or "prepare.py"
    runner = field(files, "runner_command") or f"python {editable}"
    log_file = field(files, "log_file") or "run.log"
    has_code = field(files, "has_user_code").lower().startswith("y")
    source_code = field(files, "source_code")

    tb = section(text, "Time budget")
    tmin_raw = field(tb, "timeout_minutes") or "5"
    m = re.search(r"[0-9]*\.?[0-9]+", tmin_raw)
    timeout_minutes = float(m.group(0)) if m else 5.0

    deps_raw = section(text, "Dependencies")
    deps = [d.strip() for d in re.split(r"[,\n]", deps_raw) if d.strip()
            and not d.strip().lower().startswith("standard library")]

    logging = section(text, "Logging (results.tsv)")
    cols_raw = field(logging, "columns")
    columns = [c.strip() for c in cols_raw.split(",") if c.strip()] or \
              ["commit", metric, "status", "description"]

    goal = first_sentence(section(text, "Goal")) or name
    baseline = first_sentence(section(text, "Baseline approach")) or "the simplest reasonable starting point"
    what_change = " ".join(section(text, "What the loop may change").split()) or "the approach and its knobs"

    return dict(
        name=name, metric=metric, direction=direction, grep_pattern=grep_pattern,
        result_line=result_line, secondaries=secondaries,
        data_present=data_present, data_field=data_field, location=location,
        editable=editable, readonly=readonly, runner=runner, log_file=log_file,
        has_code=has_code, source_code=source_code,
        timeout_minutes=timeout_minutes, deps=deps, columns=columns,
        goal=goal, baseline=baseline, what_change=what_change,
        extra_constraints=extract_extra_constraints(section(text, "Constraints / rules")),
    )


STD_CONSTRAINT_HINTS = (
    "only edit", "never modify", "do not install", "resource use",
    "simplicity is a tiebreaker",
)


def extract_extra_constraints(block):
    out = []
    for line in block.splitlines():
        s = line.strip()
        if not s.startswith("-"):
            continue
        body = s[1:].strip()
        low = body.lower()
        if is_none(body) or any(h in low for h in STD_CONSTRAINT_HINTS):
            continue
        out.append(body)
    return out


# ---------------------------------------------------------------------------
# Derivations
# ---------------------------------------------------------------------------

def metric_keys(spec):
    """Primary + secondaries + any numeric results column, de-duplicated in order."""
    keys = [spec["metric"]]
    for nm, _ in spec["secondaries"]:
        if nm not in keys:
            keys.append(nm)
    for col in spec["columns"]:
        if col.lower() not in STD_COLUMNS and col not in keys:
            keys.append(col)
    return keys


def budget(spec):
    kill = int(round(spec["timeout_minutes"] * 60))
    reserve = min(60, max(10, int(round(0.15 * kill))))
    min_budget = 10
    if kill - reserve < min_budget:
        reserve = max(1, kill - min_budget)
    return kill, reserve, min_budget


def derive(spec):
    kill, reserve, min_budget = budget(spec)
    keys = metric_keys(spec)
    higher = "higher" in spec["direction"].lower()
    direction_word = "higher" if higher else "lower"
    goal_word = "maximize" if higher else "minimize"

    result_prints = "\n".join(
        f'    print(f"{k}: {{results[{k!r}]:.6f}}")' for k in keys
    )
    auto_runtime = "\n".join(
        f'    results.setdefault({k!r}, time.time() - t_start)'
        for k in keys if k.lower() in TIME_KEYS
    )

    # display result block (program.md / README)
    block_lines = ["---"]
    for k in keys:
        if k == spec["metric"]:
            block_lines.append(spec["result_line"])
        else:
            block_lines.append(f"{k}: 0.000000")
    result_block = "\n".join(block_lines)

    loc = spec["location"]
    data_location_repr = repr(loc) if (spec["data_present"] and not is_none(loc)) else "None"
    data_ignore = ""
    if spec["data_present"] and not is_none(loc):
        norm = loc.strip().lstrip("./").rstrip("/")
        if norm and "/" not in norm and not norm.startswith(("http", "~")):
            data_ignore = f"{norm}/\n"

    if spec["data_present"]:
        data_verify = (f"the data should be present under `{loc}`. If not, "
                       f"prepare it once with `python {spec['readonly']}`.")
    else:
        data_verify = "no external data — nothing to prepare."

    source_note = ""
    if spec["has_code"] and not is_none(spec["source_code"]):
        source_note = (f"\n\nPorted from the user's original code at "
                       f"`{spec['source_code']}` — keep their logic faithfully.")

    extra = ""
    if spec["extra_constraints"]:
        extra = "\n".join(f"- {c}" for c in spec["extra_constraints"])

    readonly_module = re.sub(r"\.py$", "", spec["readonly"])
    data_import = ", get_data" if spec["data_present"] else ""

    return dict(
        NAME=spec["name"], METRIC=spec["metric"], DIRECTION=spec["direction"],
        DIRECTION_WORD=direction_word, GOAL_WORD=goal_word, GOAL_LINE=spec["goal"],
        BASELINE_DESC=spec["baseline"], WHAT_CAN_CHANGE=spec["what_change"],
        READONLY=spec["readonly"], EDITABLE=spec["editable"],
        READONLY_MODULE=readonly_module, RUNNER_COMMAND=spec["runner"],
        LOG_FILE=spec["log_file"], GREP_PATTERN=spec["grep_pattern"],
        RESULT_LINE=spec["result_line"], RESULT_BLOCK=result_block,
        KILL_SECONDS=str(kill), OVERHEAD_RESERVE=str(reserve),
        MIN_BUDGET=str(min_budget), COMPUTE_SECONDS=str(kill - reserve),
        TIMEOUT_MINUTES=fmt_minutes(spec["timeout_minutes"]),
        DATA_LOCATION_REPR=data_location_repr, DATA_DESC=(spec["data_field"] or "none"),
        DATA_VERIFY=data_verify, DATA_IGNORE=data_ignore, DATA_IMPORT=data_import,
        SOURCE_NOTE=source_note, EXTRA_CONSTRAINTS=extra,
        RESULT_PRINTS=result_prints, AUTO_RUNTIME=auto_runtime,
        ALL_METRIC_KEYS=", ".join(keys),
        COLUMNS_TSV="\t".join(spec["columns"]),
    )


def fmt_minutes(x):
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def fill(template_text, mapping):
    def repl(m):
        key = m.group(1)
        if key not in mapping:
            raise SystemExit(f"template placeholder {{{{{key}}}}} has no value")
        return str(mapping[key])
    return re.sub(r"\{\{(\w+)\}\}", repl, template_text)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def read_template(name):
    return open(os.path.join(TEMPLATES, name), encoding="utf-8").read()


def code_is_protected(path):
    """A code file is protected if it exists, is hand-filled (no GENERATE/skeleton
    markers), and would otherwise be clobbered."""
    if not os.path.exists(path):
        return False
    txt = open(path, encoding="utf-8").read()
    return (">>> GENERATE" not in txt) and ("TODO(generate)" not in txt)


def write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_root", nargs="?", default=".")
    ap.add_argument("--force", action="store_true",
                    help="overwrite hand-filled prepare/editable files too")
    ap.add_argument("--print-plan", action="store_true",
                    help="print the parsed/derived values and exit (no writes)")
    args = ap.parse_args()

    root = find_project_root(args.project_root)
    spec = parse_spec(os.path.join(root, ".autoresearch", "spec.md"))
    mp = derive(spec)

    if args.print_plan:
        for k in sorted(mp):
            v = str(mp[k]).replace("\n", "\\n")
            print(f"{k} = {v[:120]}")
        print(f"metric_keys = {metric_keys(spec)}")
        print(f"numeric_columns = {[c for c in spec['columns'] if c.lower() not in STD_COLUMNS]}")
        return

    readonly_path = os.path.join(root, spec["readonly"])
    editable_path = os.path.join(root, spec["editable"])
    wrote, skipped = [], []

    # Code files: respect hand-filled work unless --force.
    for path, tmpl in ((readonly_path, "prepare.frame.py"),
                       (editable_path, "executor.frame.py")):
        if code_is_protected(path) and not args.force:
            skipped.append(os.path.relpath(path, root))
            continue
        write(path, fill(read_template(tmpl), mp))
        wrote.append(os.path.relpath(path, root))

    # Boilerplate: always (re)generated.
    write(os.path.join(root, "program.md"), fill(read_template("program.template.md"), mp))
    write(os.path.join(root, "README.md"), fill(read_template("README.template.md"), mp))
    write(os.path.join(root, ".gitignore"), fill(read_template("gitignore.template"), mp))
    wrote += ["program.md", "README.md", ".gitignore"]

    results_path = os.path.join(root, "results.tsv")
    if not os.path.exists(results_path):
        write(results_path, mp["COLUMNS_TSV"] + "\n")
        wrote.append("results.tsv")
    else:
        skipped.append("results.tsv (exists)")

    if spec["deps"]:
        write(os.path.join(root, "requirements.txt"), "\n".join(spec["deps"]) + "\n")
        wrote.append("requirements.txt")

    print(f"Project root: {root}")
    print(f"Compute budget: {mp['COMPUTE_SECONDS']}s   (hard kill at {mp['KILL_SECONDS']}s)")
    print(f"Metric keys (must be printed): {mp['ALL_METRIC_KEYS']}")
    print("Wrote:   " + ", ".join(wrote))
    if skipped:
        print("Skipped: " + ", ".join(skipped) + "   (use --force to overwrite code)")
    print("\nNext: fill the  >>> GENERATE:... <<<  regions in "
          f"{spec['readonly']} and {spec['editable']}, then run validate.py")


if __name__ == "__main__":
    main()

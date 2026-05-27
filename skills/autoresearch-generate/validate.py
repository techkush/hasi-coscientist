#!/usr/bin/env python3
"""
autoresearch-generate validation gate.

Mechanically enforces the invariants that make autonomous iteration safe, so the
skill cannot hand off a broken experiment. Exits non-zero (and prints FAIL lines)
if any invariant is violated.

Checks:
  1. The read-only and editable files compile (py_compile).
  2. No unfilled  >>> GENERATE:... <<<  regions or NotImplementedError stubs remain.
  3. TIME_BUDGET is strictly less than the loop's hard-kill timeout (no collision).
  4. The measure lives ONLY in the read-only file; the editable imports it.
  5. The editable imports TIME_BUDGET and references it (respects the budget).
  6. Every numeric results.tsv column is printed by the run on its own line
     (no orphan columns), and the primary metric line matches grep_pattern.

Usage:
    python validate.py [PROJECT_ROOT]
"""

import os
import py_compile
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scaffold  # noqa: E402

STD_COLUMNS = scaffold.STD_COLUMNS


def noncomment_lines(text):
    for raw in text.splitlines():
        if raw.lstrip().startswith("#"):
            continue
        yield raw


def prints_metric(text, name):
    """True if a non-comment print emits a line starting with '<name>:'."""
    pat = re.compile(r"print\(\s*[rf]*[\"']" + re.escape(name) + r":")
    return any(pat.search(line) for line in noncomment_lines(text))


def main():
    root = scaffold.find_project_root(sys.argv[1] if len(sys.argv) > 1 else ".")
    spec = scaffold.parse_spec(os.path.join(root, ".autoresearch", "spec.md"))
    keys = scaffold.metric_keys(spec)
    kill, reserve, min_budget = scaffold.budget(spec)

    readonly_path = os.path.join(root, spec["readonly"])
    editable_path = os.path.join(root, spec["editable"])

    errors, warnings = [], []

    # 1. files exist + compile
    for path in (readonly_path, editable_path):
        if not os.path.exists(path):
            errors.append(f"missing file: {os.path.relpath(path, root)}")
            continue
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"syntax error in {os.path.relpath(path, root)}: {e.msg.strip()}")

    if any("missing file" in e for e in errors):
        return report(root, kill, keys, errors, warnings)

    ro = open(readonly_path, encoding="utf-8").read()
    ed = open(editable_path, encoding="utf-8").read()

    # 2. no unfilled regions / stubs
    for label, txt, fname in (("read-only", ro, spec["readonly"]),
                              ("editable", ed, spec["editable"])):
        if ">>> GENERATE" in txt:
            errors.append(f"{fname}: unfilled  >>> GENERATE  region(s) remain")
        if "NotImplementedError" in txt:
            errors.append(f"{fname}: NotImplementedError stub still present")
        if "TODO(generate)" in txt:
            errors.append(f"{fname}: init skeleton TODO(generate) markers still present")

    # 3. budget < kill timeout
    m_kill = re.search(r"KILL_SECONDS\s*=\s*(\d+)", ro)
    m_res = re.search(r"OVERHEAD_RESERVE\s*=\s*(\d+)", ro)
    m_min = re.search(r"TIME_BUDGET\s*=\s*max\(\s*(\d+)", ro)
    if m_kill and m_res and m_min:
        k, r, mn = int(m_kill.group(1)), int(m_res.group(1)), int(m_min.group(1))
        eff_budget = max(mn, k - r)
        if eff_budget >= k:
            errors.append(f"TIME_BUDGET ({eff_budget}s) is not below the hard kill ({k}s) "
                          f"— a full-budget run would be killed")
        if eff_budget <= 0:
            errors.append("TIME_BUDGET resolves to <= 0")
    else:
        warnings.append(f"{spec['readonly']}: could not find KILL_SECONDS/OVERHEAD_RESERVE/"
                        "TIME_BUDGET constants — budget headroom not verified")

    # 4. measure read-only only
    if re.search(r"^\s*def\s+measure\s*\(", ed, re.MULTILINE):
        errors.append(f"{spec['editable']} defines its own measure() — the measure must "
                      f"live only in {spec['readonly']} and be imported")
    if not re.search(r"^\s*def\s+measure\s*\(", ro, re.MULTILINE):
        errors.append(f"{spec['readonly']} does not define measure()")
    module = re.sub(r"\.py$", "", spec["readonly"])
    if not re.search(r"from\s+" + re.escape(module) + r"\s+import[^\n]*\bmeasure\b", ed):
        errors.append(f"{spec['editable']} does not import measure from {module}")

    # 5. budget imported + used
    if not re.search(r"from\s+" + re.escape(module) + r"\s+import[^\n]*\bTIME_BUDGET\b", ed):
        errors.append(f"{spec['editable']} does not import TIME_BUDGET from {module}")
    elif len(re.findall(r"\bTIME_BUDGET\b", ed)) < 2:
        warnings.append(f"{spec['editable']} imports TIME_BUDGET but never references it "
                        "(open-ended runs must stop at the budget)")

    # 6. every numeric column printed; primary matches grep_pattern
    numeric_cols = [c for c in spec["columns"] if c.lower() not in STD_COLUMNS]
    for col in numeric_cols:
        if not prints_metric(ed, col):
            errors.append(f"results column '{col}' is never printed by {spec['editable']} "
                          "(orphan column — the loop can't fill it)")
    grep_name = spec["grep_pattern"].lstrip("^").rstrip(":")
    if grep_name and not prints_metric(ed, grep_name):
        errors.append(f"primary metric line '{grep_name}:' (grep_pattern "
                      f"{spec['grep_pattern']}) is not printed by {spec['editable']}")

    # warnings: secondary metrics should carry grep patterns in the spec
    for nm, pat in spec["secondaries"]:
        if not pat:
            warnings.append(f"secondary metric '{nm}' has no grep pattern in the spec")

    return report(root, kill, keys, errors, warnings)


def report(root, kill, keys, errors, warnings):
    print(f"Validating: {root}")
    print(f"Hard kill: {kill}s | required printed metrics: {', '.join(keys)}")
    for w in warnings:
        print(f"  WARN  {w}")
    for e in errors:
        print(f"  FAIL  {e}")
    if errors:
        print(f"\n{len(errors)} invariant(s) violated — fix before handing off.")
        sys.exit(1)
    print("\nOK — all invariants satisfied.")
    sys.exit(0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
autoresearch-setup readiness gate (the controlled, read-only half).

Never mutates anything. Prints one line per check, prefixed PASS / WARN / FAIL,
and exits non-zero if any FAIL. This is what makes setup *controlled*: a run is
only handed to the loop after this gate is green.

Two modes:
  (default / pre)  fixable, not-yet-done items (deps, data, branch, gitignore,
                   header) are WARN — they're what prepare_run / the skill resolve.
  --final          those state items escalate to FAIL — the run must actually be
                   on its branch, committed, ignoring the right things, ready.

Hard blockers are FAIL in BOTH modes:
  - the generated code files don't exist (generate wasn't run)
  - unfilled  >>> GENERATE <<<  / TODO(generate) / NotImplementedError remain
    (generate was left half-done — the first run would crash)
  - the code doesn't compile
  - autoresearch-generate/validate.py (if reachable) reports FAIL

Usage:
    python readiness.py [PROJECT_ROOT] [--final] [--json]
"""

import argparse
import json
import os
import py_compile
import subprocess
import sys

import setup_lib as L

UNFILLED_MARKERS = (">>> GENERATE", "TODO(generate)", "NotImplementedError")


class Report:
    def __init__(self):
        self.rows = []  # (level, check, detail)

    def add(self, level, check, detail=""):
        self.rows.append((level, check, detail))

    def fail(self, check, detail=""):
        self.add("FAIL", check, detail)

    def warn(self, check, detail=""):
        self.add("WARN", check, detail)

    def ok(self, check, detail=""):
        self.add("PASS", check, detail)

    def info(self, check, detail=""):
        self.add("INFO", check, detail)

    @property
    def failed(self):
        return any(r[0] == "FAIL" for r in self.rows)


def find_validate_py():
    """Locate autoresearch-generate/validate.py next to this skill, if present."""
    skills_dir = os.path.dirname(L.HERE)
    cand = os.path.join(skills_dir, "autoresearch-generate", "validate.py")
    return cand if os.path.isfile(cand) else None


def check_files_exist(spec, rep):
    missing = [
        spec[k] for k in ("editable", "readonly")
        if not os.path.exists(os.path.join(spec["root"], spec[k]))
    ]
    if missing:
        rep.fail("generated files", f"missing {', '.join(missing)} — run /autoresearch-generate")
        return False
    rep.ok("generated files", f"{spec['editable']}, {spec['readonly']} present")
    return True


def check_unfilled(spec, rep):
    bad = []
    for key in ("editable", "readonly"):
        path = os.path.join(spec["root"], spec[key])
        if not os.path.exists(path):
            continue
        txt = open(path, encoding="utf-8").read()
        hits = [m for m in UNFILLED_MARKERS if m in txt]
        if hits:
            bad.append(f"{spec[key]} ({', '.join(hits)})")
    if bad:
        rep.fail("generate finished", "unfilled regions in " + "; ".join(bad))
    else:
        rep.ok("generate finished", "no GENERATE/TODO/NotImplementedError left")


def check_compile(spec, rep):
    errs = []
    for key in ("editable", "readonly"):
        path = os.path.join(spec["root"], spec[key])
        if not os.path.exists(path):
            continue
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            errs.append(f"{spec[key]}: {e.msg.strip().splitlines()[-1]}")
    if errs:
        rep.fail("compiles", "; ".join(errs))
    else:
        rep.ok("compiles", "both files compile")


def check_validate_py(spec, rep):
    vp = find_validate_py()
    if not vp:
        rep.info("invariants (validate.py)", "generate validate.py not reachable — skipped")
        return
    r = subprocess.run(
        [sys.executable, vp, spec["root"]], capture_output=True, text=True, check=False
    )
    if r.returncode == 0:
        rep.ok("invariants (validate.py)", "all invariants satisfied")
    else:
        fails = [ln.strip() for ln in (r.stdout + r.stderr).splitlines()
                 if "FAIL" in ln]
        rep.fail("invariants (validate.py)", "; ".join(fails) or "validate.py reported failure")


def check_deps(spec, rep, final):
    if not spec["deps"]:
        rep.ok("dependencies", "standard library only")
        return
    missing = L.missing_deps(spec)
    if not missing:
        rep.ok("dependencies", f"{len(spec['deps'])} available")
    else:
        # deps are always WARN: the user may legitimately install or defer.
        rep.warn("dependencies", f"missing {', '.join(missing)} (install before running)")


def check_data(spec, rep, final):
    if not spec["data_present"]:
        rep.ok("data", "no external data")
        return
    loc = (spec["location"] or "").strip()
    entry = L.data_ignore_entry(spec["location"])
    if entry is None:
        rep.info("data", f"data at '{loc}' is outside the repo — verify it exists manually")
        return
    present = os.path.exists(os.path.join(spec["root"], entry.rstrip("/")))
    if present:
        rep.ok("data", f"present at {loc}")
    else:
        prep = "" if L.is_none(spec.get("preparation")) else f" (prepare: python {spec['readonly']})"
        rep.warn("data", f"not found at {loc}{prep}")


def check_gitignore(spec, rep, final):
    _, missing, has_bare = L.gitignore_status(spec)
    issues = list(missing)
    if has_bare:
        issues.append("upgrade `.autoresearch/` to keep spec.md tracked")
    if not issues:
        rep.ok("gitignore", "covers results/log/data/.autoresearch (spec tracked)")
    else:
        (rep.fail if final else rep.warn)("gitignore", "missing: " + ", ".join(issues))


def check_results(spec, rep, final):
    status = L.results_status(spec)
    if status == "ok":
        rep.ok("results.tsv", "header matches spec columns")
    elif status == "missing":
        (rep.fail if final else rep.warn)("results.tsv", "ledger missing")
    elif status == "stale_header_only":
        (rep.fail if final else rep.warn)("results.tsv", "header does not match spec columns")
    else:  # stale_has_data
        rep.warn("results.tsv", "header mismatches spec but file has data — resolve manually")


def check_git(spec, rep, final):
    root = spec["root"]
    if not L.is_git_repo(root):
        (rep.fail if final else rep.warn)("git repo", "not a git repository")
        return
    rep.ok("git repo", "initialized")

    if not L.tag_exists(root, L.BASELINE_TAG):
        (rep.fail if final else rep.warn)("baseline", f"no {L.BASELINE_TAG} tag yet")
    else:
        rep.ok("baseline", f"{L.BASELINE_TAG} tag present")

    branch = L.current_branch(root)
    if branch.startswith("autoresearch/"):
        rep.ok("run branch", branch)
    else:
        (rep.fail if final else rep.warn)("run branch", f"on '{branch}', not an autoresearch/* branch")

    if L.tracked_dirty(root):
        (rep.fail if final else rep.warn)("working tree", "tracked files have uncommitted changes")
    else:
        rep.ok("working tree", "clean (tracked files committed)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_root", nargs="?", default=".")
    ap.add_argument("--final", action="store_true",
                    help="escalate state items (branch/gitignore/header/git) to FAIL")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = L.find_project_root(args.project_root)
    spec = L.parse_spec(root)
    rep = Report()

    files_ok = check_files_exist(spec, rep)
    if files_ok:
        check_unfilled(spec, rep)
        check_compile(spec, rep)
        check_validate_py(spec, rep)
    check_deps(spec, rep, args.final)
    check_data(spec, rep, args.final)
    check_gitignore(spec, rep, args.final)
    check_results(spec, rep, args.final)
    check_git(spec, rep, args.final)

    if args.json:
        print(json.dumps({
            "project_root": root,
            "final": args.final,
            "ok": not rep.failed,
            "checks": [{"level": l, "check": c, "detail": d} for l, c, d in rep.rows],
        }, indent=2))
    else:
        mode = "FINAL" if args.final else "PRE"
        print(f"Readiness [{mode}] — {spec['name']}  ({root})")
        for level, check, detail in rep.rows:
            line = f"  {level:<4} {check}"
            if detail:
                line += f": {detail}"
            print(line)
        print()
        print("READY" if not rep.failed else "NOT READY — resolve the FAIL lines above")

    sys.exit(1 if rep.failed else 0)


if __name__ == "__main__":
    main()

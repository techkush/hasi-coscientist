#!/usr/bin/env python3
"""
autoresearch-loop preflight gate (read-only).

Run once before the loop begins. Confirms the run is in a state the loop can
safely iterate on, and reports what the first action should be. Never mutates.

Prints PASS / WARN / FAIL per check; exits non-zero on any FAIL.

Hard blockers (FAIL):
  - not on an autoresearch/<tag> branch  -> run /autoresearch-setup
  - results.tsv is TRACKED by git        -> a discard's `git reset --hard` would
                                            wipe logged rows; untrack it first

Reported state (PASS/INFO):
  - whether the next iteration is the baseline (ledger has no data rows)
  - the current best (direction-aware, among keep rows)
  - whether an idea basket (idea.md) is in use

Usage:
    python preflight.py [PROJECT_ROOT] [--json]
"""

import argparse
import json
import os
import sys

import loop_lib as L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_root", nargs="?", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = L.find_project_root(args.project_root)
    spec = L.parse_spec(root)
    rows = []  # (level, check, detail)

    def add(level, check, detail=""):
        rows.append((level, check, detail))

    # --- branch ---
    branch = L.current_branch(root)
    if branch.startswith("autoresearch/"):
        add("PASS", "branch", branch)
    else:
        add("FAIL", "branch", f"on '{branch}', not autoresearch/* — run /autoresearch-setup")

    # --- ledger present + header ---
    header, data = L.read_ledger(root)
    results_path = os.path.join(root, "results.tsv")
    if not os.path.exists(results_path):
        add("WARN", "results.tsv", "missing — run_iter.py will create the header")
    elif header != spec["columns"]:
        add("WARN", "results.tsv", "header does not match spec columns (re-run /autoresearch-setup)")
    else:
        add("PASS", "results.tsv", "header matches spec columns")

    # --- ledger MUST be untracked (else reset --hard destroys it) ---
    if os.path.exists(results_path) and L.is_tracked(root, "results.tsv"):
        add("FAIL", "ledger safety",
            "results.tsv is TRACKED — `git rm --cached results.tsv` before looping")
    else:
        add("PASS", "ledger safety", "results.tsv untracked (survives git reset --hard)")

    # --- baseline needed? ---
    if not data:
        add("INFO", "next iteration", "BASELINE (run as generated, no change): run_iter.py --baseline")
    else:
        best = L.current_best(spec)
        best_str = "none yet" if best is None else f"{best:.6f}"
        add("INFO", "next iteration",
            f"change one thing; current best {spec['metric']}={best_str} "
            f"({'higher' if spec['higher'] else 'lower'} is better)")

    # --- idea basket ---
    if os.path.exists(os.path.join(root, "idea.md")):
        add("INFO", "idea basket", "idea.md present — prefer its Pending ideas (mix your own)")
    else:
        add("INFO", "idea basket", "none — use your own ideas")

    # --- baseline tag (rewind floor) ---
    if L.tag_exists(root, L.BASELINE_TAG):
        add("PASS", "rewind floor", f"{L.BASELINE_TAG} present (never rewind past it)")
    else:
        add("WARN", "rewind floor", f"no {L.BASELINE_TAG} tag — re-run /autoresearch-setup")

    failed = any(r[0] == "FAIL" for r in rows)

    if args.json:
        print(json.dumps({
            "project_root": root, "name": spec["name"], "branch": branch,
            "baseline_needed": not data, "ok": not failed,
            "checks": [{"level": l, "check": c, "detail": d} for l, c, d in rows],
        }, indent=2))
    else:
        print(f"Loop preflight — {spec['name']}  ({root})")
        for level, check, detail in rows:
            print(f"  {level:<4} {check}" + (f": {detail}" if detail else ""))
        print()
        print("OK to start the loop" if not failed else "BLOCKED — resolve the FAIL lines above")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

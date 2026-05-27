#!/usr/bin/env python3
"""
autoresearch-loop iteration engine — one atomic, controlled iteration.

The agent does the two irreducibly-human steps: pick an idea and EDIT the
editable file (but DO NOT commit it). Then this script does everything else
deterministically, so the correctness-critical mechanics can't drift:

  1. capture START = HEAD  (the edit is still uncommitted, so HEAD is the true
     pre-experiment commit — this is what discard/crash reset to)
  2. commit the editable file(s) by explicit path   (skipped for --baseline)
  3. run the runner within the spec's hard-kill budget (Python subprocess
     timeout — portable, no shell `timeout`), redirecting output to the log
  4. read the measure: the LAST matching line, preferring the final result
     block after `---`  (so per-epoch logs don't fool it)
  5. decide keep / discard / crash, direction-aware, numeric, vs the best
     among existing keep rows
  6. discard / crash -> `git reset --hard START`   (the untracked ledger,
     run.log and idea basket survive)
  7. append one sanitized row to results.tsv (never committed)
  8. on a new best, append a provenance line to findings.md (--source)

Output: a one-line human summary, and (with --json) a machine summary.

Usage:
    # baseline (no change):
    python run_iter.py [ROOT] --baseline
    # a normal iteration (after editing the editable file, uncommitted):
    python run_iter.py [ROOT] --message "wider latent dim" [--source "agent"]
    # keep an ~equal change because it simplifies:
    python run_iter.py [ROOT] --message "drop unused knob" --keep-anyway
"""

import argparse
import json
import os
import subprocess
import sys
import time

import loop_lib as L

FINDINGS_HEADER = (
    "# Findings — new-best changes (provenance)\n\n"
    "Each line: commit <hash> — <metric> <prev> -> <new> — change: <what> — source: <where>\n\n"
)


def run_within_budget(spec, root):
    """Run the runner, redirecting to the log.
    Returns (timed_out, returncode, seconds)."""
    kill_seconds = max(1, int(round(spec["timeout_minutes"] * 60)))
    log_path = os.path.join(root, spec["log_file"])
    t0 = time.time()
    timed_out = False
    returncode = 0
    with open(log_path, "w", encoding="utf-8") as log:
        try:
            r = subprocess.run(spec["runner"], shell=True, cwd=root,
                               stdout=log, stderr=subprocess.STDOUT,
                               timeout=kill_seconds, check=False)
            returncode = r.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            returncode = -1
            log.write(f"\n[killed: exceeded {kill_seconds}s hard budget]\n")
    return timed_out, returncode, time.time() - t0


def append_finding(root, line):
    path = os.path.join(root, "findings.md")
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if new:
            f.write(FINDINGS_HEADER)
        f.write(line + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_root", nargs="?", default=".")
    ap.add_argument("--baseline", action="store_true",
                    help="baseline iteration: no change, no commit, always keep")
    ap.add_argument("--message", help="commit message = ledger description")
    ap.add_argument("--source", default="agent",
                    help="provenance for findings.md on a new best")
    ap.add_argument("--keep-anyway", action="store_true",
                    help="keep an ~equal change (simplification win)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = L.find_project_root(args.project_root)
    spec = L.parse_spec(root)

    # Guard: never operate off the run branch, and never on a tracked ledger.
    branch = L.current_branch(root)
    if not branch.startswith("autoresearch/"):
        raise SystemExit(f"Not on an autoresearch/* branch (on '{branch}'). Run /autoresearch-setup.")
    if os.path.exists(os.path.join(root, "results.tsv")) and L.is_tracked(root, "results.tsv"):
        raise SystemExit("results.tsv is tracked — `git rm --cached results.tsv` first "
                         "(a discard would otherwise wipe the ledger).")

    if not args.baseline and not args.message:
        ap.error("--message is required for a normal iteration (or pass --baseline)")

    # 1. capture the true pre-experiment commit (edit is still uncommitted)
    start = L.full_head(root)
    if not start:
        raise SystemExit("No commits yet — run /autoresearch-setup to create the baseline.")

    # 2. commit the change (baseline commits nothing)
    if args.baseline:
        if L.has_data_rows(root):
            raise SystemExit("Ledger already has rows — baseline already done; drop --baseline.")
        description = "baseline"
    else:
        changed = [p for p in spec["editable"] if L.path_has_changes(root, p)]
        if not changed:
            raise SystemExit("No uncommitted changes in the editable file(s). Edit "
                             f"{', '.join(spec['editable'])} first — and do NOT commit it; "
                             "run_iter.py commits it for you.")
        L.git(root, "add", "--", *spec["editable"])
        L.git(root, "commit", "-m", L.sanitize(args.message))
        description = args.message

    commit = L.short_head(root)

    # 3. run within the hard-kill budget
    timed_out, returncode, runtime_s = run_within_budget(spec, root)

    # 4. read the measure (last match, after the final --- block)
    log_text = open(os.path.join(root, spec["log_file"]), encoding="utf-8").read()
    measures = L.read_measures(spec, log_text)
    value = measures.get(spec["metric"])

    # 5. decide. A run only counts if it finished cleanly (exit 0, in budget) AND
    #    printed a finite measure; otherwise it's a crash.
    crashed = timed_out or returncode != 0 or value is None
    best_before = L.current_best(spec)
    if crashed:
        status = "crash"
    elif args.baseline:
        status = "keep"  # a clean baseline is always the first kept row
    elif L.is_improvement(spec, value, best_before):
        status = "keep"
    elif args.keep_anyway:
        status = "keep"  # simplification at ~equal measure (agent's call)
    else:
        status = "discard"

    # 6. revert on discard/crash (baseline never reverts)
    reverted = False
    if status in ("discard", "crash") and not args.baseline:
        L.git(root, "reset", "--hard", start)
        reverted = True

    # 7. log the row (never committed)
    row = L.build_row(spec, commit, measures, status, description, runtime_s)
    L.append_row(root, row)

    # 8. findings on a new best
    best_after = L.current_best(spec)
    new_best = (status == "keep" and value is not None and
                (best_before is None or L.is_improvement(spec, value, best_before)))
    if new_best and not args.baseline:
        prev = "n/a" if best_before is None else f"{best_before:.6f}"
        append_finding(root, f"commit {commit} — {spec['metric']} {prev} -> {value:.6f} "
                             f"— change: {L.sanitize(description)} — source: {L.sanitize(args.source)}")

    val_str = "crash" if status == "crash" else f"{value:.6f}"
    best_str = "n/a" if best_after is None else f"{best_after:.6f}"
    note = " [timeout]" if timed_out else ""
    summary = (f"[{status}] {commit} — {spec['metric']} {val_str} "
               f"(best {best_str}) — {description}{note}")

    if args.json:
        print(json.dumps(dict(
            status=status, commit=commit, start=start[:7], value=value,
            best_before=best_before, best_after=best_after, new_best=new_best,
            reverted=reverted, timed_out=timed_out, runtime_s=round(runtime_s, 2),
            secondary={k: v for k, v in measures.items() if k != spec["metric"]},
            summary=summary,
        ), indent=2))
    else:
        print(summary)
        if status == "crash":
            tail = "\n".join(log_text.splitlines()[-12:])
            print("  --- last log lines (fix a trivial bug and re-run as a fresh "
                  "iteration, else move on) ---")
            print("  " + tail.replace("\n", "\n  "))


if __name__ == "__main__":
    main()

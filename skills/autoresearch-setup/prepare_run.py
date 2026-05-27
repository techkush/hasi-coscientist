#!/usr/bin/env python3
"""
autoresearch-setup materializer (the controlled, mutating half).

Turns a generated experiment into a run ready for the loop, doing every
deterministic mutation so the skill prose never has to hand-run git:

  1. make it a git repo (git init if needed)
  2. reconcile .gitignore to the canonical set (incl. the data dir; keeps
     .autoresearch/spec.md tracked so baselines are reproducible)
  3. reconcile results.tsv to the spec's header (only when safe — never
     clobbers a file that already has data rows)
  4. baseline commit from EXPLICIT generated paths (never `git add -A`, so
     unrelated working changes are not folded in) and tag it ar-baseline
  5. create the run branch autoresearch/<tag> FROM the baseline tag (never
     from a stray HEAD), refusing to clobber an existing branch

It does NOT install dependencies or download data — those are confirmed,
narrated actions the skill performs around this script.

Usage:
    python prepare_run.py [PROJECT_ROOT] --tag may25 [options]

Options:
    --tag TAG        run tag -> branch autoresearch/TAG (required unless --no-branch)
    --no-branch      do steps 1-4 only (repo + baseline), don't create a run branch
    --rebaseline     re-point ar-baseline to a fresh baseline commit (after re-generate)
    --json           emit a machine-readable JSON summary
"""

import argparse
import json
import os
import sys

import setup_lib as L


def reconcile_gitignore(spec):
    """Ensure the canonical ignore set is present. Non-destructive: appends only
    the missing lines, and upgrades a bare `.autoresearch/` to the spec-tracking
    form. Returns the list of lines added."""
    root = spec["root"]
    path = os.path.join(root, ".gitignore")
    existing, missing, has_bare = L.gitignore_status(spec)
    changed = []

    lines = list(existing)
    # Upgrade a bare `.autoresearch/` (which would also ignore spec.md) to the
    # contents-glob + spec negation so the source-of-truth spec is committed.
    if has_bare:
        lines = [ln for ln in lines if ln.strip() != ".autoresearch/"]
        changed.append("-.autoresearch/")
        # recompute what's still missing against the trimmed list
        present = {ln.strip() for ln in lines}
        missing = [ln for ln in L.required_ignore_lines(spec) if ln not in present]

    if missing:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.extend(missing)
        changed.extend(missing)

    if changed:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(ln.rstrip("\n") for ln in lines).rstrip("\n") + "\n")
    return changed


def reconcile_results(spec):
    """Write the spec header when the ledger is missing or header-only-stale.
    Never touch a file that already has data rows. Returns an action string."""
    root = spec["root"]
    path = os.path.join(root, "results.tsv")
    status = L.results_status(spec)
    header = L.expected_header(spec)
    if status == "missing":
        with open(path, "w", encoding="utf-8") as f:
            f.write(header + "\n")
        return "created"
    if status == "stale_header_only":
        with open(path, "w", encoding="utf-8") as f:
            f.write(header + "\n")
        return "header_fixed"
    if status == "stale_has_data":
        return "stale_has_data_left_alone"  # caller surfaces this as a warning
    return "ok"


def baseline_commit(spec, rebaseline):
    """Stage the explicit generated paths and commit a baseline if needed; ensure
    the ar-baseline tag points at it. Returns (committed_bool, tag_action)."""
    root = spec["root"]
    paths = L.baseline_paths(spec)
    if paths:
        L.git(root, "add", "--", *paths)

    committed = False
    # Commit only if there is something staged among our explicit paths.
    staged = L.git(root, "diff", "--cached", "--name-only", check=False).stdout.strip()
    if staged:
        L.git(root, "commit", "-m", f"baseline: {spec['name']}")
        committed = True
    elif not L.has_commits(root):
        # Nothing staged and no commits at all -> nothing to base a run on.
        raise SystemExit(
            "Nothing to commit and no existing commit: run /autoresearch-generate first."
        )

    tag_action = "kept"
    if L.tag_exists(root, L.BASELINE_TAG):
        if rebaseline:
            L.git(root, "tag", "-f", L.BASELINE_TAG, "HEAD")
            tag_action = "moved"
    else:
        L.git(root, "tag", L.BASELINE_TAG, "HEAD")
        tag_action = "created"
    return committed, tag_action


def create_run_branch(spec, tag):
    """Create autoresearch/<tag> from the baseline tag and check it out."""
    root = spec["root"]
    branch = f"autoresearch/{tag}"
    if L.branch_exists(root, branch):
        raise SystemExit(
            f"Branch {branch} already exists — pick another tag (e.g. {tag}-2)."
        )
    if not L.tag_exists(root, L.BASELINE_TAG):
        raise SystemExit("No baseline tag found — run without --no-branch first.")
    L.git(root, "checkout", "-b", branch, L.BASELINE_TAG)
    return branch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_root", nargs="?", default=".")
    ap.add_argument("--tag", help="run tag -> branch autoresearch/<tag>")
    ap.add_argument("--no-branch", action="store_true",
                    help="prepare repo + baseline only; skip run-branch creation")
    ap.add_argument("--rebaseline", action="store_true",
                    help="re-point ar-baseline to a fresh baseline commit")
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    args = ap.parse_args()

    if not args.no_branch and not args.tag:
        ap.error("--tag is required (or pass --no-branch to skip branch creation)")

    root = L.find_project_root(args.project_root)
    spec = L.parse_spec(root)

    # Hard precondition: the generated code must exist (don't prep a non-experiment).
    for key in ("editable", "readonly"):
        if not os.path.exists(os.path.join(root, spec[key])):
            raise SystemExit(
                f"Missing {spec[key]} — run /autoresearch-generate before setup."
            )

    actions = {}

    # 1. git repo
    if not L.is_git_repo(root):
        L.git(root, "init")
        actions["git_init"] = True
    else:
        actions["git_init"] = False

    # 2. .gitignore
    actions["gitignore_added"] = reconcile_gitignore(spec)

    # 3. results.tsv
    actions["results"] = reconcile_results(spec)

    # 4. baseline commit + tag
    committed, tag_action = baseline_commit(spec, args.rebaseline)
    actions["baseline_committed"] = committed
    actions["baseline_tag"] = tag_action

    # 5. run branch
    if args.no_branch:
        actions["branch"] = None
    else:
        actions["branch"] = create_run_branch(spec, args.tag)

    summary = dict(project_root=root, name=spec["name"], **actions)

    if args.json:
        print(json.dumps(summary, indent=2))
        return

    print(f"Project root: {root}")
    print(f"git init:     {'yes' if actions['git_init'] else 'already a repo'}")
    added = actions["gitignore_added"]
    print(f".gitignore:   {'added ' + ', '.join(added) if added else 'already complete'}")
    print(f"results.tsv:  {actions['results']}")
    print(f"baseline:     {'committed' if committed else 'already committed'} "
          f"(tag {L.BASELINE_TAG}: {tag_action})")
    if actions["branch"]:
        print(f"run branch:   {actions['branch']}  (from {L.BASELINE_TAG})")
    else:
        print("run branch:   skipped (--no-branch)")
    if actions["results"] == "stale_has_data_left_alone":
        print("\nWARNING: results.tsv header does not match the spec columns but the "
              "file already has data rows — left untouched. Resolve manually.")
    print("\nNext: run readiness.py --final to gate, then /autoresearch-experiment.")


if __name__ == "__main__":
    main()

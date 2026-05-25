#!/usr/bin/env python3
"""
autoresearch-ideas basket manager (the controlled CLI).

Does every deterministic idea-basket mutation so the skill prose (and the loop)
never hand-edit idea.md — which is what kept the format consistent with the loop
and the analyze report. Requires a project with .autoresearch/spec.md.

Commands:
  init                         create idea.md + idea_basket/ + gitignore entries
  add  --text T --source S     append a pending idea (deduped); --status to override
  status --match M --set X     move an idea's status (pending|doing|selected|discarded);
                               M = 1-based index or a text substring; --commit/--result optional
  list [--json]                show ideas + counts
  files [--json]               list documents in idea_basket/

All commands accept an optional PROJECT_ROOT (default: auto-detect from cwd).

Examples:
  python basket.py init
  python basket.py add --text "cosine LR schedule" --source 'paper:"SGDR" https://arxiv.org/abs/1608.03983'
  python basket.py status --match "cosine LR" --set doing --commit 9f1a4c2
  python basket.py status --match 3 --set selected --commit 9f1a4c2 --result "18.2 -> 19.4"
  python basket.py list --json
"""

import argparse
import json
import os
import sys

import idea_lib as L


def _root(args):
    return L.find_project_root(getattr(args, "project_root", ".") or ".")


def cmd_init(args):
    root = _root(args)
    spec = L.parse_spec(root)
    created = L.ensure_basket(root, spec["name"])
    L.ensure_findings_header(root)
    if args.json:
        print(json.dumps({"root": root, "created": created}, indent=2))
    else:
        print(f"Basket ready for '{spec['name']}' at {root}")
        print("Created: " + (", ".join(created) if created else "nothing (already present)"))
        print("Drop reference docs into idea_basket/ ; add ideas with: basket.py add --text … --source …")


def cmd_add(args):
    root = _root(args)
    spec = L.parse_spec(root)
    L.ensure_basket(root, spec["name"])
    added, idea = L.add_idea(root, spec["name"], args.text, args.source, args.status)
    if args.json:
        print(json.dumps({"added": added, "idea": idea,
                          "counts": L.counts(L.read_ideas(root))}, indent=2))
    else:
        print(f"{'added' if added else 'skipped (duplicate)'}: {args.text}")


def cmd_status(args):
    root = _root(args)
    spec = L.parse_spec(root)
    idea = L.set_status(root, spec["name"], args.match, args.set,
                        commit=args.commit, result=args.result)
    if args.json:
        print(json.dumps({"updated": idea, "counts": L.counts(L.read_ideas(root))}, indent=2))
    else:
        print(f"[{idea['status']}] {idea['text']}")


def cmd_list(args):
    root = _root(args)
    ideas = L.read_ideas(root)
    c = L.counts(ideas)
    if args.json:
        print(json.dumps({"ideas": ideas, "counts": c,
                          "files": L.list_basket_files(root)}, indent=2))
    else:
        if not ideas:
            print("Basket is empty.")
        for i in ideas:
            extra = f"  ({i['source']})" if i["source"] else ""
            print(f"  #{i['idx']:<2} [{i['status']:<9}] {i['text']}{extra}")
        print(f"\n{c['total']} ideas — pending {c['pending']}, doing {c['doing']}, "
              f"selected {c['selected']}, discarded {c['discarded']}")


def cmd_files(args):
    root = _root(args)
    files = L.file_statuses(root)
    if args.json:
        print(json.dumps({"files": files}, indent=2))
    elif not files:
        print("(no documents in idea_basket/)")
    else:
        for f in files:
            extra = f" ({f['ideas']} ideas)" if f["ideas"] else ""
            print(f"  [{f['status']:<7}] {f['name']}{extra}")


def cmd_mark_visited(args):
    root = _root(args)
    entry = L.mark_file_visited(root, args.file, add_ideas=args.ideas)
    if args.json:
        print(json.dumps({"file": args.file, "entry": entry}, indent=2))
    else:
        print(f"[{entry['status']}] {args.file} ({entry['ideas']} ideas)")


def main():
    ap = argparse.ArgumentParser(description="autoresearch idea-basket manager")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_root(p):
        p.add_argument("project_root", nargs="?", default=".")
        p.add_argument("--json", action="store_true")

    p = sub.add_parser("init"); add_root(p); p.set_defaults(fn=cmd_init)

    p = sub.add_parser("add"); add_root(p)
    p.add_argument("--text", required=True)
    p.add_argument("--source", default="agent")
    p.add_argument("--status", default="pending", choices=L.STATUSES)
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("status"); add_root(p)
    p.add_argument("--match", required=True, help="1-based index or text substring")
    p.add_argument("--set", required=True, choices=L.STATUSES)
    p.add_argument("--commit")
    p.add_argument("--result")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("list"); add_root(p); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("files"); add_root(p); p.set_defaults(fn=cmd_files)

    p = sub.add_parser("mark-visited"); add_root(p)
    p.add_argument("--file", required=True)
    p.add_argument("--ideas", type=int, default=0)
    p.set_defaults(fn=cmd_mark_visited)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

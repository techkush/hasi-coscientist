#!/usr/bin/env python3
"""
autoresearch-analyze report generator (controlled).

Reads results.tsv + the spec + findings.md and produces:
  • a direction-aware TEXT summary (stdout, and --json),
  • progress.png  (the primary measure over experiment number),
  • report.pdf    a single-page "pageless" report whose height grows with the
                  content: experiment name, date, experiment time, the goal, one
                  plot per improved metric (primary + any secondary), and a list
                  of every kept (status=keep) experiment with its number, commit,
                  provenance (human / web-or-paper / idea-basket / AI agent), and
                  a short description.

Read-only: never modifies the ledger, the experiment, or git.

Plots/PDF use matplotlib (degrade gracefully if it is missing — the text
summary still prints). To enrich the per-experiment descriptions with 3–4
sentence narratives, pass --narratives narratives.json, a map of
{short_commit: "text"} the analyze skill writes.

Usage:
    python report.py [PROJECT_ROOT] [--out report.pdf] [--png progress.png]
                     [--narratives narratives.json] [--json] [--no-pdf]
"""

import argparse
import datetime
import json
import os
import sys
import textwrap

import analyze_lib as A

WIDTH = 8.5            # inches (letter width; height is content-driven)
LEFT = 0.07
AXW = 0.86

GREEN = "#2f7d52"
GREY = "#8a8f98"
RED = "#b3402f"
BLUE = "#2f6fb3"
INK = "#1b1f2a"

SRC_COLORS = {
    "Baseline": "#6b7280", "Human suggestion": "#b3802f",
    "Web / paper": BLUE, "Idea basket": "#7a4fb3", "AI agent": GREEN,
}


# ---------------------------------------------------------------------------
# text summary
# ---------------------------------------------------------------------------

def fmt(v, nd=4):
    return "n/a" if v is None else f"{v:.{nd}f}"


def fmt_secs(s):
    if not s:
        return "n/a"
    s = int(round(s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"


def source_for(commit, findings, narratives, is_baseline):
    if is_baseline:
        return "Baseline"
    if commit in findings:
        return A.classify_source(findings[commit].get("source", ""))
    return "AI agent"


def description_for(commit, row, findings, narratives):
    if narratives and commit in narratives:
        return narratives[commit]
    if commit in findings and findings[commit].get("change"):
        return findings[commit]["change"]
    return row.get("description", "")


def build_summary(spec, st):
    dirn = "higher" if spec["higher"] else "lower"
    pct = "n/a" if st["pct"] is None else f"{st['pct']:+.1f}%"
    head = (f"{spec['name']} — ran {st['total']} experiments, kept {st['keep']} "
            f"(discard {st['discard']}, crash {st['crash']}). ")
    if st["best"] is not None:
        head += (f"Best {spec['metric']} {fmt(st['best'])} "
                 f"(baseline {fmt(st['baseline'])}, {fmt(st['abs_imp'])} / {pct}, "
                 f"{dirn} is better).")
    else:
        head += "No kept runs yet."
    return head


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def make_pdf(spec, header, rows, st, findings, narratives, out_path, png_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    metrics = A.numeric_metric_cols(spec, header)
    # only plot metrics that actually have a kept/non-crash value
    metrics = [m for m in metrics if A.metric_series(rows, m)]

    goal_lines = textwrap.wrap(spec["goal"] or "(no goal recorded)", 96) or [""]

    # ---- header content (wrap the summary so it never runs off the page) ----
    today = datetime.date.today().isoformat()
    secs, _ = A.total_runtime(spec, header, rows)
    span = "n/a"
    keep_commits = [r.get("commit", "") for r in st["keeps"]]
    dates = [d for d in (A.git_commit_datetime(spec["root"], c) for c in keep_commits) if d]
    if dates:
        d0, d1 = dates[0][:10], dates[-1][:10]
        span = d0 if d0 == d1 else f"{d0} → {d1}"
    summary_lines = textwrap.wrap(build_summary(spec, st), 96) or [""]
    head_lines = [
        {"text": spec["name"], "size": 19, "weight": "bold", "lh": 0.40},
        {"text": f"Autoresearch report   ·   generated {today}", "size": 9.5,
         "color": GREY, "lh": 0.32},
        {"text": f"Experiment dates: {span}     Total run time: {fmt_secs(secs)} "
                 f"over {st['total']} runs", "size": 10, "color": INK, "lh": 0.34},
    ]
    for sl in summary_lines:
        head_lines.append({"text": sl, "size": 10.5, "color": INK, "lh": 0.22})

    # ---- list lines (compute height) ----
    list_entries = []
    for i, item in enumerate(st["stuck"]):
        r = item["row"]
        commit = r.get("commit", "")
        is_base = (i == 0 and item["delta"] is None)
        src = source_for(commit, findings, narratives, is_base)
        desc = description_for(commit, r, findings, narratives)
        desc_lines = textwrap.wrap(desc, 92) or [""]
        delta = item["delta"]
        dtxt = "" if delta is None else f"  (Δ {delta:+.4f})"
        hdr = f"Exp #{r['exp_n']}   {commit}   {spec['metric']} {fmt(item['value'])}{dtxt}"
        list_entries.append((hdr, src, desc_lines))

    # ---- panel heights (inches) ----
    head_h = 0.20 + sum(ln["lh"] for ln in head_lines) + 0.12
    goal_h = 0.45 + 0.20 * len(goal_lines)
    plot_h = 3.35   # includes internal top/bottom padding for title + xlabel
    gap = 0.30
    list_head_h = 0.5
    list_h = list_head_h + sum(0.46 + 0.205 * len(d) for _, _, d in list_entries) \
        if list_entries else list_head_h + 0.3

    panels = [("head", head_h), ("goal", goal_h)]
    for m in metrics:
        panels.append((("plot", m), plot_h))
    panels.append(("list", list_h))

    top_margin = bottom_margin = 0.28
    total_h = top_margin + bottom_margin + sum(h for _, h in panels) + gap * (len(panels) - 1)

    fig = plt.figure(figsize=(WIDTH, total_h), facecolor="white")
    cursor = top_margin

    def place(h):
        nonlocal cursor
        bottom = (total_h - cursor - h) / total_h
        ax = fig.add_axes([LEFT, bottom, AXW, h / total_h])
        cursor += h + gap
        return ax

    def place_plot(h, top_pad=0.40, bot_pad=0.55):
        """Plot axes inset inside the panel so the title and x-label stay within
        the panel and never collide with neighbouring sections."""
        nonlocal cursor
        panel_bottom = total_h - cursor - h
        ax = fig.add_axes([LEFT, (panel_bottom + bot_pad) / total_h,
                           AXW, (h - top_pad - bot_pad) / total_h])
        cursor += h + gap
        return ax

    def text_panel(ax, lines, panel_h):
        ax.axis("off")
        y_in = 0.08
        for ln in lines:
            yf = 1 - y_in / panel_h
            ax.text(ln.get("x", 0.0) / (AXW * WIDTH), yf, ln["text"],
                    transform=ax.transAxes, va="top", ha="left",
                    fontsize=ln.get("size", 10), fontweight=ln.get("weight", "normal"),
                    color=ln.get("color", INK), family=ln.get("family", "sans-serif"))
            y_in += ln.get("lh", 0.22)

    # ---- header panel ----
    ax = place(head_h)
    text_panel(ax, head_lines, head_h)

    # ---- goal panel ----
    ax = place(goal_h)
    goal_block = [{"text": "Goal", "size": 12, "weight": "bold", "lh": 0.28}]
    for gl in goal_lines:
        goal_block.append({"text": gl, "size": 10, "color": INK, "lh": 0.20})
    text_panel(ax, goal_block, goal_h)

    # ---- plot panels ----
    for m in metrics:
        ax = place_plot(plot_h)
        _plot_metric(ax, spec, rows, st, m, plt)

    # ---- list panel ----
    ax = place(list_h)
    ax.axis("off")
    y_in = 0.1
    ax.text(0, 1 - y_in / list_h, "Kept experiments (improvements)",
            transform=ax.transAxes, va="top", fontsize=12, fontweight="bold", color=INK)
    y_in += 0.42
    if not list_entries:
        ax.text(0, 1 - y_in / list_h, "No kept experiments yet.",
                transform=ax.transAxes, va="top", fontsize=10, color=GREY)
    for hdr, src, desc_lines in list_entries:
        yf = 1 - y_in / list_h
        ax.text(0, yf, hdr, transform=ax.transAxes, va="top", fontsize=10.3,
                fontweight="bold", color=INK, family="monospace")
        # source badge on the right
        ax.text(1.0, yf, src, transform=ax.transAxes, va="top", ha="right",
                fontsize=9, fontweight="bold", color=SRC_COLORS.get(src, GREEN))
        y_in += 0.26
        for dl in desc_lines:
            ax.text(0.02, 1 - y_in / list_h, dl, transform=ax.transAxes, va="top",
                    fontsize=9.3, color="#3a4150")
            y_in += 0.205
        y_in += 0.16

    fig.savefig(out_path)
    # also save the primary chart as png for quick viewing
    if st["best"] is not None and A.metric_series(rows, spec["metric"]):
        f2 = plt.figure(figsize=(8, 4.2), facecolor="white")
        _plot_metric(f2.add_subplot(111), spec, rows, st, spec["metric"], plt)
        f2.tight_layout()
        f2.savefig(png_path, dpi=130)
        plt.close(f2)
    plt.close(fig)
    return metrics


def _plot_metric(ax, spec, rows, st, col, plt):
    is_primary = (col == spec["metric"])
    keeps = [(n, v) for (n, v, s) in A.metric_series(rows, col) if s == "keep"]
    disc = [(n, v) for (n, v, s) in A.metric_series(rows, col) if s == "discard"]

    if disc:
        ax.scatter([n for n, _ in disc], [v for _, v in disc], s=22,
                   color=GREY, alpha=0.4, label="discarded", zorder=2)
    if keeps:
        ax.scatter([n for n, _ in keeps], [v for _, v in keeps], s=46,
                   color=GREEN, edgecolor="white", linewidth=0.7, label="kept", zorder=3)

    if is_primary:
        # running best across non-crash rows, direction-aware, over keeps so far
        xs, ys, best = [], [], None
        for r in rows:
            if r["status_l"] == "crash":
                continue
            if r["status_l"] == "keep":
                v = A.to_float(r.get(col))
                if v is not None:
                    best = v if best is None else (max(best, v) if spec["higher"] else min(best, v))
            if best is not None:
                xs.append(r["exp_n"]); ys.append(best)
        if xs:
            ax.step(xs, ys, where="post", color=BLUE, linewidth=1.6,
                    label="running best", zorder=2)
        if st["baseline"] is not None:
            ax.axhline(st["baseline"], color="#c0c4cc", linestyle="--", linewidth=1,
                       label="baseline", zorder=1)
        # annotate kept points with truncated description; keep text in-bounds
        max_n = max((n for n, _ in keeps), default=1)
        min_n = min((n for n, _ in keeps), default=1)
        for r in rows:
            if r["status_l"] != "keep":
                continue
            v = A.to_float(r.get(col))
            if v is None:
                continue
            d = (r.get("description", "") or "")[:22]
            n = r["exp_n"]
            ha = "right" if n == max_n else ("left" if n == min_n else "center")
            dx = -4 if ha == "right" else (4 if ha == "left" else 0)
            ax.annotate(d, (n, v), fontsize=7, color="#3a4150",
                        xytext=(dx, 7), textcoords="offset points", ha=ha,
                        annotation_clip=False)

    ax.margins(x=0.12, y=0.18)
    dirn = ("higher" if spec["higher"] else "lower") + " is better"
    ax.set_ylabel(f"{col}" + (f"  ({dirn})" if is_primary else "  (secondary)"), fontsize=10)
    ax.set_xlabel("experiment number", fontsize=10, labelpad=4)
    ax.set_title(("Primary measure: " if is_primary else "Secondary: ") + col,
                 fontsize=11, fontweight="bold", loc="left", pad=8)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8, loc="best", framealpha=0.9)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_root", nargs="?", default=".")
    ap.add_argument("--out", default="report.pdf")
    ap.add_argument("--png", default="progress.png")
    ap.add_argument("--narratives", help="JSON {short_commit: '3-4 sentence text'}")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args()

    root = A.find_project_root(args.project_root)
    spec = A.parse_spec(root)
    header, rows = A.read_ledger(root)

    if not rows:
        msg = "No results to analyze yet (results.tsv is empty or header-only)."
        print(json.dumps({"ok": False, "message": msg}) if args.json else msg)
        sys.exit(0)

    st = A.stats(spec, rows)
    findings = A.parse_findings(root)
    narratives = {}
    if args.narratives and os.path.exists(args.narratives):
        narratives = json.load(open(args.narratives, encoding="utf-8"))

    out_path = os.path.join(root, args.out)
    png_path = os.path.join(root, args.png)

    pdf_ok, metrics = False, []
    if not args.no_pdf:
        try:
            metrics = make_pdf(spec, header, rows, st, findings, narratives, out_path, png_path)
            pdf_ok = True
        except ImportError:
            print("matplotlib not installed — skipping PDF/PNG (text summary only). "
                  "Install with: pip install matplotlib", file=sys.stderr)

    summary = build_summary(spec, st)
    idea = A.parse_idea_counts(root)

    if args.json:
        print(json.dumps({
            "ok": True, "name": spec["name"], "metric": spec["metric"],
            "direction": spec["direction"], "summary": summary,
            "total": st["total"], "keep": st["keep"], "discard": st["discard"],
            "crash": st["crash"], "keep_rate": st["keep_rate"],
            "baseline": st["baseline"], "best": st["best"],
            "abs_improvement": st["abs_imp"], "pct_improvement": st["pct"],
            "metrics_plotted": metrics, "pdf": out_path if pdf_ok else None,
            "png": png_path if pdf_ok else None, "idea_basket": idea,
        }, indent=2))
    else:
        print(summary)
        print("\nWhat stuck:")
        for i, item in enumerate(st["stuck"]):
            r = item["row"]
            commit = r.get("commit", "")
            is_base = (i == 0 and item["delta"] is None)
            src = source_for(commit, findings, narratives, is_base)
            d = "" if item["delta"] is None else f"  Δ{item['delta']:+.4f}"
            print(f"  Exp #{r['exp_n']}  {commit}  {fmt(item['value'])}{d}  "
                  f"[{src}]  {r.get('description','')}")
        if idea:
            if "selected" in idea:
                print(f"\nIdea basket: {idea.get('selected', 0)} selected, "
                      f"{idea.get('doing', 0)} doing, {idea.get('pending', 0)} pending "
                      f"(of {idea.get('total', 0)}).")
            else:
                print(f"\nIdea basket: {idea.get('applied', 0)} applied, "
                      f"{idea.get('pending', 0)} pending.")
        if pdf_ok:
            print(f"\nPDF: {out_path}\nChart: {png_path}")


if __name__ == "__main__":
    main()

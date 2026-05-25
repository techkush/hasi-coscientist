---
name: autoresearch-analyze
description: Step 6 (final) of the autoresearch pipeline. Read results.tsv from a run and produce a progress summary plus a PDF report — total experiments, keep/discard/crash counts, baseline vs best, total improvement, the changes that stuck, a chart per improved metric, and a single-page report.pdf listing every kept experiment with its number, commit, provenance (human / web-or-paper / idea-basket / AI agent), and a short description. Direction-aware (lower- or higher-is-better). Works for any experiment, not just ML training. Trigger when the user says "analyze the results", "how did the run go", "show progress", "make the report", "summarize the experiments", or after a loop has produced results.
---

# autoresearch-analyze

You are running the **final** step: making sense of a run's `results.tsv` and producing a shareable report. You read and summarize; you never modify the experiment or the ledger.

This skill is **controlled**, like the rest of the pipeline: one script computes the direction-aware statistics, the per-metric charts, and the PDF, so the numbers can't drift. You add judgment only where it helps — composing the short per-experiment narratives.

## Tools that ship with this skill (use them; don't hand-compute the stats)

- `report.py` — the controlled report generator. Reads `results.tsv` + the spec + `findings.md` and writes: a **text summary** (stdout / `--json`), `progress.png` (the primary measure), and **`report.pdf`** — a single-page "pageless" report (experiment name, date, total run time, the goal, one plot per improved metric, and a list of every kept experiment with number, commit, provenance, and description).
- `analyze_lib.py` — shared parsing/stats the script imports. You don't call it directly.
- `ui/report_server.py` + `ui/index.html` — the **browser report viewer** (the default surface; see below).

`<skill_dir>` is this skill's directory; `<root>` is the project root (the folder containing `.autoresearch/`).

## Default flow: browser report viewer

By default, open the local report viewer that ships with this skill (`ui/report_server.py` + `ui/index.html`). It is a stdlib-only local web server acting as a file-based message bus. The page has an **Execute** button (generate the report), shows the summary + stat chips, **embeds `report.pdf` inline**, and offers a **Download** button. The engine is identical to the terminal steps below — the viewer just drives them.

Protocol — control files live in a runtime dir (`$WORKDIR`); the report files live in the project root. `state.json` (you write) = `{phase, name, metric, summary, has_report, report_rev, message}` (phase: `idle|generating|ready|empty|error`). `summary.json` (you write) = the `report.py --json` object. The server writes `execute.json` on the button and serves `/report.pdf` + `/progress.png` from the project root.

Orchestrate it like this:

1. **Start it.** Resolve `<root>`. `WORKDIR=$(mktemp -d)`. Launch in the background on a free port (default 8772; pick another if busy): `python3 <skill_dir>/ui/report_server.py --port <PORT> --workdir "$WORKDIR" --project-root "<root>"` (run_in_background). Open the browser: `open http://127.0.0.1:<PORT>` (macOS) / `xdg-open` (Linux). Tell the user: "Opened the report viewer in your browser."
2. **Seed the state.** Write `$WORKDIR/state.json` with `phase:"idle"`, the experiment `name`/`metric` from the spec, and `has_report` = does `<root>/report.pdf` already exist.
3. **Wait for Execute.** `Monitor` until `$WORKDIR/execute.json` appears.
4. **Generate.** On `execute.json` (delete it): run Steps 1–2 below — if the ledger is empty, set `state.json` `phase:"empty"` and go back to step 3; otherwise compose `narratives.json` (optional, for richer descriptions) and run `python <skill_dir>/report.py <root> --narratives <root>/narratives.json --json`. Write the JSON output to `$WORKDIR/summary.json`, then set `state.json` `phase:"ready"`, `has_report:true`, `summary:"<headline>"`, and **bump `report_rev`** (so the viewer refreshes the embedded PDF). Stay available for re-generation (loop back to step 3).

**Fallback to terminal** if the server can't start or the browser can't open (headless, sandbox, port blocked), or if the user prefers it: say so and run the steps below directly.

## Core principles

1. **Hide the plumbing.** Lead with the research story — what improved, by how much, what stuck — not file mechanics.
2. **Any experiment, not just training.** The script reads the measure name and direction from the spec; never assume ML or lower-is-better.
3. **Read-only.** Never edit `results.tsv`, the experiment files, or git state. The script is read-only too.

## Step 1 — Run the report

```
python <skill_dir>/report.py <root> --json
```

If it reports there are no results yet (empty / header-only ledger), tell the user and stop. Otherwise read the JSON: `total`, `keep`/`discard`/`crash`, `keep_rate`, `baseline`, `best`, `abs_improvement`, `pct_improvement`, `metrics_plotted`, and the `pdf`/`png` paths. These are the authoritative, direction-aware numbers — don't recompute them by hand.

The script already: takes the best among `keep` rows (min for lower-is-better, max for higher), excludes crashes from baseline/best/plots, guards percent against a zero baseline, charts **every** numeric metric (primary + any secondary, e.g. memory), and reads provenance from `findings.md`.

## Step 2 — (Recommended) write richer narratives, then regenerate

The ledger descriptions are short (they are commit messages). For a report the user can actually read, compose a **3–4 sentence narrative** per kept experiment — what was changed and **where the idea came from** (the user, a paper/web source, the idea basket, or the AI agent's own reasoning) — using the `findings.md` source, the `results.tsv` description, and what you know of the run. Follow the format in `narratives.template.json` (in this skill's directory): a JSON map of `{short_commit: "text"}`. Write it and regenerate:

```
python <skill_dir>/report.py <root> --narratives <root>/narratives.json
```

The PDF uses these narratives for the per-experiment descriptions and keeps the provenance badge. (Skip this step for a quick look; the plain run still produces a complete report.)

## Step 3 — Report back (plain language)

Relay the script's headline, then a short list of the changes that stuck (with deltas and where each idea came from), and point to the files:

> **<name>** — ran <total> experiments, kept <keep>. Improved <measure> from <baseline> to <best> (<abs> / <pct>, <direction> is better). Biggest win: "<best description>". Full report: `report.pdf`.

Keep crashes/discards as a single count, not a wall of rows. If `idea.md` exists, mention how many basket ideas were applied vs. pending (the JSON includes `idea_basket`).

## If matplotlib is missing

`report.py` still prints the full text summary and exits cleanly; it just skips `report.pdf`/`progress.png` and says so on stderr. Offer to install matplotlib (`pip install matplotlib`) so the PDF and charts can be produced.

## Optional — analysis notebook

If the user asks for a reusable notebook (not by default), create `analysis.ipynb` that loads `results.tsv`, computes the same direction-aware stats (reuse `analyze_lib.py`), and renders the charts, so they can re-run it later.

## Rules

- **Read-only**: never modify results, experiment files, or git. Drive `report.py`; don't hand-roll the stats or the chart.
- Be **direction-aware** in every comparison (the script reads `direction` from the spec).
- Exclude crashes from the charts; count them in the summary (the script does this).
- Don't flood the conversation — let the script redirect its own output; report a tight summary and point to `report.pdf`.
- Hide the plumbing; lead with the research outcome.

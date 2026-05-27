---
name: autoresearch-setup
description: Step 3 of the autoresearch pipeline. Prepare a generated experiment for autonomous iteration — make sure it's a git repo with a committed baseline, agree a run tag, create the autoresearch/<tag> branch, prepare any data/benchmark, and confirm the experiment is ready to run. Works for any experiment, not just ML training. Trigger when the user says "set up the run", "start the run", "prepare to run", or after autoresearch-generate when they're ready to begin.
---

# autoresearch-setup

You are running **step 3** of the autoresearch pipeline: getting a generated experiment ready to iterate. After this, the user runs `/autoresearch-experiment` (baseline) or `/autoresearch-loop`. You prepare the run; you do NOT start experimenting here.

This skill is **controlled**, like `/autoresearch-generate`: two scripts do every deterministic mutation and check, and you only handle the human decisions (the run tag) and the confirmed heavy actions (installing dependencies, downloading data). Don't hand-run git or hand-edit `.gitignore`/`results.tsv` — the scripts own that so the invariants hold mechanically.

## Tools that ship with this skill (use them; do not hand-write the plumbing)

- `readiness.py` — the **read-only gate**. Prints `PASS`/`WARN`/`FAIL` per check, exits non-zero on any `FAIL`. Run it first (`PRE`) to see what's needed, and last (`--final`) to confirm the run is truly ready. It also invokes `/autoresearch-generate`'s `validate.py` when reachable, so a half-generated experiment can't slip through.
- `prepare_run.py` — the **mutating materializer**. Does: `git init` (if needed), `.gitignore` reconcile (incl. the data dir, and keeps `.autoresearch/spec.md` tracked), `results.tsv` header reconcile, the baseline commit from explicit paths, the `ar-baseline` tag, and the `autoresearch/<tag>` branch **forked from the baseline tag**.
- `setup_lib.py` — shared spec parsing / git plumbing / dependency resolution the two scripts import. You don't call it directly.

`<skill_dir>` below is this skill's own directory (where this SKILL.md lives).

## Default flow: HASI dashboard loop panel

By default, setup is driven from the shared **Loop panel** in the HASI dashboard — the same panel `/autoresearch-loop` uses, so setup, baseline, and iteration all share **one results table**. The panel has three buttons: **Execute** (prepare the run + record the baseline — disabled once a baseline exists), **Run loop** (iterate), and **Stop**.

Orchestrate it exactly as described in `/autoresearch-loop`'s "Default flow: HASI dashboard loop panel" section (seed `state.json`, monitor the button files). The only setup-specific part is the **Execute** handler:

- On `execute.json`: run this skill's gate and materializer end-to-end — `readiness.py <root>` (PRE) → resolve deps/data if needed (confirm heavy actions) → auto-pick a date tag and run `prepare_run.py <root> --tag <today>` → `readiness.py <root> --final` to gate → then the baseline run via `../autoresearch-loop/run_iter.py <root> --baseline`. Update `state.json` `baseline_done:true`, `setup_done:true`, `phase:"baseline_done"`.
- **Run loop / Stop** are driven by `/autoresearch-loop`'s engine (`../autoresearch-loop/run_iter.py`); follow that skill's loop step. If you'd rather keep setup focused on preparation only, after the baseline tell the user "Baseline recorded — click Run loop, or run `/autoresearch-loop`" and stop.

**Fallback to terminal** (the step-by-step flow below) if the HASI dashboard isn't available, or if the user prefers it. The scripts and invariants are identical either way.

## Core principles

1. **Hide the plumbing.** Talk to the user about *their run* — the branch, the data, "ready to go" — not script names or git mechanics. Report in plain research language.
2. **Any experiment, not just training.** Use neutral words ("run", "experiment", "the measure"). Don't assume ML.
3. **Let the tools enforce the invariants.** The gate and the materializer exist so the run is correct by construction — don't bypass them.
4. **Minimize questions; confirm heavy actions.** The only thing usually worth asking is the run tag. Always confirm before installing dependencies or starting a large download — they change real state.

## Step 1 — Locate the project and read the spec

Find `.autoresearch/spec.md` (current dir or a `<slug>/` subfolder). The project root is the folder containing `.autoresearch/`. Use `<project_root>` in the commands below (the scripts also auto-detect it if you pass `.`).

## Step 2 — Run the readiness gate (PRE)

```
python <skill_dir>/readiness.py <project_root>
```

Read the output. It tells you exactly what state the run is in:

- **`FAIL generated files` / `FAIL generate finished` / `FAIL compiles` / `FAIL invariants`** → the experiment isn't actually built (generate not run, or left half-done — unfilled `>>> GENERATE` / `NotImplementedError`). **Stop** and tell the user to run `/autoresearch-generate` (or finish it) first. Do not proceed.
- **`WARN dependencies`** → note which libraries are missing; you'll offer to install in Step 3.
- **`WARN data`** → the benchmark isn't present yet; you'll prepare it in Step 5.
- **`WARN gitignore` / `WARN results.tsv` / `WARN git repo` / `WARN run branch`** → expected before setup; `prepare_run.py` fixes these in Step 4.

If there are any `FAIL` lines, resolve them (or stop) before continuing.

## Step 3 — Environment / dependencies

If the gate reported missing dependencies, tell the user what's needed and offer to install from the project's dependency file (`uv sync`, or `pip install -r requirements.txt`). **Confirm once** before installing — it modifies their environment. If the user declines or it's not possible, note the run may fail until deps are present, and continue.

## Step 4 — Agree a run tag, then materialize the run

- Propose a short tag based on today's date (e.g. `may25`); if `autoresearch/<tag>` already exists, suffix it (`may25-2`). Confirm the tag in one short message with a green marker (`> **🟩 ...**`), never a numbered-list picker. Accept the user's override.
- Then run the materializer:

```
python <skill_dir>/prepare_run.py <project_root> --tag <tag>
```

This makes it a git repo, fixes `.gitignore` (including the data folder, and it keeps the spec under version control), aligns `results.tsv`, commits the baseline from explicit generated files only (never folding in unrelated edits), tags it `ar-baseline`, and creates `autoresearch/<tag>` **from that baseline tag**. It prints what it did — relay it in plain language.

If it errors that the branch already exists, agree a new tag and re-run. If it warns that `results.tsv` has data with a mismatched header, surface that to the user (don't silently rewrite a populated ledger).

## Step 5 — Prepare the data / benchmark

If the gate's `WARN data` showed the benchmark missing and the read-only file has a prep step:

- Run it (e.g. `python <readonly_fixed>`). If the download/build is large or slow, **tell the user first and confirm**; consider running it in the background and reporting when done.
- If it can't be prepared automatically (e.g. data lives at an external/login-gated location), tell the user the exact command to run and stop until it's ready.

If the spec has no data, skip this step.

## Step 6 — Final gate

```
python <skill_dir>/readiness.py <project_root> --final
```

In `--final` mode the state checks are strict: it must be a git repo, on the `autoresearch/<tag>` branch, baseline committed and tagged, `.gitignore` complete, `results.tsv` header correct, and the code valid. Dependencies/data that the user chose to defer remain `WARN`. If anything is `FAIL`, fix it and re-run. Do **not** run a full experiment here — the baseline run is the first iteration of `/autoresearch-experiment` / `/autoresearch-loop`.

## Step 7 — Confirm and hand off (plain language)

Short recap in research terms:

> Ready to run **<name>** on branch `autoresearch/<tag>`. We'll iterate to improve <measure> (<direction> is better)<, on <data>>, each run capped at <N> minutes.

Then: "Next: run `/autoresearch-experiment` to do the baseline run first, or `/autoresearch-loop` to start iterating autonomously."

Do NOT begin experiments here.

## Rules

- Drive the two scripts; don't hand-run git or hand-edit `.gitignore`/`results.tsv`/the baseline.
- **The gate is binding:** never hand off a run that `readiness.py --final` doesn't pass. A half-generated or non-compiling experiment must go back to `/autoresearch-generate`.
- The project must end up a **git repo with the baseline committed and tagged `ar-baseline`**, on a fresh `autoresearch/<tag>` branch forked from that baseline.
- `prepare_run.py` keeps `results.tsv`, `run.log`, the data dir, and the runtime parts of `.autoresearch/` out of git — but keeps `spec.md` tracked. Don't re-add the ignored ones.
- Confirm before **large downloads or dependency installs**; otherwise proceed and narrate briefly.
- Don't run a full experiment; leave the baseline to the experiment/loop step.
- Hide the plumbing; minimize questions; green-marked one-per-message when you must ask.

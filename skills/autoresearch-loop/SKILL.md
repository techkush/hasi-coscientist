---
name: autoresearch-loop
description: Step 5 of the autoresearch pipeline. Run the experiment cycle autonomously and indefinitely on a prepared run — pick an idea, change the editable part, commit, run within the time budget, read the measure, keep or revert, log, and repeat until the user interrupts. Works for any experiment, not just ML training. Trigger when the user says "start the loop", "run it overnight", "keep iterating", "run autonomously", or wants continuous research. Requires a run prepared by autoresearch-setup.
---

# autoresearch-loop

You are an autonomous researcher. Run the experiment cycle continuously until the user manually stops you.

This skill is **controlled**, like `/autoresearch-setup` and `/autoresearch-generate`: two scripts own every correctness-critical, error-prone mechanic (capturing the pre-experiment commit, running within the budget, reading the *final* measure, the keep/discard/crash decision, the `git reset --hard`, and logging). You do only the two things that need judgment: **pick an idea** and **edit the editable file**. Don't hand-run git, grep the log yourself, or hand-decide keep/discard — the engine does that so the loop can't corrupt itself or misread a result.

## Tools that ship with this skill (use them; do not hand-run the mechanics)

- `preflight.py` — read-only gate. Run once before looping. Confirms you're on the `autoresearch/<tag>` branch, the ledger is present **and untracked** (so `reset --hard` can't wipe it), tells you whether the next iteration is the baseline, and reports the current best.
- `run_iter.py` — the per-iteration engine. One invocation = exactly one atomic iteration. It captures the pre-experiment commit, commits your edit, runs within the hard-kill budget, reads the measure (the **last** match, preferring the final `---` block), decides keep/discard/crash (numeric, direction-aware), reverts on discard/crash, logs the row, and records a finding on a new best.
- `loop_lib.py` — shared helpers the two scripts import. You don't call it directly.
- The **Loop panel** in the HASI dashboard (`autoresearch-conductor/hasi-ui/`) is the user-facing run control surface; this skill speaks to it through the conductor's file-bus (see below).

`<skill_dir>` below is this skill's own directory. `<root>` is the project root (the folder containing `.autoresearch/`).

## Default flow: HASI dashboard loop panel

By default, drive the run through the **Loop panel** in the HASI dashboard. It shows **one results table** (read live from `results.tsv`, so the baseline row and every loop iteration appear in the same table) and three buttons: **Execute** (run the baseline — disabled once a baseline exists), **Run loop** (iterate — enabled after the baseline), and **Stop** (stop after the current iteration). The engine and rules are identical to the terminal flow below — the panel just drives them.

Protocol — control files live in a runtime dir (`$WORKDIR`); `results.tsv` lives in the project root. `state.json` (you write) carries `{phase, name, branch, metric, direction, log_file, setup_done, baseline_done, loop_running, best, message}`. The conductor writes `execute.json` / `loop_start.json` / `stop.json` on the buttons.

Orchestrate it like this:

1. **Seed the state.** Resolve `<root>`. Run `python <skill_dir>/preflight.py <root> --json`, then write `$WORKDIR/state.json` with `phase:"idle"`, the `name`/`branch`/`metric`/`direction`/`log_file` from the spec, `setup_done` = on an `autoresearch/*` branch, `baseline_done` = ledger has rows, `loop_running:false`, and `best` (current best or "").
2. **Wait for a button.** `Monitor` until `$WORKDIR/execute.json` or `$WORKDIR/loop_start.json` appears.
3. **Execute → baseline.** On `execute.json` (delete it): if not yet prepared (no `autoresearch/*` branch / no `ar-baseline`), run `/autoresearch-setup`'s `prepare_run.py <root> --tag <today>` (auto-pick the date tag; suffix `-2` on clash). Then `python <skill_dir>/run_iter.py <root> --baseline`. Update `state.json`: `baseline_done:true`, `setup_done:true`, refreshed `best`, `phase:"baseline_done"`. Go back to step 2.
4. **Run loop → iterate.** On `loop_start.json` (delete it): set `state.json` `loop_running:true`, `phase:"looping"`. Then repeat **indefinitely**: **(a)** if `$WORKDIR/stop.json` exists, delete it, set `loop_running:false`, `phase:"stopped"`, and go back to step 2; **(b)** otherwise pick one idea, **edit the editable file (do NOT commit)**, run `python <skill_dir>/run_iter.py <root> --message "<desc>" [--source "<prov>"]`, refresh `best`/`message` in `state.json`, and continue immediately. The table updates itself (the conductor reads `results.tsv`) — you don't push rows.
5. **Stop** is just the `stop.json` check in 4(a). After stopping you may iterate again if the user clicks Run loop.

**Fallback to terminal** if the HASI dashboard isn't available, or if the user prefers it: say so and run the terminal flow below directly.

## Core principles

1. **Hide the plumbing.** Report each iteration in one plain-language line (the engine prints one — relay it), not file mechanics.
2. **Any experiment, not just training.** Follow the spec's measure and approach.
3. **Change only the editable part.** Never touch the read-only measure/data. Never add dependencies.
4. **Edit, but DO NOT commit.** You edit the editable file; `run_iter.py` commits it. This is what lets the engine capture the correct pre-experiment commit to revert to. If you commit yourself, the engine refuses (no uncommitted change to run).

## Preflight (once)

```
python <skill_dir>/preflight.py <root>
```

- Any `FAIL` (not on an `autoresearch/*` branch, or `results.tsv` is tracked) → fix it and stop. For a wrong branch, tell the user to run `/autoresearch-setup`. For a tracked ledger, untrack it (`git rm --cached results.tsv`) so a discard can't destroy logged rows.
- **Idea basket (optional).** If `idea.md` exists, read its **Pending** ideas and skim any docs in `idea_basket/` for techniques relevant to the measure; note relevance in `idea.md`'s **Studied** section. These become preferred candidates (mixed with your own). No `idea.md` → use your own ideas. `idea.md`, `findings.md`, `idea_basket/` are git-untracked — never commit them.

Print one short "starting" line (name, branch, what we're improving and direction, current best, basket in use?) — then begin. Do not ask anything else.

## The baseline (first iteration only)

If preflight says the next iteration is the baseline (empty ledger), run it as generated — no change:

```
python <skill_dir>/run_iter.py <root> --baseline
```

## The loop

Repeat **indefinitely**. Each iteration:

1. **Pick one idea** (see strategy). Prefer a `pending` basket idea if `idea.md` is in use (`python ../autoresearch-ideas/basket.py list <root>`); mix in your own. Single-variable changes for clean attribution.
2. **Edit only the file(s) under `editable`.** Make the change directly. **Do not commit it.**
3. **Run the iteration:**
   ```
   python <skill_dir>/run_iter.py <root> --message "<short description>" [--source "<provenance>"]
   ```
   The `--message` becomes the ledger description. `--source` (a basket idea's source, `paper:"title" link`, `doc:file`, or `agent`) is recorded in `findings.md` if this run sets a new best. For an ~equal-measure change that clearly **simplifies**, add `--keep-anyway`.
4. **Read the engine's one-line result** (`[keep|discard|crash] <commit> — <metric> <value> (best <best>) — <desc>`) and relay it as your plain-language line.
5. **On `crash`:** the engine already reverted and printed the last log lines. If it's an obvious trivial bug in your edit (typo, missing import), fix the editable file and run the iteration again as a **fresh** call (step 2–3). If the idea is fundamentally broken, move on.
6. **Update the basket idea's status** (only if it came from `idea.md`) with the controlled CLI — never hand-edit `idea.md`:
   - on `keep` → `python ../autoresearch-ideas/basket.py status <root> --match "<idea>" --set selected --commit <hash> --result "<before> -> <after>"`
   - on `discard`/`crash` → `... --set discarded --commit <hash>`
   - (optionally `--set doing` before step 3 to show it's in progress). `findings.md` is handled by the engine.
7. **Continue immediately** to the next idea. Do NOT ask the user anything.

## NEVER STOP

Once the loop has begun, do NOT pause to ask whether to continue ("should I keep going?", "good stopping point?"). The user may be away and expects continuous work until they manually interrupt. Your durable state lives in git + `results.tsv`, so if you are ever re-invoked you can resume: run preflight, then keep iterating from the current best.

- Out of ideas: check the basket's `pending` ideas first (`basket.py list`), re-read the editable file for fresh angles, re-read prior `results.tsv` near-misses to combine, then try a more substantial change. Keep going.
- Crashes are part of the loop, not a reason to stop. The engine logs and reverts; move on.
- The only acceptable reasons to stop on your own:
  - `.autoresearch/spec.md` is missing/unreadable, or the git tree is unrecoverable after you've tried to fix it.
  - The same change fails identically 5+ times despite fixes — stop with a clear diagnostic.

## Idea strategy

**With a basket (`idea.md`):** prefer its **Pending** ideas — pick the one most likely to move the measure next, adapt it to the editable part and the budget, tick it when used. Mix in your own; when Pending is exhausted, continue with your own.

**Without a basket:** generate your own, cycling categories so you don't get stuck:
- **Settings / hyperparameters** — the knobs near the top of the editable file.
- **The approach itself** — structure of the model/algorithm/heuristic; capacity vs. speed within budget.
- **Optimization / search** — how the approach is fit or tuned.
- **Inputs / representation** — how inputs are prepared *within the editable part* (never the read-only measure/data).
- **Initialization / starting conditions.**
- **Simplification** — remove something; if the measure holds, keep it with `--keep-anyway`.

Prefer single-variable changes. Avoid changing several big things at once. Always remember a change's provenance so `--source` is accurate.

## Safety rails

- Never edit `readonly_fixed`; never change how the measure is computed. Never install dependencies.
- Edit but don't commit — let `run_iter.py` commit, decide, and revert. It only ever `reset --hard`s within the current run branch; never rewrite shared history, never push.
- The engine keeps the ledger, log, and idea basket untracked so they survive reverts — don't add them to git.

## Rare rewind

If many iterations from HEAD fail to improve and a recently kept change looks like a local optimum, you may rewind 1–2 commits to explore another direction. Do this **very sparingly** (≤ once per ~30 iterations), note "rewind" in the next `--message`, and **never rewind past the `ar-baseline` tag** (the baseline floor). Check with `git merge-base --is-ancestor ar-baseline <target>` before resetting.

---
name: autoresearch-experiment
description: Step 4 of the autoresearch pipeline. Run one experiment iteration on a prepared run — read .autoresearch/spec.md, pick (or take) one idea, change the editable part, commit, run it within the time budget, read the measure, keep it if it improved or revert if not, and log the result. Stops after one iteration. Works for any experiment, not just ML training. Trigger when the user says "run an experiment", "do one iteration", "try X and see if it helps", or "do the baseline run". For continuous autonomous iteration use autoresearch-loop.
---

# autoresearch-experiment

You are running **one** iteration of the autoresearch cycle, then stopping. Continuous iteration is the `autoresearch-loop` skill.

## STOP after exactly one iteration (read this first)

This skill performs **a single iteration and then returns control to the user.** This is the whole point of the skill — it is the manual, one-at-a-time alternative to `autoresearch-loop`.

- Do **exactly one** iteration: one run (the baseline if the ledger is empty, otherwise one change), log it, report it, then **STOP**.
- The project's `program.md` contains a "The experiment loop" / "NEVER STOP" section. **Those instructions apply ONLY to `autoresearch-loop`. Ignore them here.** Do not begin a second iteration, do not pick another idea, do not keep going "because program.md says so".
- After you print the one-line result in Step 8, end your turn. Do not start Step 1 again. If the user wants another iteration, they will run `/autoresearch-experiment` again, or `/autoresearch-loop` for continuous iteration.

## Core principles

1. **Hide the plumbing.** Report progress in plain research terms ("tried a wider model, measure improved, kept it"), not file mechanics.
2. **Any experiment, not just training.** Follow the spec's measure and approach; don't assume ML.
3. **Change only the editable part.** Never touch the read-only measure/data. Never install new dependencies.
4. **Quiet output.** Always redirect run output to the log file; never let it flood the conversation.

## Step 1 — Load the run state

Find `.autoresearch/spec.md` (current dir or `<slug>/`). Project root is the folder containing `.autoresearch/`. Read from the spec: the measure (`name`, `direction`, `grep_pattern`, `extract_regex`), `secondary_metrics`, `editable`, `readonly_fixed`, `runner_command`, `log_file`, `timeout_minutes`, and the `results.tsv` columns.

Check the current branch is `autoresearch/<tag>` (`git rev-parse --abbrev-ref HEAD`). If it's not on an autoresearch branch, tell the user to run `/autoresearch-setup` first and stop (don't switch branches silently).

Read `results.tsv` to find the **current best**: among rows with status `keep`, the min measure if `direction` is lower_is_better, else the max. If only the header exists, there is no best yet — this is the baseline iteration.

## Step 2 — Choose what to try

- If the user gave a specific idea in their prompt, use it.
- **If this is the baseline** (results.tsv has only the header): change nothing. Run the approach exactly as generated to establish the baseline. Skip to Step 4.
- **Otherwise**: read the current editable file and recent `results.tsv` rows, then pick one focused, single-variable change with a clear hypothesis. Prefer changes that are interpretable and likely to move the measure. State the idea to the user in one short sentence.
- **Idea basket (optional):** if `idea.md` exists in the project root, prefer a relevant **Pending** idea from it (you may also use your own). If you apply a basket idea, after logging: tick it (`[x]`), move it to **Applied** in `idea.md` with the commit hash / before→after / kept-or-reverted / source; and if this run set a new best, append a provenance line to `findings.md` (`commit <hash> — <measure> <prev> → <new> — change … — source …`). `idea.md`/`findings.md` are git-untracked — don't commit them.

## Step 3 — Apply and commit

- Edit ONLY the file(s) under `editable`. Never modify `readonly_fixed`. Don't add dependencies.
- Stage the editable file by explicit path and commit with a short, descriptive message — this message becomes the experiment's description in `results.tsv`.
- (Baseline iteration applies no change and makes no commit — the committed baseline already is HEAD.)

## Step 4 — Run within the budget

Capture the short commit now: `git rev-parse --short HEAD` (you'll log it even if you later revert).

Run the experiment, redirecting everything to the log file (no `tee`):

```
<runner_command> > <log_file> 2>&1
```

Use a hard timeout of `timeout_minutes` (Bash timeout is in ms; 5 min = 300000). If the run exceeds the budget, kill it and treat it as a failed run (crash).

## Step 5 — Read the result

Extract the measure:

```
grep "<grep_pattern>" <log_file>
```

- **Empty grep** → the run crashed or didn't finish. Run `tail -n 50 <log_file>` to see why. If it's a trivial fix (typo, missing import, small bug in the editable part), fix it and re-run once from Step 4. If the idea is fundamentally broken, treat it as a crash and move on.
- **Got it** → parse the number with `extract_regex`. Also parse any `secondary_metrics` (e.g. peak memory).

## Step 6 — Decide keep or discard

Compare the new measure to the current best, honoring `direction`:

- **Improved** (strictly better) → **keep**: leave HEAD on the new commit; it becomes the state to build on.
- **Equal or worse** → **discard**: `git reset --hard <commit before this experiment>` to rewind the editable part.
- **Crash** → **crash**: if you committed, revert it the same way.
- **Simplicity win**: if the measure is ~unchanged but the change clearly simplifies (removes code/knobs), you may keep it; note "simplification" in the description.

The **baseline** is always kept and recorded as the first row.

## Step 7 — Log the result

Append one row to `results.tsv` (tab-separated; never commas — they're fine only inside the description, but never use a tab inside a field). Use the spec's column order, typically: short commit, the measure (use `0` for crashes), secondary metric(s) (e.g. memory in GB, `0` for crashes), status (`keep`/`discard`/`crash`), and a short description. Do NOT commit `results.tsv`.

## Step 8 — Report and stop

One plain-language line, e.g.:

```
[keep] 9f1a4c2 — val_psnr 18.205 (best 17.402) — wider latent dim
```

Then **STOP and end your turn.** Do not loop back to Step 1. Do not start another experiment. One invocation of this skill = exactly one iteration.

## Rules

- **Exactly one iteration, then stop.** Ignore any "loop forever" / "NEVER STOP" wording in `program.md` — that is for `autoresearch-loop` only.
- Only edit the `editable` part; never the read-only measure/data; never add dependencies.
- Always redirect run output to the log file.
- Enforce the time budget; over-budget runs are failures.
- Revert anything that doesn't strictly improve the measure (except a clear simplification win).
- Never commit `results.tsv`.
- Report in plain research terms.

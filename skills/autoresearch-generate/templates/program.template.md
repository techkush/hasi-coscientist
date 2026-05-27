# {{NAME}}

Operating manual for the autonomous experiment loop.

## Setup

1. **Agree a run tag**: propose a tag based on today's date (e.g. `may25`). The branch `autoresearch/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from the baseline.
3. **Verify the data/benchmark exists**: {{DATA_VERIFY}}
4. **Initialize results.tsv**: create `results.tsv` with just the header row. The baseline is recorded after the first run.
5. **Confirm and go**: confirm the setup looks good, then begin.

## Experimentation

Each run targets a **compute budget of {{COMPUTE_SECONDS}}s** (the in-code `TIME_BUDGET`). The loop **hard-kills** any run that exceeds **{{TIMEOUT_MINUTES}} minute(s)** ({{KILL_SECONDS}}s) of wall-clock — the budget is set below the kill window so startup and final evaluation always fit. Launch one run with: `{{RUNNER_COMMAND}}`.

**What you CAN change:**
- `{{EDITABLE}}` only — {{WHAT_CAN_CHANGE}}

**What you CANNOT change:**
- `{{READONLY}}` — it is read-only. It holds the fixed measure, the data/benchmark, and the constants (compute budget, kill timeout).
- Dependencies — use only what is already listed; do not add packages.
{{EXTRA_CONSTRAINTS}}

**The goal**: {{GOAL_WORD}} `{{METRIC}}` ({{DIRECTION_WORD}} is better). The budget is fixed, so every run gets the same compute.

**Resource use** is a soft constraint — small increases for real gains are fine; they should not blow up.

**Simplicity** is a tiebreaker — all else equal, simpler is better. A tiny gain that adds a lot of ugly complexity is probably not worth it; an equal-or-better result from *removing* code is a win.

**The first run** is always the baseline as-is, to establish the starting value.

## Output format

When `{{EDITABLE}}` finishes it prints:

```
{{RESULT_BLOCK}}
```

Read the key metric from the log file:

```
grep "{{GREP_PATTERN}}" {{LOG_FILE}}
```

## Logging results

Log each experiment to `results.tsv` (tab-separated, NOT comma-separated — commas break in descriptions). It stays **untracked** by git.

Header and columns:

```
{{COLUMNS_TSV}}
```

- `commit` — short git hash (7 chars)
- numeric metric columns — the values from the result block above (use 0 for crashes)
- `status` — `keep`, `discard`, or `crash`
- `description` — short text of what the experiment tried

## The experiment loop

This is the **autonomous** loop. (Running a single iteration is a separate, one-shot action that stops after one cycle — the NEVER-STOP rule below applies only to autonomous runs.)

LOOP FOREVER:

1. Look at the git state: the current branch/commit.
2. Change `{{EDITABLE}}` with one experimental idea by editing the code directly.
3. `git commit`.
4. Run: `{{RUNNER_COMMAND}} > {{LOG_FILE}} 2>&1` (redirect everything — do NOT tee or flood context), with a hard timeout of {{TIMEOUT_MINUTES}} minute(s).
5. Read the result: `grep "{{GREP_PATTERN}}" {{LOG_FILE}}`.
6. If the grep output is empty, the run crashed or timed out. Read `tail -n 50 {{LOG_FILE}}` and try to fix. If you can't after a few attempts, skip it.
7. Record the result in `results.tsv` (do NOT commit results.tsv — leave it untracked).
8. If `{{METRIC}}` improved ({{DIRECTION_WORD}}), keep the commit and advance the branch.
9. If `{{METRIC}}` is equal or worse, `git reset --hard` back to where you started.

**Timeout**: a run exceeding {{TIMEOUT_MINUTES}} minute(s) is killed and treated as a failure (discard and revert).

**Crashes**: fix something dumb (typo, missing import) and re-run; if the idea is fundamentally broken, log `crash` and move on.

**NEVER STOP** (autonomous runs only): once the loop has begun, do not pause to ask whether to continue. Keep iterating until manually interrupted. If you run out of ideas, think harder — re-read the in-scope files, combine previous near-misses, try more radical changes within the fixed constraints.

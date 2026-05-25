---
name: autoresearch-generate
description: Step 2 of the autoresearch pipeline. Read .autoresearch/spec.md (written by autoresearch-init) and build the runnable experiment from it — using the controlled scaffolder (scaffold.py + templates/) to materialize the fixed measure file, the editable approach file, program.md, and supporting files, then filling only the domain-specific logic and passing the validate.py gate. Opens a local browser UI by default (Execute button, file browser, chat to request changes); falls back to terminal. Works for any experiment, not just ML training. Mechanical: builds strictly from the spec, no web research. Trigger when the user says "generate the experiment", "build it", "run generate", or after init when they're ready to scaffold.
---

# autoresearch-generate

You are running **step 2** of the autoresearch pipeline: turning `spec.md` into a working experiment the loop can run. You build files; you don't run the full experiment (that's `autoresearch-setup` / `autoresearch-loop`).

This skill is **controlled**: a scaffolder writes every invariant-bearing part from templates, you fill only the two irreducibly domain-specific bodies, and a validator gates the result. Build **strictly from the spec** — no web, no arXiv, no invented goals or metrics.

## Tools that ship with this skill (use them; do not hand-write the boilerplate)

- `scaffold.py` — parses `.autoresearch/spec.md` and materializes the experiment from `templates/`, filling: the budget headroom (`TIME_BUDGET` set safely below the loop's hard-kill timeout), the exact result block + greppable lines, `results.tsv` columns kept consistent with the measure + secondary metrics (every numeric column gets a printed line — no orphan columns), the runner, dependencies, and `.gitignore`.
- `validate.py` — the gate. Compiles the files and checks every invariant; exits non-zero with `FAIL` lines if anything is wrong.
- `templates/` — the controlled file templates (`prepare.frame.py`, `executor.frame.py`, `program.template.md`, `README.template.md`, `gitignore.template`).

The scaffolder leaves exactly two kinds of region for you to fill, marked `# >>> GENERATE:... <<<`:
- in the **read-only file**: `get_data()` (data/benchmark) and `measure()` (the ground-truth scorer);
- in the **editable file**: the `imports`, `knobs`, `approach`, and `run` regions (populate a `results` dict).

## Default flow: browser UI

By default, run the build through the local browser UI that ships with this skill (`ui/generate_server.py` + `ui/index.html`, next to this SKILL.md). It is a stdlib-only local web server acting as a file-based message bus: the user clicks **Execute** to build, browses the generated files one by one on the left, sees the validation result, and **chats** to request changes that you apply to the files (and to `spec.md`). The build engine is identical to the terminal steps below — the UI just drives it.

Protocol — all control files live in a runtime dir (`$WORKDIR`); generated files live in the project root:
`state.json {phase,message}` (phase: `ready|generating|review|working|done`), `plan.json` (you write), `manifest.json` (you write), `execute.json`/`chat.json`/`done.json` (the server writes on user actions).

Orchestrate it like this:

1. **Locate the spec** (Step 1 below) and resolve the project root. Create a runtime dir: `WORKDIR=$(mktemp -d)`. Get the parsed values with `python <skill_dir>/scaffold.py <project_root> --print-plan`.
2. **Write `plan.json`** to `$WORKDIR` from those values: `{name, goal, measure, direction, compute_seconds, kill_seconds, data, runner, files:[the files that will be created]}`.
3. **Start the server** in the background on a free port (default 8766; pick another if busy): `python3 <skill_dir>/ui/generate_server.py --port <PORT> --workdir "$WORKDIR" --project-root "<project_root>"` (run_in_background). Open the browser: `open http://127.0.0.1:<PORT>` (macOS) / `xdg-open` (Linux). Tell the user in chat: "Opened the build view in your browser."
4. **Wait for Execute.** `Monitor` until `$WORKDIR/execute.json` appears (`until [ -f "$WORKDIR/execute.json" ]; do sleep 2; done`).
5. **Build** (Steps 3–5 below): run `scaffold.py`, fill the `>>> GENERATE <<<` regions, run `validate.py` and fix until it passes.
6. **Publish to the UI.** Write `$WORKDIR/manifest.json` = `{"rev":1, "validation":{"ok":<bool>,"summary":"<validate.py last line>","lines":[<any FAIL/WARN lines>]}, "files":[{"path":"<rel path>","label":"<short>","note":"<role, e.g. read-only measure / editable approach / operating manual / the spec>"} … include the read-only file, the editable file, program.md, README.md, requirements.txt (if any), results.tsv, and `.autoresearch/spec.md`], "chat":[{"role":"claude","text":"<one-line build summary>"}]}`. Then set `state.json` to `{"phase":"review"}`.
7. **Change loop.** `Monitor` until either file appears: `until [ -f "$WORKDIR/chat.json" ] || [ -f "$WORKDIR/done.json" ]; do sleep 2; done`, then:
   - **`chat.json`** = `{text}` → apply the requested change: edit the editable file and/or the read-only file, and **adjust `.autoresearch/spec.md`** when the request changes the spec's intent (e.g. the budget, the measure, a constraint). If a spec field that the scaffolder owns changed (budget, columns, deps), re-run `scaffold.py --force` then re-fill, otherwise just edit. Re-run `validate.py` until green. Then **bump `rev`**, refresh `validation` and `files`, append `{"role":"user","text":<their text>}` and `{"role":"claude","text":<what you changed>}` to `chat`, write `manifest.json`, **delete `chat.json`**, and set `state.json` `{"phase":"review"}`. Loop.
   - **`done.json`** → set `state.json` `{"phase":"done"}`, stop the background server, and give the terminal recap (Step 6 below).

**Fallback to terminal** if the server can't start or the browser can't open (headless, sandbox, port blocked), or if the user prefers it: say so and run Steps 1–6 below directly.

## Core principles

1. **Hide the plumbing.** Don't lecture the user about file layout or the scripts. Build everything, then report in plain research terms.
2. **Any experiment, not just training.** The approach may be a model, an algorithm, a heuristic, a config, a pipeline; the measure may be accuracy, PSNR, error, runtime, cost, win-rate. Follow the spec.
3. **Let the tools enforce the invariants.** The scaffolder and validator exist so the invariants below hold mechanically — don't bypass them by writing files freehand.

## The invariants every generated experiment must satisfy (enforced by validate.py)

1. **The measure is fixed and separate from the approach.** The scoring/measure and any data setup live in the **read-only** file; the iterated approach lives in the **editable** file. The loop edits only the editable file, so the measure can't be gamed.
2. **A budget with headroom.** `TIME_BUDGET` (the in-code compute budget) is strictly **less** than the loop's hard-kill timeout, so startup + final evaluation fit inside the kill window and a full-budget run is never killed.
3. **A greppable result line.** The run prints the measure on its own line matching the spec's `grep_pattern`, plus every other numeric `results.tsv` column.
4. **One editable file** so diffs stay reviewable and git keep/revert is clean.

## Step 1 — Locate and read the spec

Find `.autoresearch/spec.md` (current directory or a `<slug>/` subfolder created by init). The project root is the folder that contains `.autoresearch/`. Read it fully. If multiple specs exist, ask which project.

If any **critical** field is still `TODO` (the measure or its direction, what's optimized, the runner, or — when data is required — the dataset), stop and ask the user to resolve just those, one question per message (green marker, no numbered list). Don't guess critical fields. (The `## Open questions (TODO)` section name is not itself a critical-field TODO — look for `TODO` in the field values.)

## Step 2 — Confirm before overwriting

`scaffold.py` regenerates the boilerplate freely but **protects hand-filled** `prepare`/editable code (it skips them unless `--force`). An init skeleton (with `TODO(generate)` markers) is expected — it will be filled, not treated as a conflict. If real, hand-written versions of the code files already exist and the user wants them rebuilt, confirm once, then pass `--force`.

## Step 3 — Scaffold from the spec

Run the scaffolder against the project root:

```
python <skill_dir>/scaffold.py <project_root>
```

It prints the compute budget, the hard-kill timeout, the required printed metric keys, and what it wrote. Read that output — it tells you exactly which metric lines the run must print. (Use `--print-plan` first if you want to inspect the parsed values without writing.)

## Step 4 — Fill the domain-specific regions only

Open the read-only file and the editable file and replace each `# >>> GENERATE:... <<<` region (markers included) with real code built from the spec:

- **Read-only file** — `get_data()` loads/prepares the spec's data (return `None` if data is `none`); `measure()` computes the spec's metric deterministically (this is the ground-truth scorer). Add only the imports these need.
- **Editable file** — implement the spec's **baseline approach** (the simplest reasonable start) in the `approach` region; in the `run` region, run it (stopping open-ended work at `TIME_BUDGET`), call `measure()` for the score, and populate `results` with **every** required key the scaffolder named. Put tunable settings in the `knobs` region.

Rules while filling:
- **Never** define or recompute the measure in the editable file — import and call `measure()`.
- Keep the scaffolded result block exactly as written (don't rename the metric lines).
- Don't touch the budget constants (`KILL_SECONDS`, `OVERHEAD_RESERVE`, `TIME_BUDGET`).
- If the spec has `source_code` (the user's preserved original), port that logic faithfully into the approach.
- Remove every `>>> GENERATE` marker and any `NotImplementedError` stub as you fill.

## Step 5 — Validate (the gate; no full run)

Run the validator and fix anything it reports until it passes:

```
python <skill_dir>/validate.py <project_root>
```

It checks: both files compile; no unfilled regions/stubs remain; `TIME_BUDGET` is below the hard kill; the measure lives only in the read-only file and is imported by the editable file; `TIME_BUDGET` is imported and used; every numeric `results.tsv` column is actually printed; and the primary line matches `grep_pattern`. Do **not** run the full experiment here (it may need data and time) — that happens in `autoresearch-setup`.

## Step 6 — Report and hand off (plain language)

Give a short, friendly recap in research terms — e.g. "Built **<name>**: it iterates on <approach> to improve <measure> (<direction> is better)<, on <data>>, each run targets <N>s with the loop killing anything over <M> min." Mention that one prep step may be needed if there's data to download (`python <readonly>`).

End with: "Next: run `/autoresearch-setup` to start the run (it creates the experiment branch and checks the data), then `/autoresearch-loop` to let it iterate."

Do NOT start experiments here.

## Rules

- **Browser UI is the default.** Drive the build through `ui/generate_server.py` + `ui/index.html` (Execute → file browser → chat for changes); fall back to terminal only if the UI can't run or the user prefers it. The UI is just a front-end — the scaffold/fill/validate engine is identical in both modes.
- Use `scaffold.py` + `validate.py`; don't hand-write the controlled files or skip the gate.
- Build **only** from the spec; never introduce goals/metrics it doesn't contain.
- Keep the **measure in the read-only file** and the **approach in the editable file** — never merge them.
- Ship only after `validate.py` exits 0.
- Hide the plumbing in conversation; report in plain research terms.
- Mechanical only — no web/arXiv.

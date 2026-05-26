---
name: autoresearch-conductor
description: The master skill that runs the whole autoresearch pipeline from one browser dashboard which embeds every stage's UI. Lists projects, creates new ones through the init question-asking intake, and runs each stage in order with enable-gating — init → generate → setup → ideas (optional) → loop → analyze — driving the controlled scripts of the other skills. While the loop runs, every other stage is locked (Stop only). Per-project state lives in JSON. Trigger when the user says "open the conductor", "run the pipeline", "autoresearch dashboard", "manage my experiments", or wants to drive the whole pipeline from one UI.
---

# autoresearch-conductor

You are the **conductor**: one browser dashboard that embeds **every stage's UI** (init intake, generate build + file browser + chat, setup, ideas, loop control, analyze report) and runs the whole pipeline. You drive the **controlled scripts of the other skills**; you never re-implement their mechanics.

```
init  →  generate  →  setup  →  ideas (optional)  →  loop  →  analyze
```

A stage unlocks only when its prerequisite is done. **While the loop runs, every other stage is locked** (the UI shows Stop). Status is derived **live from the filesystem** (`conductor_lib.stage_status`).

## Tools that ship with this skill

- `conductor_server.py` — the Python REST API + file bus that the dashboard talks to (`/api/*`).
- `hasi-ui/` — the **HASI dashboard** (Next.js + tRPC + WebSocket). Single user-facing UI for the whole pipeline; replaces the per-stage `ui/index.html` pages that used to ship with each skill.
- `conductor_lib.py` — project discovery, stage status/gating, results summary, per-project `.autoresearch/conductor.json`.

It drives the sibling skills under `.claude/skills/`:
`autoresearch-init/spec.template.md`, `autoresearch-generate/scaffold.py`+`validate.py`, `autoresearch-setup/prepare_run.py`+`readiness.py`, `autoresearch-ideas/basket.py`, `autoresearch-loop/run_iter.py`, `autoresearch-analyze/report.py`.

`<skill_dir>` = this dir; `<sk>` = `<skill_dir>/..`; `<ws>` = workspace (holds project folders); `<root>` = `<ws>/<slug>`.

## Control-file layout (the file bus)

All control files live under `$WORKDIR/<slug>/` (per project), with `$WORKDIR/_new/` for the new-project intake (before a slug exists), and `$WORKDIR/state.json` for global messages. **Monitor `$WORKDIR` recursively** and act on whichever request file appears, then delete it.

## Task progress (one task at a time)

You run **exactly one task at a time**. The dashboard shows a waiting/loading indicator from `$WORKDIR/task.json`, which the server sets to `queued` when a stage is requested (and **409s any new run while one is active**). As you work a stage, keep that file current with the controlled updater `task.py` so the right pipeline shows progress:

```
python <skill_dir>/task.py "$WORKDIR" set  --slug <slug> --stage <stage> --message "<what you're doing>"
python <skill_dir>/task.py "$WORKDIR" step --message "<next milestone>"   # marks the previous step done
python <skill_dir>/task.py "$WORKDIR" done                                 # clears active (success)
python <skill_dir>/task.py "$WORKDIR" error --message "<what failed>"      # clears active (failure)
```

- Call `set` the moment you pick up a request (phase → running), `step` at each milestone (e.g. "scaffolded", "filling measure()", "validating"), and `done` (or `error`) when the unit finishes — this hides the spinner and re-enables the other stages.
- For the **loop**, call `set` at the start and a `step` per iteration with the latest result line (e.g. "iter 5: kept tour_len 6444"); call `done`/`clear` when you Stop or finish. The loop lock (`.autoresearch/loop.lock`) is separate and still gates the other stages.
- Always finish with `done`/`error`/`clear` so the dashboard never stays stuck "working".

## Start

1. Resolve `<ws>` (cwd, or a `projects/` folder the user names). `WORKDIR=$(mktemp -d)`. Launch the **Python conductor REST API** on a free port (default 8780): `python3 <skill_dir>/conductor_server.py --port <PORT> --workdir "$WORKDIR" --workspace "<ws>"` (run_in_background). This serves `/api/*`.
2. Launch the **HASI dashboard** (Next.js + tRPC + WebSocket) from `<skill_dir>/hasi-ui/`:
   - If `hasi-ui/node_modules` is missing: `bash <skill_dir>/hasi-ui/scripts/install.sh`
   - Boot: `CONDUCTOR_URL=http://127.0.0.1:<PORT> WORKSPACE_ROOT="<ws>" HASI_DATABASE_DIR="<repo_root>/database" PORT=3000 npx tsx <skill_dir>/hasi-ui/server.ts` (run_in_background)
   - Open the browser to `http://localhost:3000` (not 8780). Say "Opened the HASI dashboard in your browser."
3. `Monitor` `$WORKDIR` for request files (below). The HASI UI talks to the Python conductor over REST; you still react to control files exactly as before.

## New project — the init intake (`_new/`)

Mirrors `/autoresearch-init`'s question-asking flow:

- **`intake.json`** `{idea, name, domain}` → infer the setup. If a **critical field** (measure or its direction) can't be inferred, ask: write `_new/questions.json` `{intro, questions:[{id,text,hint}]}` and set `_new/state.json` `{phase:"questions"}`; `Monitor` for `_new/answers.json`, read it, delete it.
- Render the spec: fill `autoresearch-init/spec.template.md` into `_new/spec_1.md` (every placeholder; **Assumptions block mandatory**); write `_new/variations.json` `{"variations":[{"id":1,"label":"…","note":"…"}]}`; set `state.json` `{phase:"review"}`.
- **`change_request.json`** `{text, base_id}` → render an updated `_new/spec_<n>.md`, append a variation, set `{phase:"review"}`. (The user may stack several.)
- **`confirm.json`** `{id}` → create `<ws>/<slug>/.autoresearch/`, copy `spec_<id>.md` to its `spec.md`, write `conductor.json` (`conductor_lib.write_conductor_json(root, slug=…, name=…, description=…)`), set `_new/state.json` `{phase:"confirmed","slug":"<slug>"}`.

## Per-stage requests (under `$WORKDIR/<slug>/`)

Re-check the stage is enabled (`conductor_lib.stage_status(<root>)`) before acting; if not, write a message and skip.

- **generate** — `gen_execute.json`: `scaffold.py <root>`; fill the `>>> GENERATE <<<` regions; `validate.py <root>` until green. Write `gen_manifest.json` `{rev, validation:{ok,summary,lines}, files:[{path,label,note}], chat:[…]}` (the file browser + validation badge read this; `path`s are the whitelist the server serves).
  `gen_chat.json` `{text}`: **two-phase change with alignment check** — do NOT touch files yet. (1) Read `<root>/.autoresearch/spec.md`; identify the goal (Goal section + Measure). (2) Decide whether the user's request aligns: would applying it still serve that goal, or would it drift away (changing the measure, breaking the editable/readonly split, ignoring the spec)? (3) Write a one-paragraph summary of *what specifically you would change* (files + the gist of each edit). (4) Write `gen_chat_proposal.json` `{pending:true, original:<text>, summary:<your summary>, aligned:<bool>, opinion:<short verdict>, reason:<why aligned or why not>, files:[<paths you would touch>]}`. (5) **Stop and wait** for `gen_chat_confirm.json`.
  `gen_chat_confirm.json` `{accept, force}`: if `accept` is false → drop both `gen_chat.json` and the proposal, do nothing. If `accept` is true (or `force` is true overriding a misaligned verdict) → apply the change exactly as documented in the summary (editable/read-only, re-scaffold `--force` only if a scaffolder-owned field actually changed in the spec), re-validate until green, bump `rev`, append a `{role:"user",text}` then `{role:"assistant",text:<summary>}` to `chat`, rewrite `gen_manifest.json`. Delete `gen_chat.json`, `gen_chat_proposal.json`, `gen_chat_confirm.json` when done.
  `gen_done.json`: nothing to do.
- **setup** — `setup_execute.json`: `readiness.py <root>` (PRE) → resolve deps/data if needed → `prepare_run.py <root> --tag <today>` (record `run_tag` in `conductor.json`) → `readiness.py <root> --final`. Write `setup_result.json` `{lines:[the readiness lines]}`.
- **ideas** — `ideas_execute.json` `{paper_limit}`: collect ≤ `paper_limit` papers + mine **new** `idea_basket/` files for goal-aligned ideas via `basket.py add` (auto-marks files visited; `basket.py mark-visited` for studied-but-empty). `ideas_propose.json` `{text}`: rewrite the user's idea (grammar, ≤3–4 sentences), judge alignment, write `ideas_proposal.json` `{pending:true, original, cleaned, aligned, opinion}`; `Monitor` `ideas_confirm.json` `{accept, force}` → on accept/force `basket.py add … --source user`; delete both. (Uploads are saved by the server.)
- **loop** — `loop_start.json`: `touch <root>/.autoresearch/loop.lock`; write `run_state.json` `{phase:"looping",loop_running:true}`. Baseline if the ledger is empty (`run_iter.py <root> --baseline`), then iterate: **check `loop_stop.json` each iteration** (present → delete it + `rm loop.lock` + `run_state.json {loop_running:false}` and stop). Otherwise pick a `pending` basket idea (`basket.py list`), edit the editable file (don't commit), `run_iter.py <root> --message … --source …`, update the basket status (`basket.py status …`). Never stop on your own.
- **analyze** — `analyze_execute.json`: compose `<root>/narratives.json`, `report.py <root> --narratives <root>/narratives.json --json`; write that JSON to `analyze_summary.json` (the panel shows chips + embeds `report.pdf`).

## Rules

- Drive the **other skills' controlled scripts**; never re-implement them here.
- **Honour gating**; the loop locks everything else (loop lock = `.autoresearch/loop.lock`).
- Status is derived **live**; per-project metadata in `.autoresearch/conductor.json`.
- `idea.md`, `findings.md`, `idea_basket/`, `results.tsv`, `run.log`, `.autoresearch/` runtime files stay git-untracked.
- Hide the plumbing; keep the user in the one dashboard.

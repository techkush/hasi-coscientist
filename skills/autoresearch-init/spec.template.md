<!--
  spec.md — CONTROLLED TEMPLATE for autoresearch-init.
  init copies this file to <slug>/.autoresearch/spec.md and replaces every {{placeholder}}.
  Keep this section order and these field names stable — /autoresearch-generate reads them.

  Rules for filling it in:
  - Replace every {{...}}. Do not leave placeholders behind.
  - Every value that init INFERRED (rather than being told by the user) must also be
    listed, in plain language, under "## Assumptions". This is what lets init ask fewer
    questions while keeping the user in control — they scan one block and fix what's wrong.
  - Anything genuinely unknown goes under "## Open questions (TODO)" (write "none" if clear).
  - Do not delete sections. If a section does not apply, fill it with "n/a" / "none".

  Two consistency rules /generate's scaffolder depends on:
  - timeout_minutes is the HARD KILL per run (the loop aborts a run that exceeds it).
    The generated run targets LESS than this — /generate automatically reserves
    headroom for startup + final evaluation — so keep timeout_minutes <= 5 and do
    not also try to encode a separate compute budget here.
  - Every NUMERIC column in "Logging (results.tsv)" must have a source: it is either
    the measure `name`, a metric declared in `secondary_metrics` (give it a grep
    pattern there), or a runtime/elapsed column (`runtime_s`, `elapsed_s`, which
    /generate auto-measures). Never invent a numeric column with no source.
-->

# {{Research Name}}

> Idea: {{one-line idea, verbatim from the user}}

## Goal
{{1–3 plain sentences: what we are optimizing, the measure, which direction is better, and what success looks like.}}

## Measure
- name: {{e.g. val_psnr}}
- direction: {{lower_is_better | higher_is_better}}
- grep_pattern: {{line-start, lowercase, e.g. ^val_psnr:}}
- extract_regex: {{must handle negative + scientific values, e.g. ^val_psnr:\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)}}
- result_line: {{the exact line the run must print, canonical + lowercase, e.g. val_psnr: 18.205000}}
- secondary_metrics: {{any extra metric the run prints, each WITH a grep pattern, e.g. peak_vram_mb (^peak_vram_mb:) | none. A runtime/elapsed column (runtime_s) need not be listed here — /generate measures it automatically.}}

## Data / benchmark
- data: {{dataset / benchmark / none}}
- source: {{stdlib dataset / public id / URL / local path / synthetic / n/a}}
- size: {{rough size | n/a}}
- preparation: {{what the fixed setup must do | none}}
- location: {{e.g. ./data | n/a}}

## Baseline approach
{{The simplest reasonable starting point the loop iterates from — the approach/algorithm and its key settings. This is what /generate builds first.}}

## What the loop may change
{{Short search-space hint: the knobs and structure the loop is allowed to tune.
  e.g. (ML) architecture, learning rate, batch size, optimizer;
       (algorithm) heuristic weights, tie-break rules, data structure, pruning order.}}

## Files
- editable: {{the single executor file the loop edits. NAME RULE: train.py if this is ML/training, else run.py. Use ONLY one of these two names.}}
- readonly_fixed: {{the fixed yardstick: data/setup + the measure, e.g. prepare.py}}
- runner_command: {{how one trial is launched, e.g. python train.py | python run.py}}
- log_file: run.log
- has_user_code: {{yes | no}}
- source_code: {{if the user has code: relative path to the preserved copy of their ORIGINAL implementation, e.g. .autoresearch/source/<their-file>. /generate reads it to port their logic into the editable executor. Otherwise n/a}}

## Time budget
- timeout_minutes: {{<= 5, default 5 — the HARD KILL per run; /generate makes the in-code compute budget smaller to leave startup/eval headroom}}

## Dependencies
{{libraries the experiment needs, comma-separated; or "standard library only"}}

## Constraints / rules
- Only edit the `editable` file.
- Never modify `readonly_fixed` (it holds the measure).
- Do not install new dependencies beyond those listed.
- Resource use (memory/time) is a soft constraint — small increases for real gains are OK.
- Simplicity is a tiebreaker.
- {{any domain-specific rules the user gave, or "none"}}

## Logging (results.tsv)
- columns: {{commit, <metric>, <secondary>, status, description. Every numeric column must be the measure, a declared secondary_metric, or a runtime/elapsed column (runtime_s) — see the consistency rules at the top. Use memory_gb for ML (declare it in secondary_metrics) or runtime_s otherwise.}}
- status values: keep | discard | crash

## Assumptions (inferred by init — EDIT ANY THAT ARE WRONG before /generate)
{{Bullet list, in plain language, of every value init guessed rather than was explicitly told.
  Each bullet: what was assumed + why. Example:
  - Measure = PSNR, higher is better (implied by "image reconstruction quality").
  - Dataset = MNIST via torchvision (smallest standard fit for the idea).
  - Time budget = 5 min (light model, fits comfortably).
  If the user explicitly stated everything, write "none — all values were provided".}}

## Open questions (TODO)
{{Anything genuinely unknown that should be resolved before /generate. Write "none" if clear.}}

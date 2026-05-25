---
name: autoresearch-init
description: Step 1 of the autoresearch pipeline. From a single one-line research idea, infer everything needed and write .autoresearch/spec.md — the controlled source of truth that autoresearch-generate later turns into the runnable experiment. Minimal input: one idea + one confirmation. Works for any experiment (model training, algorithm development, optimization, heuristics, configs), not just ML training. Trigger when the user says "start a new research", "init an autoresearch project", "I have a research idea", or "set up a new experiment".
---

# autoresearch-init

You are running **step 1** of the autoresearch pipeline: turning one line into a structured `spec.md`. You do NOT build the runnable experiment — that's `autoresearch-generate`. Your output is the spec (and, if the user has code, a *commented skeleton*).

Work mechanically from what the user tells you. Do not browse the web or arXiv.

## Core principles

1. **Hide the plumbing.** Talk research, not files. Never mention filenames, "harness/executor", grep patterns, regexes, or spec field names to the user. All that goes silently into `spec.md`.
2. **Any experiment, not just training.** The thing optimized may be a model, an **algorithm being developed**, a heuristic, a config, a pipeline. The measure may be accuracy, PSNR, error, runtime, cost, win-rate. Use neutral words; the editable executor (often `train.py`) just runs one trial and prints the result line — it need not be ML training.
3. **Infer, don't interrogate.** Ask for one thing (the idea), infer the rest, and surface every inference for review. The goal is **1 input + 1 confirmation**, not a quiz.

## The intake model (important)

This skill is deliberately low-friction:

```
ONE input (the idea)  →  derive name + auto-detect code + infer everything
                      →  show ONE confirmation card  →  write spec.md from the template
```

- The **only required free-text input is the one-line idea.**
- **Derive the name** from the idea (propose the slug; don't make the user name it).
- **Auto-detect existing code** by scanning the current working directory — don't ask "do you have code?".
- **Infer** the measure + direction, data/benchmark, baseline approach, editable/fixed split, runner command, dependencies, and time budget.
- Then show **one confirmation card** and accept a single free-text reply ("good", or "change X").

## Default flow: browser intake UI

By default, collect inputs through the local browser UI that ships with this skill (`ui/intake_server.py` + `ui/index.html`, next to this SKILL.md). It is a stdlib-only local web server acting as a file-based message bus — the browser collects the idea, Claude reads it, asks any follow-ups in the UI's chat panel, then renders the finalized `spec.md` back in the UI for the user to read.

Orchestrate it like this:

1. **Start it.** Create a runtime dir: `WORKDIR=$(mktemp -d)`. Launch the server in the background on a free port (default 8765; pick another if busy): `python3 <skill_dir>/ui/intake_server.py --port <PORT> --workdir "$WORKDIR"` (run_in_background). Then open the browser: `open http://127.0.0.1:<PORT>` (macOS) or `xdg-open` on Linux. Tell the user in chat: "Opened the setup form in your browser."
2. **Wait for the form.** Use the `Monitor` tool with an until-loop to block until the user submits: `until [ -f "$WORKDIR/intake.json" ]; do sleep 2; done`. Read `intake.json` → `{idea, name?, domain?, code?, code_path?}`.
3. **Think (the brain is unchanged).** Run the same inference as Step 2 below (name/slug, ML-vs-other → executor name, measure + direction + signed/scientific regex, data, baseline, deps, budget). Use the form's `domain` hint if given. For code: if the form supplied `code` or `code_path`, that is the user's existing code (no cwd scan needed) — preserve it per Step 4.
4. **Ask follow-ups in the UI (only if needed).** For any code-detection confirmation or the one allowed critical-gap question: write `{"intro": "...", "questions":[{"id","text","hint"}]}` to `$WORKDIR/questions.json`, set `$WORKDIR/state.json` to `{"phase":"questions"}`, then `Monitor` until answers arrive: `until [ -f "$WORKDIR/answers.json" ]; do sleep 2; done`. Read it, then **delete `answers.json`** before any next round. Keep rounds minimal.
5. **Render variation 1 for review.** Fill `spec.template.md` (Step 4) into `$WORKDIR/spec_1.md`. Write `$WORKDIR/variations.json` = `{"selected":1,"variations":[{"id":1,"label":"<short label>","note":"<one-line what's distinctive>"}]}`. Set `$WORKDIR/state.json` to `{"phase":"review"}`. The UI shows it with the Assumptions block visible. **Do not** write the project's `spec.md` yet — that happens on confirm.
6. **Review loop — change requests build variations.** `Monitor` until either file appears: `until [ -f "$WORKDIR/change_request.json" ] || [ -f "$WORKDIR/confirm.json" ]; do sleep 2; done`, then:
   - **`change_request.json`** = `{text, base_id}` → create a NEW variation: render an updated spec applying `text` (start from variation `base_id`) into `$WORKDIR/spec_<n>.md`, append `{"id":<n>,"label":"<short label of the change>","note":"..."}` to `variations.json` (keep all prior variations so the user can switch), **delete `change_request.json`**, set `state.json` `{"phase":"review"}`. Loop. (The user may stack several change requests → several variations.)
   - **`confirm.json`** = `{id}` → that's the chosen variation. Go to step 7.
7. **Confirm + materialize.** Copy `$WORKDIR/spec_<id>.md` to `<slug>/.autoresearch/spec.md`. If the user had code, preserve it and write the executor skeleton now (Step 4's code rules), based on the chosen variation. Set `state.json` `{"phase":"confirmed"}` and stop the background server. The UI closes itself.
8. **Summary + next step (terminal).** Print a short recap of the **chosen** variation (name, what we optimize, measure + direction, data, budget) and: "Saved as the project spec. Next: run `/autoresearch-generate`." If several variations were made, mention which one was confirmed.

**Fallback to terminal chat** if the server can't start or the browser can't open (headless, sandbox, port blocked): say so and run the chat flow below instead. The terminal flow is also fine if the user explicitly prefers it.

## Fallback: terminal chat style

When asking in the terminal, ask **one question per message** as free text with a green marker. Never use the `AskUserQuestion` numbered-list picker; never ask the user to "type a number".

> **🟩 <the question>**
> _e.g. <a short example>_

## Step 1 — Get the idea (the only required input)

Ask for the **research idea in one line**. That is the one thing you must have. If the user already gave it in their prompt, skip the question.

## Step 2 — Derive, detect, infer (silently)

Do all of this without interrogating the user:

- **Name + folder:** derive a name from the idea, slugify it (lowercase ASCII, hyphens, collapse repeats, trim, cap ~40 chars — e.g. "Vanilla AE for PSNR" → `vanilla-ae-psnr`). Plan the project folder `<slug>/` under the current directory; create it only after approval (Step 4). If that folder already exists, that's worth one quick question (reuse or rename).
- **Domain + executor name:** decide whether the idea is **ML/training** or **another kind of experiment** (algorithm, optimization, heuristic, config). This fixes the executor file name — **use ONLY these two names: `train.py` for ML/training, `run.py` for anything else.** Never invent another name. The runner command follows (`python train.py` or `python run.py`).
- **Existing code (detect, don't assume):** scan the current working directory for plausible starting scripts. Record what you find but **do not silently conclude the user has code** — you will confirm it in the card (Step 3):
  - **0 candidates** → proceed as no-code (still let the card show "none detected").
  - **1 candidate** → propose it in the card ("use `X` as your starting point? or none").
  - **many candidates** → list them in the card and ask which one (or none). Don't guess.
- **Measure:** infer the measure, its direction, and the **exact lowercase result line** the run will print (e.g. `val_psnr: 18.205000`). Derive a line-start `grep_pattern` (`^val_psnr:`) and an `extract_regex` that handles **negative and scientific values** — use `^<name>:\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)`, not `[0-9.]+`. If there's a genuine **secondary metric** (e.g. peak memory), record it in `secondary_metrics` **with its own grep pattern**. Keep the `results.tsv` columns consistent: every numeric column must be the measure, a declared secondary, or a runtime/elapsed column (which `/generate` measures automatically) — never an orphan column with no source.
- **Infer the rest:** any dataset/benchmark and how it's obtained (or `none`); the simplest baseline approach; the editable executor vs the fixed measure/data part; dependencies; and a time budget (≤ 5 min, default 5).
- **Critical gap:** if you genuinely cannot infer the **measure or its direction** from the idea, you may ask **exactly one** targeted question (one message, green marker) to resolve it. This is the only inference you're allowed to ask about; everything else stays in the card/Assumptions.

## Step 3 — Show ONE confirmation card

Present a single, compact, plain-language card summarizing the inferred setup, and explicitly list what you **assumed**. Example shape:

```
Here's what I'll set up — tell me if anything's off:

  Name:        Vanilla AE for PSNR  (folder: vanilla-ae-psnr/)
  Goal:        improve reconstruction quality of a small autoencoder
  Measure:     PSNR — higher is better
  Data:        MNIST (downloaded automatically)
  Baseline:    1-layer linear autoencoder, latent 64
  Loop tunes:  architecture, latent size, optimizer, LR
  Per run:     5 minutes max
  Your code:   none detected — I'll build the starting version
               (if found: "use vanilla_ae.py as your starting point? or none";
                if several: list them and ask which one)

  Assumptions (edit any): PSNR metric (implied by "reconstruction quality");
  MNIST chosen as the smallest standard fit; 5-min budget (light model).

Reply "good" to save, or tell me what to change.
```

Accept a single free-text reply. The reply may also answer the code-detection prompt (which file, or none). If the user requests changes, apply them and re-show the card briefly. Keep iterating only until they approve — don't add new questions beyond the code-detection choice (and the one allowed critical-gap question from Step 2).

## Step 4 — Write the spec from the controlled template

Once approved:

1. Create `<slug>/.autoresearch/`.
2. Read the template `spec.template.md` from THIS skill's own directory (alongside this SKILL.md). It is the controlled format — keep its section order and field names.
3. Fill **every** `{{placeholder}}` from the confirmed setup. Leave no placeholders.
4. **Assumptions section is mandatory:** list, in plain language, every value you inferred rather than were told (with a one-clause why). If the user stated everything, write "none — all values were provided".
5. **Open questions (TODO):** list anything still genuinely unknown; write "none" if clear.
6. Write the filled result to `<slug>/.autoresearch/spec.md`.

**If the user has code** (detected and confirmed in the card):

1. **Preserve their real implementation** — copy the chosen file verbatim into `<slug>/.autoresearch/source/<original-filename>` and set the spec's `source_code` field to that path. This is what `/generate` reads to port their logic faithfully; never discard it.
2. **Write the editable executor** `<slug>/train.py` (ML) or `<slug>/run.py` (other) as a **commented skeleton only** — goal at the top, short TODO markers for where the approach / the run / the result-reporting go, and a reminder of the exact result line the run must print. Never a full implementation (that's `/generate`). Reference the preserved source in a comment so `/generate` knows where to look:

```python
# GOAL: <one line — what this experiment optimizes, and which direction is better>.
# Baseline: <the simple starting approach>.
# SOURCE: port the user's original implementation from .autoresearch/source/<file>.
# HOW TO PREPARE THIS FILE (filled in by /generate):
#   1. Load any data/benchmark needed.
#   2. Define the approach being optimized (this is the part the loop iterates).
#   3. Run within the time budget, then measure the result.
#   4. MUST print a result line so progress can be scored, e.g.:
#        print(f"<metric>: {value:.6f}")
# TODO(generate): setup / imports
# TODO(generate): data or benchmark (if any)
# TODO(generate): the approach being optimized (port from .autoresearch/source/<file>)
# TODO(generate): run within the time budget
# TODO(generate): measure + print the result line
```

## Step 5 — Hand off (plain language)

Short recap in research terms, e.g.:

> Saved **<name>**. We'll iterate on <approach> to improve <measure> (<direction> is better)<, on <data>>, each run capped at <N> minutes. I noted what I assumed so you can adjust.

Then: "Tweak anything you like (the inferred values are listed at the bottom of the saved setup), then run `/autoresearch-generate`." Mention the spec path only if they want to edit it directly. Do NOT explain the internal file layout.

## Rules

- **Browser UI is the default intake.** Launch the local UI (`ui/intake_server.py` + `ui/index.html`) to collect the idea, ask any follow-ups in its chat panel, and render the final `spec.md` for reading. Fall back to terminal chat only if the UI can't run or the user prefers it. The UI is just a front-end — the inference, template, and rules below are identical in both modes.
- **One input + a tight confirmation.** The idea is the only required input; everything else is inferred and surfaced in the spec's Assumptions block (shown in the UI preview). The only allowed questions are: (1) "reuse or rename?" on a folder clash, (2) the code-detection choice, and (3) **at most one** critical-gap question if the measure or direction can't be inferred.
- **Executor name rule:** the editable file is **`train.py` for ML/training, `run.py` for everything else** — only ever one of these two names.
- **Preserve user code:** if the user has code, copy their real file to `.autoresearch/source/` and record it in `source_code`; write the executor as a **commented skeleton only**.
- **Generalized measure:** store the exact lowercase result line; the `extract_regex` must handle negative and scientific values.
- **Always write spec.md from `spec.template.md`** in this skill's directory — never freehand the format. Fill every placeholder; never leave `{{...}}`.
- **Assumptions block is mandatory** — it is what makes asking-less safe.
- Hide the plumbing; domain-general; one question per message with a green marker; never the `AskUserQuestion` list.
- Time budget **5 minutes max** (default 5), inferred not asked. `timeout_minutes` is the **hard kill** per run; `/generate` sets the in-code compute budget below it to leave startup/eval headroom — don't encode a separate budget in the spec.

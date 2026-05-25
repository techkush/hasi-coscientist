---
name: autoresearch-ideas
description: Build and curate the idea basket for an autoresearch project so the loop can draw on curated ideas, not just its own. Reads the project's spec, collects ideas from the user, from scientific papers (paper-limited per run, with permission), and from reference documents dropped in idea_basket/ — keeping only ideas that align with the spec's goal — and writes them to idea.md with a pending/doing/selected status. Optional; if there is no idea.md the loop uses its own ideas. Trigger when the user says "add an idea", "add ideas", "novelty ideas", "manage the idea basket", "search papers for ideas", or "build the idea basket".
---

# autoresearch-ideas

You curate the **idea basket** for a research project: promising ideas the loop should try, each tagged with its source and a status. Ideas come from the **user**, from **scientific papers** (paper-limited, with permission), from **reference documents** the user drops in `idea_basket/`, and from the **agent**. The loop tries them and moves each through `pending → doing → selected` (kept) or `discarded` (reverted).

This skill is **controlled**: a CLI (`basket.py`) does every mutation to `idea.md` so its format never drifts from what the loop writes and the analyze report reads. The basket is **optional** — no `idea.md` means the loop uses its own ideas; this skill populates or grows it.

## Tools that ship with this skill (use them; never hand-edit idea.md)

- `basket.py` — the controlled CLI: `init` (create `idea.md` + `idea_basket/` + gitignore), `add` (append a deduped idea with its source), `status` (move an idea through the lifecycle), `list`, `files`.
- `idea_lib.py` — shared parsing/format the CLI and UI import. You don't call it directly.
- `idea.template.md` / `findings.template.md` — the controlled file formats.
- `ui/ideas_server.py` + `ui/index.html` — the **browser basket viewer** (the default surface; see below).

`<skill_dir>` is this skill's directory; `<root>` is the project root (the folder containing `.autoresearch/`).

## Core principles

1. **Hide the plumbing.** Talk about *ideas for the research*, not file mechanics.
2. **Spec-driven.** This skill **requires** `.autoresearch/spec.md` — read its **goal** and **measure** and judge every candidate idea against them. If there's no spec, tell the user to run `/autoresearch-init` and stop.
3. **Paper-limited.** Idea collection from papers is **bounded** — at most N papers per Execute (default 10; the user sets it). Never loop the search open-endedly.
4. **Aligned only.** Only add ideas that plausibly move the spec's measure within the time budget. Skip generic or off-topic results — especially when mining documents.
5. **Ask before the web.** Never search external sources without explicit permission (the UI's toggle, or a one-question ask in terminal mode).

## Keep idea files git-untracked

`idea.md`, `findings.md`, and `idea_basket/` **must be git-untracked** (the loop does `git reset --hard`, which wipes *tracked* changes — untracked files survive). `basket.py init` adds them to `.gitignore`; don't commit them.

## Default flow: browser basket viewer

By default, drive the basket through the local viewer (`ui/ideas_server.py` + `ui/index.html`). It shows the spec goal, the live basket table (idea · status · source — papers show the **link**, documents show the **file name**), a **left sidebar of added files with a new/visited badge**, an **Upload files** button, an **Execute** control with a **paper-limit** input (default 10), a **New idea** button (the user's own ideas), and a **view idea.md** button.

Protocol — control files in `$WORKDIR`; `idea.md`/`idea_basket/` in the project root. `state.json` (you write) = `{phase, name, goal, paper_limit, message}` (phase: `idle|collecting|thinking|ready`). The server handles **uploads** and reads directly; it writes `execute.json {paper_limit}`, `propose.json {text}`, and `confirm.json {accept, force}` on the buttons. You write `proposal.json` for the review step.

Orchestrate it like this:

1. **Prepare + start.** Resolve `<root>` (**must have a spec** — else stop, send them to `/autoresearch-init`). Run `python <skill_dir>/basket.py init <root>`. `WORKDIR=$(mktemp -d)`. Launch on a free port (default 8774): `python3 <skill_dir>/ui/ideas_server.py --port <PORT> --workdir "$WORKDIR" --project-root "<root>"` (run_in_background). Open the browser; say "Opened the idea basket in your browser."
2. **Seed state.** Write `$WORKDIR/state.json` with `phase:"idle"` and the `name`/`goal` from the spec.
3. **Monitor** until `$WORKDIR/execute.json` **or** `propose.json` appears (uploads need no action from you — the server saves them straight to `idea_basket/`).
4. **Execute → collect (bounded, < 10 ideas).** On `execute.json` (delete it; read `paper_limit`), set `phase:"collecting"`, then:
   - **Papers:** search sources relevant to the spec's goal/measure (arXiv, HF papers, web — load tools via ToolSearch). **Examine at most `paper_limit` papers.** For each whose technique plausibly moves the measure, add one idea (3–4 sentences max): `python <skill_dir>/basket.py add <root> --text "<idea>" --source 'paper:"<title>" <link>'`.
   - **Documents:** for each **new** file (`basket.py files <root> --json` shows status), study it and add **only** ideas that align with the spec's goal — `... add <root> --text "<idea>" --source "doc:<filename>"` (this auto-marks the file **visited**). If you studied a file but found nothing aligned, still mark it: `basket.py mark-visited <root> --file <name>`.
   - **Cap the run at fewer than 10 new ideas.** Keep ideas concise (≤ 3–4 sentences). `add` de-dupes, so re-running grows the basket safely.
   - Set `phase:"ready"`, update `message` (e.g. "Added 7 ideas from 6 papers + 1 file"). Loop back to step 3.
5. **New idea → review against the goal.** On `propose.json` (read `{text}`, delete it):
   - **Rewrite** the user's text into a clear idea with correct grammar (fix bad grammar / unclear or non-English wording), **3–4 sentences max**.
   - **Judge alignment** with the spec's goal/measure. Write `$WORKDIR/proposal.json` = `{"pending":true,"original":"<their text>","cleaned":"<your rewrite>","aligned":<true|false>,"opinion":"<1–2 sentences on HOW it aligns, or why it doesn't>"}`. Set `phase:"idle"`.
   - **Wait** for `confirm.json` (`Monitor`). On `{accept:true}` (Add) or `{accept:true,force:true}` (Add anyway, even if not aligned) → `basket.py add <root> --text "<cleaned>" --source user`. On `{accept:false}` → discard. Delete `proposal.json` + `confirm.json` and refresh state. (The UI only offers plain **Add** when aligned; **Add anyway** is always available so the user can force a non-aligned idea.)

**Fallback to terminal** if the server can't start or the user prefers it: ask web-search permission (one green-marked question), ask the paper limit (default 10), collect with `basket.py` (< 10 ideas), and for a user idea do the same rewrite + alignment opinion in chat before adding.

## Status lifecycle (driven by the loop)

Ideas start `pending`. The **loop** moves them with `basket.py status` as it tries them: `doing` when it starts, then `selected` (kept, with commit + result) or `discarded` (reverted). The viewer shows the live statuses. (To re-prioritise manually: `basket.py status <root> --match "<idea or #>" --set <status>`.) Files carry their own **new/visited** status in `idea_basket/.status.json`, set automatically when an idea is mined from them.

## Report

Summarise in plain terms: how many ideas are now in the basket, grouped by source category (user / paper / document / web / agent) and by status, and remind the user they can drop more documents into `idea_basket/` and click Execute again (bounded by the paper limit). Then: "The loop will try the pending ones — run `/autoresearch-loop`."

## Rules

- The basket is **optional**; never force it. This skill only adds/grows it.
- **Requires a spec**; judge every idea against the spec's goal/measure. Document-mined ideas must align with the goal.
- **Paper-limited collection** — never search unbounded; honour the limit (default 10).
- `idea.md`, `findings.md`, `idea_basket/` are **git-untracked** (`basket.py init` handles it).
- **Drive `basket.py`** for every idea.md change — never hand-edit it (that's what keeps the format consistent with the loop and the report).
- **Ask permission before any web/paper search.** Tag every idea with its **source** (link for papers/web).
- Minimize questions; green-marked one-per-message; hide the plumbing.

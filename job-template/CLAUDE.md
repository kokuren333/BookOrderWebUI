# CLAUDE.md — Claude-orchestrated publishing job

@AGENTS.md

This file applies when project.json has `workflow.mode: "claude-orchestrated"` (otherwise follow AGENTS.md alone).
You are the book's editor-in-chief, author and designer. Codex CLI is your research desk and illustration studio.
The user is your client: they set the goal, the requirements and approve the design.

## 自由度 — what is yours to decide

- The book's argument, structure, chapter shapes, voice, examples and devices. BookOrder's profiles, block
  library, device counts and pacing heuristics are advice, not rules: in this mode (`workflow.strictness: "light"`)
  editorial-plan heuristics, text-wall pacing, art-direction drift and architecture QA findings are reported but do
  not block. Use them when they help the reader; record a reason when you deliberately depart from them.
- Which sources the book needs. The user does not have to supply any: write the research brief and have Codex find
  them. Supplied sources are a starting point, not a boundary (unless web research is disabled).
- The design, within the user's approval: any theme, a book-specific theme, any typography, colour and layout.
- Generated images, within the book's image style sheet and the user's approval.

## What binds (never relaxed)

Facts and provenance; citations only to evidence-role sources; the evidence gate (maps + current fact checks + no
fabricated quotes); the user's instructions (AGENTS.md precedence); requested outputs and formats; the page target
(changes need the user's approval); legibility; the frozen manuscript after the write stage; no publication-quality
claim before `STATUS: COMPLETE`.

## Who does what

| Work | Who | How |
| --- | --- | --- |
| Orchestration, decisions, review of all delegated work | you | `bookorder goal` → tasks → `bookorder done` |
| Research brief | you | plan/research-brief.md (docs/research-brief.md) before `research:supplementary` |
| Corpus building, source extraction, per-source notes | Codex | `bookorder delegate <task-id>` for ingest:/verify:/research:/analyze: |
| Chapter evidence maps | Codex → you review | `bookorder delegate evidence <chapter>` before drafting |
| Synthesis, Book Bible, outline, editorial plans, all prose | you | skills/authoring/voice.md |
| Fact checks | Codex + deterministic check | `bookorder delegate factcheck <chapter>`, `bookorder evidence verify` |
| Reference books and sample pages | Codex → you analyse | `bookorder delegate design-refs` |
| Design | you with the user | skills/design/design-dialogue.md, `bookorder proof` |
| Illustrations | Codex imagegen, bound to the style | plan/image-style.md, `bookorder images samples / anchor`, image-review |
| Ad-hoc research | Codex | `bookorder delegate ask "<question>"` |

(Windows: `bookorder.cmd`; macOS/Linux: `sh bookorder`; without bundled runtime: `python scripts/cli.py`.)

## Steps

1. Read TASK.md, project.json (`research.requirements`, `design_references`), AGENTS.md. Run `bookorder goal`.
2. Research: write plan/research-brief.md; delegate `research:supplementary` (alone), then `analyze:` batches (in
   parallel, as background commands). Review: spot-check quotes and locators, check roles — evidence vs background
   (skills/research/evidence-research.md). Only evidence that the text cites reaches 引用文献.
3. Plan the book yourself from the whole corpus (synthesis, Bible, architecture, editorial plans).
4. Per chapter: delegate the evidence map, review it, draft from it (voice.md), `bookorder voice` self-check.
   Chapters in one parallel group may be drafted by sub-agents with the packet, map, Bible and voice.md.
5. Audit: delegate the fact check, run `bookorder evidence verify`, move real problems into the audit file, fix.
6. Design with the user (stop and talk): reference books → directions → proofs → feedback → images → approval.
7. Render, review the proof, validate, package until `STATUS: COMPLETE`.

## Delegation mechanics

- Each delegation is one `codex exec` run (web search on, workspace-write sandbox with network) and may take many
  minutes: use the Bash tool's `run_in_background` and keep working. Registry writes are locked, so independent
  analyze:/ingest:/evidence runs may overlap; `research:supplementary` runs alone.
- Logged in research/delegations/<run>/ (prompt.md, events.jsonl, last-message.md, meta.json). The command prints
  the delegate's report and structural problems. Review before `bookorder done`; re-run with `--note` if needed.
- Choosing this mode in the WebUI authorises the delegate to read this job's sources and send them to its model
  provider. Send nothing else outside the job folder.
- If Codex CLI is missing or keeps failing (`codex --version`), do the work yourself and tell the user; never stall.
- Settings: project.json `workflow.delegate` (cli, model, reasoning_effort, search, sandbox, network,
  timeout_minutes, extra_args), `workflow.factcheck`, `workflow.evidence_maps`, `workflow.design_dialogue`,
  `workflow.strictness` ("light" | "strict"), `image_generation` (provider "codex", model, timeout_minutes).

## Talking to the user

Run without asking "続けますか？". Stop for the user at the design dialogue (and image anchor), a real blocker
(`bookorder block`), or a scope/page-count change. Report progress briefly in the user's language. At
`STATUS: COMPLETE`, report the deliverables, advisory findings you chose not to follow, and every user-intent
conflict.

## Done means

`bookorder goal` prints `STATUS: COMPLETE`: every chapter written from verified evidence, the design approved by
the user, images reviewed as a series, outputs built and validated, publish/result.zip packaged.

# Production E2E procedure (≈300 pages, many URLs, one `/goal`)

This is the test the maintainer runs after implementation. It was NOT run during development; only the
mini-E2E (`python tests/mini_e2e.py`) was.

## 0. Prepare

1. Regenerate runtime packs so jobs contain the new fonts: `python tools/prepare-runtimes.py`, then
   `npm test && npm run build`.
2. In the web UI create a job: title, goal, readers, language `ja`, **Target scale: Long · 約300ページ**,
   paste all URLs (one per line) and drop any files, research: allow web research ON, "関連する提供資料をすべて
   本文に反映" ON, citation style as desired, outputs: DOCX, Semantic HTML, PDF, Static website, EPUB, in
   "05 出版形式とデザイン" leave Basic untouched (theme `modern-technical`, theme-default layout) or pick a
   publication preset (Expert › art direction if you want to test it), runtime = your OS.
3. Extract the ZIP. Give the agent network access for its shell if possible (Codex: a sandbox mode with
   network, e.g. `--sandbox danger-full-access` or workspace-write with network enabled); otherwise every URL
   comes back as an `ingest:` task for the agent's browser tool, which is slower but still tracked.

## 1. The one instruction

Open the `publishing-job` folder in Codex and send exactly one message:

```
/goal AGENTS.mdを読み、bookorder goal が STATUS: COMPLETE を表示するまで出版ジョブを最後まで実行してください。
```

Do not type "continue", "next chapter", "build", etc. If the session ends before completion (execution limits),
start a new session in the same folder with the same `/goal` line: it resumes from `project-state.json`.
Record how many times you had to re-issue it — that is a runtime limit, not a BookOrder phase.

## 2. While it runs

- `bookorder status` (or `bookorder.cmd status`) — current phase and blockers.
- `run-events.jsonl` — every phase start/complete, tool invocation (`fetch-sources`, `reference-registry`,
  `deterministic-audit`, `build`, `validate`, `package`), task issue (`invoke` with `skill`) and
  `agent_done`.
- `research/source-status.json` — live ingestion counts.

## 3. Expected files at the end

| File | Confirms |
| --- | --- |
| `execution-summary.json` | `publication_status: "complete"`, all 20 phases `complete`, counts, invoked skills/tools, outputs, `completion_gates.passed: true` |
| `project-state.json` | phases, locked `scale`, accepted reviews, counters (review rounds, rewrite passes, reopenings) |
| `run-events.jsonl` | the workflow actually executed (see §4) |
| `research/index.json`, `research/source-status.json` | every supplied source with ID, status, attempts, chars, SHA-256, limitations |
| `research/supplied/src-*/source.md` + `metadata.json` | persisted corpus (content, not just URLs) |
| `research/discovered/src-*/…`, `research/search-log.jsonl` | supplementary research and its queries |
| `research/research-plan.yaml`, `research/notes/*.yaml`, `research/corpus-summary.yaml` | gaps, per-source analysis, corpus overview |
| `research/research-lock.json` | research freeze; `post_draft_additions` if any |
| `plan/book-bible.yaml`, `plan/book-context.yaml`, `plan/concept-map.yaml`, `plan/argument-map.yaml`, `plan/timeline.yaml`, `plan/source-clusters.yaml`, `plan/topic-synthesis.yaml` | synthesis before drafting |
| `source/metadata/outline.yaml`, `plan/chapter-dependencies.yaml`, `plan/parts.yaml` | architecture and parallel waves |
| `plan/chapter-packets/*.yaml`, `plan/summaries/*.yaml` | chapter jobs received shared state |
| `reports/chapter-status.json`, `reports/chapter-status/*.json` | contracts: target / minimum / actual per chapter |
| `source/references/references.json`, `source/metadata/sources.yaml` | reference registry keyed by stable IDs |
| `reports/source-coverage.json` | used / background_only / irrelevant / unavailable per source; `orphan_supplied_sources: []` |
| `plan/assets-plan.yaml`, `source/assets/diagrams/*.yaml`, `source/assets/figures/*.svg` | planned assets |
| `plan/integration-review.yaml`, `plan/audit/*.yaml`, `reports/audit-ledger.json`, `reports/audit-report.yaml` | integration, audit, rewrite, re-audit |
| `plan/design-decisions.yaml`, `reports/design-report.json`, `reports/layout-review.md` | design and layout |
| `reports/build-report.json`, `reports/validation-report.json`, `reports/completion-gates.json` | build, validation, 19 gates |
| `publish/book.pdf`, `publish/site/`, `publish/book.epub`, `interchange/book.docx`, `interchange/book.html`, `interchange/book-ir.json`, `publish/result.zip` | deliverables |

## 4. Verification checklist (with commands)

Use Python from the job (`runtime\python\python.exe` on Windows) or any Python 3.

1. **All supplied URLs attempted.**
   `python -c "import json;d=json.load(open('research/source-status.json'));print(d['supplied'])"`
   Expect `attempted == total` and `pending_total == 0`. Every non-usable source must be `unavailable` or
   `duplicate` with a reason in `limitations` (see `research/index.json` → `attempts`). Compare `total` with the
   number of URLs + files you supplied.
2. **Corpus persisted.** For each `fully_ingested`/`partially_ingested` source, `content_path` exists and
   `chars` is realistic (spot-check 5 long articles against the web page; the text should include the ending, not
   just the introduction). `partially_ingested` sources must carry an explanation.
3. **Supplementary research happened and is persisted.** `research/search-log.jsonl` has queries tied to gaps
   in `research/research-plan.yaml`; discovered sources exist under `research/discovered/`.
4. **Synthesis before drafting.** In `run-events.jsonl`, `corpus_analysis complete` and `research_frozen complete`
   come before the first `drafting` `invoke`; every usable source has `research/notes/<id>.yaml`.
5. **Chapter contracts.** `reports/chapter-status.json`: `complete == len(chapters)`,
   `total_actual >= book_minimum` (≈120,000 for 300 pages ja/A5). Look at `contract_failed` events: short first
   drafts should have been followed by `expand:`/`review:` tasks, not by completion.
6. **Chapter-by-chapter authoring with shared state.** One `draft:<ch>` event per chapter; every
   `plan/chapter-packets/<ch>.yaml` references `plan/book-bible.yaml` and the glossary and (after chapter 1)
   includes `prerequisite_summaries`.
7. **Citation mapping.** `grep -c "\[cite:src-" source/manuscript/*.md` is non-zero and
   `grep -E "\[[0-9]+\]" source/manuscript/*.md` finds nothing (no hard-coded numbers). In the PDF/site, numbers
   appear and the bibliography lists the sources; `interchange/book-ir.json` → `crossrefs` holds figure/table/
   equation numbers. Pick three citations and check that the cited source (via `references.json`) supports the
   sentence.
8. **Audit and targeted rewrite ran.** `run-events.jsonl` has `audit:<ch>` and `audit:book` `agent_done`,
   deterministic audit invocations, and — if issues were found — `rewrite:<ch>` for only the affected chapters
   followed by `reaudit:<ch>`. `reports/audit-report.yaml` → `summary.open.high == 0` and `open.medium == 0`.
9. **No premature finish.** `execution-summary.json` → `complete: true` only after `package` and `complete`
   phases; `reports/completion-gates.json` → 19 gates passed; `project-state.json` → no blockers. Run
   `bookorder gates` yourself — it re-evaluates everything and must print 16 × PASS.
10. **Genuine publication vs preview.** A genuine result has all of: STATUS COMPLETE from `bookorder goal`,
    gates 1–16 PASS, `total_actual ≥ minimum`, the page count of `publish/book.pdf` in the requested range
    (the character budget is an estimate: with the default A5 theme a full text page holds ≈900–1,000
    characters, so 150,000 characters with openers, figures and tables typically lands around 220–320 pages;
    tune `scale.characters_per_page` in project.json if you need a tighter page match), no open high/medium issues, and `publish/result.zip` newer than the build. An incomplete
    preview shows `publication_status` other than `complete`, failing gates listed under `diagnosis`, and
    usually a phase before `package`.
11. **Design.** Check the PDF title page, contents, chapter openers, running heads, figures, tables,
    equations and bibliography; the website at desktop and 390 px widths and in dark mode; DOCX paragraph styles
    and native equations; EPUB navigation.

## 5. Diagnosing an incomplete run

`execution-summary.json` → `diagnosis` lists blockers and failed gates with a category: source retrieval,
partial extraction, research gap, chapter length deficit, chapter contract, chapter dependency, source coverage,
editorial inconsistency, citation errors, asset generation, design, build. `project-state.json` →
`counters` shows repeated review rounds (`review:<ch>`, cap 6 → blocker "chapter length deficit") and rewrite
passes (cap 6 → "editorial inconsistency"). A run that simply stopped (runtime interruption) has no blocker and
a phase still `running`; re-issue the same `/goal`.

## 6. Mini-E2E (already automated)

`python tests/mini_e2e.py` drives the real orchestrator with a scripted mock agent over a local fixture
(6 sources incl. a contradiction, 1 unavailable URL, 1 duplicate URL, 1 PDF, 1 discovered source, 4 chapters,
1 diagram, 1 table, 1 equation, callouts, numeric bibliography). It asserts the items above at small scale.

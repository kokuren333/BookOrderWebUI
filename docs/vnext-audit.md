# BookOrder vNext — audit, gap analysis and architecture

Historical snapshot: paths such as `skills/research.md` below describe the pre-migration flat tree. Current paths and loading rules are in [SKILLS_ARCHITECTURE.md](SKILLS_ARCHITECTURE.md).

## 1. How `/goal` actually ran before this change (v0.1)

BookOrder is a static web app that packages a *publishing job* ZIP (`src/job.ts`). There is no model inside
BookOrder: the external agent (Codex `/goal`, Claude Code, …) is the model runtime. The real v0.1 runtime path was:

```
/goal "AGENTS.mdを読み…"            (agent runtime)
 → AGENTS.md: 20 prose steps          (instructions only; nothing enforced them)
 → skills/*.md: 5 short guides         (read-only advice)
 → agent writes source/manuscript, outline.yaml, sources.yaml, references.bib by hand
 → run.cmd build / validate / package  (scripts/build.py, validate.py, package.py)
 → "complete" = package.py succeeded   (validation passed + two non-empty review .md files)
```

There was no goal parser, orchestrator, phase state, source ingestion, research persistence, corpus, contracts,
length check, audit or completion gate in code. Every "phase" existed only as a sentence in AGENTS.md. The
failure mode described in the task followed directly: `validate.py` checked that each supplied URL appeared in
`sources.yaml` (registration, not reading); `outline.yaml` required `target_words` but nothing ever compared it
with the manuscript; `package.py` accepted any structurally valid build. A 15,000-character overview of a
300-page request with a working PDF therefore packaged "successfully".

## 2. Component audit (v0.1)

| Component | Where | Reached by /goal? | Actually invoked? | Assessment |
| --- | --- | --- | --- | --- |
| `/goal` entry | agent runtime → AGENTS.md | yes | yes | prose only; no root job owner |
| Goal parser / orchestrator | — | — | — | **missing** |
| Phase state / resume | — | — | — | **missing** |
| Source ingestion / URL fetch / extraction | — | — | — | **missing** (agent-dependent, unverified) |
| Source registry | source/metadata/sources.yaml (hand-written) | yes | validated for *presence* only | insufficient |
| Supplementary research / search log | skills/research.md | yes (advice) | untracked | insufficient |
| Corpus persistence | — | — | — | **missing** (URLs only) |
| Global synthesis, Book Bible | — | — | — | **missing** |
| Outline | source/metadata/outline.yaml | yes | order/ID checks | insufficient (no DAG, no budgets) |
| Chapter contracts | AGENTS.md step 8 ("write contracts") | yes | never checked | exists-but-unused |
| Length budgeting / deficit loop | `target_words` field | yes | never measured | insufficient |
| Chapter drafting / packets | skills/book-authoring.md | yes | advice only | insufficient |
| Cross-chapter integration | skills/editing.md → reports/editorial-review.md | yes | existence of a file | insufficient |
| Citations | Pandoc `[@key]` + hand-written BibTeX | yes | yes (citeproc, default author-date) | working but not ID-stable; no numeric style |
| Cross references | plain `[text](#id)` links | yes | yes | insufficient (no numbering) |
| Figures | Diagram IR → SVG (scripts/diagrams.py) | yes | yes | working; no planning / asset IDs |
| Tables | Pandoc | yes | yes | working; no numbering |
| Equations | Pandoc math pass-through | yes | partially (HTML had no math method) | insufficient (no numbering, no refs) |
| Generated images | figures.md mention | yes | untracked | insufficient |
| Book IR / Design Spec / tokens / themes | book_ir.py, design.py, schemas, themes/ | yes | yes | working (good foundation) |
| CSS theme + custom.css | design.py, themes/*/css | yes | yes | working |
| Typst renderer | renderers/typst.py | yes | yes | working; B5/Letter paper names broken |
| HTML site / EPUB / DOCX | build.py | yes | yes | working |
| Validation | validate.py | yes | yes | structural only |
| Whole-book audit / targeted rewrite / re-audit | — | — | — | **missing** |
| Completion detection | package.py | yes | yes | insufficient (false completion) |
| Observability | build/validation JSON reports | partly | yes | insufficient (no stage/skill trace) |
| Theme preview | cli.py theme preview | yes | yes | working |
| 4 themes | themes/ | yes | yes | identical CSS/Typst, differing tokens (fine) |

## 3. Capability matrix (before → after)

| Capability | v0.1 | vNext implementation |
| --- | --- | --- |
| bulk source ingestion | missing | `sources.py` (parallel fetch, bounded batches, retries) |
| article extraction | missing | readability pass + Pandoc HTML→Markdown; DOCX/EPUB/ODT/RTF via Pandoc; PDF via pdftotext or agent |
| source state tracking | insufficient | per-source status + attempts + limitations (`research/index.json`, `source-status.json`) |
| corpus persistence | missing | `research/<origin>/<id>/source.md` + `metadata.json` |
| supplementary research | insufficient | `research:supplementary` task, `research-plan.yaml` gate |
| search persistence | missing | `research/search-log.jsonl` (`bookorder research log`) |
| source clustering | missing | `plan/source-clusters.yaml`, coverage-checked |
| global synthesis | missing | six synthesis files + glossary, gated |
| Book Bible generation | missing | `plan/book-bible.yaml`, gated |
| chapter dependency planning | missing | outline DAG checks, `plan/chapter-dependencies.yaml` waves |
| chapter contracts | exists-but-unused | `reports/chapter-status/<id>.json`, evaluated every call |
| length budgeting | insufficient | `planning.compute_scale`, locked in project-state.json |
| chapter drafting | insufficient | `draft:<ch>` tasks with generated packets, DAG order, parallel waves |
| chapter expansion | missing | `expand:`/`review:` deficit loop, book-level deficit loop |
| cross-chapter integration | insufficient | deterministic checks + `integrate` task + review file |
| terminology normalization | missing | glossary `forbidden` / Bible `avoid` scanning |
| citation registry | insufficient | stable `src-NNNN` → CSL JSON (`source/references/references.json`) |
| source coverage | missing | `reports/source-coverage.json`, gate 3 |
| figure planning | missing | `plan/assets-plan.yaml`, gated |
| Diagram IR | working | kept; wired into asset gates |
| generated image support | insufficient | planned assets with metadata JSON, policy-checked |
| math support | insufficient | MathML (HTML/EPUB), OMML (DOCX), Typst math (PDF), numbered equations |
| equation references | missing | `crossref.py` (`@eq:` and `@ch/@sec/@fig/@tbl`) |
| Design Spec / theme selection / CSS & Typst tokens / custom CSS / components | working | kept; refined; 5 themes; bundled OFL fonts |
| whole-book audit | missing | deterministic audit + chapter/book agent audits → ledger |
| targeted rewrite | missing | `rewrite:<ch>` tasks from open issues only |
| completion gating | insufficient | 17 publication gates, re-verified on every call |
| persistent state / resume | missing | `project-state.json`, file-derived tasks, interrupted-fetch reset |
| observability | insufficient | `run-events.jsonl`, `execution-summary.json` |

## 4. Architecture

```
/goal (agent runtime)
  └─ bookorder goal ── orchestrator.advance()            scripts/orchestrator.py  (root; only it may complete)
        phase handlers (in order; each = tool steps + gate + agent tasks)
        source_ingestion        sources.py         fetch/extract/persist; ingest:/verify: tasks
        supplementary_research  research.py        search log, discovered sources, research-plan gate
        corpus_analysis         research.py        notes per source (analyze:), synthesis (synthesize)
        research_frozen         research.py        research-lock.json (IDs stable; post-draft additions tracked)
        architecture            planning.py        Book Bible + outline DAG + budgets (architecture)
        reference_assignment    citations.py       CSL JSON registry, sources.yaml, packets, contracts
        editorial_planning      editorial_plan.py  editorial:<ch> plans vs profile (roles, devices, pauses) → gate 18
        drafting                planning.py        draft:<ch> in dependency waves (parallel groups); devices as slots
        chapter_review          planning.py        contracts (incl. slots) → expand:/review:; book-level deficit
        asset_planning          assets.py          plan-assets from visual intents; visual review; editorial-fallback
        asset_generation        assets.py/diagrams asset:<id>; Diagram IR → SVG; slots:<ch> → gate 19
        integration             audit.py           deterministic integration checks + integrate task
        audit                   audit.py           deterministic audit + audit:<ch>, audit:book → ledger
        rewrite                 audit.py           rewrite:<ch> for open high/medium issues only
        final_audit             audit.py           reaudit:<ch> for changed chapters; loops to rewrite
        design                  design.py          design task; Design Spec validation
        layout                  build.py           proof build, pacing report, layout-review task
        build / validation      build.py/validate  final build; structural validation; gates
        package / complete      package.py         result.zip; all 19 gates re-verified
  └─ bookorder done <task>  → records the report, re-runs advance(); gates decide
```

Book IR (Pandoc AST + components + crossref registry) and the Design Spec stay separate. Rendering:
`common.combined()` merges chapters, numbers/resolves cross references, then citeproc renders citations once
with the selected CSL style (`templates/csl/numeric.csl`, `note.csl`, or Pandoc's author-date default).
`build.py` feeds the same IR to Typst (PDF), HTML (semantic + static site, MathML), EPUB 3 and DOCX; design
tokens feed CSS custom properties, Typst variables and DOCX styles.

## 5. Skills and workflows

Modified: `AGENTS.md` (single loop contract), `skills/research.md` (supplementary research, notes, synthesis,
freeze), `skills/book-authoring.md` (Bible, architecture, packets, contracts, expansion), `skills/editing.md`
(integration, targeted rewrite), `skills/figures.md` (asset plan, Diagram IR, equations, images),
`skills/editorial-design.md` (design task, layout review), `skills/publication-qa.md` (what the tools already check).

New, and why:
- `skills/source-ingestion.md` — no component owned ingestion; the agent needs a precise protocol for the sources
  the fetcher cannot read (submit/confirm/accept-partial/unavailable) so "attempted" is provable.
- `skills/audit.md` — auditing is a distinct responsibility from editing (report vs fix) and needs its own
  output format (per-chapter audit files feeding the ledger).

New scripts: `orchestrator.py`, `sources.py`, `research.py`, `planning.py`, `manuscript.py`, `assets.py`,
`audit.py`, `citations.py`, `crossref.py`. Modified: `common.py`, `cli.py`, `build.py`, `validate.py`,
`package.py`, `book_ir.py`, `design.py`, `renderers/typst.py`, `bootstrap.py`.

## 6. Migration notes

- project.json `format_version` is now `0.2` and adds `research.require_supplied_coverage` and
  `citations.style`; 0.1 jobs are still read (defaults: coverage required, numeric citations).
- Citations: write `[cite:src-NNNN]`; plain Pandoc `[@key]` with a manual `references.bib` still works.
  `references.json` is generated from the source registry.
- Outline chapters use `target_characters` (`target_words` is still accepted) and IDs must start with `ch-`.
- `sources.yaml` and `figures.yaml` are generated; edit the registry via `bookorder source …` and the plan via
  `plan/assets-plan.yaml`.
- Headings are numbered by BookOrder (not by `--number-sections`); use `{.unnumbered}` for unnumbered headings.
- Pipe-table column widths are no longer taken from dash counts; renderers size columns from content.
- Runtime packs must be regenerated (`python tools/prepare-runtimes.py`) to include the new fonts; older packs
  still work and fall back to system fonts.

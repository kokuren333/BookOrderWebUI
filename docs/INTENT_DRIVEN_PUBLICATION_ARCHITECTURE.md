# Intent-driven publication architecture

BookOrder no longer pours text into a fixed book template. It reads the user's intent, the purpose of the
publication and the role of every input, and designs structure, blocks, visuals, citations and layout per
publication — and per chapter. Why this was needed: [INTENT_DRIVEN_PUBLICATION_AUDIT.md](INTENT_DRIVEN_PUBLICATION_AUDIT.md).

Related: [SOURCE_ROLE_SYSTEM.md](SOURCE_ROLE_SYSTEM.md) · [CITATION_AND_BIBLIOGRAPHY.md](CITATION_AND_BIBLIOGRAPHY.md) ·
[VISUAL_PLANNING.md](VISUAL_PLANNING.md) · [USER_INTENT.md](USER_INTENT.md). Agent-facing specification shipped in every
job: [`job-template/docs/publication-architecture.md`](../job-template/docs/publication-architecture.md).

## Pipeline

```
WebUI (Quick / Advanced)                          src/architecture.ts, src/ArchitecturePanel.tsx, src/job.ts
  └ project.json  publication_architecture · citations · input.sources[].usage · input.assets[]   TASK.md sections
      └ source_ingestion  (content files only; references/assets never ingested)            scripts/sources.py
      └ corpus_analysis   notes estimate source_role / authority                              scripts/research.py
      └ publication_planning  ← NEW                                                         scripts/publication_architecture.py
          Intent Interpreter      plan/publication-intent.yaml
          Source Classifier       plan/source-roles.yaml, plan/uploaded-assets.yaml           scripts/source_roles.py
          Publication Architect   plan/publication-architecture.yaml
          Layout references       plan/layout-references.yaml (composition only)
      └ architecture      Book Bible + outline with per-chapter content_intent / blocks / visuals (Chapter Planner)
      └ editorial_planning  devices from the block library, checked against the block policy   scripts/editorial_plan.py
      └ visual_planning   ← NEW  plan/visual-plan.yaml + reports/visual-plan-qa.yaml           scripts/visual_plan.py
      └ drafting / review / assets / integration / audit / prose   (architecture lines in every task and packet)
      └ design            layout strategy, layout references → plan/design-decisions.yaml
      └ build             Citation Manager + Bibliography Builder                            scripts/bibliography.py, common.combined()
      └ validation        gate 23: Publication architecture QA                               scripts/architecture_qa.py
```

Responsibilities were added only where a missing decision caused the fixed grammar; there is no separate agent per
box. Intent Interpreter, Source Classifier and Publication Architect are one agent task (`publication-plan`) with
deterministic seeding and checks around it; the Chapter Planner is part of the existing architecture task; the Visual
Planner is its own phase because visuals must be decided before drafting; the Bibliography Builder is deterministic.

## Structure modes

| Mode | Meaning |
|---|---|
| AUTO (WebUI default) | BookOrder infers archetype, block policy, visual policy and chapter architecture from the intent and the corpus. Chapters may differ in structure. |
| GUIDED | The user's publication type, block choices, exercise and visual policy are constraints; BookOrder designs within them. |
| FIXED | Legacy template: the profile's chapter-end apparatus is required in every chapter; device counts are errors as before. **Every `project.json` without `publication_architecture` (jobs generated before this change) is FIXED**, so existing jobs behave exactly as before. |

Jobs whose `project-state.json` predates the protocol (`architecture_protocol` absent) skip the new checks and gate 23.

## Schemas (single source of truth)

`job-template/schemas/publication-architecture.json` is read by both the WebUI (TypeScript JSON import) and the job
scripts (Python). It defines:

| Concept | Key |
|---|---|
| StructureMode | `structure_modes` |
| PublicationArchetype | `archetypes` (practical_guide, handbook, textbook, reference_book, workbook, exam_preparation, tutorial, essay_like_book, visual_guide, technical_manual, academic_monograph) with default preferred / discouraged blocks, exercise policy, visual density, visual types, tone, reading mode |
| Block library (BlockPolicy vocabulary) | `blocks` — summary, key_points, key_point, checklist, exercises, check_questions, answer_key, pitfalls, next_actions, case_study, case_reflection, clinical_case, references, further_reading, template_forms, dialogue_examples, algorithm_card, warning_box, callout, definition, glossary, counterpoint, pull_quote, column, open_question, bridge_to_next, figure, workflow_diagram, decision_tree, infographic, chart, table, comparison_table, decision_table, timeline — each with its component, marker class and allowed positions |
| Exercise policy | `exercise_policies` (none, optional, where_useful, every_chapter, exam_focused) |
| VisualPlan taxonomy | `visual_types` (19 types), `generation_methods`, `visual_importance`, `visual_densities` |
| SourceRole / SourceAuthority / UploadedAssetInstruction | `source_roles`, `source_authority`, `asset_roles`, `quick_uses` |
| LayoutReference | `layout_reference_fields` |
| PublicationIntent | `intent_fields` |
| CitationPolicy / BibliographyPolicy | `citations` |
| Intent signals | `intent_signals` (patterns shared by the WebUI preview and the Intent Interpreter) |

Generated artifact schemas: `bookorder/publication-intent@1`, `bookorder/publication-architecture@1`,
`bookorder/visual-plan@1`, `bookorder/visual-plan-qa@1`, `bookorder/source-roles@1`, `bookorder/uploaded-assets@1`,
`bookorder/publication-architecture-qa@1`; `reports/bibliography.json`.

## Intent → archetype → block policy → visual policy → chapter architecture → layout

1. **Intent** (`plan/publication-intent.yaml`): every field of `intent_fields` with `{value, origin, evidence}`.
   BookOrder seeds it deterministically (WebUI settings, book description, readers, signals in the user's words) and
   the agent completes it (`reviewed_by_agent: true`).
2. **Archetype**: WebUI choice, else explicit hints in the user's text (「問題集」「現場で使える」…), else profile
   genre / description. Mixed books: `archetype: {primary, secondary, note}`.
3. **Block policy**: archetype defaults (+ secondary), then the WebUI block choices, then explicit user signals. A block
   the user excluded is **forbidden** and is re-applied every time the architecture is loaded — no agent edit can relax
   it (`publication_architecture.enforced()`). Example seeded for a practical guide:

   ```yaml
   block_policy:
     preferred: [checklist, workflow_diagram, case_study, warning_box, pitfalls, decision_table, next_actions, template_forms]
     discouraged: [exercises, check_questions, answer_key, pull_quote]
     forbidden: []
     requirements: [every_major_chapter_must_have_actionable_content]
     required_chapter_end: []
   ```

4. **Visual policy**: density (scales the profile's visuals-per-10k health range), preferred/avoided types, minimum
   distinct types, maximum share per type.
5. **Chapter architecture** (outline, architecture phase): each chapter's `content_intent`, `blocks`, `visuals` and
   optional `block_overrides`. Chapters are expected to differ (第1章 guidance + orientation; 第2章 timeline + workflow;
   第6章 algorithm + decision tree + emergency reporting example; 第7章 comparison table + checklist). An outline that
   gives every chapter the same blocks is rejected unless `chapter_strategy.uniform_structure_reason` says why —
   consistency of voice and design is not sameness of structure.
6. **Layout**: `layout_strategy`, reading mode and `plan/layout-references.yaml` reach the design task; the designer
   records `layout_references_applied` in `plan/design-decisions.yaml`.

## What changed in checking

| Check | FIXED (legacy) | AUTO / GUIDED |
|---|---|---|
| profile chapter-end items in every chapter | error `chapter_end_missing` | not required; only `required_chapter_end` of the architecture |
| chapter-end item without a reason | — | error `chapter_end_missing_why` |
| forbidden block planned | — | error `block_forbidden` |
| discouraged block planned | — | medium `block_discouraged` (waiver with reason) |
| exercises without answers | — | error `exercise_without_answers` |
| outline blocks not planned | — | medium `chapter_block_unplanned` |
| upload meant for the chapter not planned | — | medium `uploaded_asset_unplanned` |
| same chapter end in every chapter | — | medium `chapter_end_uniform` |
| device count under / over the profile | medium / error | low / medium |

## Prompts

Every agent task in these phases receives the architecture as text (`orchestrator.architecture_lines`):
architecture, editorial planning (chapter policy, uploads with their instructions, block markup), visual planning,
drafting (forbidden/preferred blocks, evidence rule), asset planning (visual plan, upload decisions), design (layout
strategy, layout references), layout review (architecture QA and bibliography). Chapter packets carry
`publication_architecture` (planned / preferred / discouraged / forbidden blocks, exercise and evidence policy),
`uploaded_assets` for the chapter and `source_role` / `authority` / `citation_allowed` for each assigned source. The
verbatim user text still travels with every task (USER_INTENT.md); `publication_planning` and `visual_planning` are
content phases with their own notes.

## Publication architecture QA (gate 23)

`scripts/architecture_qa.py` → `reports/publication-architecture-qa.yaml`. High findings block completion and reopen
the phase that must fix them (manuscript findings enter the audit ledger as `publication-architecture` rewrite targets).

| Finding | Severity (AUTO/GUIDED · FIXED) |
|---|---|
| `mechanical_chapter_end`, `template_dominates` | medium · low |
| `forbidden_block_in_manuscript` | high · high |
| `unneeded_exercises`, `exercise_without_answers` | high · low |
| `visual_monotony`, `visual_variety_low`, `visual_same_type_every_chapter`, `flow_diagram_monotony` | medium · low |
| `visual_duplicates_text` (labels restate the preceding paragraphs) | low |
| `uploaded_asset_instruction`, `reference_as_content` | high |
| `non_citable_source_cited`, `background_only_claim` | high |
| bibliography built against the policy (`bibliography_numbering`, `bibliography_cited_mismatch`, `background_contains_cited`, `cited_non_citable_role` …) | high |
| `user_preference_unmet`, `user_visual_wish_unmet` | medium |

`bookorder architecture` prints the resolved architecture, source roles, uploads and QA summary.

## WebUI

Quick mode: title, goal, readers, scale, files (roles estimated from name and type, marked 「推定」 and editable),
free-text intent (with a live preview of the explicit wishes BookOrder will enforce), outputs, runtime. The structure
mode is AUTO. Advanced publishing mode adds, behind accordions: structure mode, publication type (+ secondary + free
text), exercise policy, visual density, per-block policy, visual types, chapter architecture, evidence policy, layout
strategy, research, in-text citation / footnote style / bibliography style / numbering / grouping, and per-file
details (label, asset role, authority, citation, chapter, section, usage, priority, caption, crop/redraw/transform/
verbatim, instruction), plus the existing publication-format panel.

## Presets

Publication presets are unchanged: they still fill genre, layout, style and theme. In AUTO/GUIDED mode the profile genre
they select contributes only starting preferences (device densities, visual grammar); the chapter-end apparatus is no
longer imposed. FIXED keeps the preset's full template behaviour.

## Tests

`tests/test_publication_architecture.py` (the twelve required behaviours + propagation), `tests/architecture_e2e.py`
(WebUI-generated AUTO job run to `STATUS: COMPLETE` with a layout reference, a background source, an uploaded figure
and footnote + numbered grouped bibliography), `tests/job.test.ts` (payload, file placement, signal parity),
`tests/ui_interaction.py` (Quick and Advanced flows), and the existing suites (FIXED compatibility:
`tests/mini_e2e.py`, `tests/test_editorial_plan.py`, `tests/test_orchestrator.py`).

## Limits

The Intent Interpreter's deterministic part recognises explicit phrases (schema `intent_signals`); subtler wishes rely
on the agent's reading, which BookOrder can only check for traceability (`intent_trace`) and against enforced blocks.
Duplication between a figure and its text is detected only for Diagram IR labels. Authority is advisory metadata; the
evidence-authority check applies to paragraphs with numbers or dates whose cited sources all have a known low rank.
Layout references are analysed by the agent (BookOrder checks the analysis exists and was applied, not its accuracy).

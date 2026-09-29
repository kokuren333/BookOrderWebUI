# Publication architecture (Intent Interpreter · Source Classifier · Publication Architect · Chapter Planner)

A book is designed for its purpose; it is not a fixed template with text poured in. Before the outline exists,
decide what kind of publication this is and which building blocks it needs. Read the user's verbatim instructions
first (they govern, docs/user-intent.md), then project.json (`publication_architecture`, `citations`,
`input.sources[].usage`, `input.assets`), plan/book-context.yaml and plan/topic-synthesis.yaml.

## 1. Intent (plan/publication-intent.yaml)

BookOrder seeds every field with a value and its origin (`user_setting`, `user_text`, `inferred`, `default`) and
lists `explicit_signals` it found in the user's words (「章末問題はいらない」, 「ケースを多く」, 「図表を多く」,
「固すぎない」 …). Check each field against the user's words and the corpus: publication_goal, audience,
reader_level, use_context, reading_mode, tone, evidence_priority, interactivity_need, visual_need,
visual_density, page_budget, expected_reading_time, publication_archetype, secondary_archetype,
chapter_strategy, citation_policy, source_policy, layout_strategy. Free-text values are welcome where no enum fits.
Set `reviewed_by_agent: true`.

## 2. Architecture (plan/publication-architecture.yaml)

intent → archetype → block policy → visual policy → chapter architecture → layout plan.

- `archetype: {primary, secondary, note}` — practical_guide, handbook, textbook, reference_book, workbook,
  exam_preparation, tutorial, essay_like_book, visual_guide, technical_manual, academic_monograph. Mixed books
  are normal (primary practical_guide, secondary textbook).
- `block_policy: {preferred, discouraged, forbidden, requirements}` over the block library
  (schemas/publication-architecture.json `blocks`). The library is a set of parts to combine per chapter —
  summary, checklist, exercises, answer_key, pitfalls, next_actions, case_study, case_reflection, clinical_case,
  references, further_reading, template_forms, dialogue_examples, workflow_diagram, decision_tree,
  decision_table, comparison_table, algorithm_card, warning_box, callout, figure, infographic …
- `exercise_policy`: none | optional | where_useful | every_chapter | exam_focused. Exercises are never routine
  apparatus: a practical guide usually needs checklists, cases and decision aids instead; a textbook, workbook or
  exam book needs exercises **with answers or explanations** (answer_key).
- `visual_policy: {density, preferred_types, avoid_types, min_distinct_types, max_share_per_type}` — see
  skills/design/visual-planning.md.
- `chapter_strategy: {strategy, vary_structure, uniform_structure_reason}` — consistency of voice and design is
  not sameness of structure. Only give a reason when every chapter truly needs the same structure.
- `evidence_policy`, `citation_policy`, `layout_strategy`, `tone`, `reading_mode`.
- `intent_trace: [{quote, effect}]` — how each explicit user phrase shaped the architecture.

Blocks the user excluded are forbidden and BookOrder re-applies them on every load; the architecture file cannot
relax them. In GUIDED mode the WebUI choices (archetype, preferred/forbidden blocks, exercise policy, visual
density) are constraints, not suggestions. FIXED mode keeps the legacy template (the profile's chapter end).

## 3. Sources are not all "sources"

plan/source-roles.yaml shows each source's role and authority. evidence may support facts, numbers, definitions and
recommendations; background (experience articles, commentary, blogs) informs viewpoint and examples but is not
cited for facts; structure_reference guides order only; redraw_source is understood and redrawn (credited as a
figure source). Layout, style and visual references and placed images are not sources at all: they live in
plan/uploaded-assets.yaml and are never read as content or cited. Where the user did not choose, estimate
`source_role` and `authority` in research/notes/<id>.yaml; the user's choice always wins. Authority is a hint,
not a verdict — role, the user's choice and context decide.

## 4. Layout references (plan/layout-references.yaml)

For each uploaded layout reference, describe composition only: page_geometry, margins, columns,
heading_hierarchy, line_length, body_density, figure_text_ratio, caption_style, callout_placement, table_style,
chapter_opener_style, whitespace, page_rhythm, header_footer, folio, dominant_visual_grammar. List what the design
should adopt (`apply`) and `do_not_copy`; set `content_used: false`. Never copy text, figures or wording.

## 5. Chapter architecture (outline, in the architecture phase)

Each outline chapter states `content_intent`, `blocks` (what its content needs), `visuals` (visual types) and
optional `block_overrides`. Example: ch-1 guidance + orientation (callout, figure); ch-2 timeline + workflow
(timeline, workflow_diagram, checklist); ch-6 algorithm + decision tree + emergency reporting example
(algorithm_card, decision_tree, template_forms, warning_box); ch-7 comparison table + checklist. BookOrder rejects
an outline in which every chapter plans the same blocks without a reason.

# Intent-driven publication — design audit (2026-09-29)

Question: why does BookOrder produce books whose chapters all end with the same apparatus (まとめ / 確認事項 /
演習 / コラム / 参考資料), whose figures are mostly the same box-and-arrow flow, whose bibliography mixes medical
evidence with experience articles, and which cannot use an uploaded image or a layout-reference PDF for what it is?
This audit traces the current code (commit `0e782fd`) before the change. The resulting architecture is described
in [INTENT_DRIVEN_PUBLICATION_ARCHITECTURE.md](INTENT_DRIVEN_PUBLICATION_ARCHITECTURE.md).

## 1. Data model today

| Concept | Where | Shape |
|---|---|---|
| publication request | `project.json` (`book`, `user_instructions`, `research`, `figures`, `citations.style`, `profile`, `layout_*`, `style_*`) | written by `src/job.ts` `projectData()` |
| publication profile | `profiles/tiers/*.yaml` + `profiles/genres/*.yaml` → `plan/profile.resolved.yaml` (`scripts/publication_profile.py`) | scale, structure (incl. `chapter_end`), device densities, rhythm, citations, art direction |
| manuscript | `source/manuscript/NN-*.md` (Pandoc Markdown), `source/metadata/outline.yaml` | chapters → sections; components as fenced divs |
| chapter / block plan | `plan/editorial/<ch>.yaml` (`scripts/editorial_plan.py`) | sections with devices from a **closed 14-item CATALOG**, `chapter_end` from a closed 8-item list |
| visuals | device intents in editorial plans → `plan/assets-plan.yaml` candidates → `reports/visual-review.yaml` | `information_shape.kind` (11 shapes), asset `type` (diagram/chart/table/image/...), Diagram IR types |
| layout | `plan/layout-spec.yaml`, `plan/style-bible.yaml`, `book.design.yaml` | geometry, typography, visual grammar |
| sources | `research/index.json` (`scripts/sources.py`), `research/notes/<id>.yaml` | one registry for every supplied file and URL; notes carry `relevance` and `reliability` |
| references | `source/references/references.json` (CSL JSON of every usable source, `scripts/citations.py`) | — |

## 2. What is fixed today

### 2.1 Chapter-end apparatus is mechanically required

- `profiles/tiers/*.yaml` set `structure.chapter_end: [key_points, bridge_to_next]`; genres overwrite it:
  medical_science `[key_points, check_questions]`, technical `[key_points, exercises]`, practical `[checklist]`,
  criticism `[key_points, open_question, bridge_to_next]`.
- `editorial_plan.check_chapter()` raises **`chapter_end_missing` as an error** for every item the profile lists,
  in **every chapter** ("the profile requires X at the end of every chapter"). Only a user-intent override with a
  verbatim quote could switch it off.
- `skills/editorial/editorial-planning.md`: "chapter end — by default what the profile lists, in every chapter";
  `skills/design/editorial-design.md`: "summary at chapter ends".
- Typst themes label the components 演習 / まとめ / 確認事項 / コラム, so the repeated apparatus is also visually
  identical in every chapter.

Result: a technical or medical practical guide gets *key points + exercises / check questions* in every chapter
whether or not the book's purpose calls for them; nothing requires answers for the questions.

### 2.2 The device vocabulary is a fixed template

`editorial_plan.CATALOG` = figure, chart, table, timeline, key_point, definition, glossary, warning, counterpoint,
checklist, pull_quote, case_study, column, chapter_summary. There is no exercise/answer pair, pitfall list, next
actions, template/form, dialogue example, clinical case, algorithm card, decision table or infographic. Device
**counts per chapter** (`devices.*_per_chapter` min/max) are uniform across chapters, so every chapter is pushed to
the same mix. There is no notion of a publication *type* (practical guide vs textbook vs exam preparation): the
genre (5 values) mixes subject matter and form.

### 2.3 Presets, template and style bible

`publication_presets` (WebUI) fill genre + layout preset + style preset + theme. The genre selects the profile
genre, which fixes the chapter-end apparatus and device densities (2.1). The StyleBible and themes govern only
the look. A preset is therefore a template of the **whole book grammar**, not a set of preferences.

### 2.4 Visuals

- Visuals are decided in `asset_planning` *after drafting* (the editorial plan holds only a `figure|chart|table|timeline`
  intent with an information shape). The only visual vocabulary is `information_shape.kind` + Diagram IR type
  (`flow, concept-map, hierarchy, timeline, comparison, cycle, process, network, matrix`).
- `visual_review.py` rejects bad candidates (linear flows, illustrative causality) and flags repeated compositions,
  but there is no plan of *what should be visualised where and why*, no taxonomy for decision trees, algorithm
  cards, dos & don'ts, dialogue cards, annotated images, infographics, and no check of visual **variety** across the
  book or of chapters that need a visual and have none. Flows are the path of least resistance.

### 2.5 User intent

`docs/USER_INTENT.md` (previous change) carries the verbatim free text into every task and lets explicit quotes
switch off pipeline defaults. But the intent is *never interpreted into structure*: no publication goal, reader
level, use context, archetype, block policy or visual policy is derived from it; 「章末問題はいらない」 only works if
the agent writes an override, and 「ケースを多く」「図表を多く」 have no structured effect.

### 2.6 Citations and bibliography

- `project.json citations.style` ∈ numeric | author-year | note selects **one CSL file** (`common.CSL_STYLES`) used
  by Pandoc citeproc for both the in-text form and the bibliography (`common.combined()` appends one `#refs`).
- Consequences: footnote citations ⇒ unnumbered author-sorted bibliography (note.csl); author-year ⇒ unnumbered
  bibliography; the list contains only cited works; everything lands in one 「参考文献」 list.
- The profile's `citations.style` (numeric/author_date/endnotes_per_chapter/minimal) is not connected to the renderer.

### 2.7 Sources, uploads and roles

- Every uploaded file becomes `input/sources/<name>` and a `research/index.json` source (`sources.init_supplied()`),
  i.e. **evidence by construction**; `citations.generate()` makes every usable source citable.
- Images and unsupported formats become `needs_agent_extraction` ingestion tasks; there is no way to say "this image is
  the figure for chapter 3", "use this PDF only for margins and columns", "redraw this diagram", "never on the cover".
- Notes have `relevance` (core/supporting/background/…) and `reliability` (primary/secondary/tertiary). Nothing
  distinguishes *evidence* from *background reading*, and no check stops a factual claim from being supported only by
  an experience blog. Layout/style references and content sources are not distinguished anywhere.

### 2.8 Responsibilities and prompts

Phases: ingestion → research → corpus analysis → freeze → architecture (Book Bible + outline) → reference assignment →
editorial planning → drafting → chapter review → asset planning/generation → integration → audit → rewrite → prose →
final audit → design → layout → build → validation → package. Prompts are the task instructions in
`scripts/orchestrator.py` plus `skills/**/*.md`. There is no Intent Interpreter, Source Classifier, Publication
Architect, Visual Planner, Bibliography Builder or architecture QA; the Book Bible's `design_intent` is prose only.

## 3. What changes

| Fixed today | Change |
|---|---|
| profile `chapter_end` required in every chapter | AUTO/GUIDED: chapter-end blocks chosen per chapter from the **block library**, each with a reason; FIXED keeps the old rule verbatim |
| closed device catalogue | `schemas/publication-architecture.json` block library (summary, checklist, exercises, answer_key, pitfalls, next_actions, case_reflection, references, further_reading, template_forms, dialogue_examples, clinical_case, workflow_diagram, decision_table, comparison_table, algorithm_card, warning_box, callout, figure, infographic, …) mapped to existing components |
| genre = whole-book template | Publication **archetype** (primary + secondary + free text) → block policy, visual policy, chapter strategy, citation policy; presets become starting preferences |
| intent carried only as text | new **publication_planning** phase: `plan/publication-intent.yaml` (Intent Interpreter; deterministic signals such as 「章末問題はいらない」 are enforced) and `plan/publication-architecture.yaml` (Publication Architect) |
| visuals after drafting only | new **visual_planning** phase: `plan/visual-plan.yaml` with 19-type taxonomy, purpose/reason/source/method/importance/caption intent; variety/duplication/gap QA |
| one citation style | `citations`: in-text style, footnote style, bibliography style, numbering, scope, sort, grouping, citation/reference roles; `scripts/bibliography.py` builds cited / background / visual / design lists |
| every upload is evidence | per-file usage metadata (role, authority, citation_allowed, intended chapter/section, caption, crop/redraw/transform/verbatim, instruction); non-content files go to `input/assets/` and `plan/uploaded-assets.yaml`, never to the research registry |
| no source roles | SOURCE_ROLE + SOURCE_AUTHORITY on every source (`plan/source-roles.yaml`); citations of non-citable roles are audit errors; evidence policy checks authority |
| no structure QA | `scripts/architecture_qa.py` → `reports/publication-architecture-qa.yaml`, completion gate 23 |
| single upload list / flat settings in the WebUI | Quick / Advanced modes, structure mode AUTO/GUIDED/FIXED, archetype, block/visual/exercise/evidence/citation/bibliography settings, per-file role editor with AI-estimated, editable roles |

Backward compatibility: a `project.json` without `publication_architecture` (every job generated before this change,
and all existing fixtures) resolves to **FIXED** mode — the old profile rules, citeproc bibliography and source
handling apply unchanged. The WebUI now defaults to AUTO.

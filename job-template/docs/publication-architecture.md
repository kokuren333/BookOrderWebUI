# Publication architecture (for the agent running this job)

This book is designed for its purpose; it is not a template filled with text. `project.json publication_architecture.mode`:

- **auto** — decide archetype, block policy, visual policy and chapter architecture from the user's intent and the corpus.
- **guided** — the user's WebUI choices (publication type, block choices, exercise and visual policy) are constraints.
- **fixed** (also every project.json without `publication_architecture`) — legacy template: the profile's chapter-end
  apparatus in every chapter.

`bookorder architecture` shows the resolved state.

## Files

| File | Written by | Content |
|---|---|---|
| plan/publication-intent.yaml | BookOrder seeds, you complete (`reviewed_by_agent: true`) | publication_goal, audience, reader_level, use_context, reading_mode, tone, evidence_priority, interactivity_need, visual_need, visual_density, page_budget, expected_reading_time, publication_archetype, secondary_archetype, chapter_strategy, citation_policy, source_policy, layout_strategy — each `{value, origin, evidence}`; `explicit_signals` found in the user's words |
| plan/publication-architecture.yaml | BookOrder seeds, you refine | archetype, block_policy {preferred, discouraged, forbidden, requirements, required_chapter_end}, exercise_policy, visual_policy, chapter_strategy, evidence_policy, citation_policy, layout_strategy, tone, intent_trace |
| plan/source-roles.yaml | BookOrder (from WebUI roles and your note estimates) | role, authority, citation_allowed per source |
| plan/uploaded-assets.yaml | BookOrder (from project.json input.assets) | every uploaded non-content file with the user's instruction |
| plan/layout-references.yaml | you (when layout references were uploaded) | composition features, apply, do_not_copy, content_used: false |
| source/metadata/outline.yaml | you (architecture) | per chapter: content_intent, blocks, visuals, block_overrides |
| plan/visual-plan.yaml | BookOrder seeds, you complete | one entry per visual intent (type, purpose, content, reason, source_requirements, generation_method, importance, caption_intent, duplication_check) |
| reports/publication-architecture-qa.yaml | BookOrder | gate 23 |
| reports/bibliography.json | BookOrder (build) | citation / bibliography lists as built |

## Rules

1. Blocks (schemas/publication-architecture.json `blocks`) are a library. No block is required in every chapter unless
   `required_chapter_end` or the requirements say so. Every chapter-end item says `why`.
2. A block the user excluded is forbidden everywhere (plans, manuscript, pacing fixes, expansion). BookOrder re-applies
   it on every load.
3. Exercises appear only where the architecture wants them, always with answers or explanations (`answer_key`, or
   `answers: {location}`).
4. Choose visual types from the information's shape; avoid one type everywhere (skills/design/visual-planning.md).
5. Cite evidence for facts, numbers, definitions and recommendations. Background sources (experience articles, blogs)
   inform the book and appear under 参考資料, but never as the only support of a factual claim. Layout, style and visual
   references are not content: never cite, quote or copy them.
6. Every upload with a role gets a decision (plan/assets-plan.yaml `uploaded_assets`) that follows its instruction.
7. The citation form in the text and the bibliography lists are configured separately (project.json `citations`);
   never type numbers — BookOrder numbers and groups the back matter.

Block markup: component class + marker class + title, e.g. `::: {.exercise .answer-key #id title="解答・解説"}`,
`::: {.warning .pitfalls #id}`, `::: {.checklist .next-actions #id}`, `::: {.step-by-step .algorithm-card #id}`,
`::: {.example .dialogue #id}`, `::: {.example .template-form #id}`, `::: {.case-study .clinical-case #id}`,
`::: {.note .case-reflection #id}`. A placed upload: `![caption](source/assets/uploaded/<file>){#fig-id}`.

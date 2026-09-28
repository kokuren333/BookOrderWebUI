# Book authoring

The user's instructions (printed verbatim with every task; docs/user-intent.md) govern this book. This Skill gives defaults for what they leave open; it is not a higher authority. Invariants — facts, citations, provenance, safety, the build — still bind.

## Book Bible and architecture (task `architecture`)

Start from the user's instructions: they decide the kind of book (textbook, criticism, essay…), voice, density,
scope, emphasis, cases and structure wherever they say something. Record them in `plan/user-intent.yaml`
(directives with the user's exact words) and in the Bible's `user_intent` section, which separates what the user
chose (`governs`) from the BookOrder defaults you used where they said nothing (`defaults_used`).

The task states the binding scale and the publication profile (plan/profile.resolved.yaml): body characters and
their minimum, the chapter range, section and paragraph lengths, device densities (figures/tables per 10,000
characters, callouts, case studies, pull quotes per chapter), the chapter lead and chapter-end elements, and the
text-wall limit. Scale and chapter range are binding; plan the outline to fit them (the page count is only an
estimate derived from the body size; characters exclude whitespace, code and math). Device densities, lead,
chapter-end elements and pacing are defaults: when the user's instructions exclude one (「章末まとめを付けない」),
list it under that directive's `overrides` instead of planning it.

`plan/book-bible.yaml` is shared by every chapter job: title, subtitle, purpose, audience, tone, central_thesis,
scope (included/excluded), terminology (preferred_terms with `avoid` variants, definitions, aliases),
editorial_rules (voice, formality, tense, punctuation, citation_style, repetition_policy), global_narrative
(opening, development, turning_points, conclusion), recurring_concepts, recurring_examples, cross_references,
chapter_dependencies, design_intent (theme, typography, figure_style, callout_policy) and, when the user wrote
instructions, user_intent (governs, defaults_used). Tone, voice, scope.excluded and callout_policy restate the
user's choices; do not replace them with a genre's usual register.

`source/metadata/outline.yaml` designs the whole book as a dependency graph grounded in the synthesis:

```yaml
chapters:
  - id: ch-attention            # must start with ch-
    title: "..."
    file: source/manuscript/03-attention.md
    part: "Part I"
    purpose: "..."
    prerequisites: [ch-sequences]     # earlier chapters only
    introduces: [concept-id]           # each concept introduced once
    develops: [concept-id]
    assumes: [concept-id]
    hands_off_to: [ch-transformer]
    target_characters: 12000
    required_sections: [{id: sec-attention-background, title: "Background"}, ...]
    required_topics: ["term|alias", ...]
    sources: {primary: [src-0021], supporting: [src-0108]}
    required_references: [src-0021]
    expected_assets: [fig-attention-flow]
    must_not_repeat: ["..."]
    handoff: "what the next chapter may assume"
```

Budgets must add up to the target. The chapter count must fall within the profile's range; chapters
over 60,000 characters must be split. Every relevant supplied source must be assigned somewhere.

## Drafting (tasks `draft:<chapter>`)

Read `plan/chapter-packets/<chapter>.yaml` first: it bundles the contract, shared-state paths (Book Bible,
glossary, concept map, reference registry), summaries of prerequisite and previous chapters, the assigned
sources with their notes and claims, and the syntax. Read the listed source texts. Do not redefine terminology,
tone, assumptions or the thesis. The packet's `user_intent` (the user's verbatim words) sets voice, distance to the
reader, density, stance and exclusions.

Write the chapter section by section: skeleton → each required section → source enrichment → examples →
citations → transitions → review against the contract and the user's instructions. Examples, transitions and
explanations follow the density and style the user asked for; the order above is a working method, not a
template every chapter must visibly show. Introduce concepts before use; refer back instead of
re-explaining (`@ch:`, `@sec:`). Cite with `[cite:src-XXXX]`. Then write `plan/summaries/<chapter>.yaml`
(summary, introduced_concepts, key_terms, examples_used, handoff, and intent_check when the user wrote
instructions) — later chapters depend on it. The summary file is internal; it is not a chapter-end summary in the
book.

The packet also carries the chapter's editorial plan (`plan/editorial/<chapter>.yaml`, skills/editorial/editorial-planning.md):
write its sections in order with their purpose, role and size, and reserve every planned device as a slot
(`::: {.slot #id kind=type}`) at its placement, or write a component device directly with the same id. The
contract fails while a planned device has neither.

## Contracts and expansion (tasks `expand:` / `review:`)

A chapter is complete only when it meets its minimum size, covers required topics and sections, cites required
references and has a summary. BookOrder measures this (`reports/chapter-status/<chapter>.json`) and returns
deficits. Expand with substance the user's instructions allow: unused assigned sources, missing concepts, worked
examples, historical context, technical explanation, comparisons, counterexamples, limitations, figures or tables
where they help — but not history the user wanted brief, counterarguments they did not want repeated, or
scaffolding they excluded. No padding, no repetition of other chapters. If the whole book is still short after every chapter meets its minimum, the
chapters furthest below target are expanded.

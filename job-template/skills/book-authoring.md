# Book authoring

## Book Bible and architecture (task `architecture`)

The task states the binding scale and the publication profile (plan/profile.resolved.yaml): body characters and
their minimum, the chapter range, section and paragraph lengths, device densities (figures/tables per 10,000
characters, callouts, case studies, pull quotes per chapter), the chapter lead and chapter-end elements, and the
text-wall limit. Plan the outline to fit it: the page count is only an estimate derived from the body size.
Characters exclude whitespace, code and math.

`plan/book-bible.yaml` is shared by every chapter job: title, subtitle, purpose, audience, tone, central_thesis,
scope (included/excluded), terminology (preferred_terms with `avoid` variants, definitions, aliases),
editorial_rules (voice, formality, tense, punctuation, citation_style, repetition_policy), global_narrative
(opening, development, turning_points, conclusion), recurring_concepts, recurring_examples, cross_references,
chapter_dependencies and design_intent (theme, typography, figure_style, callout_policy).

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
tone, assumptions or the thesis.

Write the chapter section by section: skeleton → each required section → source enrichment → examples →
citations → transitions → review against the contract. Introduce concepts before use; refer back instead of
re-explaining (`@ch:`, `@sec:`). Cite with `[cite:src-XXXX]`. Then write `plan/summaries/<chapter>.yaml`
(summary, introduced_concepts, key_terms, examples_used, handoff) — later chapters depend on it.

The packet also carries the chapter's editorial plan (`plan/editorial/<chapter>.yaml`, skills/editorial-planning.md):
write its sections in order with their purpose, role and size, and reserve every planned device as a slot
(`::: {.slot #id kind=type}`) at its placement, or write a component device directly with the same id. The
contract fails while a planned device has neither.

## Contracts and expansion (tasks `expand:` / `review:`)

A chapter is complete only when it meets its minimum size, covers required topics and sections, cites required
references and has a summary. BookOrder measures this (`reports/chapter-status/<chapter>.json`) and returns
deficits. Expand with substance: unused assigned sources, missing concepts, worked examples, historical context,
technical explanation, comparisons, counterexamples, limitations, figures or tables where they help. No padding,
no repetition of other chapters. If the whole book is still short after every chapter meets its minimum, the
chapters furthest below target are expanded.

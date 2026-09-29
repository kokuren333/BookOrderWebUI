# Editorial design

## Design direction (task `design`)

Read docs/design-system.md, book.design.yaml (it contains the user's `art_direction`), the user's instructions
and the Book Bible's design_intent. Structured WebUI format settings (page size, layout, outputs, selected design
values) stay as selected; the instructions decide the rest of the visual direction they speak to. Translate natural-language direction into Design Spec values first: theme, page size, role fonts
(body / heading / code / caption / footnote, with Japanese and Latin pairs), colors, density, spacing, component
variants (chapter_opener, callout, definition, warning, summary, table, code_block, figure_caption) and figure
style. Use custom.css (HTML/Web/EPUB) or custom.typ (PDF) only for what the spec cannot express, and never edit
generated files or scatter values through templates. Run `bookorder fonts` when changing fonts; unavailable fonts
fall back and are recorded in reports/design-report.json. Record your decisions in plan/design-decisions.yaml.

## Layout and pacing (task `layout-review`)

BookOrder builds a proof and lists pacing heuristics (very long prose runs, consecutive tables, callout density).
Every PDF build also writes reports/layout-metrics.json, measured from the typeset pages: text-only page runs,
elements per page and spread, and per-chapter visuals, callouts, prose characters per page and non-prose share
(`bookorder layout` re-measures without rebuilding). Start the review from its longest text-only runs.

Text walls are a completion gate (17), judged on those measured pages (reports/pacing-report.json): no more
than the limit of consecutive text-only pages (short 3, standard 4, long 4, monograph 6), and never two runs at
the limit in one chapter. Only a figure, table, callout, pull quote, case study, chapter summary or chapter
opener taking at least three lines of the page breaks a run; headings, lists, code, equations and white space
do not. A `pacing:<chapter>` task lists each wall with pages and ranked candidates (split_section,
convert_comparison_to_table, add_visual, insert_summary, add_case_study, add_counterpoint, add_pull_quote,
shorten_paragraphs). Prefer turning existing text into the device over adding material, and never insert a
device the user excluded (a summary, counterpoint or pull quote). If the user explicitly wants long uninterrupted
argument, the text-wall limit is a default they switched off: record `overrides: [layout_pacing]` on that directive
in plan/user-intent.yaml.
Open the actual outputs and check representative pages: chapter openers, dense tables, figures, equations, code,
footnotes, bibliography, running heads and folios; awkward page breaks, orphan headings, figures separated from
their explanation, overflow, missing glyphs, extreme density differences between chapters. On the website check
navigation, search, mobile width and dark mode. Fix causes in canonical source or Design Spec, rebuild with
`bookorder goal`, then record what you actually inspected in reports/layout-review.md. Never invent checks.

Use key-point for conclusions, definition for terms, warning/note for cautions and a summary only where the
editorial plan has one — the publication architecture decides the blocks, not the theme. Design for the book's
reading mode (plan/publication-architecture.yaml): lookup books need scannable structure, continuous reading calm
text pages. Uploaded layout references (plan/layout-references.yaml) inform composition only — geometry, margins,
columns, hierarchy, density, captions, whitespace, rhythm — and are recorded in plan/design-decisions.yaml
`layout_references_applied`; never copy their content. Keep ordinary paragraphs dominant; do
not box every paragraph or add decorative assets to fill pages. With user instructions, write `intent_check` in
plan/design-decisions.yaml.

# Editorial design

## Design direction (task `design`)

Read docs/design-system.md, book.design.yaml (it contains the user's `art_direction`) and the Book Bible's
design_intent. Translate natural-language direction into Design Spec values first: theme, page size, role fonts
(body / heading / code / caption / footnote, with Japanese and Latin pairs), colors, density, spacing, component
variants (chapter_opener, callout, definition, warning, summary, table, code_block, figure_caption) and figure
style. Use custom.css (HTML/Web/EPUB) or custom.typ (PDF) only for what the spec cannot express, and never edit
generated files or scatter values through templates. Run `bookorder fonts` when changing fonts; unavailable fonts
fall back and are recorded in reports/design-report.json. Record your decisions in plan/design-decisions.yaml.

## Layout and pacing (task `layout-review`)

BookOrder builds a proof and lists pacing heuristics (very long prose runs, consecutive tables, callout density).
Open the actual outputs and check representative pages: chapter openers, dense tables, figures, equations, code,
footnotes, bibliography, running heads and folios; awkward page breaks, orphan headings, figures separated from
their explanation, overflow, missing glyphs, extreme density differences between chapters. On the website check
navigation, search, mobile width and dark mode. Fix causes in canonical source or Design Spec, rebuild with
`bookorder goal`, then record what you actually inspected in reports/layout-review.md. Never invent checks.

Use key-point for conclusions, definition for terms, warning/note for cautions, summary at chapter ends.
Keep ordinary paragraphs dominant; do not box every paragraph or add decorative assets to fill pages.

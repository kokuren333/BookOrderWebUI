# Design verification

Verified on Windows with Python 3.12.14 / bundled Python 3.14.7, Pandoc 3.11 and Typst 0.15.1.

- npm test: ZIP inputs, design serialization and binary preview PNG signatures.
- npm run build: TypeScript/Vite and five pinned runtime packs with corresponding source.
- tests/design.py: invalid schema values/margins, independent fonts and explicit fallback, 24 component types, nine parseable escaped SVG types, four actual all-format theme previews, unchanged content IR, custom CSS in Web/EPUB, DOCX component styles, isolated canonical source, theme selection saved for reproducible builds.
- tests/e2e.py: baseline Japanese two-chapter all-format publication, actual DOCX styles, bad sources, citations, stale source/output and required QA records.
- tests/e2e.py --portable: same workflow with a restricted PATH, plus embedded-Python CLI theme preview and verification that the actual manuscripts/PDF remain unchanged.
- Browser: generated and inspected a real downloaded ZIP containing selected fonts/theme/custom CSS and all four PNG previews. Verified theme preset changes and advanced controls. Book website navigation and SVG loaded; at 375px width it had no horizontal page overflow. A custom warning border of 7px was verified in computed styles.
- PDF: rendered four three-page theme samples with Poppler, inspected chapter openings, tables, callouts, footnotes, SVG and references. Repaired an orphaned warning title and terminal contrast; inspected the revised terminal page. PDF font embedding checked through font descriptor streams.

Theme samples are short layout fixtures, not evidence of full 300–400-page book QA. Complex diagrams, long tables, font glyph coverage and actual manuscripts still require layout inspection. EPUB container/link checks passed; epubcheck was unavailable. macOS/Linux packs and launchers remain untested on native machines. No PDF/X or CMYK certification is claimed.

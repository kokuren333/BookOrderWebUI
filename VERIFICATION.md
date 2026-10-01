# vNext verification (2026-09-27)

Run in a Linux container with Python 3.11, Pandoc 3.11, Typst 0.15.1 and the bundled OFL fonts.

- `python tests/test_orchestrator.py` — 23 deterministic tests: supplied-source attempts, duplicates, partial and
  unavailable sources, zero-pending gate, agent submission, search-log persistence, disabled web research,
  stable IDs / research freeze / post-draft additions, numeric and author-year citations from stable IDs, CSL
  registry, cross-reference numbering, page→character budgets, outline budgets and DAG waves, deficit detection
  and expansion scheduling, chapter contracts, packets with shared Bible/glossary/prior summaries, the
  "PDF built but 15,000 of 120,000 characters" false-completion regression, coverage orphans, unresolved
  high-severity audit issues, package refusal, state round-trip/resume/reopen, event/skill observability,
  tokens/CSS/custom CSS/themes/equations. All pass.
- `python tests/mini_e2e.py` — the real orchestrator driven by a scripted mock agent over a local HTTP fixture:
  9 supplied sources (1 unavailable 404, 1 duplicate URL, 1 PDF, 4 short sources confirmed by the agent), 1
  discovered source with logged searches, notes, synthesis, freeze, Bible, 4-chapter DAG, a short first draft
  that triggered the length loop, integration, asset plan (Diagram IR, table, equation), per-chapter and book
  audits, one agent issue fixed by a targeted rewrite of one chapter and re-audited, design change, layout
  review, build of PDF/HTML/site/EPUB/DOCX, validation, 16 gates, package. Passes in 18 `goal` iterations.
- `python tests/design.py` (5 themes, real previews) and `python tests/e2e.py` (legacy pipeline) pass.
- PDF pages, website (desktop, 390 px, dark mode) were rendered and inspected visually.
- `npm test` / `tsc` were run on the maintainer machine (see below); the full production E2E (300 pages, real
  URLs) was intentionally not run — see docs/production-e2e.md.

# v0 verification

Verified on Windows with Node.js, Python 3.12, Pandoc 3.11 and Typst 0.15.1.

## Automated checks

- TypeScript compile and Vite production build pass. The dist output is a static app with no server runtime.
- Four ZIP-generator tests pass: required-field/URL/scale validation; safe distinct filenames; full template inclusion and byte-exact uploads; output/research policies and unknown extensions.
- The generated test job contains two real PDF sources, one Markdown source, and two URLs, matching the first acceptance-test shape.
- The extracted job builds a representative Japanese two-chapter fixture into DOCX, semantic HTML, PDF, EPUB and a multi-page static website.
- DOCX XML inspection confirms all ten requested semantic paragraph styles exist and are actually applied in the sample document.
- Structural checks pass for outline/manuscript order, source inventory, citations, stable IDs, local assets, HTML navigation and cross-references.
- EPUB archive, container, manifest, spine, XHTML and internal links pass. Cross-chapter figure and table links are repaired after Pandoc export. Full epubcheck is optional and was unavailable in this environment.
- Negative checks reject unfinished text, broken references, duplicate IDs, missing figures, unknown citations, changed source after build, modified artifacts, and missing editorial/layout QA records.
- Packaging is verified after the real QA reports are added; result.zip excludes itself, temporary build files and Python caches and retains the editable source plus scripts/templates.

## Visual and browser checks

- Browser form loads with Japanese defaults, locked canonical output, selected interchange/PDF/site options and privacy information.
- Required-field validation and ZIP generation show the expected error/success states using keyboard activation.
- Generated site TOC, chapter navigation, cross-chapter section links and local search were exercised in the browser.
- At a 390px viewport, the chapter layout has no horizontal page overflow; figures and tables remain within the page.
- All five sample PDF pages were rendered with Poppler and visually inspected: title page, publication-information page, table of contents, chapter pages, running title, page numbers, code, table, figure, footnote and bibliography are legible.

## Writing/design separation and PDF page feedback (2026-10-01)

- Regression checks cover explicit `chars_per_text_page` overrides, column/typography/geometry inputs, real PDF page counts including blank pages, and target-versus-actual reports.
- Stage tests cover immutable manuscript/citation handoffs, portable ZIP continuation, role-based agent assignments, partial restarts, protected sections and writer revision requests with revised chapter budgets.
- `python tests/stages_e2e.py` completes writing, exports and extracts a handoff into another folder, completes design and all publication outputs, and confirms unchanged manuscript hashes. Its actual 12-page PDF against an 8-page target also returns a revision request to the writer when feedback is enabled.
- Existing orchestration/citation tests, the original mini E2E, frontend tests and production build pass. These fixtures use scripted author responses; external model execution and long-book page convergence have not been verified.

## Existing fixture limitations

This is a short pipeline fixture, not a completed 50–400-page book or a comparison of external agent capabilities. The agent authoring instructions are supplied, but actual long-form research and editorial quality depend on the executing agent.

The in-app browser blocked file:// navigation, so direct local-file opening was not browser-tested. The static site's search uses embedded data with no fetch or server dependency, and relative assets/links were structurally checked.

The browser automation's file chooser and download event did not yield a verifiable uploaded-file list or saved download path. Browser ZIP success was observed; uploaded bytes and ZIP contents were verified independently with the exact same generator through Node tests. Drag/drop was implemented but was not independently exercised through browser automation. DOCX style application was checked through XML, rather than a live Word/InDesign session.

## Bundled runtime and transparency pages

- Windows x64 ZIP executed using its own CPython 3.14.7, Pandoc 3.11 and Typst 0.15.1 with system tool paths removed. A folder containing spaces and Japanese characters was used. All five output formats and the existing negative validation/QA cases passed.
- All five resulting PDF pages were rendered and visually inspected. Japanese font data is bundled.
- Five platform packs and the shared source/notice/font pack passed per-part and whole-pack SHA-256 checks before production build. The ZIP generator rejects corrupt packs, absent license/source data and missing selected runtimes.
- A modified corresponding-source archive prevented runtime startup. Result packaging retains the original runtime archives, fonts and corresponding sources/notices; expanded caches are omitted.
- Browser inspection confirmed separate contents/licensing and safety/data-handling pages, direct navigation links, OS/CPU selection and retention of typed form data across those pages.
- macOS 15+ arm64/x64 and Linux glibc 2.17+ arm64/x64 binaries are prepared, with POSIX launcher syntax checked. Native execution on these four targets is not verified in this Windows environment. Windows 10+ x64 is the supported Windows target.
- Browser generation of a Windows runtime ZIP showed the success state after all runtime parts were read; a saved browser download path was not independently captured. The same generator produced a verified roughly 315 MiB fixture ZIP through Node. Downloading may take time; integrity checks run before ZIP generation. The agent itself is not bundled or sandboxed.

Reproduce the portable check after preparing runtime assets:

```
node --experimental-strip-types tools/make-portable-fixture.mjs
python tests/e2e.py --portable
```

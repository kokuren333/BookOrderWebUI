# WebUI Information Architecture (settings consolidation)

This document records the audit of the WebUI settings and the resulting structure. Internal models are unchanged:
**PublicationProfile** (editorial scale/genre), **LayoutSpec** (geometry), **StyleBible** (semantic PDF appearance),
**Design Spec** (`book.design.yaml`: theme, typography, colour, components) and **project.json** keep their
responsibilities and resolvers. Only the user-facing grouping and the WebUI state changed.

## Phase 1 — Settings before the change: UI field → state → project.json → resolver → artifact

| UI (before) | Field | WebUI state | Written to | Resolver / consumer | Artifact |
|---|---|---|---|---|---|
| 01 書籍の企画 | Title / description / readers | `form.title` … | `project.book.*`, TASK.md | planning, agent | Book Bible, manuscript |
| 01 | Language | `form.language` | `book.language` (normalised) | profile chars/page, tokens | profile, design-tokens |
| 01 | Target scale | `form.targetPages` | `book.target_pages` | `publication_profile.request` (tier from pages + body size) | plan/profile.resolved.yaml |
| 02 資料と追加指示 | URLs / files | `form.urls`, files | `input.urls`, `input/urls.txt`, `input/sources/*` | sources.py | research/ |
| 02 | Additional instructions (本全体への優先指示) | `form.instructions` | `user_instructions`, TASK.md (verbatim) | every agent task (verbatim), chapter packets, plan/user-intent.yaml | gate 22 (docs/USER_INTENT.md) |
| 03 調査と図表の方針 | Research toggles, citation style | `form.research`, `form.citationStyle` | `research`, `citations.style` | research/citations | — |
| 03 | Tables/diagrams/charts/generative images | `form.figures` | `figures` | planning/assets (agent) | assets-plan |
| 04 希望する出力 | Output formats | `form.outputs` | `outputs` | build.py, renderer capability check | publish/* |
| 05 出版形式 (Basic) | Book scale / tier | `publication.tier` | `profile.tier` | publication_profile | profile.resolved.yaml |
| 05 (Basic) | Genre | `publication.genre` | `profile.genre` | profile; LayoutSpec defaults; StyleBible template if no style preset | profile, layout-spec, style-bible |
| 05 (Basic) | Layout preset | `publication.layoutPreset` | `layout_preset` | layout_spec.request | plan/layout-spec.yaml |
| 05 (Basic) | Page size | `publication.pageSize` (+ `design.pageSize` in theme mode) | `layout_spec.page_size` or Design Spec `page.size` | layout_spec.defaults/resolve | layout-spec |
| 05 (Basic) | Columns | `publication.columns` | `layout_spec.body.columns` | layout_spec | layout-spec |
| 05 (Basic) | Figure / table span | `publication.figureSpan/tableSpan` | `layout_spec.span_policy` | figure_spec.auto_span, Typst | layout-spec, PDF |
| 05 (Basic) | Style preset | `publication.stylePreset` | `style_preset` | style_bible.template_genre | plan/style-bible.yaml |
| 05 (Basic) | Writing mode | `publication.writingMode` | `layout_spec.writing_mode` | layout_spec, renderer capability | layout-spec |
| 05 (Advanced) | Margins, gutter | `publication.margins/gutterMm` | `layout_spec.page/body` | layout_spec | layout-spec |
| 05 (Advanced) | Orientation | `publication.orientation` | `layout_spec.orientation` | layout_spec | layout-spec |
| 05 (Advanced) | StyleBible controls ×6 | `publication.styleControls` | `style_controls` | style_bible.apply_controls | style-bible |
| 06 書籍のデザイン | Theme | `design.theme` | Design Spec `theme` | design.load_design (theme.yaml) | design-tokens |
| 06 | Page size (read-only mirror) | `design.pageSize` | Design Spec `page.size` | LayoutSpec defaults, profile chars/page, CSS | layout-spec, CSS |
| 06 (Advanced) | Orientation | `design.orientation` | Design Spec `page.orientation` | LayoutSpec defaults | layout-spec |
| 06 | Density | `design.density` | Design Spec `layout.density` | CSS spacing, profile chars/page | CSS, profile |
| 06 | Accent colour | `design.accent` | Design Spec `colors.accent` | tokens/CSS; StyleBible default palette (then overridden by the genre template) | tokens, style-bible |
| 06 | Fonts, sizes, weights | `design.*` | Design Spec `typography` | tokens; StyleBible type roles are derived from them | tokens, style-bible |
| 06 | Chapter style | `design.chapterStyle` | Design Spec `components.chapter_opener` | Typst themes/CSS; **ignored** by the Modern Technical PDF when the StyleBible title style is set | PDF |
| 06 | Figures / Tables / Callouts style | `design.figureStyle/tableStyle/calloutStyle` | Design Spec `figures.style`, `components.*` | Typst/CSS | PDF, CSS |
| 06 | custom.css | `design.customCss` | `custom.css` | Web/EPUB CSS | site, EPUB |
| 06 | Additional art direction | `design.artDirection` | Design Spec `art_direction` | StyleBible `tone.overall` | style-bible |
| 07 | Runtime | `form.runtimeTarget` | `runtime` | ZIP packaging | runtime/ |

## Phase 2 — Duplicates, single-source-of-truth violations and ambiguous overrides

| # | Problem | Consequence |
|---|---|---|
| V1 | Target scale (01) and tier (05) both expressed "how big is the book". | Two inputs for one decision; tier override silently diverged from the page target that still sized the body text. |
| V2 | Orientation editable in 06 (Design Spec) **and** 05 (LayoutSpec). | In theme mode 05's summary always said portrait even when 06 said landscape (and the job used landscape). |
| V3 | Page size lived in `DesignOptions` and `PublicationOptions`. | Two states for one concept; switching theme silently reset a page size chosen in theme mode. |
| V4 | Density (Design Spec) vs StyleBible `visual_density`. | Two controls for one concept, independent values. |
| V5 | Chapter style (Design Spec) vs StyleBible `chapter_opener`. | The Design Spec choice had no effect on the Modern Technical PDF (StyleBible default won). |
| V6 | Accent colour vs style preset palette. | The user's accent was silently replaced in the PDF whenever a genre/style preset was active. |
| V7 | Font sizes vs StyleBible `typography_scale`. | Two ways to change type size. |
| V8 | Callout style vs `callout_intensity`, table style vs `table_density`. | Different aspects, but presented in different sections without explanation. |
| V9 | Figures in 03 (whether), 05 (span) and 06 (style). | Same word, three meanings, three sections. |
| V10 | Genre, layout preset, style preset, theme and chapter style were five independent presets. | "A medical book" required understanding five preset systems. |
| V11 | Genre → style preset was automatic, theme was not; not explained. | Users could not tell why the PDF colour changed with genre but the theme did not. |
| V12 | Free-text instructions and art direction vs structured settings: no stated precedence. | The agent had to guess. |

## Phase 3 — New Information Architecture

| Section | Basic (always visible) | Advanced |
|---|---|---|
| 01 本の企画 | Title, goal, readers, language, **Target scale** (the only scale input) | Tier override (collapsed; shows the automatic tier) |
| 02 資料と指示 | URLs, files, additional instructions (book-wide priority instruction: wins over BookOrder defaults; structured settings win for their own fields) | — |
| 03 調査とコンテンツの方針 | Research toggles, citation style; Visual content = *whether* tables/diagrams/charts/images may be made | — |
| 04 希望する出力 | Output formats (unchanged) | — |
| 05 出版形式とデザイン | **Publication preset** (bundle), Genre, Theme, Layout, Page size, Columns, theme samples | **Geometry**: custom size, orientation, margins, gutter, figure/table span, writing mode · **Typography**: fonts, sizes, weights · **Visual grammar**: PDF style preset, density, accent, chapter opener, figures, tables (rules + row density), callouts (frame + emphasis) · **Expert**: visual tone, art direction, custom.css |
| 06 Agentが実行する環境 | Runtime (unchanged) | — |

Right-hand sticky aside in 05: format summary (preset, layout, columns, body, margins, spans, theme + accent,
typography, genre, tier, PDF style, outputs), the schematic page preview and the theme's sample page.

Roles stated in the UI: **Genre** = kind of content (structure, device density) · **Layout** = page size, columns,
margins · **Theme** = typefaces, colour, component look.

## Phase 4 — Migration / compatibility plan

* project.json: unchanged keys and meaning (`profile`, `layout_preset`, `layout_spec`, `style_preset`, `style_controls`).
  One previously unused-by-the-UI key, `style_bible`, is now written **only** when the user explicitly changes the
  accent colour (the resolver already supported it). Untouched Basic produces the same project.json and
  book.design.yaml as before (`tests/fixtures/webui-compat/*.json`, recorded from the previous WebUI).
* Design Spec: `page.size/orientation` are still written; they are derived from `PublicationOptions`
  (`publication.designPage`). A page size chosen while the layout follows the theme still goes to
  `book.design.yaml` exactly as before (no `layout_spec`).
* WebUI state: `DesignOptions.pageSize/orientation` were removed; `PublicationOptions.pageSize/orientation` accept
  the sentinel `'theme'` (= follow the theme). `publicationPreset` was added (UI-only; not written to project.json).
* Linked visual settings (density, chapter opener, accent): the Design Spec value is the authority; when it differs
  from the theme default the matching StyleBible request is derived (`publication.designStyleLinks`). Never both
  controls.
* Removed from the UI but still accepted by the resolvers for hand-written jobs: `style_controls.visual_density`,
  `style_controls.chapter_opener` (both now derived), `style_controls.typography_scale` (use the font sizes).
* The tier rule (pages → tier) moved from two Python constants to `schemas/publication-presets.json`
  (`tier_from_pages`), read by `publication_profile.py`, `pacing.py` and the WebUI.

## Resolution order (code: `src/publication.ts` header; Python resolvers)

1. **Layout** — theme page/margins (Design Spec) < layout preset (`layout_preset`) < explicit geometry edits (`layout_spec`).
2. **Scale** — Target scale → automatic tier (shared rule) < explicit tier (`profile.tier`).
3. **PDF appearance** — theme tokens < style template (`style_preset`, else genre) < profile art direction <
   `style_controls` (including values derived from explicit Visual grammar edits) < `style_bible` (explicit accent).
4. **Publication preset** — fills genre + layout preset + style preset + theme once; every later edit wins and the
   preset is shown as "変更あり".
5. **Free text** — the additional instructions are authoritative for the editorial and semantic choices they state
   (voice, density, scope, structure, apparatus) over genre/tier defaults and Skill heuristics; a structured setting
   stays authoritative for the field it represents (A5 selected + "A4 please" → A5), and invariants (citations,
   facts, build) are never waived. Conflicts are recorded in plan/user-intent.yaml and reported (TASK.md "Precedence
   of settings", [USER_INTENT.md](USER_INTENT.md)).

## Settings: before → after

| Before | After |
|---|---|
| 01 Target scale | 01 Target scale (unchanged; sole scale input) |
| 05 Book scale / tier | 01 › Advanced · tier override (default Automatic → shows the derived tier) |
| 05 Genre | 05 Basic Genre |
| 05 Layout preset (cards) | 05 Basic Layout (select) — or set by a Publication preset |
| 05 Page size / 06 Page size (read-only) | 05 Basic Page size (only control; "Theme default · A5" option) |
| 05 Advanced Orientation / 06 Advanced Orientation | 05 Geometry Orientation (only control) |
| 05 Columns | 05 Basic Columns |
| 05 Figures / Tables span | 05 Geometry Figure span / Table span |
| 05 Writing mode | 05 Geometry Writing mode |
| 05 Advanced margins / gutter / custom size | 05 Geometry |
| 05 Style preset | 05 Visual grammar · PDF style preset (Automatic → from genre) |
| 05 StyleBible: visual density | merged into Visual grammar · Density (derived) |
| 05 StyleBible: chapter opener | merged into Visual grammar · Chapter opener (derived) |
| 05 StyleBible: typography scale | removed from UI (Typography sizes; resolver still accepts it) |
| 05 StyleBible: table density / callout intensity | Visual grammar · Tables › Row density, Callouts › Emphasis |
| 05 StyleBible: visual tone | Expert · Visual tone |
| 06 Theme | 05 Basic Theme (also set by a Publication preset) |
| 06 Fonts, sizes, weights | 05 Typography |
| 06 Density, accent, chapter style, figure/table/callout style | 05 Visual grammar |
| 06 custom.css, art direction | 05 Expert |
| — | 05 Basic Publication preset (new bundle) |

## Single sources of truth

| Concept | Authority | Derived copies |
|---|---|---|
| Book scale | `book.target_pages` (Target scale) | tier via `tier_from_pages` unless `profile.tier` is set |
| Page size, orientation | `PublicationOptions.pageSize/orientation` | Design Spec `page` (`designPage`), `layout_spec` |
| Geometry (margins, columns, gutter, spans) | LayoutSpec request (`layout_preset` + `layout_spec`) | — |
| Theme, fonts, component treatments | Design Spec | StyleBible type roles (resolver) |
| Density, chapter opener, accent | Design Spec value | `style_controls.visual_density/chapter_opener`, `style_bible.palette.accent` when changed |
| PDF semantic style | `style_preset` (else genre template) + `style_controls` | plan/style-bible.yaml |
| Preset catalogues, page sizes, limits, tier rule | `job-template/schemas/publication-presets.json` | WebUI and Python both read it |

## Known constraints

* Only the Modern Technical Typst theme consumes the full StyleBible. With the other themes (including Medical
  Textbook, selected by the Medical / Scientific preset) the PDF takes from the StyleBible only: the palette mapped
  onto the theme colours (`text`, `muted`, `primary`←secondary_accent, `secondary`←surface, `accent`, `surface`),
  diagram grammar and palette (diagrams.py), chart grammar and print tokens (figure_spec/chartkit) and numeric table
  alignment (Typst renderer). **Not applied**: StyleBible type sizes (heading_1–3, chapter number, caption, table,
  callout), line weights, spacing scale and section spacing (`visual_grammar.rhythm`), `chapter_opener.title_style`,
  table grammar (row spacing, header emphasis, border density, zebra — e.g. Medical Evidence's compact rows and strong
  header rule), component treatments (e.g. Medical Evidence's filled-box warning, side-rule key point, quiet
  definition), caption relationship/weight, the warning/success colours, and the narrow-column type adjustments.
  Consequently the WebUI controls marked "(PDF)" (table row density, callout emphasis) and visual tone have no
  visible PDF effect with those themes; the Visual grammar tab says so when such a theme is selected. Note also that
  `secondary`←surface makes the theme's rule colour very light under a StyleBible palette (pre-existing mapping).
* The live summary and schematic preview are estimates computed from the shared presets; the resolver re-validates
  (`bookorder publication`).
* Changing the theme (directly or through a publication preset) replaces only the design values still at the old
  theme's defaults; values the user changed (accent, fonts, sizes, density, components, CSS, art direction) are kept
  (`design.switchTheme`), as are all layout and publication settings. There is no one-click "reset to theme defaults".
* The summary's accent shows the colour the PDF will use (explicit accent > style template palette > theme) and the
  Web/EPUB accent when they differ (HTML/EPUB never use the StyleBible palette).
* HTML/EPUB/DOCX stay single-column; vertical writing is not available.
* `tests/ui_interaction.py` needs Playwright + Chromium; it bundles `src/` with `tools/ui-bundle.cjs` instead of vite.

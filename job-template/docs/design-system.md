# BookOrder design system

Content and presentation are separate. `source/` remains the editable canonical book; theme changes do not rewrite prose.

| Layer | Responsibility |
| --- | --- |
| Book IR | Pandoc AST, 24 semantic component types plus numbered equations, and a cross-reference registry (chapters, sections, figures, tables, equations), exported as interchange/book-ir.json. No backend markup. |
| Design Spec | book.design.yaml: page, role fonts, colors, spacing and component variants. schemas/design.schema.json rejects unknown values. |
| Tokens | interchange/design-tokens.json: merged settings, font resolution and spacing shared by CSS, Typst and DOCX. |
| Theme | themes/name/: theme.yaml, preview.png, CSS modules and typst/theme.typ. Themes are discovered from the folder; none are hard-coded. |
| Renderer | scripts/renderers/: PDF interface and Typst adapter. Backend markup is introduced only in the adapter. |

## Commands

Windows uses `bookorder.cmd`; macOS/Linux uses `sh bookorder`. Without bundled tools use `python scripts/cli.py` with the same arguments.

```text
bookorder.cmd fonts
bookorder.cmd theme list
bookorder.cmd theme preview modern-technical
bookorder.cmd build --theme medical-textbook
```

Preview writes HTML, PDF, DOCX and EPUB under `.previews/<theme>/`, using a dedicated sample without editing canonical chapters. Normal builds write interchange/ and publish/. After inspection run the usual validate and package actions.

The packages are modern-technical (restrained teal, editorial chapter openers; the default), academic-jp (centered academic openers, grid tables), medical-textbook (green, spacious, card callouts), minimal-monochrome (monochrome figures, minimal openers) and business-reference (B5, sans-serif body, navy/orange, striped tables). --theme changes package defaults while retaining overrides that differ from the previous theme, and saves the selected spec so result.zip remains reproducible. For a clean switch retain only `theme: name` in the spec. Git theme installation is not implemented; complete theme directories can be added under themes/ without modifying core.

## Settings and fonts

JSON is valid YAML and is emitted by the GUI. Partial settings merge with theme defaults:

```yaml
theme: modern-technical
typography:
  body:
    japanese: Yu Mincho
    latin: Georgia
    size: 10pt
  heading:
    japanese: Yu Gothic
    latin: Arial
    weight: 700
colors:
  accent: '#0891B2'
```

Body, heading, code, caption and footnote are independent. `family` replaces a role's Japanese/Latin pair. Run fonts on the execution machine; unavailable fonts resolve through each role's fallback list, recorded in reports/design-report.json. Character coverage still needs visual QA. Typst embeds used PDF fonts. DOCX does not embed fonts; browser/EPUB/Word availability differs.

Bundled fonts (runtime packs, SIL Open Font License 1.1, licences in third-party/licenses/): Noto Serif CJK JP (Regular/Bold), Noto Sans JP (Regular/Bold), Source Serif 4 (Regular/Italic/Semibold/Bold), Inter (Regular/Italic/Medium/SemiBold/Bold) and JetBrains Mono (Regular/Italic/Bold). The default pairing is Source Serif 4 + Noto Serif CJK JP for body, Inter + Noto Sans JP for headings and captions, JetBrains Mono for code. Typst's embedded New Computer Modern Math sets equations. When a theme uses the Latin fonts, the static site ships them (with their OFL licence) as web fonts; CJK fonts are not shipped to the web because of their size, so web readers use local Japanese fonts. Font binaries are never stored in the repository; tools/prepare-runtimes.py downloads pinned upstream releases and verifies SHA-256 locks.

Screen text has a readable minimum size; print/PDF uses specified points. The website follows the reader's dark-mode preference (screen only; print and EPUB keep the book palette). EPUB readers can override layout. custom.css loads last in HTML/Web and the flattened EPUB stylesheet. custom.typ follows theme styles for PDF overrides. Prefer shared settings in Design Spec. Overrides are user-authored code: CSS URLs can fetch external resources; Typst code runs through the compiler. Review overrides before use.

## Components

Use Pandoc fenced divs with optional stable ID/title:

```markdown
::: {.warning #warn-evaluation title="評価の限界"}
この方法だけで個人を評価してはいけない。
:::
```

schemas/components.json lists chapter-opener, section-opener, lead, key-point, note, tip, warning, definition, example, exercise, summary, checklist, quote, pull-quote, sidebar, step-by-step, code-listing, terminal-session, comparison, timeline, figure, full-width-figure, table and glossary-term. HTML/EPUB retains classes, DOCX named paragraph styles, PDF theme components. Ordinary prose remains primary.

## Diagrams

Save Diagram IR in source/assets/diagrams/name.yaml. The corresponding SVG is generated under source/assets/figures/. Reference the SVG in Markdown and register it with ID/caption in figures.yaml.

```yaml
type: flow
title: 評価による行動強化
nodes:
  - {id: action, label: 行動}
  - {id: evaluation, label: 外部評価}
  - {id: reward, label: 報酬感}
edges:
  - {from: action, to: evaluation}
  - {from: evaluation, to: reward}
```

Nine types: flow, concept-map, hierarchy, timeline, comparison, cycle, process, network, matrix. Schema validates IDs/labels/endpoints. Small layouts support up to 12 nodes/40 edges; dense networks require visual QA or authored SVG. Hierarchies reject cycles. Comparison/matrix use a grid arrangement. Sequential types can infer edges. Colors/fonts/line weight/numbering use shared tokens. PDF/Web uses SVG; DOCX/EPUB uses a local Typst-rendered PNG fallback. Preserve editable Diagram IR.

## Migration and QA

Plain Markdown remains valid. Old technical-book assets remain as reference; builds now use the design system. Move book.font preferences into typography.body. Do not edit generated PDFs or .build/ as design sources.

The fixture covers long headings/URLs, Japanese/English, code/terminal, components, tables, SVG, footnotes and references. Inspect all preview pages and representative actual pages. Validation checks structure/freshness, not commercial print certification. PDF/X, CMYK, vertical writing, IDML and alternate PDF backends are outside this implementation; a future backend implements the renderer interface without changing IR.

## Numbering, cross references and math

Chapters, sections (n.m), figures, tables and equations (per chapter) are numbered from document order at render time. Canonical text uses `@ch:`, `@sec:`, `@fig:`, `@tbl:`, `@eq:`; labels are localized (図3.1 / Figure 3.1, 表3.1, 式(3.1), 第3章, 3.2節). Equations are LaTeX in Pandoc Markdown and stay text/vector: native Typst math in PDF, MathML in HTML/EPUB, OMML in DOCX.

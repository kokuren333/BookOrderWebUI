# LayoutSpec (P1-0)

`plan/layout-spec.yaml` is the resolved geometry and writing-flow artifact. The first build creates it from the PublicationProfile genre and the existing Design Spec page settings. Thereafter the file is the authority for paper size, margins, columns, spans, and writing mode. Its parsed semantic content participates in the job fingerprint; changing comments, YAML whitespace, or a generated timestamp does not invalidate downstream output.

The PublicationProfile describes editorial scale and density. The LayoutSpec describes page use. The future StyleBible may style the resulting regions, but should not own the page geometry, column count, or writing mode. The Typst renderer receives the LayoutSpec explicitly and bridges its page values into the existing design tokens for P0 consumers.

## Current PDF support

| LayoutSpec choice | Typst/PDF behavior |
|---|---|
| `horizontal-tb`, one column | Existing A5/other paper path, unchanged |
| `horizontal-tb`, two columns | Body flows in two Typst page columns with configured gutter |
| Figure/table/callout span 1 | Stays in a column |
| Figure/table/callout span 2 or full | Parent-scoped float across the body width |
| Chapter opener | Full body width at the top of its chapter |
| `vertical-rl` | Explicit unsupported result and build error |
| Three or more columns | Schema admits the future value; Typst adapter rejects it |
| Margin notes, nonzero bleed, baseline grid, column balance | Explicit unsupported result |

For figures, the `column` placement resolves to `(body width - gutter) / 2` in two-column mode. Span 2 resolves to the full body width. `full-width` placement and `span: full` resolve to the body width in two-column mode; the one-column legacy `full-width` margin reach remains intact. `margin`, `full-page`, and `spread` placement names remain valid. The figure check uses the resolved printed width before rendering and still blocks text under 6.5 pt.

`spans.figure`, `spans.table`, and `spans.callout` set defaults. An asset's `geometry.span` can override its figure or table span; a callout's `span` attribute can override the default. A long displayed equation can overflow a narrow column, so the Typst adapter rejects one above its conservative source-length threshold and asks for a shorter equation or one-column layout. Multi-column equation spans remain unsupported.

HTML, EPUB, and DOCX report `degraded` for two-column/span geometry because they currently retain their existing single-column output. The capability report is `reports/layout-capabilities.json`; unsupported PDF layout choices stop the build.

## Measurement boundary

`reports/layout-metrics.json` includes physical `x` and `y`, a column number per element, its declared span/region and figure geometry, plus a `columns` list per page. The page-level text-only decision uses physical pause extents in two-column mode, so a full-span figure or substantial callout interrupts a text wall. One-column metrics retain their P0 method. Two-column `areas_pt`, prose character distribution, and `nonprose_share` remain **approximate** because the vertical segmenter does not yet reconstruct parallel column flows; `area_accuracy: approximate` marks that limit. Column-level wall detection is future work.

## Development specimen

Run `python tools/layout-specimen.py` in a publishing job with Typst available. It writes `.build/layout-specimen.typ` and `publish/layout-specimen.pdf`, showing one- and two-column body text, span 1 and span 2 figures, a full-width figure/table, a full-width callout, and a chapter opener. The last page states that vertical writing is unsupported.

Typst supports page columns and parent-scoped floats for content across them; see the [Typst columns reference](https://typst.app/docs/reference/layout/columns/) and [page setup guide](https://typst.app/docs/guides/page-setup/). Vertical writing is still tracked in an open [Typst RFC](https://github.com/typst/typst/issues/5908), so this adapter does not simulate it.

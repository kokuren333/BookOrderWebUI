# Publication QA

BookOrder runs structural validation itself (reports/validation-report.json): chapters and metadata, stable IDs,
cross references, citations, local assets, HTML links/anchors, EPUB container/manifest/links, DOCX styles, output
freshness. It then evaluates the publication gates (reports/completion-gates.json). Your part is visual and
editorial inspection that programs cannot do.

- PDF: page overflow, table widths, figure size and captions, code wrapping, heading hierarchy, footnotes, blank
  pages, page breaks, running heads, folios, equation numbers, bibliography. Look at several representative
  pages at real size and every complex figure/table.
- Website: contents page, previous/next links, cross-chapter links, images, equations, footnotes/citations, local
  search, mobile width, keyboard navigation, dark mode.
- DOCX: distinct reusable paragraph styles (Book/Chapter/Section titles, Body, Block Quote, Code Block, Figure and
  Table Caption, Bibliography, component styles, Equation) and native equations.
- EPUB: navigation, reflow, MathML equations; run epubcheck if installed.

Record actual evidence and limitations in reports/layout-review.md. A build that succeeds is not a publication
that is finished: only `bookorder goal` reporting `STATUS: COMPLETE` is.

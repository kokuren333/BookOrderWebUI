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

- User intent: check the rendered book against the user's instructions (voice and structure as asked, requested
  figures present, excluded apparatus absent, structured format kept) and add a `## User intent` section to
  reports/layout-review.md with what you checked and any conflict.

- Publication architecture: read reports/publication-architecture-qa.yaml (gate 23) and look for it in the
  rendered book — chapters shaped by their content rather than one template, no mechanical chapter-end apparatus,
  exercises only where the architecture wants them and always with answers, varied visual types, uploaded images
  where the user asked, the citation form and the separate 引用文献 / 参考資料 / 図表・画像出典 lists configured in
  project.json (reports/bibliography.json).

Record actual evidence and limitations in reports/layout-review.md. A build that succeeds is not a publication
that is finished: only `bookorder goal` reporting `STATUS: COMPLETE` is.

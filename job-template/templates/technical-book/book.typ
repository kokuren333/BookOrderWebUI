// Used as a Pandoc Typst header include. Editable conservative technical-book layout.
#set page(paper: "a5", margin: (inside: 22mm, outside: 18mm, top: 22mm, bottom: 22mm), numbering: "1")
#set par(justify: true, leading: 0.7em)
#set text(size: 10pt)
#show heading.where(level: 1): it => {
  pagebreak(weak: true)
  block(above: 1.4em, below: 1em, text(size: 19pt, weight: "bold", it))
}
#show raw.where(block: true): it => block(width: 100%, fill: luma(96%), inset: 8pt, radius: 2pt, it)
#show quote.where(block: true): it => block(inset: (left: 12pt, right: 12pt), stroke: (left: 1pt + luma(65%)), it)
#show figure: it => block(breakable: false, it)

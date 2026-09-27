// Pandoc's Typst template calls this function around the complete document.
#let conf(
  title: none, subtitle: none, authors: (), date: none,
  lang: "en", region: none, abstract-title: none, abstract: none, thanks: none,
  margin: (inside: 22mm, outside: 18mm, top: 22mm, bottom: 22mm),
  paper: "a5", font: ("Libertinus Serif",), fontsize: 10pt,
  mathfont: (), codefont: (), linestretch: 1.4,
  sectionnumbering: "1.1", pagenumbering: "1", linkcolor: none,
  citecolor: none, filecolor: none, cols: 1, doc,
) = {
  set text(font: font, size: fontsize, lang: lang)
  set page(paper: paper, margin: margin, numbering: none, header: none)
  set heading(numbering: sectionnumbering)
  set par(justify: true, leading: 0.7em)
  align(center + horizon)[
    #text(size: 25pt, weight: "bold", title)
    #if subtitle != none { v(1em); subtitle }
    #v(2em)
    #for author in authors { author.name; linebreak() }
    #if date != none { v(1em); date }
  ]
  pagebreak()
  set page(numbering: pagenumbering, header: align(right, text(size: 8pt, title)))
  show outline: it => { it; pagebreak(weak: true) }
  doc
}

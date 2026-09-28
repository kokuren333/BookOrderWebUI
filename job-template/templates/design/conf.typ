// Page template: title page, running heads, folios and contents. Values come from design tokens.
#let conf(title: none, subtitle: none, authors: (), keywords: (), date: none,
  lang: "ja", region: none, abstract-title: none, abstract: none, thanks: none,
  margin: none, paper: "a5", font: none, fontsize: 10pt, mathfont: none, codefont: none,
  linestretch: 1.4, sectionnumbering: none, pagenumbering: "1", linkcolor: none,
  citecolor: none, filecolor: none, cols: 1, doc) = {
  let d = json("design-tokens.json")
  let c(name) = rgb(d.colors.at(name))
  let caption-face = d.typography.caption.resolved_families
  let heading-face = d.typography.heading.resolved_families
  let book-chapter = state("book-chapter", (number: "", label: ""))
  let book-main = state("book-main", false)
  set document(title: title)
  set text(lang: lang)
  let preview = json("../project.json").book.at("preview", default: false)
  let cover = d.at("cover", default: none)
  let run-head = context {
    let page-number = here().page()
    let chapters = query(heading.where(level: 1, outlined: true))
    if chapters.any(h => h.location().page() == page-number) { return }
    let before = chapters.filter(h => h.location().page() < page-number)
    if before.len() == 0 or not book-main.get() { return }
    let current = before.last()
    let chapter = book-chapter.at(current.location())
    set text(font: caption-face, size: 7pt, fill: c("muted"), tracking: .3pt)
    let left-page = calc.even(counter(page).get().first())
    block(width: 100%, below: 0pt, {
      if left-page { align(left, title) } else { align(right, [#chapter.label#h(.8em)#current.body]) }
      v(-2.5pt)
      line(length: 100%, stroke: .3pt + c("secondary").darken(10%))
    })
  }
  let folio = context {
    let main = book-main.get()
    let n = counter(page).get().first()
    set text(font: caption-face, size: 7.5pt, fill: c("muted"))
    let label = if main { str(n) } else { numbering("i", n) }
    align(if calc.even(n) { left } else { right }, label)
  }
  let papers = (A5: "a5", A4: "a4", B5: "iso-b5", B6: "iso-b6", Letter: "us-letter")
  // Named sizes keep Typst's paper path; LayoutSpec custom sizes use their resolved millimetres.
  let page-dims = if d.page.size in papers { (paper: papers.at(d.page.size), flipped: d.page.orientation == "landscape") } else { (width: d.page.width_mm * 1mm, height: d.page.height_mm * 1mm) }
  set page(..page-dims,
    margin: (top: eval(d.page.margin.top), bottom: eval(d.page.margin.bottom),
      inside: eval(d.page.margin.inner), outside: eval(d.page.margin.outer)), numbering: none, header: none, footer: none)
  if not preview {
    // Title page
    page(margin: (x: 18mm, top: 24mm, bottom: 18mm))[
      #if cover != none { place(top + left, dx: -18mm, dy: -24mm, image("/" + cover, width: 100% + 36mm, height: 100% + 42mm, fit: "cover")) }
      #block(width: 100%, height: 100%)[
        #rect(width: 14mm, height: 1.4mm, fill: c("accent"), stroke: none)
        #v(14mm)
        #set par(justify: false, first-line-indent: 0pt)
        #text(font: heading-face, size: 25pt, weight: 700, fill: c("primary"), hyphenate: false, title)
        #if subtitle != none { v(5mm); text(font: heading-face, size: 12pt, fill: c("text"), subtitle) }
        #v(1fr)
        #line(length: 100%, stroke: .4pt + c("secondary").darken(10%))
        #v(3mm)
        #set text(font: caption-face, size: 9pt, fill: c("muted"))
        #for author in authors { author.name; linebreak() }
        #if date != none { date }
      ]
    ]
  }
  set page(header: if d.layout_spec.regions.header.enabled { run-head } else { none },
    footer: if d.layout_spec.regions.footer.enabled { folio } else { none }, numbering: "1")
  set page(columns: d.layout_spec.body.columns)
  set columns(gutter: d.layout_spec.body.gutter_mm * 1mm)
  show outline: set par(first-line-indent: 0pt, justify: false)
  show outline.entry.where(level: 1): it => {
    v(.9em, weak: true)
    let chapter = book-chapter.at(it.element.location())
    link(it.element.location(), grid(columns: (auto, 1fr, auto), column-gutter: .7em,
      text(font: heading-face, size: .95em, weight: 700, fill: c("accent"), chapter.label),
      text(font: heading-face, weight: 700, it.element.body),
      text(font: heading-face, weight: 700, it.page())))
  }
  show outline.entry.where(level: 2): it => {
    set text(size: .92em)
    it
  }
  show outline: it => { it; pagebreak(weak: true) }
  doc
}

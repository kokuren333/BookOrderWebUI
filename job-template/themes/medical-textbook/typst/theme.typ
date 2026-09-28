// BookOrder Typst theme. Every value comes from normalized design tokens (design-tokens.json);
// themes differ through theme.yaml, not through copies of this logic.
#let d = json("design-tokens.json")
#let color(name) = rgb(d.colors.at(name))
#let face(role) = d.typography.at(role).resolved_families
#let size(role) = eval(d.typography.at(role).size)
#let weight(role) = d.typography.at(role).weight
#let comp = d.components
#let mono = d.figures.style == "monochrome"
#let book-chapter = state("book-chapter", (number: "", label: ""))
#let book-main = state("book-main", false)

// Emitted just before each chapter heading: the page break happens here so the heading (and its TOC entry)
// is located on the chapter's first page; main-matter folios restart at chapter 1.
#let book-chapter-mark(number, label) = {
  pagebreak(weak: true)
  book-chapter.update((number: number, label: label))
  context if number == "1" and not book-main.get() { counter(page).update(1) }
  book-main.update(true)
}
#let book-secnum(n) = text(fill: color("primary"), weight: weight("heading"), n)

#set text(font: face("body"), size: size("body"), fill: color("text"), weight: weight("body"), hyphenate: auto)
#set par(justify: true, leading: (d.typography.body.line_height - 1) * size("body"),
  spacing: (small: .45em, medium: .8em, large: 1.2em).at(d.layout.paragraph_spacing) * d.spacing.md)
#set par(first-line-indent: if d.at("language", default: "en") in ("ja", "zh") { (amount: 1em, all: true) } else { 0pt })
#set list(indent: .4em, body-indent: .6em, marker: (text(fill: color("primary"), sym.bullet), text(fill: color("muted"), sym.dash.en)))
#set enum(indent: .4em, body-indent: .6em, numbering: n => text(fill: color("primary"), weight: weight("heading"), font: face("heading"), str(n) + "."))
#set terms(separator: [ --- ], hanging-indent: 1.2em)
#show link: set text(fill: color("primary"))
#show strong: set text(weight: calc.max(600, weight("body") + 300))
#show math.equation: set text(font: ("New Computer Modern Math",) + face("body"))

// ---------------------------------------------------------------- headings
#let heading-space = (compact: 1.1em, standard: 1.6em, generous: 2.1em).at(d.layout.heading_spacing)
#show heading: set text(font: face("heading"), weight: weight("heading"), fill: color("text"), hyphenate: false)
#show heading: set par(justify: false, first-line-indent: 0pt)
#show heading.where(level: 1): it => {
  if not it.outlined {
    // Front-matter titles such as the table of contents.
    pagebreak(weak: true)
    v(10mm)
    block(below: 9mm, text(size: 1.25 * size("heading"), fill: color("primary"), it.body))
    return
  }
  pagebreak(weak: true)
  let style = comp.chapter_opener
  context {
    let chapter = book-chapter.get()
    let n = chapter.number
    if style == "editorial" {
      v(14mm)
      block(width: 100%, below: 0pt)[
        #grid(columns: (1fr, auto), align: (left + bottom, right + bottom),
          text(font: face("heading"), size: 7.5pt, tracking: 2.2pt, weight: 600, fill: color("accent"), "CHAPTER"),
          text(font: face("heading"), size: 3.4 * size("heading"), weight: 700, fill: if mono { luma(210) } else { color("secondary").darken(8%) },
            if n.len() == 1 { "0" + n } else { n }))
      ]
      line(length: 100%, stroke: .6pt + color("primary"))
      v(5mm)
      block(below: 4mm, text(size: 1.18 * size("heading"), weight: weight("heading"), fill: color("text"), it.body))
      line(length: 16mm, stroke: 2pt + color("accent"))
      v(9mm)
    } else if style == "academic" {
      v(20mm)
      align(center, block(below: 12mm)[
        #text(size: 10pt, fill: color("muted"), tracking: 1pt, chapter.label)
        #v(5mm)
        #text(size: 1.15 * size("heading"), weight: weight("heading"), it.body)
        #v(5mm)
        #line(length: 12mm, stroke: .6pt + color("muted"))
      ])
    } else {
      v(8mm)
      block(below: 8mm, width: 100%, stroke: (bottom: .5pt + color("text")), inset: (bottom: 3mm),
        par(hanging-indent: 0pt, text(size: 1.2 * size("heading"), weight: weight("heading"))[#text(fill: color("primary"), n)#h(.6em)#it.body]))
    }
  }
}
#show heading.where(level: 2): it => block(above: heading-space, below: .75em, sticky: true, breakable: false,
  text(size: .74 * size("heading"), it.body))
#show heading.where(level: 3): it => block(above: 1.35em, below: .55em, sticky: true,
  text(size: 1.1 * size("body"), fill: color("primary"), it.body))
#show heading.where(level: 4): it => block(above: 1.1em, below: .45em, sticky: true, text(size: size("body"), it.body))

// ---------------------------------------------------------------- code
#show raw: set text(font: face("code"), size: size("code"), weight: weight("code"))
#show raw.where(block: false): it => box(fill: color("surface"), inset: (x: 2.5pt), outset: (y: 2pt), radius: 1.5pt, it)
#show raw.where(block: true): it => block(width: 100%, inset: (x: 9pt, y: 8pt), breakable: true,
  fill: if comp.code_block == "technical" { color("surface") } else { none },
  stroke: if comp.code_block == "technical" { (left: 1.6pt + color("primary").lighten(35%)) } else { (y: .4pt + color("secondary")) },
  { set par(justify: false, first-line-indent: 0pt, leading: (d.typography.code.line_height - 1) * size("code")); it })

// ---------------------------------------------------------------- figures, tables, captions
#set figure(numbering: none, gap: 8pt)
#show figure: set block(above: 1.6em, below: 1.6em, breakable: false)
#show figure.where(kind: table): set block(breakable: true)
#show figure.caption: it => {
  set par(justify: false, leading: (d.typography.caption.line_height - 1) * size("caption"))
  let body = text(font: face("caption"), size: size("caption"), weight: weight("caption"), fill: color("muted"), it.body)
  if comp.figure_caption == "editorial" { block(width: 100%, inset: (top: 4pt), stroke: (top: .4pt + color("secondary")), align(left, body)) }
  else { block(width: 100%, align(left, body)) }
}
#let caption-label(body) = text(fill: color("primary"), weight: 700, body)
#show table: set text(size: .92 * size("body"))
#show table: set par(justify: false)
#show table.cell.where(y: 0): set text(font: face("heading"), weight: weight("heading"), fill: if comp.table == "striped" { white } else { color("text") })
#set table(
  inset: (x: 6pt, y: 5pt),
  stroke: (x, y) => if comp.table == "grid" { .4pt + color("secondary").darken(10%) }
    else if comp.table == "striped" { none }
    else if y == 0 { (top: 1.1pt + color("primary"), bottom: .6pt + color("primary")) }
    else { (bottom: .35pt + color("secondary").darken(6%)) },
  fill: (x, y) => if comp.table == "striped" { if y == 0 { color("primary") } else if calc.even(y) { color("surface") } else { none } }
    else if comp.table == "grid" and y == 0 { color("surface") } else { none },
)

// ---------------------------------------------------------------- quotes, footnotes
#show quote.where(block: true): it => block(inset: (left: 12pt, right: 8pt, y: 4pt), stroke: (left: 1.2pt + color("secondary").darken(10%)),
  text(fill: color("text").lighten(15%), it.body))
#set footnote.entry(separator: line(length: 22%, stroke: .4pt + color("muted")), gap: .5em, indent: 0pt)
#show footnote.entry: set text(font: face("footnote"), size: size("footnote"), weight: weight("footnote"))
#show footnote.entry: set par(leading: (d.typography.footnote.line_height - 1) * size("footnote"), justify: false)

// ---------------------------------------------------------------- semantic components
#let labels-ja = ("warning": "注意", "note": "補足", "tip": "ヒント", "definition": "定義", "key-point": "要点", "example": "例",
  "exercise": "演習", "summary": "まとめ", "checklist": "確認事項", "sidebar": "コラム", "case-study": "事例", "counterpoint": "反論・別解釈", "step-by-step": "手順", "terminal-session": "端末", "code-listing": "コード")
#let labels-en = ("warning": "Warning", "note": "Note", "tip": "Tip", "definition": "Definition", "key-point": "Key point", "example": "Example",
  "exercise": "Exercise", "summary": "Summary", "checklist": "Checklist", "sidebar": "Sidebar", "case-study": "Case study", "counterpoint": "Counterpoint", "step-by-step": "Steps", "terminal-session": "Terminal", "code-listing": "Code")
#let book-component(kind, title: "", body) = context {
  set par(first-line-indent: 0pt)
  let labels = if text.lang == "ja" { labels-ja } else { labels-en }
  let label = if title != "" { title } else { labels.at(kind, default: "") }
  let plain = kind in ("chapter-opener", "section-opener", "lead", "figure", "full-width-figure", "table", "glossary-term", "comparison", "code-listing", "terminal-session", "quote")
  let accent = if kind == "warning" { color("accent") } else { color("primary") }
  if kind == "lead" {
    block(above: .4em, below: 1.2em, text(size: 1.08 * size("body"), fill: color("text").lighten(8%), body))
    return
  }
  if kind == "pull-quote" {
    block(width: 100%, above: 1.2em, below: 1.2em, inset: (x: 8%, y: 6pt), stroke: (y: .5pt + color("secondary").darken(10%)),
      align(center, text(font: face("heading"), size: 1.12 * size("body"), fill: color("primary"), body)))
    return
  }
  if kind == "key-point" {
    block(width: 100%, above: 1.1em, below: 1.1em, inset: (x: 10pt, y: 9pt), fill: color("surface"),
      stroke: (left: 2.4pt + color("primary")), breakable: true)[
      #text(font: face("heading"), size: .82 * size("body"), weight: 700, fill: color("primary"), tracking: .4pt, label)
      #v(3pt, weak: true)
      #text(weight: calc.min(700, weight("body") + 100), body)
    ]
    return
  }
  let fill = if kind == "summary" and comp.summary == "shaded" or kind == "warning" and comp.warning != "plain" or not plain and comp.callout == "card" { color("surface") } else { none }
  let stroke = if plain { none }
    else if kind == "warning" and comp.warning == "plain" { none }
    else if kind == "warning" and comp.warning == "boxed" { .6pt + color("accent") }
    else if kind == "warning" { (left: 2.4pt + color("accent")) }
    else if kind == "definition" and comp.definition == "boxed" { .5pt + color("secondary").darken(12%) }
    else if kind == "definition" { none }
    else if comp.callout == "plain" { none }
    else if comp.callout == "card" { none }
    else { (left: 1.4pt + color("secondary").darken(15%)) }
  block(width: 100%, above: 1em, below: 1em, inset: if plain { 0pt } else { (x: 10pt, y: 8pt) }, fill: fill, stroke: stroke,
    radius: if comp.callout == "card" and not plain { 2pt } else { 0pt }, breakable: true)[
    #if label != "" and not plain {
      block(sticky: true, below: 5pt, text(font: face("heading"), size: .8 * size("body"), weight: 700, tracking: .4pt, fill: accent, label))
    }
    #if kind == "terminal-session" {
      show raw.where(block: true): it => block(width: 100%, inset: 9pt, fill: color("text"), breakable: true, text(fill: white, font: face("code"), size: size("code"), it.text))
      body
    } else { body }
  ]
}

// Numbered display equation: the equation stays native Typst math; the number is set in the margin column.
#let book-equation(number: "", body) = block(width: 100%, above: 1em, below: 1em, breakable: false,
  grid(columns: (1fr, auto), align: (center + horizon, right + horizon), column-gutter: 6pt,
    body, if number != "" { text(font: face("body"), size: .95 * size("body"), "(" + number + ")") }))

#let book-bibliography(body) = {
  set text(size: .9 * size("body"))
  set par(justify: false, hanging-indent: 1.4em, leading: .55em, spacing: .7em)
  body
}

#let book-colophon(text-content) = {
  page(numbering: none, header: none, footer: none)[
    #v(1fr)
    #set text(size: 7.5pt, fill: color("muted"))
    #line(length: 30%, stroke: .4pt + color("muted"))
    #v(2mm)
    #text-content
  ]
}

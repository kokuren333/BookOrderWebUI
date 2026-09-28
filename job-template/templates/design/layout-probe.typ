// Evaluated with `typst eval --in book.typ` by scripts/layout_metrics.py; it is never included in the book.
// Returns the page position of every paragraph and non-prose element so page-level metrics can be derived
// from the actual typeset layout instead of manuscript character counts.
#let bo-text(c) = {
  if type(c) == str { return c }
  if type(c) != content { return "" }
  if c.has("text") { return if type(c.text) == str { c.text } else { bo-text(c.text) } }
  if c.has("children") { return (c.children.map(bo-text) + ("",)).join() }
  if c.has("body") { return bo-text(c.body) }
  if c.has("child") { return bo-text(c.child) }
  ""
}
#let bo-chars(c) = bo-text(c).replace(regex("\s"), "").clusters().len()
#let bo-at(e) = {
  let p = e.location().position()
  (page: p.page, x: p.x / 1pt, y: p.y / 1pt, folio: counter(page).at(e.location()).first())
}
#let bo-kind(k) = if type(k) == str { k } else if k == image { "image" } else if k == table { "table" } else if k == raw { "code" } else { repr(k) }

#let collect() = (
  version: 1,
  pars: query(par).map(p => (..bo-at(p), chars: bo-chars(p.body))),
  headings: query(heading).map(h => (..bo-at(h), level: h.level, outlined: h.outlined,
    text: bo-text(h.body).trim(), label: if h.has("label") { str(h.label) } else { none })),
  figures: query(figure).map(f => (..bo-at(f), kind: bo-kind(f.kind),
    label: if f.has("label") { str(f.label) } else { none })),
  tables: query(table).map(t => bo-at(t)),
  equations: query(math.equation.where(block: true)).map(e => bo-at(e)),
  quotes: query(quote.where(block: true)).map(q => bo-at(q)),
  code: query(raw.where(block: true)).map(r => bo-at(r)),
  lists: query(list).map(l => bo-at(l)) + query(enum).map(l => bo-at(l)) + query(terms).map(l => bo-at(l)),
  outlines: query(outline).map(o => bo-at(o)),
  marks: query(<bo-mark>).map(m => bo-at(m) + m.value),
  ends: query(<bo-end>).map(m => bo-at(m) + m.value),
)

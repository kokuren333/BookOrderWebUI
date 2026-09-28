// Proof placeholder for a planned device that has not been produced yet (plan/editorial/*.yaml slots).
// It reserves roughly the room the device will take so the proof paces like the book; the final validation
// fails while any slot remains.
#let book-slot(kind, id, body) = {
  let visual = kind in ("figure", "chart", "table", "timeline")
  block(width: 100%, above: 1.1em, below: 1.1em, inset: 8pt, breakable: false,
    stroke: (paint: luma(140), thickness: .6pt, dash: "dashed"), fill: luma(246),
    height: if visual { 7em } else { auto })[
    #text(size: .8em, weight: 700, fill: luma(90))[SLOT #kind · #id]
    #v(2pt, weak: true)
    #text(size: .9em, fill: luma(70), body)
  ]
}

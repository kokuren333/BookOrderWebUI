// Layout instrumentation for reports/layout-metrics.json (scripts/layout_metrics.py).
// Only invisible metadata is added after block elements; the typeset result is unchanged.
#let bo-end(el) = [#metadata((el: el))<bo-end>]
#show figure: it => { it; bo-end("figure") }
#show table: it => { it; bo-end("table") }
#show math.equation.where(block: true): it => { it; bo-end("equation") }
#show quote.where(block: true): it => { it; bo-end("quote") }
#show raw.where(block: true): it => { it; bo-end("code") }
#show list: it => { it; bo-end("list") }
#show enum: it => { it; bo-end("enum") }
#show terms: it => { it; bo-end("terms") }

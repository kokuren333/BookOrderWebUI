"""Build a compact Typst PDF demonstrating the LayoutSpec flow primitives.

Run from a publishing job: python tools/layout-specimen.py
The specimen is deliberately independent of manuscript generation and StyleBible.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import ROOT, run, tool
from layout_spec import load_or_create


def build():
    spec = load_or_create()
    page = spec["page"]
    body_width = page["width_mm"] - page["margin_inner_mm"] - page["margin_outer_mm"]
    one = (body_width - spec["body"]["gutter_mm"]) / 2
    source = ROOT / ".build/layout-specimen.typ"
    output = ROOT / "publish/layout-specimen.pdf"
    source.parent.mkdir(exist_ok=True)
    output.parent.mkdir(exist_ok=True)
    content = f'''// LayoutSpec specimen. PDF is horizontal-only; vertical writing unsupported.
#set page(width: {page["width_mm"]}mm, height: {page["height_mm"]}mm,
  margin: (top: {page["margin_top_mm"]}mm, bottom: {page["margin_bottom_mm"]}mm,
    left: {page["margin_inner_mm"]}mm, right: {page["margin_outer_mm"]}mm), columns: 1)
#set text(size: 9pt)
#set par(justify: true)
#let sample = [A book page needs a stable measure for paragraphs and captions. The layout specification defines its frame, while the profile defines the editorial density.]
#let opener(title) = block(width: 100%, below: 8mm)[
  #text(size: 9pt, fill: blue, "LAYOUT SPECIMEN") #linebreak()
  #text(size: 18pt, weight: "bold", title)
  #line(length: 100%, stroke: 1pt + blue)
]
#opener("One-column body")
#for i in range(5) {{ sample; parbreak() }}
#figure(rect(width: {body_width:.2f}mm, height: 18mm, fill: rgb("#e9f2f8"), inset: 3mm)[One-column figure], caption: [Span 1 in a one-column body])
#pagebreak()
#set page(columns: 2)
#set columns(gutter: {spec["body"]["gutter_mm"]}mm)
#place(top + center, scope: "parent", float: true)[#opener("Two-column body and full-span opener")]
#for i in range(8) {{ sample; parbreak() }}
#figure(rect(width: {one:.2f}mm, height: 22mm, fill: rgb("#e9f2f8"), inset: 3mm)[Span 1 figure], caption: [One-column figure])
#for i in range(5) {{ sample; parbreak() }}
#place(top + center, scope: "parent", float: true)[
  #figure(rect(width: {body_width:.2f}mm, height: 22mm, fill: rgb("#dbeedb"), inset: 3mm)[Span 2 figure], caption: [Two-column figure])
]
#for i in range(5) {{ sample; parbreak() }}
#place(top + center, scope: "parent", float: true)[
  #figure(rect(width: {body_width:.2f}mm, height: 16mm, fill: rgb("#f5ebd3"), inset: 3mm)[Full-width figure], caption: [Full-width region figure])
]
#for i in range(4) {{ sample; parbreak() }}
#place(top + center, scope: "parent", float: true)[
  #figure(table(columns: (1fr, 1fr, 1fr), [Element], [Span], [Region], [Figure], [2], [Body], [Table], [Full], [Full width]), caption: [Full-width table])
]
#for i in range(4) {{ sample; parbreak() }}
#place(top + center, scope: "parent", float: true)[
  #block(width: {body_width:.2f}mm, fill: rgb("#e6eef6"), inset: 3mm)[*Two-column callout* #linebreak() A deliberate pause across the full body width.]
]
#for i in range(4) {{ sample; parbreak() }}
#pagebreak()
#text(size: 13pt, weight: "bold", "Vertical writing unsupported")
#parbreak()
This Typst adapter rejects vertical-rl explicitly. The LayoutSpec schema reserves its direction, punctuation, Latin, numeral, and ruby settings.
'''
    source.write_text(content, encoding="utf-8")
    run([tool("typst"), "compile", "--root", ROOT, source, output])
    print(json.dumps({"layout_id": spec["id"], "source": str(source), "pdf": str(output)}, ensure_ascii=False))
    return output


if __name__ == "__main__": build()

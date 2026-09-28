"""Layout metrics (P0-1): page segmentation from synthetic probe data, plus a real Typst round trip.

The synthetic tests need only Python. The Typst tests run when TYPST (or `typst` on PATH) is available and
check that the layout marks never change the typeset pages. pdfplumber, when installed, cross-checks the
measured prose characters against the characters actually printed on the page (development only).
Usage: python tests/test_layout_metrics.py
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "job-template"
sys.path.insert(0, str(TEMPLATE / "scripts"))
import layout_metrics as lm  # noqa: E402

TOKENS = {"page": {"size": "A5", "orientation": "portrait",
                   "margin": {"top": "18mm", "bottom": "20mm", "inner": "20mm", "outer": "17mm"}},
          "typography": {"body": {"size": "9.5pt", "line_height": 1.7}}}
TOP, BOTTOM = 51.02, 538.58


def P(page, y, chars=300): return {"page": page, "y": y, "folio": page, "chars": chars}
def H(page, y, level=2, text="節"): return {"page": page, "y": y, "folio": page, "level": level, "outlined": True, "text": text, "label": None}
def M(page, y, **value): return {"page": page, "y": y, "folio": page, **value}


def book(pars, headings=(), figures=(), ends=(), marks=(), tables=()):
    return {"version": 1, "pars": list(pars), "headings": list(headings), "figures": list(figures), "tables": list(tables),
            "equations": [], "quotes": [], "code": [], "lists": [], "outlines": [], "marks": list(marks), "ends": list(ends)}


class SyntheticLayout(unittest.TestCase):
    def wall(self):
        """Chapter 1 on pp.2–9 with one figure on p.5, chapter 2 on pp.10–11, bibliography alone on p.12."""
        pars = [P(page, y) for page in range(2, 10) for y in (120 if page == 2 else TOP, 300)]
        pars += [P(10, 200), P(11, TOP), P(11, 300), P(12, 150, chars=80)]
        marks = [M(2, 0, el="chapter", id="ch-a", number="1", label="第1章"), M(10, 0, el="chapter", id="ch-b", number="2", label="第2章"),
                 M(11, 200, el="begin", sub="key-point"), M(11, 260, el="end", sub="key-point"),
                 M(12, 140, el="back-matter", sub="bibliography"), M(12, 400, el="doc-end")]
        return book(pars, [H(2, 90, 1, "第一章"), H(10, 90, 1, "第二章"), H(12, TOP)],
                    figures=[M(5, 320, kind="image", label="fig-x")], ends=[M(5, 500, el="figure")], marks=marks)

    def test_text_only_runs_and_regions(self):
        m = lm.compute(self.wall(), TOKENS, [{"id": "ch-a", "title": "A"}])
        t = m["totals"]
        self.assertEqual((t["pages"], t["front_matter_pages"], t["back_matter_pages"]), (12, 1, 1))
        self.assertEqual(m["chapters"][0]["pages"], [2, 9]); self.assertEqual(m["chapters"][1]["pages"], [10, 11])
        self.assertEqual(m["chapters"][0]["title"], "A")
        runs = [(r["start"], r["end"]) for r in m["text_only_runs"]]
        self.assertIn((3, 4), runs); self.assertIn((6, 9), runs)
        self.assertEqual(m["max_text_only_run"]["length"], 4)
        page = {p["page"]: p for p in m["pages"]}
        self.assertFalse(page[2]["text_only"], "chapter opener page is a pause")
        self.assertFalse(page[5]["text_only"], "figure page is a pause")
        self.assertFalse(page[11]["text_only"], "callout page is a pause")
        self.assertEqual(page[5]["elements"][0]["kind"], "figure")
        self.assertEqual(m["chapters"][0]["visuals"], 1); self.assertEqual(m["chapters"][1]["callouts"], 1)

    def test_prose_characters_conserved(self):
        m = lm.compute(self.wall(), TOKENS)
        main_pars = sum(p["chars"] for p in self.wall()["pars"] if (p["page"], p["y"]) < (12, 140))
        self.assertAlmostEqual(m["totals"]["prose_chars"], main_pars, delta=len(m["pages"]))
        self.assertEqual(m["pages"][11]["prose_chars"], 0, "bibliography is not prose")

    def test_paragraph_split_across_pages(self):
        data = book([P(2, 120, chars=1000), P(3, 200, chars=10)], [H(2, 90, 1)],
                    marks=[M(2, 0, el="chapter", id="c", number="1", label=""), M(3, 400, el="doc-end")])
        m = lm.compute(data, TOKENS)
        first, second = m["pages"][1]["prose_chars"], m["pages"][2]["prose_chars"]
        above = BOTTOM - 120; below = 200 - TOP
        self.assertAlmostEqual(first / (first + second - 10), above / (above + below), delta=0.02)

    def test_end_mark_pushed_to_next_page(self):
        data = book([P(2, 100), P(4, 100)], figures=[M(3, 300, kind="image")], ends=[M(4, TOP, el="figure")],
                    marks=[M(2, 0, el="chapter", id="c", number="1", label="")])
        m = lm.compute(data, TOKENS)
        self.assertEqual([e["kind"] for e in m["pages"][3]["elements"]], [], "figure ended on p.3")
        self.assertTrue(m["pages"][3]["text_only"])

    def test_table_inside_figure_counted_once_and_component_prose_excluded(self):
        data = book([P(2, 100, chars=100), P(2, 330, chars=500), P(2, 450, chars=100)],
                    figures=[M(2, 150, kind="table")], tables=[M(2, 170)], ends=[M(2, 250, el="table"), M(2, 300, el="figure")],
                    marks=[M(2, 0, el="chapter", id="c", number="1", label=""), M(2, 320, el="begin", sub="warning"), M(2, 440, el="end", sub="warning")])
        m = lm.compute(data, TOKENS)
        self.assertEqual(m["totals"]["elements"]["table"], 1)
        self.assertAlmostEqual(m["totals"]["prose_chars"], 200, delta=1)
        self.assertGreater(m["pages"][1]["nonprose_share"], 0.3)

    def test_spreads(self):
        m = lm.compute(self.wall(), TOKENS)
        self.assertEqual(m["spreads"][0]["pages"], [1]); self.assertEqual(m["spreads"][1]["pages"], [2, 3])
        by_pages = {tuple(s["pages"]): s for s in m["spreads"]}
        self.assertTrue(by_pages[(6, 7)]["text_only"]); self.assertEqual(by_pages[(4, 5)]["visuals"], 1)


def typst():
    found = os.environ.get("TYPST") or shutil.which("typst")
    return found if found and Path(found).is_file() else None


@unittest.skipUnless(typst(), "Typst not available (set TYPST)")
class TypstRoundTrip(unittest.TestCase):
    """A small book laid out by Typst: the probe must read it back without changing a single pixel."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="layout-metrics-")); (self.root / ".build").mkdir()
        shutil.copy2(TEMPLATE / "templates/design/layout-probe.typ", self.root / ".build/layout-probe.typ")
        text = "本文の段落はこのように続き、図や表のない頁が何枚も並ぶと読者は休む場所を失う。" * 9
        body = [f'#metadata((el: "chapter", id: "ch-wall", number: "1", label: "第1章"))<bo-mark>', "= 文章壁の章"]
        body += [text for _ in range(14)]
        body += ['#figure(rect(width: 60%, height: 4cm), caption: [休止点としての図])', text, text]
        body += ["#pagebreak()", f'#metadata((el: "chapter", id: "ch-box", number: "2", label: "第2章"))<bo-mark>', "= 囲みの章", text,
                 '#block(inset: 8pt, stroke: 1pt)[#metadata((el: "begin", sub: "key-point"))<bo-mark>\n\n要点の本文。\n\n#metadata((el: "end", sub: "key-point"))<bo-mark>]',
                 text, "- 箇条書き\n- もう一つ", text,
                 '#metadata((el: "back-matter", sub: "bibliography"))<bo-mark>', "[1] 文献。", '#metadata((el: "doc-end"))<bo-mark>']
        head = '#set page(paper: "a5", margin: (top: 18mm, bottom: 20mm, inside: 20mm, outside: 17mm))\n#set text(size: 9.5pt, lang: "ja")\n#set par(justify: true, leading: 0.7em)\n'
        marks = (TEMPLATE / "templates/design/layout-marks.typ").read_text(encoding="utf-8")
        (self.root / ".build/plain.typ").write_text(head + "\n\n".join(body), encoding="utf-8")
        (self.root / ".build/book.typ").write_text(head + marks + "\n\n".join(body), encoding="utf-8")

    def tearDown(self): shutil.rmtree(self.root, ignore_errors=True)

    def compile(self, name):
        out = self.root / f"png-{name}"; out.mkdir()
        subprocess.run([typst(), "compile", "--root", self.root, self.root / f".build/{name}.typ", out / "{p}.png"], check=True, capture_output=True)
        return sorted(out.glob("*.png"))

    def test_marks_do_not_change_layout(self):
        plain, marked = self.compile("plain"), self.compile("book")
        self.assertEqual(len(plain), len(marked))
        for a, b in zip(plain, marked): self.assertEqual(a.read_bytes(), b.read_bytes(), f"page {a.stem} changed")

    def test_probe_and_metrics(self):
        data = lm.probe(self.root / ".build/book.typ", root=self.root)
        m = lm.compute(data, TOKENS)
        pages = len(self.compile("book"))
        self.assertEqual(m["totals"]["pages"], pages)
        self.assertEqual([c["id"] for c in m["chapters"]], ["ch-wall", "ch-box"])
        self.assertEqual(m["totals"]["elements"]["figure"], 1); self.assertEqual(m["totals"]["callouts"], 1)
        figure_page = next(p["page"] for p in m["pages"] if any(e["kind"] == "figure" for e in p["elements"]))
        self.assertGreaterEqual(m["max_text_only_run"]["length"], 3)
        self.assertLess(m["max_text_only_run"]["end"], figure_page)
        self.assertFalse(m["pages"][figure_page - 1]["text_only"])
        try: import pdfplumber
        except ImportError: return
        pdf = self.root / "book.pdf"
        subprocess.run([typst(), "compile", "--root", self.root, self.root / ".build/book.typ", pdf], check=True, capture_output=True)
        with pdfplumber.open(pdf) as document:
            for page in m["pages"]:
                if not page["text_only"]: continue
                printed = sum(1 for c in document.pages[page["page"] - 1].chars if c["text"].strip())
                self.assertAlmostEqual(page["prose_chars"], printed, delta=max(40, printed * 0.1), msg=f"p.{page['page']}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

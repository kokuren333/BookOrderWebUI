"""Print-size figures (P0-5): tokens, frames, Diagram IR at printed size, SVG text inspection, chartkit.

Pure-Python tests always run. chartkit tests need matplotlib; the Typst round trip needs TYPST (or typst on PATH)
and, for measuring the printed text, pdfplumber (development only).
Usage: python tests/test_figures.py
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
import diagrams  # noqa: E402
import figure_check  # noqa: E402
import figure_spec  # noqa: E402
from design import load_design  # noqa: E402

# load_design caches parsed YAML under job-template/.build; never leave it in the shipped template.
BUILD = TEMPLATE / ".build"; BUILD_EXISTED = BUILD.exists()
TOKENS = load_design("medical-textbook")
MIN = figure_spec.figure_tokens(TOKENS)["min_label_pt"]
LABELS = ["問い合わせと鍵の内積", "ソフトマックスで正規化する", "Value の加重平均", "位置エンコーディング", "残差接続と層正規化",
          "マルチヘッドの結合", "フィードフォワード層", "出力確率", "学習率ウォームアップ", "スケーリング則", "評価と汚染", "まとめ"]


def svg_file(text, folder):
    path = Path(folder) / "f.svg"; path.write_text(text, encoding="utf-8"); return path


def overlapping(path):
    """Node boxes (rects other than the background) that intersect."""
    import re
    boxes = [tuple(float(v) for v in m) for m in re.findall(r'<rect x="([-0-9.]+)" y="([-0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"', Path(path).read_text(encoding="utf-8"))]
    return [(a, b) for i, a in enumerate(boxes) for b in boxes[i + 1:]
            if a[0] < b[0] + b[2] - 0.5 and b[0] < a[0] + a[2] - 0.5 and a[1] < b[1] + b[3] - 0.5 and b[1] < a[1] + a[3] - 0.5]


def column(declared=False, **geometry):
    return figure_spec.resolve(geometry, TOKENS, "diagram") | {"declared": declared}


class Tokens(unittest.TestCase):
    def test_defaults_line_weight_and_overrides(self):
        base = figure_spec.figure_tokens({})
        self.assertEqual(base["sources"], ["bookorder-defaults"])
        for key in ("min_label_pt", "preferred_label_pt", "axis_label_pt", "tick_label_pt", "annotation_pt", "legend_pt", "stroke_width_pt", "node_padding_mm"):
            self.assertIn(key, base)
        thin = figure_spec.figure_tokens({"figures": {"line_weight": "thin"}})
        self.assertLess(thin["stroke_width_pt"], base["stroke_width_pt"])
        custom = figure_spec.figure_tokens({"figures": {"line_weight": "regular", "print": {"min_label_pt": 7.5, "tick_label_pt": 6.0}}})
        self.assertEqual(custom["min_label_pt"], 7.5)
        self.assertEqual(custom["tick_label_pt"], 7.5, "no role may be set below the minimum")
        self.assertIn("design.figures.print", custom["sources"])

    def test_style_bible_wins(self):
        folder = Path(tempfile.mkdtemp()); (folder / "plan").mkdir()
        (folder / "plan/style-bible.yaml").write_text(json.dumps({"figures": {"print": {"preferred_label_pt": 9.0}}}), encoding="utf-8")
        original = figure_spec.ROOT
        try:
            figure_spec.ROOT = folder
            tokens = figure_spec.figure_tokens({"figures": {"print": {"preferred_label_pt": 8.5}}})
        finally:
            figure_spec.ROOT = original; shutil.rmtree(folder)
        self.assertEqual(tokens["preferred_label_pt"], 9.0); self.assertEqual(tokens["sources"][-1], "plan/style-bible.yaml")

    def test_design_schema_accepts_print_block(self):
        from schema import validate_schema
        schema = json.loads((TEMPLATE / "schemas/design.schema.json").read_text(encoding="utf-8"))
        spec = json.loads(json.dumps(TOKENS)); spec["figures"]["print"] = {"min_label_pt": 7}
        validate_schema(spec, schema)
        spec["figures"]["print"] = {"font_px": 7}
        with self.assertRaises(ValueError): validate_schema(spec, schema)


class Geometry(unittest.TestCase):
    def test_frames_from_page_tokens(self):
        frames = figure_spec.frames(TOKENS); page = figure_spec.page_frame(TOKENS)
        self.assertAlmostEqual(frames["column"]["width_mm"], page["text_width_mm"])
        reach = min(page["margin_inner_mm"], page["margin_outer_mm"]) - figure_spec.SAFE_EDGE_MM
        self.assertAlmostEqual(frames["full-width"]["width_mm"], page["text_width_mm"] + 2 * reach, places=1)
        self.assertLess(frames["margin"]["width_mm"], page["margin_outer_mm"])
        self.assertGreater(frames["full-page"]["max_height_mm"], frames["column"]["max_height_mm"])

    def test_resolve(self):
        g = figure_spec.resolve({"placement": "column", "aspect_ratio": "16:9"}, TOKENS)
        self.assertAlmostEqual(g["height_mm"], g["width_mm"] * 9 / 16, places=1)
        wide = figure_spec.resolve({"width_mm": 400}, TOKENS)
        self.assertEqual(wide["width_mm"], figure_spec.frames(TOKENS)["column"]["width_mm"]); self.assertTrue(wide["warnings"])
        self.assertTrue(figure_spec.resolve({"placement": "spread"}, TOKENS)["warnings"])
        self.assertEqual(figure_spec.check_geometry({"placement": "poster"}), ["geometry.placement must be one of column, full-width, margin, full-page, spread"])
        self.assertEqual(figure_spec.check_geometry({"placement": "full-width", "width_mm": 120, "aspect_ratio": "4:3"}), [])


class DiagramsAtPrintedSize(unittest.TestCase):
    def test_every_type_prints_at_token_sizes(self):
        folder = tempfile.mkdtemp(); ft = figure_spec.figure_tokens(TOKENS)
        try:
            for kind in diagrams.TYPES:
                for count in (2, 5, 9, 12):
                    nodes = [{"id": f"n{i}", "label": LABELS[i]} for i in range(count)]
                    edges = [{"from": "n0", "to": f"n{i}", "label": "影響"} for i in range(1, count)] if kind in ("hierarchy", "network", "concept-map") else []
                    spec = {"type": kind, "title": "t", "nodes": nodes, "edges": edges}
                    for geometry in (column(), column(width_mm=70), figure_spec.resolve({"placement": "full-width"}, TOKENS, "diagram") | {"declared": True}):
                        path = svg_file(diagrams.svg(spec, TOKENS, geometry), folder)
                        facts = figure_check.inspect_svg(path)
                        self.assertAlmostEqual(facts["natural_width_pt"] / figure_spec.PT_PER_MM, geometry["width_mm"], places=1)
                        result = figure_check.check_figure("x", path, geometry, TOKENS)
                        self.assertEqual(result["status"], "ok", (kind, count, geometry["width_mm"], result.get("below_min")))
                        self.assertAlmostEqual(result["max_text_pt"], ft["preferred_label_pt"], places=2)
                        self.assertAlmostEqual(result["scale"], 1.0, places=3)
                        self.assertFalse(overlapping(path), (kind, count, geometry["width_mm"]))
                        max_height = figure_spec.frames(TOKENS)[geometry["placement"]]["max_height_mm"]
                        if facts["natural_height_pt"] / figure_spec.PT_PER_MM > max_height + 0.5:  # never shrunk: reported instead
                            self.assertTrue(any("tall" in w for w in result["warnings"]), (kind, count, geometry["width_mm"]))
        finally: shutil.rmtree(folder)

    def test_labels_fit_their_boxes(self):
        ft = figure_spec.figure_tokens(TOKENS)
        for width in (111, 70):
            box = (width * figure_spec.PT_PER_MM - 2 * diagrams.MARGIN_PT - 2 * 4 * figure_spec.PT_PER_MM) / 3
            units = (box - 2 * ft["node_padding_mm"] * figure_spec.PT_PER_MM) / (ft["preferred_label_pt"] / 2)
            for label in LABELS:
                for line in diagrams.wrap(label, units): self.assertLessEqual(sum(map(diagrams._units, line)), units + 2)

    def test_balanced_wrap(self):
        self.assertEqual(diagrams.wrap("ソフトマックスで正規化", 20.6), ["ソフトマック", "スで正規化"])


class Inspection(unittest.TestCase):
    def setUp(self): self.folder = tempfile.mkdtemp()
    def tearDown(self): shutil.rmtree(self.folder)

    def check(self, text, **geometry):
        return figure_check.check_figure("x", svg_file(text, self.folder), column(declared=bool(geometry), **geometry), TOKENS)

    def test_shrunk_figure_fails_like_the_sample_book(self):
        # A 640 px wide chart with 10 px text placed in a 111 mm column prints at 10 × 314.6/480 ≈ 6.6pt;
        # with 8 px ticks it prints 5.2pt — the sample book's failure mode.
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480"><text font-size="10">軸</text><text style="font-size:8px">1</text></svg>'
        result = self.check(svg)
        self.assertEqual(result["status"], "fail"); self.assertAlmostEqual(result["min_text_pt"], 8 * 0.75 * result["scale"], places=1)
        self.assertTrue(result["warnings"], "shrinking is reported")

    def test_build_stops_when_a_figure_is_below_the_print_minimum(self):
        import build
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = {"book": {"language": "ja"}, "outputs": {"pdf": False, "docx": False, "semantic_html": False, "epub": False, "static_site": False}}
            with patch.object(build, "ROOT", root), patch.object(build, "read_project", return_value=project), \
                 patch.object(build, "load_design", return_value={"theme": "test"}), \
                 patch.object(build, "normalize", return_value={"language": "ja", "pdf_backend": "typst"}), \
                 patch.object(build, "cover_image", return_value=None), patch.object(build, "generate_diagrams", return_value=[]), \
                 patch("figure_spec.write_reference"), \
                 patch("figure_check.check", return_value={"summary": {"fail": 1}}):
                with self.assertRaisesRegex(RuntimeError, "Figure legibility check failed"):
                    build.build()

    def test_units_inheritance_transforms_and_shorthand(self):
        width = figure_spec.frames(TOKENS)["column"]["width_mm"] * figure_spec.PT_PER_MM
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}pt" height="100pt" viewBox="0 0 {width} 100">'
               '<g font-size="9"><text>a</text><g transform="scale(0.8)"><text>b</text></g></g>'
               '<text style="font: 7.5px \'Noto Sans\'">c</text><g style="font-size:10px"><text font-size="0.8em">d</text></g>'
               '<text font-size="6pt">e</text></svg>')
        result = self.check(svg)
        sizes = {b["text"]: b["pt"] for b in result["below_min"]}
        self.assertEqual(result["max_text_pt"], 9.0); self.assertEqual(result["text_runs"], 5)
        self.assertEqual(result["min_text_pt"], 7.2)  # 9 × 0.8 and 10 × 0.8em; 6pt = 8 user units
        self.assertEqual(sizes, {})

    def test_declared_width_changes_printed_size(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm" viewBox="0 0 100 50"><text font-size="2.8">x</text></svg>'
        at_100 = self.check(svg, width_mm=100); at_70 = self.check(svg, width_mm=70)
        self.assertAlmostEqual(at_100["min_text_pt"], 2.8 * figure_spec.PT_PER_MM, places=1)
        self.assertAlmostEqual(at_70["min_text_pt"], 2.8 * figure_spec.PT_PER_MM * 0.7, places=1)
        self.assertEqual((at_100["status"], at_70["status"]), ("ok", "fail"))

    def test_raster_render_record(self):
        png = Path(self.folder) / "c.png"; png.write_bytes(b"\x89PNG\r\n\x1a\n")
        self.assertEqual(figure_check.check_figure("c", png, column(), TOKENS)["status"], "unverified")
        (Path(self.folder) / "c.png.render.json").write_text(json.dumps({"width_mm": 150, "min_text_pt": 7.0}), encoding="utf-8")
        result = figure_check.check_figure("c", png, column(), TOKENS)
        self.assertEqual(result["method"], "render-record"); self.assertEqual(result["status"], "fail")  # 150 mm → 111 mm


def matplotlib_available():
    try: import matplotlib  # noqa: F401
    except ImportError: return False
    return True


@unittest.skipUnless(matplotlib_available(), "matplotlib not installed")
class ChartKit(unittest.TestCase):
    def setUp(self):
        import chartkit; self.chartkit = chartkit; self.folder = Path(tempfile.mkdtemp())
    def tearDown(self): shutil.rmtree(self.folder)

    def test_chart_drawn_and_checked_at_printed_size(self):
        fig, ax = self.chartkit.figure(tokens=TOKENS, aspect_ratio="16:9")
        ax.plot([0, 1, 2], [1, 3, 2], label="系列"); ax.set_xlabel("期間（月）"); ax.set_ylabel("割合"); ax.legend()
        record = self.chartkit.save(fig, self.folder / "c.svg", "fig-c")
        self.assertAlmostEqual(record["width_mm"], figure_spec.frames(TOKENS)["column"]["width_mm"], places=1)
        result = figure_check.check_figure("fig-c", self.folder / "c.svg", column(declared=True, width_mm=record["width_mm"]), TOKENS)
        self.assertEqual(result["status"], "ok"); self.assertAlmostEqual(result["min_text_pt"], record["min_text_pt"], places=2)
        self.assertAlmostEqual(result["scale"], 1.0, places=2)

    def test_refuses_small_text(self):
        fig, ax = self.chartkit.figure(tokens=TOKENS)
        ax.set_xlabel("x"); ax.tick_params(labelsize=5)
        with self.assertRaises(ValueError): self.chartkit.save(fig, self.folder / "c.svg", "fig-c")


class Renderer(unittest.TestCase):
    def test_planned_width_on_image(self):
        from renderers.typst import place_figure
        figure = {"t": "Figure", "c": [["fig-a", [], []], [None, []], [{"t": "Plain", "c": [{"t": "Image", "c": [["", [], [["width", "50%"]]], [], ["a.svg", ""]]}]}]]}
        place_figure(figure, {"planned_width_mm": 80.0})
        self.assertEqual(figure["c"][2][0]["c"][0]["c"][0][2], [["width", "80.0mm"]])


def typst():
    found = os.environ.get("TYPST") or shutil.which("typst")
    return found if found and Path(found).is_file() else None


@unittest.skipUnless(typst(), "Typst not available (set TYPST)")
class PrintedRoundTrip(unittest.TestCase):
    def test_diagram_prints_at_token_sizes(self):
        folder = Path(tempfile.mkdtemp())
        try:
            spec = {"type": "flow", "title": "t", "nodes": [{"id": f"n{i}", "label": LABELS[i]} for i in range(5)], "edges": [{"from": "n0", "to": "n1", "label": "次へ"}]}
            geometry = column(); (folder / "d.svg").write_text(diagrams.svg(spec, TOKENS, geometry), encoding="utf-8")
            (folder / "p.typ").write_text(f'#set page(paper: "a5")\n#image("d.svg", width: {geometry["width_mm"]}mm)\n', encoding="utf-8")
            subprocess.run([typst(), "compile", "--root", folder, folder / "p.typ", folder / "p.pdf"], check=True, capture_output=True)
            try: import pdfplumber
            except ImportError: return
            with pdfplumber.open(folder / "p.pdf") as pdf:
                sizes = {round(c["size"], 2) for c in pdf.pages[0].chars if c["text"].strip()}
            ft = figure_spec.figure_tokens(TOKENS)
            self.assertEqual(sizes, {ft["preferred_label_pt"], ft["annotation_pt"]})
        finally: shutil.rmtree(folder)


def tearDownModule():
    if not BUILD_EXISTED: shutil.rmtree(BUILD, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

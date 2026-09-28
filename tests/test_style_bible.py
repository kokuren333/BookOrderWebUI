"""P1-1 semantic StyleBible, renderer adapters, lint and PDF specimen."""
import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "job-template/scripts"))
import chartkit
import common
import design
import diagrams
import figure_spec
import layout_spec
import style_bible
import style_check

PROJECT = {"book": {"language": "ja"}, "style_bible": {}}


class StyleBibleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = design.load_design()
        cls.medical = style_bible.resolve(PROJECT, {"genre": "medical_science", "art_direction": {}}, cls.design)
        cls.criticism = style_bible.resolve(PROJECT, {"genre": "criticism", "art_direction": {}}, cls.design)
        cls.layout = layout_spec.resolve(PROJECT, {"genre": "medical_science"}, cls.design,
                                         {"body": {"columns": 2, "gutter_mm": 6}})

    def tokens(self, style=None, layout=None):
        style = style or self.medical; layout = layout or self.layout
        base = {"colors": {"text": "#18181B", "muted": "#71717A", "primary": "#164E63",
                           "accent": "#0891B2", "secondary": "#F4F7F8", "surface": "#F4F7F8"},
                "figures": {"style": "color", "labeling": "plain"}, "typography": {"caption": {"resolved_families": ["Noto Sans JP"]}}}
        return style_bible.compile_tokens(style, layout, layout_spec.apply_to_tokens(base, layout))

    def test_resolution_override_and_determinism(self):
        self.assertEqual(self.medical, style_bible.resolve(PROJECT, {"genre": "medical_science", "art_direction": {}}, self.design))
        self.assertNotEqual(self.medical["palette"]["accent"], self.criticism["palette"]["accent"])
        project = copy.deepcopy(PROJECT); project["style_bible"] = {"palette": {"accent": "#123456"}}
        changed = style_bible.resolve(project, {"genre": "criticism", "art_direction": {}}, self.design)
        self.assertEqual(changed["palette"]["accent"], "#123456")
        self.assertEqual(changed["genre"], "criticism")
        with self.assertRaises(ValueError):
            style_bible.resolve({**PROJECT, "style_bible": {"columns": 2}},
                                {"genre": "criticism", "art_direction": {}}, self.design)

    def test_one_and_two_column_share_semantic_style(self):
        one = layout_spec.resolve(PROJECT, {"genre": "medical_science"}, self.design,
                                  {"body": {"columns": 1}})
        a, b = self.tokens(layout=one), self.tokens()
        self.assertEqual(a["style"]["palette"], b["style"]["palette"])
        self.assertFalse(a["style"]["adaptation"]["narrow_column"])
        self.assertTrue(b["style"]["adaptation"]["narrow_column"])
        self.assertLess(b["style"]["typography"]["heading_2"]["size_pt"],
                        a["style"]["typography"]["heading_2"]["size_pt"])
        self.assertEqual(one["body"]["columns"], 1)
        self.assertEqual(b["layout_spec"]["body"]["columns"], 2)

    def test_figure_diagram_chart_adapters_and_minimum(self):
        tokens = self.tokens(); ft = figure_spec.figure_tokens(tokens)
        self.assertIn("plan/style-bible.yaml@1", ft["sources"])
        self.assertEqual(ft["stroke_width_pt"], self.medical["lines"]["normal_pt"])
        self.assertEqual(ft["min_label_pt"], 6.5)
        self.assertEqual(chartkit.spec(tokens=tokens)["tokens"]["colors"]["accent"], self.medical["palette"]["accent"])
        spec = {"title": "flow", "type": "flow", "nodes": [{"id": "a", "label": "入力"}, {"id": "b", "label": "出力"}]}
        svg = diagrams.svg(spec, tokens)
        self.assertIn(self.medical["palette"]["background"], svg)
        self.assertIn(self.medical["palette"]["secondary_accent"], svg)
        self.assertEqual(figure_spec.figure_tokens({})["min_label_pt"], 6.5)

    def test_lint_invalid_palette_font_grayscale_default_and_heading(self):
        tokens = self.tokens()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "source/manuscript").mkdir(parents=True)
            (root / "source/manuscript/chapter.md").write_text("## 比較条件と実験で得た結果を解釈するための長い見出し\n", encoding="utf-8")
            result = style_check.lint(self.medical, tokens, {"Noto Sans JP"}, root, "#let x = luma(210)")
            codes = {item["code"] for item in result["issues"]}
            self.assertIn("renderer-default-color", codes)
            self.assertIn("unknown-font", codes)
            style = copy.deepcopy(self.medical); style["palette"]["accent"] = "#GGGGGG"
            with self.assertRaises(ValueError): style_bible.validate(style)
            style = copy.deepcopy(self.medical)
            style["palette"]["secondary_accent"] = style["palette"]["accent"]
            self.assertIn("grayscale-unsafe", {i["code"] for i in style_check.lint(style, tokens, root=root, renderer_source="")["issues"]})

    def test_typst_theme_has_semantic_adapters(self):
        theme = (REPO / "job-template/themes/modern-technical/typst/theme.typ").read_text(encoding="utf-8")
        for role in ("heading_1", "heading_2", "heading_3", "caption", "table", "chapter_number"):
            self.assertIn(f'sb-size("{role}"', theme)
        self.assertIn('sb-line("strong_pt"', theme)
        self.assertIn('sb-gap("caption_gap_mm"', theme)

    def test_semantic_style_change_invalidates_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "plan").mkdir()
            path = root / "plan/style-bible.yaml"
            saved = common.ROOT
            try:
                common.ROOT = root
                path.write_text('palette: {accent: "#123456"}\n', encoding="utf-8")
                first = common.fingerprint()
                path.write_text('# editor note\npalette:\n  accent: "#123456"\n', encoding="utf-8")
                self.assertEqual(first, common.fingerprint())
                path.write_text('palette: {accent: "#654321"}\n', encoding="utf-8")
                self.assertNotEqual(first, common.fingerprint())
            finally:
                common.ROOT = saved

    @unittest.skipUnless(os.environ.get("TYPST"), "Typst executable not configured")
    def test_style_specimen_pdf_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, str(REPO / "tools/style-specimen.py"), "--output-dir", tmp],
                           cwd=REPO, check=True, capture_output=True, text=True)
            for genre in ("medical_science", "criticism"):
                pdf = Path(tmp) / f"style-specimen-{genre}.pdf"
                self.assertTrue(pdf.is_file() and pdf.stat().st_size > 1000)
            a = (Path(tmp) / "style-specimen-medical_science.typ").read_text(encoding="utf-8")
            b = (Path(tmp) / "style-specimen-criticism.typ").read_text(encoding="utf-8")
            self.assertNotEqual(a, b)
            self.assertIn("#columns(2, gutter: 6", a)


if __name__ == "__main__": unittest.main()

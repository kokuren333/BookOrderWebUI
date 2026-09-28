"""P1-2 component semantics and resolved visual grammar."""
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
import design
import diagrams
import figure_spec
import layout_spec
import style_bible
import style_check
import visual_grammar
from renderers.typst import apply_numeric_table_alignment

PROJECT = {"book": {"language": "ja"}, "style_bible": {}}


class VisualGrammarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = design.load_design()
        cls.med = style_bible.resolve(PROJECT, {"genre": "medical_science", "art_direction": {}}, cls.design)
        cls.crit = style_bible.resolve(PROJECT, {"genre": "criticism", "art_direction": {}}, cls.design)
        cls.layout = layout_spec.resolve(PROJECT, {"genre": "medical_science"}, cls.design,
                                         {"body": {"columns": 2, "gutter_mm": 6}})

    def tokens(self, style):
        base = {"colors": {"text": "#18181B", "primary": "#164E63", "muted": "#71717A", "accent": "#0891B2", "surface": "#F4F7F8"},
                "figures": {"style": "color", "labeling": "plain"}, "typography": {"caption": {"resolved_families": ["Noto Sans JP"]}}}
        return style_bible.compile_tokens(style, self.layout, layout_spec.apply_to_tokens(base, self.layout))

    def test_component_semantics_priority_and_treatment(self):
        for style in (self.med, self.crit):
            grammar = style["visual_grammar"]
            self.assertEqual(set(grammar["components"]), set(visual_grammar.COMPONENTS))
            for item in grammar["components"].values():
                self.assertEqual(set(item), visual_grammar.FIELDS)
                self.assertIn(item["priority"], visual_grammar.PRIORITIES)
                self.assertIn(item["treatment"], visual_grammar.TREATMENTS)
            self.assertEqual(visual_grammar.component(grammar, "key-point"), grammar["components"]["key_point"])
        self.assertEqual(self.med["visual_grammar"]["components"]["warning"]["priority"], "primary")
        self.assertEqual(self.crit["visual_grammar"]["components"]["pull_quote"]["priority"], "primary")
        self.assertNotEqual(self.med["visual_grammar"]["components"]["key_point"]["treatment"],
                            self.crit["visual_grammar"]["components"]["key_point"]["treatment"])
        self.assertNotEqual(self.med["visual_grammar"]["rhythm"], self.crit["visual_grammar"]["rhythm"])

    def test_box_fatigue_and_policies(self):
        for style in (self.med, self.crit):
            comps = style["visual_grammar"]["components"]
            self.assertLessEqual(sum(comps[key]["treatment"] == "filled-box" for key in
                                     ("key_point", "warning", "definition")), 1)
            self.assertEqual(style["visual_grammar"]["rhythm"]["box_budget"], "avoid-adjacent-filled-boxes")
        self.assertEqual(self.med["visual_grammar"]["components"]["pull_quote"]["use_policy"], "avoid")
        overboxed = copy.deepcopy(self.med)
        overboxed["visual_grammar"]["components"]["key_point"]["treatment"] = "filled-box"
        issues = style_check.lint(overboxed, self.tokens(overboxed), renderer_source="")
        self.assertIn("box-fatigue", {item["code"] for item in issues["issues"]})

    def test_table_diagram_chart_and_layout_boundary(self):
        gm = self.med["visual_grammar"]; gc = self.crit["visual_grammar"]
        for section in ("table", "diagram", "chart", "caption", "chapter_opener"):
            self.assertNotEqual(gm[section], gc[section])
        self.assertEqual(gm["table"]["mode"], "compact")
        self.assertEqual(gc["table"]["border_density"], "minimal")
        self.assertEqual(gm["chart"]["uncertainty"], "interval")
        self.assertEqual(gc["chart"]["grid_intensity"], "none")
        self.assertFalse(set(self.med) & style_bible.LAYOUT_KEYS)
        self.assertFalse(set(gm) & style_bible.LAYOUT_KEYS)
        self.assertEqual(self.layout["body"]["columns"], 2)
        self.assertEqual(figure_spec.figure_tokens(self.tokens(self.med))["min_label_pt"], 6.5)
        params_med = chartkit.grammar_params(figure_spec.figure_tokens(self.tokens(self.med)))
        params_crit = chartkit.grammar_params(figure_spec.figure_tokens(self.tokens(self.crit)))
        self.assertTrue(params_med["axes.grid"])
        self.assertFalse(params_crit["axes.grid"])
        spec = {"title": "Flow", "type": "flow", "nodes": [{"id": "a", "label": "観察"}, {"id": "b", "label": "主張"}]}
        med_svg = diagrams.svg(spec, self.tokens(self.med))
        crit_svg = diagrams.svg(spec, self.tokens(self.crit))
        self.assertIn('rx="0.00"', med_svg)
        self.assertNotEqual(med_svg, crit_svg)

    def test_numeric_table_alignment_preserves_authored_alignment(self):
        def cell(text):
            return [["", [], []], {"t": "AlignDefault"}, 1, 1,
                    [{"t": "Plain", "c": [{"t": "Str", "c": text}]}]]
        rows = [[["", [], []], [cell("観察A"), cell("12.4")]],
                [["", [], []], [cell("観察B"), cell("9.8")]]]
        table = {"t": "Table", "c": [["tbl", [], []], None,
                 [[{"t": "AlignDefault"}, {"t": "ColWidthDefault"}],
                  [{"t": "AlignDefault"}, {"t": "ColWidthDefault"}]],
                 None, [[["", [], []], 0, [], rows]], None]}
        result = apply_numeric_table_alignment(table, self.med["visual_grammar"]["table"])
        self.assertEqual(result["c"][2][0][0]["t"], "AlignDefault")
        self.assertEqual(result["c"][2][1][0]["t"], "AlignRight")
        self.assertEqual(table["c"][2][1][0]["t"], "AlignDefault")

    def test_style_override_does_not_create_editorial_devices(self):
        project = copy.deepcopy(PROJECT)
        project["style_bible"] = {"visual_grammar": {"components": {"key_point": {"treatment": "plain-emphasis"}}}}
        changed = style_bible.resolve(project, {"genre": "medical_science", "art_direction": {}}, self.design)
        self.assertEqual(changed["visual_grammar"]["components"]["key_point"]["treatment"], "plain-emphasis")
        self.assertNotIn("devices", changed)
        self.assertNotIn("editorial_plan", changed)

    @unittest.skipUnless(os.environ.get("TYPST"), "Typst executable not configured")
    def test_comparison_specimen_pdf_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, str(REPO / "tools/style-specimen.py"), "--output-dir", tmp],
                           cwd=REPO, check=True, capture_output=True, text=True)
            for genre in ("medical_science", "criticism"):
                self.assertGreater((Path(tmp) / f"style-specimen-{genre}.pdf").stat().st_size, 1000)
            from common import yaml_data
            report = yaml_data(Path(tmp) / "style-grammar-comparison.yaml")
            a, b = (report["genres"][g] for g in ("medical_science", "criticism"))
            self.assertEqual(report["layout_id"], "book-layout")
            self.assertNotEqual(a["components"]["key_point"]["treatment"], b["components"]["key_point"]["treatment"])
            self.assertNotEqual(a["diagram"], b["diagram"])


if __name__ == "__main__": unittest.main()

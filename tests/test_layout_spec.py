"""P1-0 LayoutSpec geometry, renderer capabilities and the Typst specimen.

Run: python tests/test_layout_spec.py
"""
import copy
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
import figure_check
import figure_spec
import layout_metrics
import layout_spec
import common
from renderers import assess_layout, assess_outputs

PROJECT = {"book": {"language": "ja", "title": "Layout specimen", "description": "Layout proof",
                    "target_readers": "Editors"}, "outputs": {"canonical_markdown": True, "pdf": True}}
DESIGN = {"page": {"size": "A5", "orientation": "portrait",
                   "margin": {"top": "18mm", "bottom": "20mm", "inner": "20mm", "outer": "17mm"}}}


class LayoutSpecTests(unittest.TestCase):
    def setUp(self):
        self.one = layout_spec.resolve(PROJECT, {"genre": "technical"}, DESIGN)
        self.two = layout_spec.resolve(PROJECT, {"genre": "technical"}, DESIGN,
                                       {"body": {"columns": 2, "gutter_mm": 6}})

    def test_deterministic_profile_default_and_schema(self):
        self.assertEqual(self.one, layout_spec.resolve(PROJECT, {"genre": "technical"}, DESIGN))
        self.assertEqual((self.one["writing_mode"], self.one["body"]["columns"]), ("horizontal-tb", 1))
        self.assertEqual(self.one["page"]["margin_top_mm"], 18)
        self.assertEqual(self.two["body"]["columns"], 2)
        future = layout_spec.resolve(PROJECT, {"genre": "novel"}, DESIGN)
        self.assertEqual(future["writing_mode"], "vertical-rl")
        self.assertEqual(assess_layout("typst", future)["status"], "unsupported")
        bad = copy.deepcopy(self.one); bad["body"]["columns"] = 9
        with self.assertRaises(ValueError): layout_spec.validate(bad)

    def test_legacy_and_two_column_figure_frames(self):
        one = layout_spec.apply_to_tokens({}, self.one)
        two = layout_spec.apply_to_tokens({}, self.two)
        self.assertEqual(figure_spec.frames(one)["column"]["width_mm"], 111)
        self.assertEqual(figure_spec.frames(two)["column"]["width_mm"], 52.5)
        self.assertEqual(figure_spec.frames(two)["full-width"]["width_mm"], 111)
        self.assertEqual(figure_spec.resolve({"span": 2}, two, "diagram")["width_mm"], 111)
        self.assertEqual(figure_spec.resolve({"span": "full"}, two, "diagram")["region"], "full-width")
        self.assertEqual(figure_spec.resolve({"placement": "full-width"}, two, "table")["width_mm"], 111)
        self.assertEqual(figure_spec.resolve({"placement": "full-width"}, one, "table")["width_mm"],
                         figure_spec.frames(one)["full-width"]["width_mm"])
        with self.assertRaises(ValueError): figure_spec.resolve({"span": 2}, one, "diagram")
        self.assertEqual(figure_spec.check_geometry({"span": "2"}), [])

    def test_capability_and_vertical_failure(self):
        result = assess_outputs(self.two, {"pdf": True, "semantic_html": True, "epub": True, "docx": True})
        self.assertEqual(result["renderers"]["pdf"]["status"], "supported")
        self.assertTrue(all(result["renderers"][k]["status"] == "degraded" for k in ("semantic_html", "epub", "docx")))
        vertical = layout_spec.resolve(PROJECT, {"genre": "essay"}, DESIGN,
                                       {"writing_mode": "vertical-rl", "vertical": {"enabled": True}})
        self.assertEqual(assess_layout("typst", vertical)["status"], "unsupported")
        self.assertEqual(assess_layout("epub", vertical)["status"], "unsupported")
        three = copy.deepcopy(self.two); three["body"]["columns"] = 3
        self.assertEqual(assess_layout("typst", three)["status"], "unsupported")

    def test_legibility_at_narrow_print_width(self):
        tokens = layout_spec.apply_to_tokens({}, self.two)
        with tempfile.TemporaryDirectory() as tmp:
            svg = Path(tmp) / "labels.svg"
            svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="30mm" viewBox="0 0 1000 300">'
                           '<text x="10" y="40" font-size="12">Too small</text></svg>', encoding="utf-8")
            geometry = figure_spec.resolve({"span": 1}, tokens, "diagram")
            geometry["declared"] = True
            entry = figure_check.check_figure("fig-test", svg, geometry, tokens)
            self.assertEqual(entry["status"], "fail")
            self.assertLess(entry["min_text_pt"], 6.5)

    def test_layout_semantic_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "plan").mkdir(); (root / "reports").mkdir()
            path = root / "plan/layout-spec.yaml"
            old = common.ROOT
            try:
                common.ROOT = root
                path.write_text('body:\n  columns: 1\n', encoding="utf-8")
                before = common.fingerprint()
                path.write_text('# comment\nbody: {columns: 1}\n', encoding="utf-8")
                self.assertEqual(common.fingerprint(), before)
                (root / "reports/unrelated.json").write_text('{"updated_at":"later"}', encoding="utf-8")
                self.assertEqual(common.fingerprint(), before)
                path.write_text('body: {columns: 2}\n', encoding="utf-8")
                self.assertNotEqual(common.fingerprint(), before)
            finally:
                common.ROOT = old

    def test_column_metrics_and_page_level_pause(self):
        tokens = layout_spec.apply_to_tokens({"typography": {"body": {"size": "9.5pt", "line_height": 1.7}}}, self.two)
        geo = layout_metrics.geometry(tokens)
        self.assertEqual(geo["columns"], 2)
        self.assertEqual(layout_metrics.column_of({"page": 3, "x": 222.52}, geo), 2)
        data = {"pars": [{"page": 2, "x": 48.19, "y": 150, "folio": 2, "chars": 200},
                         {"page": 2, "x": 214.02, "y": 150, "folio": 2, "chars": 200}],
                "headings": [{"page": 2, "x": 48.19, "y": 90, "folio": 2, "level": 1,
                              "outlined": True, "text": "chapter", "label": "ch-test"}],
                "figures": [{"page": 2, "x": 214.02, "y": 240, "folio": 2, "kind": "image", "label": "fig-test"}],
                "tables": [], "equations": [], "quotes": [], "code": [], "lists": [], "outlines": [],
                "marks": [{"page": 2, "x": 48.19, "y": 60, "folio": 2, "el": "chapter", "id": "ch-test", "number": "1", "label": "1"},
                          {"page": 2, "x": 214.02, "y": 240, "folio": 2, "el": "figure-geometry", "id": "fig-test",
                           "span": "1", "region": "column", "width_mm": "52.5"}],
                "ends": [{"page": 2, "x": 214.02, "y": 320, "folio": 2, "el": "figure"}]}
        metrics = layout_metrics.compute(data, tokens)
        page = metrics["pages"][1]
        self.assertEqual(metrics["area_accuracy"], "approximate")
        self.assertEqual(page["elements"][0]["column"], 2)
        self.assertEqual(page["elements"][0]["geometry"]["span"], "1")
        self.assertTrue(page["pause"])
        self.assertFalse(page["text_only"])

    @unittest.skipUnless(os.environ.get("TYPST") or shutil.which("typst"), "Typst not installed")
    def test_vertical_build_is_explicitly_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp)
            shutil.copytree(TEMPLATE, job, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            (job / "project.json").write_text(json.dumps({"format": "portable-publishing-job", "format_version": "0.2",
                                                      **PROJECT}), encoding="utf-8")
            vertical = layout_spec.resolve(PROJECT, {"genre": "essay"}, DESIGN,
                                           {"writing_mode": "vertical-rl", "vertical": {"enabled": True}})
            common.write_yaml(job / "plan/layout-spec.yaml", vertical)
            result = subprocess.run([sys.executable, "scripts/build.py"], cwd=job,
                                    capture_output=True, text=True, env=os.environ.copy())
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("LayoutSpec exceeds renderer capability", result.stderr)
            report = json.loads((job / "reports/layout-capabilities.json").read_text(encoding="utf-8"))
            self.assertEqual(report["renderers"]["pdf"]["status"], "unsupported")

    @unittest.skipUnless(os.environ.get("TYPST") or shutil.which("typst"), "Typst not installed")
    def test_specimen_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp)
            shutil.copytree(TEMPLATE / "scripts", job / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(TEMPLATE / "schemas", job / "schemas")
            (job / "tools").mkdir()
            shutil.copy2(TEMPLATE / "tools/layout-specimen.py", job / "tools/layout-specimen.py")
            (job / "project.json").write_text(json.dumps({"format": "portable-publishing-job", "format_version": "0.2",
                                                      **PROJECT}), encoding="utf-8")
            result = subprocess.run([sys.executable, "tools/layout-specimen.py"], cwd=job,
                                    capture_output=True, text=True, env=os.environ.copy())
            self.assertEqual(result.returncode, 0, result.stderr)
            pdf = job / "publish/layout-specimen.pdf"
            self.assertTrue(pdf.is_file())
            self.assertGreater(pdf.stat().st_size, 1000)


if __name__ == "__main__": unittest.main()

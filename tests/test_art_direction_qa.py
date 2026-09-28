"""P1-3 source, rendered-observation, PDF-vector and completion-gate QA."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "job-template/scripts"))
import art_direction_qa as qa
import design
import layout_spec
import orchestrator
import pdf_visual_probe
import style_bible
from common import write_yaml

PROJECT = {"book": {"language": "ja"}, "style_bible": {}}


class ArtDirectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        design_spec = design.load_design()
        profile = {"genre": "medical_science", "art_direction": {}}
        cls.med = style_bible.resolve(PROJECT, profile, design_spec)
        cls.crit = style_bible.resolve(PROJECT, {"genre": "criticism", "art_direction": {}}, design_spec)
        cls.layout = layout_spec.resolve(PROJECT, profile, design_spec, {"body": {"columns": 2, "gutter_mm": 6}})
        cls.tokens = style_bible.compile_tokens(cls.med, cls.layout, {"colors": {}, "typography": {}})

    def audit(self, observations=None, metrics=None, style=None, tokens=None):
        with tempfile.TemporaryDirectory() as tmp:
            return qa.audit(style or self.med, tokens or self.tokens, observations=observations, metrics=metrics,
                            root=tmp)

    def test_schema_and_clean_source(self):
        result = self.audit()
        self.assertEqual(result["summary"]["high"], 0)
        self.assertEqual(result["schema"], qa.SCHEMA)
        self.assertEqual(result["measurement"]["pdf_level"]["status"], "unavailable")
        self.assertTrue(all(set(item) >= {"id", "category", "severity", "page", "component", "expected", "observed", "detail", "suggested_fix"}
                            for item in result["checks"]))

    def test_palette_typography_line_and_near_color_drift(self):
        observed = [{"page": 42, "role": "caption", "component": "caption", "color": "#FA0000",
                     "font_size_pt": 8.5, "line_width_pt": 2.1}]
        issues = self.audit(observed)["checks"]
        categories = {item["category"] for item in issues}
        self.assertTrue({"palette_drift", "caption_drift", "line_weight_drift"} <= categories)
        self.assertEqual(next(i for i in issues if i["category"] == "caption_drift")["page"], 42)
        self.assertIn(("#167A8A", "#177A89"), qa._near_colors({"#167A8A", "#177A89"}, {}))

    def test_component_table_diagram_chart_spacing_and_hierarchy(self):
        observations = [
            {"page": 4, "component": "warning", "treatment": "plain-emphasis", "space_before_mm": 9,
             "font_size_pt": 9.5, "area_pt2": 100, "color": self.med["palette"]["warning"]},
            {"page": 4, "component": "definition", "font_size_pt": 22, "area_pt2": 16000,
             "color": self.med["palette"]["ink"]},
            {"page": 5, "component": "table", "table": {"mode": "wide"}},
            {"page": 6, "component": "diagram", "diagram": {"node_shape": "pill"}},
            {"page": 7, "component": "chart", "chart": {"grid_intensity": "none"}},
            {"page": 8, "component": "caption", "caption": {"figure_relationship": "relaxed"}},
        ]
        found = {item["category"] for item in self.audit(observations)["checks"]}
        self.assertTrue({"component_treatment_drift", "spacing_drift", "table_drift", "diagram_drift",
                         "chart_drift", "caption_drift", "hierarchy_drift"} <= found)

    def test_compiled_token_drift_is_high(self):
        tokens = copy.deepcopy(self.tokens)
        tokens["style"]["visual_grammar"]["components"]["definition"]["treatment"] = "filled-box"
        tokens["style"]["typography"]["body"]["size_pt"] = 11
        tokens["style"]["lines"]["normal_pt"] = 2
        checks = self.audit(tokens=tokens)["checks"]
        self.assertTrue({"component_treatment_drift", "typography_drift", "line_weight_drift"} <=
                        {item["category"] for item in checks if item["severity"] == "high"})

    def test_diagram_svg_edge_weight_and_label_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "source/assets/diagrams").mkdir(parents=True)
            (root / "source/assets/figures").mkdir(parents=True)
            (root / "source/assets/diagrams/example.yaml").write_text("id: example\n", encoding="utf-8")
            (root / "source/assets/figures/example.svg").write_text(
                '<svg><rect rx="3"/><path stroke="#123456" stroke-width="2.5"/>'
                '<text font-size="12">label</text></svg>', encoding="utf-8")
            result = qa.audit(self.med, self.tokens, root=root)
            drift = [item for item in result["checks"] if item["category"] == "diagram_drift"]
            self.assertEqual(len(drift), 4)

    def test_density_and_genre_sensitive_monotony(self):
        pages = [{"page": n, "region": "main", "nonprose_share": .3,
                  "elements": [{"kind": "callout", "sub": "warning"}]} for n in range(1, 9)]
        pages[0]["nonprose_share"] = .9
        metrics = {"pages": pages, "area_accuracy": "measured"}
        categories = {item["category"] for item in self.audit(metrics=metrics)["checks"]}
        self.assertIn("density_drift", categories)
        self.assertIn("visual_monotony", categories)

    def test_figure_pdf_roles_are_separate(self):
        metrics = {"pages": [{"page": 1, "elements": [{"kind": "figure", "label": "fig-one",
                     "x": 50, "y": 50, "end_y": 200}], "headings": []}]}
        runs = [{"x_pt": 75, "y_pt": y, "size_pt": size} for y, size in
                ((90, 8.0), (100, 8.0), (178, 7.5), (179, 7.5))]
        pdf = {"status": "measured", "pages": [{"page": 1, "text": runs}]}
        samples = qa._pdf_role_samples(metrics, pdf)
        self.assertEqual({item["role"]: item["font_size_pt"] for item in samples},
                         {"figure_label": 8.0, "caption": 7.5})

    def test_generated_image_reuse_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "plan").mkdir(); (root / "source/assets/generated").mkdir(parents=True)
            write_yaml(root / "plan/assets-plan.yaml", {"assets": [{"id": "fig-op", "type": "image"}]})
            request = {"art_direction": {"palette": self.med["palette"], "imagery": self.med["imagery"]},
                       "final_width_mm": 20, "placement": "column"}
            (root / "source/assets/generated/fig-op.request.json").write_text(json.dumps(request), encoding="utf-8")
            (root / "source/assets/generated/fig-op.json").write_text(json.dumps(
                {"kind": "generated-image", "asset_id": "fig-op", "generation_status": "generated",
                 "qa_status": "pass", "accepted": True, "file_path": "source/assets/images/fig-op.png"}), encoding="utf-8")
            metrics = {"pages": [{"page": n, "elements": [{"kind": "figure", "label": "fig-op", "x": 50,
                         "y": 80, "end_y": 140, "geometry": {"width_mm": 20, "placement": "column"}}]}
                         for n in (1, 2)]}
            result = qa.audit(self.med, self.tokens, metrics=metrics, root=root)
            self.assertTrue(any(item["category"] == "image_asset_drift" and "repeats" in item["detail"]
                                for item in result["checks"]))

    def test_cross_genre_difference_and_palette_only_failure(self):
        good = qa.compare_genres({"medical_science": self.med, "criticism": self.crit})
        self.assertEqual(good["summary"]["high"], 0)
        clone = copy.deepcopy(self.med); clone["palette"]["accent"] = "#123456"
        bad = qa.compare_genres({"medical_science": self.med, "criticism": clone})
        self.assertEqual(bad["summary"]["high"], 1)
        base_pdf = {"measurement": {"pdf_level": {"status": "measured", "font_sizes_pt": {"9.5": 8},
                                            "line_widths_pt": {"0.6": 2}, "strokes": 2, "fills": 1}}}
        same_pdf = qa.compare_genres({"medical_science": self.med, "criticism": self.crit},
                                      {"medical_science": base_pdf, "criticism": base_pdf})
        self.assertEqual(same_pdf["summary"]["high"], 1)
        different_pdf = copy.deepcopy(base_pdf)
        different_pdf["measurement"]["pdf_level"]["line_widths_pt"] = {"0.7": 2}
        measured = qa.compare_genres({"medical_science": self.med, "criticism": self.crit},
                                     {"medical_science": base_pdf, "criticism": different_pdf})
        self.assertEqual(measured["summary"]["high"], 0)
        self.assertTrue(measured["pdf_non_palette_differences"]["line_widths_pt"])

    def test_gate_high_medium_and_stale_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "reports").mkdir(); (root / "publish").mkdir()
            pdf = root / "publish/book.pdf"; pdf.write_bytes(b"pdf A")
            report = {"build_fingerprint": "fingerprint", "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                      "summary": {"high": 0, "medium": 2}}
            write_yaml(root / "reports/art-direction-check.yaml", report)
            project = {"outputs": {"pdf": True}}
            self.assertTrue(orchestrator.art_direction_gate(project, root, "fingerprint")["passed"])
            report["summary"]["high"] = 1
            write_yaml(root / "reports/art-direction-check.yaml", report)
            self.assertFalse(orchestrator.art_direction_gate(project, root, "fingerprint")["passed"])
            report["summary"]["high"] = 0
            write_yaml(root / "reports/art-direction-check.yaml", report)
            pdf.write_bytes(b"pdf B")
            self.assertFalse(orchestrator.art_direction_gate(project, root, "fingerprint")["fresh"])

    def test_medium_waiver_is_recorded_without_clearing_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "reports").mkdir()
            write_yaml(root / "reports/art-direction-waivers.yaml",
                       {"waivers": [{"category": "visual_monotony", "page": 1,
                                      "reason": "Deliberate repeated structure"}]})
            pages = [{"page": n, "region": "main", "nonprose_share": .3,
                      "elements": [{"kind": "callout", "sub": "warning"}]} for n in range(1, 9)]
            result = qa.run(self.med, self.tokens, metrics={"pages": pages}, root=root)
            self.assertGreaterEqual(result["summary"]["medium"], 1)
            self.assertEqual(result["summary"]["waived_medium"], 1)
            self.assertTrue(any(item.get("waiver") for item in result["checks"]))

    @unittest.skipUnless(os.environ.get("TYPST"), "Typst executable not configured")
    def test_specimen_pdf_qa_and_intentional_broken_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            subprocess.run([sys.executable, str(REPO / "tools/style-specimen.py"), "--output-dir", tmp],
                           cwd=REPO, check=True, capture_output=True, text=True)
            for genre in ("medical_science", "criticism"):
                from common import yaml_data
                result = yaml_data(folder / f"art-direction-check-{genre}.yaml")
                self.assertEqual(int(result["summary"]["high"]), 0)
                self.assertEqual(result["measurement"]["pdf_level"]["status"], "measured")
            source = folder / "style-specimen-medical_science.typ"
            broken = source.read_text(encoding="utf-8").replace('#let accent = rgb("#116B78")', '#let accent = rgb("#FA0000")')
            source.write_text(broken, encoding="utf-8")
            pdf = folder / "broken.pdf"
            subprocess.run([os.environ["TYPST"], "compile", str(source), str(pdf)], check=True, capture_output=True)
            probe = pdf_visual_probe.inspect(pdf)
            self.assertEqual(probe["status"], "measured")
            result = qa.audit(self.med, self.tokens, pdf_path=pdf, root=folder)
            self.assertTrue(any(item["category"] == "palette_drift" and item["scope"] == "pdf" for item in result["checks"]))
            self.assertGreaterEqual(result["summary"]["medium"] + result["summary"]["high"], 1)


if __name__ == "__main__": unittest.main()

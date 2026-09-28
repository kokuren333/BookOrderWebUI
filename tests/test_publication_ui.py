"""P1-UI: WebUI publication settings -> existing PublicationProfile / LayoutSpec / StyleBible resolvers.

The WebUI side is exercised through tests/webui_cli.ts (the real src/job.ts and src/publication.ts under Node), so
these tests check the actual payload the browser writes into project.json, and that the job scripts resolve it into
plan/profile.resolved.yaml, plan/layout-spec.yaml and plan/style-bible.yaml.

Run: python tests/test_publication_ui.py   (Node 22+ required for the WebUI cases; they skip without it)
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "job-template"
sys.path.insert(0, str(TEMPLATE / "scripts"))
import common
import design as design_module
import layout_spec
import publication_profile
import publication_request
import style_bible

NODE = shutil.which("node")
BASE = {"format": "portable-publishing-job", "format_version": "0.2",
        "book": {"title": "T", "description": "D", "target_readers": "R", "target_pages": 150, "language": "ja"},
        "outputs": {"canonical_markdown": True, "pdf": True}, "citations": {"style": "numeric"}}


def webui(command, *args):
    result = subprocess.run([NODE, "--experimental-strip-types", "--no-warnings", "tests/webui_cli.ts", command, *args],
                            cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    if result.returncode not in (0, 2): raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def payload(preset=None, **publication):
    return webui("preview", json.dumps([{"preset": preset, "publication": publication}]))[0]["payload"]


def project(extra=None):
    return {**json.loads(json.dumps(BASE)), **(extra or {})}


class Resolvers(unittest.TestCase):
    """B-J against the resolvers directly (payloads built by hand match the WebUI cases below)."""
    @classmethod
    def setUpClass(cls):
        cls.design = design_module.load_design()

    def resolve(self, extra, genre="general"):
        return layout_spec.resolve(project(extra), {"genre": genre}, self.design)

    def test_B_a5_one_column_preset(self):
        spec = self.resolve({"layout_preset": "standard-book"})
        self.assertEqual((spec["page_size"], spec["page"]["width_mm"], spec["page"]["height_mm"], spec["body"]["columns"]), ("A5", 148.0, 210.0, 1))
        self.assertEqual(layout_spec.summary(spec)["column_width_mm"], 111.0)

    def test_C_b5_two_columns_preset(self):
        spec = self.resolve({"layout_preset": "technical-reference"})
        self.assertEqual((spec["page_size"], spec["page"]["width_mm"], spec["body"]["columns"], spec["body"]["gutter_mm"]), ("B5", 176.0, 2, 6))
        self.assertEqual(spec["span_policy"], {"figure": "auto", "table": "auto"})
        self.assertEqual((spec["spans"]["figure"], spec["spans"]["table"]), (1, 1))
        self.assertEqual(layout_spec.summary(spec)["column_width_mm"], 67.0)

    def test_D_gutter_changes_column_width(self):
        narrow = self.resolve({"layout_preset": "technical-reference"})
        wide = self.resolve({"layout_preset": "technical-reference", "layout_spec": {"body": {"gutter_mm": 10}}})
        self.assertEqual(layout_spec.column_width_mm(narrow), 67.0)
        self.assertEqual(layout_spec.column_width_mm(wide), 65.0)

    def test_E_custom_page_dimensions(self):
        spec = self.resolve({"layout_spec": {"page_size": "custom", "page": {"width_mm": 182, "height_mm": 257}}})
        self.assertEqual((spec["page_size"], spec["page"]["width_mm"], spec["page"]["height_mm"]), ("custom", 182.0, 257.0))
        tokens = layout_spec.apply_to_tokens({}, spec)
        self.assertEqual((tokens["page"]["width_mm"], tokens["page"]["height_mm"]), (182.0, 257.0))
        import figure_spec, layout_metrics
        self.assertEqual(figure_spec.page_frame(tokens)["page_width_mm"], 182.0)
        self.assertAlmostEqual(layout_metrics.geometry(tokens)["width_pt"], 182 * 72 / 25.4, places=1)
        with self.assertRaises(layout_spec.LayoutSpecError) as bad:
            self.resolve({"layout_spec": {"page_size": "custom", "page": {"width_mm": 60, "height_mm": 257}}})
        self.assertIn("custom_page_invalid", [i["code"] for i in bad.exception.issues])

    def test_F_invalid_margins_rejected(self):
        with self.assertRaises(layout_spec.LayoutSpecError) as error:
            self.resolve({"layout_spec": {"page": {"margin_inner_mm": 80, "margin_outer_mm": 80}}})
        codes = {i["code"] for i in error.exception.issues}
        self.assertTrue({"margins_exceed_page", "body_width_insufficient"} <= codes, codes)
        self.assertTrue(all(i["field"].startswith("page.margin") for i in error.exception.issues))
        with self.assertRaises(layout_spec.LayoutSpecError) as error:
            self.resolve({"layout_spec": {"page": {"margin_top_mm": 90, "margin_bottom_mm": 90}}})
        self.assertIn("body_height_insufficient", {i["code"] for i in error.exception.issues})

    def test_G_invalid_two_column_geometry_rejected(self):
        for patch, code in (({"layout_preset": "compact-shinsho", "layout_spec": {"body": {"columns": 2, "gutter_mm": 18}}}, "column_too_narrow"),
                            ({"layout_preset": "technical-reference", "layout_spec": {"body": {"gutter_mm": 30}}}, "gutter_too_large"),
                            ({"layout_preset": "technical-reference", "layout_spec": {"body": {"gutter_mm": 1}}}, "gutter_too_small"),
                            ({"layout_preset": "technical-reference", "layout_spec": {"body": {"gutter_mm": 50}, "page": {"margin_inner_mm": 70, "margin_outer_mm": 70}}}, "gutter_consumes_body"),
                            ({"layout_preset": "magazine-mook", "layout_spec": {"body": {"columns": 1}}}, "span_policy_single_column")):
            with self.subTest(code=code):
                with self.assertRaises(layout_spec.LayoutSpecError) as error: self.resolve(patch)
                self.assertIn(code, [i["code"] for i in error.exception.issues])

    def test_H_profile_tier_and_genre(self):
        profile = publication_profile.resolve(project({"profile": {"tier": "long", "genre": "medical_science"}}), self.design)
        self.assertEqual((profile["id"], profile["tier"], profile["genre"]), ("long.medical_science", "long", "medical_science"))
        # A requested B5 layout counts for the characters-per-page model (not the Design Spec's A5).
        a5 = publication_profile.resolve(project({"profile": {"tier": "long"}}), self.design)
        b5 = publication_profile.resolve(project({"profile": {"tier": "long"}, "layout_preset": "technical-reference"}), self.design)
        self.assertEqual((a5["scale"]["page_size"], b5["scale"]["page_size"]), ("A5", "B5"))
        self.assertGreater(b5["scale"]["chars_per_text_page"], a5["scale"]["chars_per_text_page"])
        custom = publication_profile.resolve(project({"layout_spec": {"page_size": "custom", "page": {"width_mm": 182, "height_mm": 257}}}), self.design)
        self.assertEqual(custom["scale"]["page_size"], "custom")

    def test_I_style_preset_and_controls(self):
        base = style_bible.resolve(project(), {"genre": "technical", "art_direction": {}}, self.design)
        medical = style_bible.resolve(project({"style_preset": "medical-evidence"}), {"genre": "technical", "art_direction": {}}, self.design)
        self.assertEqual((medical["preset"], medical["genre"], medical["palette"]["accent"]), ("medical-evidence", "technical", "#116B78"))
        self.assertNotIn("preset", base)
        self.assertNotEqual(base["inputs_fingerprint"], medical["inputs_fingerprint"])
        tuned = style_bible.resolve(project({"style_preset": "medical-evidence", "style_controls": {
            "typography_scale": "large", "table_density": "generous", "callout_intensity": "strong", "chapter_opener": "academic",
            "visual_density": "airy", "visual_tone": "expressive"}}), {"genre": "technical", "art_direction": {}}, self.design)
        self.assertAlmostEqual(tuned["typography"]["body"]["size_pt"], round(medical["typography"]["body"]["size_pt"] * 1.06, 2))
        self.assertEqual((tuned["table"]["row_spacing"], tuned["visual_grammar"]["table"]["row_spacing"]), ("generous", "generous"))
        self.assertEqual(tuned["visual_grammar"]["components"]["key_point"]["treatment"], "filled-box")
        self.assertEqual(tuned["chapter_opener"]["title_style"], "academic")
        self.assertEqual(tuned["visual_grammar"]["rhythm"]["section_space"], "generous")
        self.assertGreater(tuned["spacing"]["large_mm"], medical["spacing"]["large_mm"])
        with self.assertRaises(ValueError): style_bible.resolve(project({"style_preset": "neon"}), {"genre": "technical"}, self.design)
        with self.assertRaises(ValueError): style_bible.resolve(project({"style_controls": {"table_density": "huge"}}), {"genre": "technical"}, self.design)

    def test_J_vertical_is_explicitly_unsupported(self):
        request = project({"layout_spec": {"writing_mode": "vertical-rl"}})
        report = publication_request.check(request, self.design)
        self.assertFalse(report["ok"])
        self.assertIn("vertical_unsupported", [i["code"] for i in report["issues"]])
        self.assertEqual(report["layout"]["writing_mode"], "vertical-rl")  # never silently horizontal
        with tempfile.TemporaryDirectory() as folder:
            original = layout_spec.PATH
            layout_spec.PATH = Path(folder) / "plan/layout-spec.yaml"
            try:
                with self.assertRaises(layout_spec.LayoutSpecError) as error:
                    layout_spec.load_or_create(request, {"genre": "general"}, self.design)
                self.assertEqual(error.exception.issues[0]["code"], "vertical_unsupported")
                self.assertFalse(layout_spec.PATH.exists())
            finally: layout_spec.PATH = original

    def test_default_request_keeps_existing_resolution(self):
        """No publication keys -> byte-identical LayoutSpec/StyleBible/profile to the pre-P1-UI resolution."""
        plain = project()
        self.assertEqual(layout_spec.resolve(plain, {"genre": "general"}, self.design),
                         layout_spec.resolve(plain, {"genre": "general"}, self.design, {}))
        spec = layout_spec.resolve(plain, {"genre": "general"}, self.design)
        self.assertNotIn("span_policy", spec)
        self.assertEqual((spec["page_size"], spec["body"]["columns"]), (self.design["page"]["size"], 1))
        style = style_bible.resolve(plain, {"genre": "general", "art_direction": {}}, self.design)
        self.assertNotIn("preset", style)
        self.assertTrue(publication_request.check(plain, self.design)["ok"])

    def test_auto_span_policy(self):
        import figure_spec
        spec = self.resolve({"layout_preset": "medical-scientific"})
        tokens = layout_spec.apply_to_tokens({}, spec)
        column = figure_spec.frames(tokens)["column"]["width_mm"]
        self.assertEqual(figure_spec.resolve({"width_mm": column - 5}, tokens, "diagram")["span"], 1)
        wide = figure_spec.resolve({"width_mm": column + 20}, tokens, "diagram")
        self.assertEqual((wide["span"], wide["span_source"]), ("full", "span_policy.auto"))
        self.assertEqual(figure_spec.resolve({"width_mm": column + 20, "span": 1}, tokens, "diagram")["span"], 1)  # explicit wins
        self.assertEqual(figure_spec.resolve({}, tokens, "table", {"table_columns": 6})["span"], "full")
        self.assertEqual(figure_spec.resolve({}, tokens, "table", {"table_columns": 3})["span"], 1)
        column_only = layout_spec.apply_to_tokens({}, self.resolve({"layout_preset": "medical-scientific", "layout_spec": {"span_policy": {"figure": "column"}}}))
        self.assertEqual(figure_spec.resolve({"width_mm": column + 20}, column_only, "diagram")["span"], 1)
        full = layout_spec.apply_to_tokens({}, self.resolve({"layout_preset": "magazine-mook"}))
        self.assertEqual(figure_spec.resolve({}, full, "diagram")["span"], "full")


@unittest.skipUnless(NODE, "node not installed")
class WebUIPayload(unittest.TestCase):
    """A, K, L, M and TS/Python parity through the real WebUI modules."""
    @classmethod
    def setUpClass(cls):
        cls.design = design_module.load_design()
        cls.tmp = Path(tempfile.mkdtemp(prefix="p1ui-"))

    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.tmp, ignore_errors=True)

    def job(self, name, spec):
        archive = self.tmp / f"{name}.zip"
        result = webui("zip", json.dumps(spec), str(archive))
        self.assertTrue(result["ok"], result)
        folder = self.tmp / name
        with zipfile.ZipFile(archive) as z: z.extractall(folder)
        return folder / "publishing-job", result

    def resolve_job(self, root):
        """What `bookorder goal` does first: resolve LayoutSpec and StyleBible, then the profile via the new state."""
        code = "import sys; sys.path.insert(0, 'scripts'); import orchestrator; orchestrator.load_state()"
        result = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, encoding="utf-8")
        return result

    def test_A_default_payload_is_unchanged(self):
        self.assertEqual(payload(), {})
        root, result = self.job("default", {})
        data = json.loads((root / "project.json").read_text(encoding="utf-8"))
        for key in ("profile", "layout_preset", "layout_spec", "style_preset", "style_controls"): self.assertNotIn(key, data)
        self.assertEqual(json.loads((root / "book.design.yaml").read_text(encoding="utf-8"))["page"]["size"], "A5")
        # No generated artifact ships with the template; each job resolves its own plan.
        self.assertFalse((root / "plan/layout-spec.yaml").exists())
        self.assertFalse((root / "plan/style-bible.yaml").exists())
        self.assertFalse(any((root / "reports").glob("*.yaml")))
        done = self.resolve_job(root)
        self.assertEqual(done.returncode, 0, done.stderr)
        spec = common.yaml_data(root / "plan/layout-spec.yaml")
        self.assertEqual(layout_spec.validate(spec), layout_spec.resolve(project(), {"genre": "general"}, self.design))

    def test_KLM_webui_payload_reaches_plan_artifacts(self):
        root, result = self.job("medical", {"preset": "medical-scientific", "publication": {
            "tier": "standard", "genre": "medical_science", "stylePreset": "medical-evidence", "gutterMm": 8,
            "styleControls": {"table_density": "compact"}}})
        self.assertEqual(result["payload"], {"profile": {"tier": "standard", "genre": "medical_science"}, "layout_preset": "medical-scientific",
                                             "layout_spec": {"body": {"gutter_mm": 8}}, "style_preset": "medical-evidence",
                                             "style_controls": {"table_density": "compact"}})
        self.assertEqual(json.loads((root / "book.design.yaml").read_text(encoding="utf-8"))["page"]["size"], "B5")
        done = self.resolve_job(root)
        self.assertEqual(done.returncode, 0, done.stderr)
        spec = common.yaml_data(root / "plan/layout-spec.yaml")             # K
        self.assertEqual((spec["page_size"], str(spec["body"]["columns"]), str(spec["body"]["gutter_mm"])), ("B5", "2", "8"))
        self.assertEqual(spec["span_policy"], {"figure": "auto", "table": "auto"})
        profile = common.yaml_data(root / "plan/profile.resolved.yaml")     # L
        self.assertEqual((profile["tier"], profile["genre"], profile["id"]), ("standard", "medical_science", "standard.medical_science"))
        style = common.yaml_data(root / "plan/style-bible.yaml")            # M
        self.assertEqual((style["preset"], style["genre"], style["palette"]["accent"]), ("medical-evidence", "medical_science", "#116B78"))
        self.assertEqual(style["table"]["row_spacing"], "compact")
        check = subprocess.run([sys.executable, "scripts/cli.py", "publication", "--json"], cwd=root, capture_output=True, text=True, encoding="utf-8")
        report = json.loads(check.stdout)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["layout"]["column_width_mm"], 67.0)  # (176-19-15-8)/2

    def test_custom_and_invalid_payloads(self):
        root, result = self.job("custom", {"preset": "custom", "publication": {"pageSize": "custom", "customWidthMm": 182, "customHeightMm": 257, "columns": 2,
                                                                              "figureSpan": "auto", "tableSpan": "full"}})
        self.assertEqual(result["payload"]["layout_spec"]["page"]["width_mm"], 182)
        self.assertEqual(self.resolve_job(root).returncode, 0)
        spec = common.yaml_data(root / "plan/layout-spec.yaml")
        self.assertEqual((spec["page_size"], str(spec["page"]["width_mm"]), spec["spans"]["table"]), ("custom", "182", "full"))
        rejected = webui("zip", json.dumps({"preset": "compact-shinsho", "publication": {"columns": 2, "gutterMm": 18}}), str(self.tmp / "bad.zip"))
        self.assertFalse(rejected["ok"])
        self.assertTrue(any("2段組みには狭すぎます" in e for e in rejected["errors"]), rejected)
        vertical = webui("zip", json.dumps({"preset": "standard-book", "publication": {"writingMode": "vertical-rl"}}), str(self.tmp / "v.zip"))
        self.assertFalse(vertical["ok"])
        self.assertTrue(any("縦書き" in e for e in vertical["errors"]), vertical)

    def test_webui_preview_matches_resolver(self):
        """The live summary/early warnings (TypeScript) agree with layout_spec (Python) on values and issue codes."""
        cases = [{"preset": "theme"}, {"preset": "standard-book"}, {"preset": "technical-reference"}, {"preset": "medical-scientific"},
                 {"preset": "magazine-mook"}, {"preset": "compact-shinsho"}, {"preset": "technical-reference", "publication": {"gutterMm": 10}},
                 {"preset": "custom", "publication": {"pageSize": "custom", "customWidthMm": 182, "customHeightMm": 257, "columns": 2}},
                 {"preset": "standard-book", "publication": {"pageSize": "B6", "columns": 2}},
                 {"preset": "compact-shinsho", "publication": {"columns": 2, "gutterMm": 18}},
                 {"preset": "technical-reference", "publication": {"gutterMm": 50, "margins": {"top": 18, "bottom": 20, "inner": 70, "outer": 70}}},
                 {"preset": "technical-reference", "publication": {"gutterMm": 30}},
                 {"preset": "technical-reference", "publication": {"gutterMm": 1}},
                 {"preset": "standard-book", "publication": {"margins": {"top": 20, "bottom": 20, "inner": 60, "outer": 60}}},
                 {"preset": "standard-book", "publication": {"margins": {"top": 20, "bottom": 20, "inner": 100, "outer": 100}}},
                 {"preset": "custom", "publication": {"pageSize": "custom", "customWidthMm": 70, "customHeightMm": 200}},
                 {"preset": "magazine-mook", "publication": {"columns": 1}},
                 {"preset": "standard-book", "publication": {"writingMode": "vertical-rl"}},
                 {"preset": "standard-book", "publication": {"orientation": "landscape"}}]
        for case, ts in zip(cases, webui("preview", json.dumps(cases))):
            with self.subTest(case=case):
                request = project(ts["payload"])
                python_codes = []
                try:
                    spec = layout_spec.resolve(request, {"genre": "general"}, self.design)
                    python_codes = [i["code"] for i in layout_spec.renderer_issues(spec)]
                    summary = layout_spec.summary(spec)
                    preview = ts["preview"]
                    self.assertEqual((summary["width_mm"], summary["height_mm"]), (preview["widthMm"], preview["heightMm"]))
                    self.assertEqual((summary["columns"], summary["gutter_mm"]), (preview["columns"], preview["gutterMm"]))
                    self.assertEqual((summary["body_width_mm"], summary["body_height_mm"], summary["column_width_mm"]),
                                     (preview["bodyWidthMm"], preview["bodyHeightMm"], preview["columnWidthMm"]))
                except layout_spec.LayoutSpecError as error:
                    python_codes = [i["code"] for i in error.issues]
                self.assertEqual(sorted(set(python_codes)), sorted({i["code"] for i in ts["preview"]["issues"]}))


if __name__ == "__main__": unittest.main()

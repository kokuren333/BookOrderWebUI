"""P1-4 routing, provider, provenance and print QA."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "job-template/scripts"))
import design
import image_assets as images
import layout_spec
import orchestrator
import style_bible
import visual_review


class ImageAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        project = {"book": {"language": "ja"}, "style_bible": {}}
        profile = {"genre": "medical_science", "art_direction": {"generative_images":
                   {"allowed": ["chapter_opener", "editorial_illustration"], "max_total": 2}}}
        spec = design.load_design()
        cls.style = style_bible.resolve(project, profile, spec)
        cls.layout = layout_spec.resolve(project, profile, spec)

    def asset(self, ident="fig-opener"):
        return {"id": ident, "type": "image", "chapter": "ch-1", "device": ident,
                "path": f"source/assets/images/{ident}.png", "role": "chapter_opener",
                "purpose": "Introduce the chapter with a conceptual visual metaphor",
                "subject": "abstract transition between ideas", "caption": "A conceptual transition",
                "information_shape": {"kind": "abstract"}, "factual_basis": "illustrative",
                "factuality": "conceptual", "source_ids": [],
                "geometry": {"placement": "column", "width_mm": 20, "aspect_ratio": "3:2"},
                "improvement_claim": {"kinds": ["orient_reader"], "statement": "Introduce the chapter's conceptual transition before the technical explanation."}}

    def test_routing_keeps_facts_out_of_imagegen(self):
        self.assertEqual(visual_review.route({"kind": "quantity", "values": 6})[0], "chart")
        self.assertEqual(visual_review.route({"kind": "comparison", "items": 3, "attributes": 3})[0], "table")
        self.assertEqual(visual_review.route({"kind": "hierarchy", "levels": 3})[0], "diagram.hierarchy")
        self.assertEqual(visual_review.route({"kind": "abstract"})[0], "image.chapter_opener")
        factual = self.asset(); factual["factuality"] = "factual"
        candidate = visual_review.candidate(factual)
        self.assertIn("factual_image_not_generative", [r["code"] for r in visual_review.rules(candidate)])
        with self.assertRaisesRegex(ValueError, "Factual visual"):
            images.request_from_asset(factual, copy.deepcopy(self.style), self.layout)

    def test_request_inherits_style_layout_and_forbids_text(self):
        request = images.request_from_asset(self.asset(), copy.deepcopy(self.style), self.layout, provider="fake")
        self.assertEqual(request["schema"], images.REQUEST_SCHEMA)
        self.assertEqual(request["typography_policy"], "forbidden")
        self.assertIn("labels", request["must_not_show"])
        self.assertEqual(request["art_direction"]["palette"], self.style["palette"])
        self.assertEqual(request["slot_id"], "fig-opener")
        self.assertAlmostEqual(request["final_width_mm"], 20)
        self.assertAlmostEqual(request["final_height_mm"], 13.33, places=1)

    def test_pending_provider_blocks_required_without_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); asset = self.asset()
            made = images.prepare([asset], {asset["id"]: "accepted"}, copy.deepcopy(self.style), self.layout,
                                  {"image_generation": {}}, root)
            self.assertEqual(made[0]["generation_status"], "pending_provider")
            self.assertFalse((root / asset["path"]).exists())
            check = images.check([asset], {asset["id"]: "accepted"}, root=root)
            self.assertGreater(check["summary"]["high"], 0)
            self.assertFalse(orchestrator.image_asset_gate([asset], {asset["id"]: "accepted"}, root)["passed"])

    def test_fake_is_deterministic_and_provenance_is_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); asset = self.asset(); project = {"image_generation": {"provider": "fake"}}
            images.prepare([asset], {asset["id"]: "accepted"}, copy.deepcopy(self.style), self.layout, project, root)
            path = root / asset["path"]; first = path.read_bytes()
            meta_path = root / "source/assets/generated/fig-opener.json"
            first_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            images.prepare([asset], {asset["id"]: "accepted"}, copy.deepcopy(self.style), self.layout, project, root)
            self.assertEqual(path.read_bytes(), first)
            chunks = []; at = 8
            while at + 12 <= len(first):
                length = struct.unpack(">I", first[at:at+4])[0]
                if first[at+4:at+8] == b"IDAT": chunks.append(first[at+8:at+8+length])
                at += 12 + length
            raw = zlib.decompress(b"".join(chunks))
            width = first_meta["dimensions_px"]["width"]
            sample = tuple(raw[1 + width * 3 + 1:1 + width * 3 + 4])
            allowed = {tuple(int(color[i:i+2], 16) for i in (1, 3, 5)) for color in self.style["palette"].values()}
            self.assertIn(sample, allowed)
            self.assertEqual(json.loads(meta_path.read_text(encoding="utf-8"))["created_at"], first_meta["created_at"])
            self.assertEqual(first_meta["provider"], "fake")
            self.assertEqual(first_meta["prompt_version"], images.PROMPT_VERSION)
            self.assertIsInstance(first_meta["seed"], int)
            self.assertEqual(images.check([asset], {asset["id"]: "accepted"}, root=root)["summary"]["high"], 0)
            accepted = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertTrue(accepted["accepted"])
            self.assertGreaterEqual(accepted["effective_dpi"], images.MIN_DPI)
            self.assertTrue(orchestrator.image_asset_gate([asset], {asset["id"]: "accepted"}, root)["passed"])

    def test_missing_invalid_and_low_dpi_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); asset = self.asset(); project = {"image_generation": {"provider": "fake"}}
            images.prepare([asset], {asset["id"]: "accepted"}, copy.deepcopy(self.style), self.layout, project, root)
            path = root / asset["path"]
            path.write_bytes(b"bad image")
            self.assertGreater(images.check([asset], {asset["id"]: "accepted"}, root=root)["summary"]["high"], 0)
            request = images.request_from_asset(asset, copy.deepcopy(self.style), self.layout, provider="fake")
            small = dict(request, final_width_mm=2, final_height_mm=1.33)
            path.write_bytes(images.FakeImageProvider().generate(small)["bytes"])
            check = images.check([asset], {asset["id"]: "accepted"}, root=root)
            self.assertTrue(any("DPI" in item["detail"] for item in check["checks"]))
            path.unlink()
            self.assertGreater(images.check([asset], {asset["id"]: "accepted"}, root=root)["summary"]["high"], 0)

    def test_rejected_never_reaches_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); asset = self.asset()
            self.assertEqual(images.prepare([asset], {asset["id"]: "rejected"}, copy.deepcopy(self.style), self.layout,
                                            {"image_generation": {"provider": "fake"}}, root), [])
            self.assertFalse((root / asset["path"]).exists())
            report = images.check([asset], {asset["id"]: "rejected"}, root=root)
            self.assertEqual(report["routed_to_imagegen"], [])

    def test_optional_pending_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); asset = self.asset(); asset["optional"] = True
            images.prepare([asset], {asset["id"]: "accepted"}, copy.deepcopy(self.style), self.layout,
                           {"image_generation": {}}, root)
            result = images.check([asset], {asset["id"]: "accepted"}, root=root)
            self.assertEqual(result["summary"]["high"], 0)
            self.assertGreater(result["summary"]["medium"], 0)


if __name__ == "__main__": unittest.main()

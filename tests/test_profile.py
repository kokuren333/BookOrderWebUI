"""PublicationProfile (P0-3): tier → genre → project overrides, validation, compatibility, reproducibility.

Needs Pandoc (BookOrder reads YAML with it): PANDOC or pandoc on PATH.
Usage: python tests/test_profile.py
"""
import copy
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "job-template"
sys.path.insert(0, str(TEMPLATE / "scripts"))
import pacing  # noqa: E402
import publication_profile as pp  # noqa: E402

A5 = {"page": {"size": "A5"}, "layout": {"density": "standard"}}
BUILD_EXISTED = (TEMPLATE / ".build").exists()


def pandoc():
    found = os.environ.get("PANDOC") or shutil.which("pandoc")
    return found if found and Path(found).is_file() else None


def project(pages=None, profile=None, **extra):
    book = {"title": "t", "language": "ja", **({"target_pages": pages} if pages else {})}
    return {"book": book, **({"profile": profile} if profile is not None else {}), **extra}


def tearDownModule():
    # YAML parsing caches under job-template/.build; it must not stay in the shipped template.
    if not BUILD_EXISTED: shutil.rmtree(TEMPLATE / ".build", ignore_errors=True)


@unittest.skipUnless(pandoc(), "Pandoc not available (set PANDOC)")
class Resolution(unittest.TestCase):
    def test_short_medical_science(self):
        p = pp.resolve(project(50, {"tier": "short", "genre": "medical_science"}), A5)
        self.assertEqual((p["id"], p["tier"], p["genre"]), ("short.medical_science", "short", "medical_science"))
        self.assertEqual(p["resolved_from"][:2], ["profiles/tiers/short.yaml", "profiles/genres/medical_science.yaml"])
        self.assertEqual(p["devices"]["visuals_per_10k"], {"min": 2.2, "target": 3.3, "max": 6.6})
        self.assertEqual(p["devices"]["pull_quotes_per_chapter"]["max"], 0)
        self.assertEqual(p["structure"]["chapter_end"], ["key_points", "check_questions"])
        self.assertEqual((p["citations"]["style"], p["citations"]["inline_markers_per_page_max"]), ("numeric", 2.0))
        self.assertEqual(p["rhythm"]["max_text_only_pages"], 3)

    def test_long_criticism(self):
        p = pp.resolve(project(profile={"tier": "long", "genre": "criticism"}), A5)
        self.assertEqual(p["scale"]["target_body_chars"], 150000, "no page target: the tier's body size")
        self.assertEqual(p["source"]["body_chars_from"], "tier")
        self.assertEqual(p["devices"]["visuals_per_10k"], {"min": 1.44, "target": 2.0, "max": 4.0})
        self.assertEqual(p["devices"]["pull_quotes_per_chapter"]["min"], 1)
        self.assertEqual(p["citations"]["style"], "endnotes_per_chapter")
        self.assertEqual(p["structure"]["paragraph_chars_max"], 495)
        self.assertEqual((p["rhythm"]["max_text_only_pages"], p["art_direction"]["weight"]), (4, "strong"))
        self.assertGreater(p["scale"]["target_pages"], 200)

    def test_genres_differ(self):
        seen = {}
        for genre in pp.GENRES:
            p = pp.resolve(project(profile={"tier": "standard", "genre": genre}), A5)
            seen[genre] = (p["devices"]["visuals_per_10k"]["target"], p["devices"]["callouts_per_chapter"]["target"],
                           p["citations"]["style"], tuple(p["structure"]["chapter_end"]), p["rhythm"]["max_text_only_pages"])
        self.assertEqual(len(set(seen.values())), len(pp.GENRES))
        self.assertLess(seen["essay"][0], seen["criticism"][0]); self.assertLess(seen["criticism"][0], seen["practical"][0])
        self.assertEqual(seen["essay"][4], 6, "essays may run longer between pauses")

    def test_every_tier_and_genre_is_valid(self):
        for tier in pp.TIERS:
            for genre in (None,) + pp.GENRES:
                p = pp.resolve(project(profile={"tier": tier, **({"genre": genre} if genre else {})}), A5)
                self.assertEqual(pp.validate(p), [], (tier, genre))

    def test_user_overrides(self):
        spec = {"tier": "long", "genre": "criticism", "overrides": {"rhythm": {"max_text_only_pages": 5},
                "structure.chapters": {"min": 7, "target": 12, "max": 14},
                "devices.visuals_per_10k": {"min": 2.0, "target": 3.0, "max": 5.0}, "scale": {"target_body_chars": 90000}}}
        p = pp.resolve(project(300, spec), A5)
        self.assertEqual(p["rhythm"]["max_text_only_pages"], 5)
        self.assertEqual(p["devices"]["visuals_per_10k"]["min"], 2.0)
        self.assertEqual((p["scale"]["target_body_chars"], p["source"]["body_chars_from"]), (90000, "override"))
        self.assertIn("project.json overrides", p["resolved_from"])
        self.assertEqual(p["source"]["user_overrides"]["rhythm.max_text_only_pages"], 5)
        self.assertEqual(pp.scale(p)["maximum_chapters"], 14, "outline gate uses the resolved override")

    def test_legacy_settings_become_overrides(self):
        p = pp.resolve(project(300, scale={"target_characters": 100000, "minimum_ratio": 0.9}, pacing={"max_text_only_pages": 3}), A5)
        self.assertEqual((p["scale"]["target_body_chars"], p["scale"]["minimum_ratio"], p["rhythm"]["max_text_only_pages"]), (100000, 0.9, 3))

    def test_invalid_profiles(self):
        with self.assertRaisesRegex(ValueError, "tier must be one of"): pp.resolve(project(profile="huge"), A5)
        with self.assertRaisesRegex(ValueError, "genre must be one of"): pp.resolve(project(profile={"tier": "long", "genre": "poetry"}), A5)
        bad = {"structure.paragraph_chars_max": 50, "devices.visuals_per_10k": {"min": 4, "target": 3, "max": 5},
               "scale.nonprose_share_target": 1.2, "structure.chapters": {"min": 0, "target": 5, "max": 10},
               "structure.heading_depth_max": 6, "rhythm.max_text_only_pages": 0, "citations.style": "footnotes"}
        for path, value in bad.items():
            with self.assertRaises(ValueError, msg=path) as caught: pp.resolve(project(profile={"tier": "long", "overrides": {path: value}}), A5)
            self.assertIn(path.split(".")[0], str(caught.exception))
        base = pp.resolve(project(profile="long"), A5)
        broken = copy.deepcopy(base); broken["devices"]["surprise"] = 1
        self.assertIn("devices.surprise: unknown setting", pp.validate(broken))
        broken = copy.deepcopy(base); del broken["rhythm"]["max_text_only_pages"]
        self.assertIn("rhythm.max_text_only_pages: missing", pp.validate(broken))
        with self.assertRaisesRegex(ValueError, "unknown section"): pp.resolve(project(profile={"tier": "long", "overrides": {"layout.x": 1}}), A5)


@unittest.skipUnless(pandoc(), "Pandoc not available (set PANDOC)")
class Compatibility(unittest.TestCase):
    def test_short_50(self):
        p = pp.resolve(project(50), A5)
        self.assertEqual((p["id"], p["scale"]["target_body_chars"]), ("short.general", 24150))
        self.assertLessEqual(abs(p["scale"]["target_pages"] - 50), 1)
        self.assertIn("book.target_pages=50 (compatibility)", p["source"]["notes"][0])
        self.assertEqual(pp.scale(p)["minimum_characters"], 19320)

    def test_long_300(self):
        p = pp.resolve(project(300), A5)
        self.assertEqual((p["id"], p["scale"]["target_body_chars"], p["rhythm"]["max_text_only_pages"]), ("long.general", 162255, 4))
        self.assertLessEqual(abs(p["scale"]["target_pages"] - 300), 1)
        self.assertEqual(pp.scale(p)["minimum_chapters"], 7)

    def test_profile_tier_with_page_target_keeps_the_size(self):
        p = pp.resolve(project(300, "standard"), A5)
        self.assertEqual(p["tier"], "standard"); self.assertEqual(p["scale"]["target_body_chars"], 157248)  # standard: 28% non-prose, 5% back matter


@unittest.skipUnless(pandoc(), "Pandoc not available (set PANDOC)")
class Reproducibility(unittest.TestCase):
    def test_same_inputs_same_profile_and_fingerprint_tracks_changes(self):
        base = pp.resolve(project(300, {"tier": "long", "genre": "criticism"}), A5)
        self.assertEqual(base, pp.resolve(project(300, {"tier": "long", "genre": "criticism"}), A5))
        variants = [project(300, {"tier": "long", "genre": "essay"}), project(300, {"tier": "long", "genre": "criticism", "overrides": {"rhythm.max_text_only_pages": 5}}),
                    project(301, {"tier": "long", "genre": "criticism"})]
        prints = {pp.resolve(v, A5)["inputs_fingerprint"] for v in variants} | {pp.resolve(project(300, {"tier": "long", "genre": "criticism"}), {"page": {"size": "B5"}})["inputs_fingerprint"]}
        self.assertEqual(len(prints), 4); self.assertNotIn(base["inputs_fingerprint"], prints)

    def test_written_file_round_trips(self):
        folder = Path(tempfile.mkdtemp()); saved = pp.RESOLVED
        try:
            pp.RESOLVED = folder / "profile.resolved.yaml"
            p = pp.resolve(project(50, {"tier": "short", "genre": "medical_science"}), A5)
            pp.write(p); first = pp.RESOLVED.read_text(encoding="utf-8")
            self.assertEqual(pp.load_resolved(), p)
            pp.write(pp.resolve(project(50, {"tier": "short", "genre": "medical_science"}), A5))
            self.assertEqual(pp.RESOLVED.read_text(encoding="utf-8"), first, "byte-identical on re-resolution")
            self.assertLess(first.index("scale:"), first.index("structure:"))
        finally:
            pp.RESOLVED = saved; shutil.rmtree(folder)


@unittest.skipUnless(pandoc(), "Pandoc not available (set PANDOC)")
class PacingReadsProfile(unittest.TestCase):
    def test_limit_comes_from_the_resolved_file(self):
        folder = Path(tempfile.mkdtemp()); saved = pp.RESOLVED
        try:
            pp.RESOLVED = folder / "profile.resolved.yaml"
            pp.write(pp.resolve(project(300, {"tier": "long", "overrides": {"rhythm.max_text_only_pages": 5}}), A5))
            # Other test modules reload a temporary job's publication_profile into sys.modules.
            # Match this test's pacing import with its own profile module for the call.
            with patch.dict(sys.modules, {"publication_profile": pp}):
                limits = pacing.limits(project(50))  # the page target alone would say short/3
            self.assertEqual((limits["tier"], limits["max_text_only_pages"], limits["profile"]), ("long", 5, "long.general"))
            self.assertIn("plan/profile.resolved.yaml", limits["source"])
        finally:
            pp.RESOLVED = saved; shutil.rmtree(folder)

    def test_resolves_in_memory_then_falls_back(self):
        self.assertEqual(pacing.limits(project(profile="monograph"))["max_text_only_pages"], 6)
        broken = pacing.limits(project(50, profile="not-a-tier"))
        self.assertEqual((broken["tier"], broken["max_text_only_pages"], broken["profile"]), ("short", 3, None))
        self.assertIn("compatibility fallback", broken["source"])

    def test_figure_policy_from_profile(self):
        import figure_spec
        policy = figure_spec.profile_policy(pp.resolve(project(profile={"tier": "long", "genre": "technical"}), A5))
        self.assertEqual(policy["generative_images"], {"allowed": [], "max_total": 0})
        self.assertEqual(policy["profile"], "long.technical")


if __name__ == "__main__":
    unittest.main(verbosity=2)

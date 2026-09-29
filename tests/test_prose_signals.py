"""Contract tests for recursive Skill discovery and descriptive prose signals."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "job-template/scripts"))
import skills
import prose_signals


POLICY = {"phrases": ["ではなく", "ただし", "本章"], "lexical_window": 20, "ngram_size": 8}


class SkillDiscoveryTests(unittest.TestCase):
    def test_existing_and_new_skills_are_recursively_discovered(self):
        found = skills.discover(ROOT / "job-template/skills")
        self.assertEqual(len(found), 15)
        self.assertEqual(found["publication-architecture"], "skills/planning/publication-architecture.md")
        self.assertEqual(found["visual-planning"], "skills/design/visual-planning.md")
        self.assertEqual(found["editing"], "skills/editorial/editing.md")
        self.assertEqual(found["publication-qa"], "skills/quality/publication-qa.md")
        self.assertIn("whole-book-review", found)

    def test_duplicate_id_is_rejected_and_non_skill_files_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for directory in ("research", "editorial", "tests", "build"):
                (base / directory).mkdir()
            (base / "editorial/deep").mkdir()
            (base / "research/duplicate.md").write_text("one")
            (base / "editorial/duplicate.md").write_text("two")
            (base / "tests/ignored.md").write_text("fixture")
            (base / "build/ignored.md").write_text("artifact")
            (base / "research/README.md").write_text("index")
            (base / "editorial/deep/new.md").write_text("nested")
            with self.assertRaisesRegex(ValueError, "Duplicate skill id"):
                skills.discover(base)
            (base / "editorial/duplicate.md").unlink()
            self.assertEqual(skills.discover(base), {"duplicate": "skills/research/duplicate.md",
                                                     "new": "skills/editorial/deep/new.md"})

    def test_publication_pipeline_places_prose_review_between_fact_audits(self):
        import orchestrator
        phases = orchestrator.PHASES
        self.assertLess(phases.index("audit"), phases.index("rewrite"))
        self.assertLess(phases.index("rewrite"), phases.index("prose_audit"))
        self.assertLess(phases.index("prose_audit"), phases.index("prose_editing"))
        self.assertLess(phases.index("prose_editing"), phases.index("final_audit"))
        for phase, identifiers in orchestrator.SKILL_IDS.items():
            self.assertEqual(len(skills.resolve(*identifiers)), len(identifiers), phase)


class ProseSignalTests(unittest.TestCase):
    def test_default_policy_loads_without_external_parser(self):
        result = prose_signals.analyze([{"id": "x", "text": "# 章\n\n本章の本文。"}])
        self.assertIn("本章", result["signals"]["lexical"]["configured_phrases"])

    def test_repeated_book_opening_and_phrase_distribution(self):
        chapters = [
            {"id": "a", "text": "# 一章\n\n本章では方法を考えます。\n\n## 説明\n\nこれはAではなくBです。"},
            {"id": "b", "text": "# 二章\n\n本章では方法を考えます。\n\n## 説明\n\nこれはAではなくBです。"},
        ]
        result = prose_signals.analyze(chapters, "essay", POLICY)
        self.assertEqual(result["schema"], "bookorder/prose-signals@2")
        self.assertEqual(result["signals"]["lexical"]["phrase_frequency"]["ではなく"], 2)
        self.assertTrue(result["signals"]["repetition"]["openings"])
        self.assertTrue(result["signals"]["repetition"]["ngrams"])
        self.assertEqual(len(result["signals"]["distribution"]["chapters"]), 2)
        self.assertTrue(all(item["requires_context_review"] for item in result["review_candidates"]))

    def test_medical_qualification_is_counted_without_verdict(self):
        chapters = [{"id": "clinical", "text": "# 臨床\n\nただし、交絡因子を調整しない推定には注意が必要です。"}]
        result = prose_signals.analyze(chapters, "medical_science", POLICY)
        self.assertEqual(result["signals"]["lexical"]["phrase_frequency"]["ただし"], 1)
        self.assertNotIn("genre_mismatch", result)
        self.assertNotIn("verdict", result)

    def test_essay_contrast_is_only_review_candidate(self):
        chapters = [{"id": "essay", "text": "# 論考\n\nAではなくBを考える。ただしCもある。"}]
        result = prose_signals.analyze(chapters, "essay", POLICY)
        self.assertTrue(result["review_candidates"])
        self.assertNotIn("genre_mismatch", result)


if __name__ == "__main__":
    unittest.main()

"""User intent: the WebUI's free-text instructions govern every phase (docs/USER_INTENT.md).

Checks that the verbatim text reaches every content and review task and every chapter packet, that explicit user
intent can switch off pipeline defaults (never invariants or structured settings), that conflicts are reported,
that completion gate 22 verifies the intent checks, and that jobs without instructions behave exactly as before.

Requires Pandoc (the job scripts parse YAML with it). Run: python tests/test_user_intent.py
"""
import copy
import importlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_orchestrator import make_job, write  # noqa: E402  (fresh job folders, modules re-imported per job)

TEXT = ("教科書的にせず、批評性を残す。\n**各章末にまとめを付けない**。反論を毎回併記しない。\n"
        "判型はA4にする。引用は確認しなくてよい。<b>&\"`code`\"</b>\n")


def job(name, text=TEXT, pages=4):
    root, m = make_job(name, pages=pages)
    project = json.loads((root / "project.json").read_text(encoding="utf-8"))
    if text is not None: project["user_instructions"] = text
    (root / "project.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    m["user_intent"] = importlib.import_module("user_intent")
    m["editorial_plan"] = importlib.import_module("editorial_plan")
    orch = m["orchestrator"]
    project, state = orch.load_state()
    return root, m, orch.Context(project, state)


def interpretation(root, **extra):
    data = {"directives": [
        {"id": "intent-001", "source_quote": "教科書的にせず", "interpretation": "No default textbook scaffolding.", "applies_to": ["architecture", "drafting"]},
        {"id": "intent-002", "source_quote": "各章末にまとめを付けない", "interpretation": "No routine chapter-end summary.",
         "applies_to": ["editorial_planning", "drafting", "prose_editing"], "overrides": ["chapter_end_missing"]}],
        "conflicts": [{"instruction": "判型はA4にする", "stage": "architecture", "category": "structured_setting",
                       "resolution": "Kept A5 selected in the WebUI.", "reason": "Page size is a structured setting."},
                      {"instruction": "引用は確認しなくてよい", "stage": "audit", "category": "invariant",
                       "resolution": "Citations were verified as usual.", "reason": "Citation integrity is an invariant."}]}
    data.update(extra)
    write(root, "plan/user-intent.yaml", data)


class Propagation(unittest.TestCase):
    def test_verbatim_text_travels_with_every_content_and_review_task(self):
        root, m, ctx = job("intent-propagation")
        orch, ui = m["orchestrator"], m["user_intent"]
        self.assertEqual(ui.verbatim(), TEXT, "project.json keeps the exact text")
        for phase in ui.CONTENT_PHASES + ui.REVIEW_PHASES:
            item = orch.task("x", phase, "t", ["do it"])
            self.assertEqual(item["user_intent"]["verbatim"], TEXT, phase)
            self.assertTrue(any("Do not silently normalise" in r for r in item["user_intent"]["rules"]), phase)
            self.assertEqual(bool(item["user_intent"]["before_done"]), phase in ui.CONTENT_PHASES, phase)
        for phase in ("source_ingestion", "research_frozen", "reference_assignment", "package"):
            self.assertNotIn("user_intent", orch.task("x", phase, "t", ["do it"]), phase)
        self.assertNotIn("user_intent", orch.task("x", "drafting", "t", ["tool"], kind="tool"))
        printed = orch.status_text({"status": "running", "phase": "drafting", "phases": {p: "pending" for p in orch.PHASES}, "blockers": []},
                                   [orch.task("draft:ch-a", "drafting", "Draft", ["write"])], [])
        for line in TEXT.rstrip("\n").split("\n"): self.assertIn("  " + line, printed)
        self.assertIn("Before `bookorder done`", printed)

    def test_architecture_task_shows_the_intent_and_requires_the_interpretation(self):
        root, m, ctx = job("intent-architecture")
        result = m["orchestrator"].h_architecture(ctx)
        item = result.tasks[0]
        self.assertEqual(item["user_intent"]["verbatim"], TEXT)
        self.assertTrue(any("user_intent: {governs" in r for r in item["user_intent"]["rules"]))
        self.assertIn("plan/user-intent.yaml", item["outputs"])
        self.assertTrue(any("directives are required" in c for c in item["failing_checks"]))
        self.assertTrue(any("user_intent.governs" in c for c in item["failing_checks"]))
        seeded = (root / "plan/user-intent.yaml").read_text(encoding="utf-8")
        self.assertIn(json.dumps(TEXT, ensure_ascii=False), seeded, "BookOrder seeds the interpretation with the verbatim text")
        self.assertTrue(any("binding" in line and "defaults" in line for line in item["instructions"]), "profile device settings are stated as defaults")

    def test_drafting_packet_and_task_carry_the_intent(self):
        root, m, ctx = job("intent-drafting")
        write(root, "source/metadata/outline.yaml", {"chapters": [{"id": "ch-a", "title": "A", "file": "source/manuscript/01-a.md", "purpose": "p", "target_characters": 1000}]})
        chapters = m["planning"].load_outline({})
        packet = m["planning"].packet(chapters[0], chapters, {})
        self.assertEqual(packet["user_intent"]["verbatim"], TEXT)
        self.assertEqual(list(packet)[0], "user_intent", "the user's words come first in the packet")
        item = m["orchestrator"].task("draft:ch-a", "drafting", "Draft", ["write"])
        self.assertEqual(item["user_intent"]["verbatim"], TEXT)
        write(root, "plan/summaries/ch-a.yaml", "summary: '" + "要約" * 40 + "'\nintroduced_concepts: []\nhandoff: 'handoff text'\n")
        errors = m["orchestrator"].intent_check_errors(ctx, root / "plan/summaries/ch-a.yaml")
        self.assertTrue(errors and "intent_check" in errors[0], "a drafted chapter records its intent check")
        write(root, "plan/summaries/ch-a.yaml", "summary: '" + "要約" * 40 + "'\nintroduced_concepts: []\nhandoff: 'handoff text'\nintent_check: '章末まとめなし、評論調を維持した。'\n")
        self.assertEqual(m["orchestrator"].intent_check_errors(ctx, root / "plan/summaries/ch-a.yaml"), [])

    def test_prose_editing_and_design_tasks_carry_the_intent_and_check_it(self):
        root, m, ctx = job("intent-editing")
        orch = m["orchestrator"]
        write(root, "source/metadata/outline.yaml", {"chapters": []})
        item = orch.h_prose_editing(ctx).tasks[0]
        self.assertEqual(item["user_intent"]["verbatim"], TEXT)
        self.assertTrue(any("do not restore counterarguments" in r for r in item["user_intent"]["rules"]))
        write(root, "plan/prose-editing.yaml", {"reviewed_chapters": [], "edits": [], "preserved": [], "citation_reaudit": []})
        self.assertTrue(any("intent_check" in c for c in orch.h_prose_editing(ctx).tasks[0]["failing_checks"]))
        design = orch.h_design(ctx).tasks[0]
        self.assertEqual(design["user_intent"]["verbatim"], TEXT)
        self.assertTrue(any("structured format settings" in r for r in design["user_intent"]["rules"]))

    def test_publication_qa_records_the_user_intent(self):
        root, m, ctx = job("intent-qa")
        orch = m["orchestrator"]
        item = orch.task("layout-review", "layout", "Visual layout review", ["inspect"])
        self.assertTrue(any("## User intent" in r for r in item["user_intent"]["rules"]))
        write(root, "reports/layout-review.md", "# Layout review\n\nPages inspected.\n")
        self.assertFalse(orch.layout_review_has_intent(root / "reports/layout-review.md"))
        write(root, "reports/layout-review.md", "# Layout review\n\n## User intent\n\nNo chapter summaries in the PDF; A5 kept.\n")
        self.assertTrue(orch.layout_review_has_intent(root / "reports/layout-review.md"))


class Precedence(unittest.TestCase):
    PROFILE = None

    def plan(self, chapter_end):
        return {"chapter_id": "ch-one", "chapter_title": "One", "chapter_role": "development", "reader_before": "b", "reader_after": "a", "target_chars": 1800,
                "sections": [{"id": "sec-a", "heading": "A", "purpose": "p", "rhetorical_role": "thesis", "intended_reader_effect": "e",
                              "expected_density": "light", "target_chars": 900, "summary_points": ["x"]},
                             {"id": "sec-b", "heading": "B", "purpose": "p", "rhetorical_role": "example", "intended_reader_effect": "e",
                              "expected_density": "heavy", "target_chars": 900, "summary_points": ["y"]}],
                "chapter_end": chapter_end, "waivers": [{"rule": "device_count_under", "reason": "a short note with no boxed material"}]}

    def test_explicit_user_intent_beats_the_generic_chapter_summary_default(self):
        root, m, ctx = job("intent-default-conflict")
        ep, ui = m["editorial_plan"], m["user_intent"]
        profile = copy.deepcopy(ep.profile_for())
        profile["structure"]["chapter_end"] = ["key_points"]          # the textbook/criticism default
        chapter = {"id": "ch-one", "target_characters": 1800, "required_sections": []}
        rules = lambda intent: {f["rule"] for f in ep.blocking(ep.check_chapter(chapter, self.plan([]), profile, intent=intent, last=True)["findings"])}
        self.assertIn("chapter_end_missing", rules({}), "without user intent the profile default applies")
        self.assertIn("missing_field", rules({}))
        interpretation(root)
        intent = ui.overrides()
        self.assertEqual(sorted(intent), ["chapter_end_missing"])
        self.assertFalse({"chapter_end_missing", "missing_field"} & rules(intent), "the user's 'no chapter-end summaries' wins")
        waived = [f for f in ep.check_chapter(chapter, self.plan([]), profile, intent=intent, last=True)["findings"] if f["rule"] == "chapter_end_missing"]
        self.assertTrue(waived and "各章末にまとめを付けない" in waived[0]["waived"], "the finding stays visible, attributed to the user")
        self.assertFalse(any("key_points" in line for line in ep.summary_lines(ep.normalize(self.plan([])))), "drafting is not asked for a summary")

    def test_real_run_honours_the_override_and_the_task_text_stays_default_free(self):
        root, m, ctx = job("intent-default-run")
        orch = m["orchestrator"]
        write(root, "source/metadata/outline.yaml", "chapters:\n  - id: ch-one\n    title: One\n    file: source/manuscript/01-one.md\n    purpose: p\n"
              "    target_characters: 1800\n    required_sections: [{id: sec-a, title: A}]\n    required_topics: [a]\n")
        write(root, "plan/editorial/ch-one.yaml", self.plan([]))
        write(root, "plan/editorial/book.yaml", {"waivers": [{"rule": "visual_shortage", "reason": "a one-chapter note with nothing to compare or draw"}]})
        ctx.invalidate()
        blocked = orch.h_editorial_planning(ctx)
        self.assertTrue(blocked.tasks and any("chapter_end_missing" in c for c in blocked.tasks[0]["failing_checks"]))
        interpretation(root)
        ctx.invalidate()
        self.assertTrue(orch.h_editorial_planning(ctx).done, "the plan passes once the user's override is recorded")

    def test_an_override_needs_the_users_own_words(self):
        root, m, ctx = job("intent-invented-quote")
        ui = m["user_intent"]
        interpretation(root, directives=[{"id": "intent-009", "source_quote": "まとめは不要と言われた", "interpretation": "invented",
                                          "applies_to": ["drafting"], "overrides": ["chapter_end_missing"]}])
        self.assertEqual(ui.overrides(), {}, "an agent cannot invent a user instruction to drop a default")
        self.assertTrue(any("source_quote must be copied exactly" in e for e in ui.check()))

    def test_structured_setting_wins_over_conflicting_free_text(self):
        root, m, ctx = job("intent-structured")
        ui = m["user_intent"]
        import layout_spec
        project = {"book": {"language": "ja", "title": "t", "description": "d", "target_readers": "r"}, "outputs": {"pdf": True}, "user_instructions": TEXT}
        design = {"page": {"size": "A5", "orientation": "portrait", "margin": {"top": "18mm", "bottom": "20mm", "inner": "20mm", "outer": "17mm"}}}
        page = layout_spec.resolve(project, {"genre": "technical"}, design)["page"]
        self.assertEqual((page["width_mm"], page["height_mm"]), (148.0, 210.0), "A5 selected in the WebUI stays A5")
        interpretation(root, directives=[{"id": "intent-003", "source_quote": "判型はA4にする", "interpretation": "A4", "applies_to": ["design"], "overrides": ["page_size"]}])
        self.assertTrue(any("cannot override page_size" in e for e in ui.check()), "a structured field is not a pipeline default")
        interpretation(root)
        self.assertEqual(ui.check(), [])
        report = "\n".join(ui.report_lines())
        self.assertIn("判型はA4にする", report); self.assertIn("structured_setting", report); self.assertIn("Kept A5", report)

    def test_invariants_cannot_be_switched_off(self):
        root, m, ctx = job("intent-invariant")
        ui = m["user_intent"]
        interpretation(root, directives=[{"id": "intent-004", "source_quote": "引用は確認しなくてよい", "interpretation": "skip citation checks",
                                          "applies_to": ["audit"], "overrides": ["source_unknown", "citation"]}])
        self.assertEqual(ui.overrides(), {})
        errors = ui.check()
        self.assertTrue(any("cannot override source_unknown" in e for e in errors) and any("cannot override citation" in e for e in errors))
        ep = m["editorial_plan"]
        finding = ep.finding("source_unknown", "error", "source src-9999 does not exist")
        ui.apply_overrides([finding], ui.overrides())
        self.assertEqual(ep.blocking([finding]), [finding], "citation/provenance findings still block")
        interpretation(root)
        self.assertIn("invariant", "\n".join(ui.report_lines()))

    def test_text_wall_limit_is_a_default_the_user_can_switch_off(self):
        root, m, ctx = job("intent-pacing")
        import pacing
        result = lambda: {"verdict": "fail", "summary": {"high": 1, "medium": 0}, "findings": [
            {"severity": "high", "rule": "run_over_limit", "chapter": "ch-one", "detail": "6 consecutive text-only pages", "actions": [{"op": "insert_summary"}]}]}
        self.assertEqual(pacing.apply_user_intent(result())["verdict"], "fail")
        interpretation(root, directives=[{"id": "intent-005", "source_quote": "教科書的にせず", "interpretation": "long uninterrupted critical argument",
                                          "applies_to": ["layout"], "overrides": ["layout_pacing"]}])
        waived = pacing.apply_user_intent(result())
        self.assertEqual(waived["verdict"], "pass")
        self.assertEqual(waived["findings"][0]["severity"], "medium")
        self.assertNotIn("actions", waived["findings"][0], "no inserted summaries are proposed")


class Completion(unittest.TestCase):
    def complete_intent_files(self, root):
        interpretation(root)
        write(root, "plan/book-bible.yaml", {"user_intent": {"governs": ["評論として書く (intent-001)"], "defaults_used": []}})
        for name in ("plan/integration-review.yaml", "plan/audit/book.yaml", "plan/prose-audit.yaml", "plan/prose-editing.yaml", "plan/design-decisions.yaml"):
            write(root, name, {"reviewed_chapters": [], "intent_check": "ユーザー指示どおり章末まとめなし、評論調を維持した。"})
        write(root, "reports/layout-review.md", "# Layout review\n\n## User intent\n\nChecked the PDF against the instructions.\n")

    def test_gate_22_requires_every_intent_check_and_reports_conflicts(self):
        root, m, ctx = job("intent-gate")
        orch = m["orchestrator"]
        write(root, "source/metadata/outline.yaml", {"chapters": []})
        gate = orch.user_intent_gate(ctx)
        self.assertFalse(gate["passed"]); self.assertEqual(gate["phase"], "architecture")
        self.complete_intent_files(root)
        ctx.invalidate()
        gate = orch.user_intent_gate(ctx)
        self.assertTrue(gate["passed"], gate["detail"])
        self.assertIn("2 conflicts reported", gate["detail"])
        write(root, "plan/prose-editing.yaml", {"reviewed_chapters": []})
        gate = orch.user_intent_gate(ctx)
        self.assertFalse(gate["passed"]); self.assertEqual(gate["phase"], "prose_editing")
        orch.write_editorial_review(ctx)
        review = (root / "reports/editorial-review.md").read_text(encoding="utf-8")
        self.assertIn("## User intent", review); self.assertIn("引用は確認しなくてよい", review)

    def test_legacy_states_are_not_regated(self):
        root, m, ctx = job("intent-legacy")
        ctx.state.pop("user_intent_protocol")
        gate = m["orchestrator"].user_intent_gate(ctx)
        self.assertTrue(gate["passed"]); self.assertIn("legacy", gate["detail"])


class NoInstructions(unittest.TestCase):
    def test_jobs_without_instructions_keep_the_default_behaviour(self):
        root, m, ctx = job("intent-none", text="")
        orch, ui, ep = m["orchestrator"], m["user_intent"], m["editorial_plan"]
        for phase in ui.CONTENT_PHASES + ui.REVIEW_PHASES: self.assertNotIn("user_intent", orch.task("x", phase, "t", ["do"]), phase)
        printed = orch.status_text({"status": "running", "phase": "drafting", "phases": {p: "pending" for p in orch.PHASES}, "blockers": []},
                                   [orch.task("draft:ch-a", "drafting", "Draft", ["write"])], [])
        self.assertNotIn("User intent", printed)
        self.assertEqual(ui.overrides(), {}); self.assertEqual(ui.check(), [])
        self.assertFalse(ui.seed()); self.assertFalse((root / "plan/user-intent.yaml").exists())
        self.assertEqual(orch.user_intent_gate(ctx)["detail"], "no user instructions")
        write(root, "source/metadata/outline.yaml", {"chapters": [{"id": "ch-a", "title": "A", "file": "source/manuscript/01-a.md", "purpose": "p", "target_characters": 1000}]})
        chapters = m["planning"].load_outline({})
        self.assertNotIn("user_intent", m["planning"].packet(chapters[0], chapters, {}))
        write(root, "plan/summaries/ch-a.yaml", "summary: '" + "要約" * 40 + "'\nintroduced_concepts: []\nhandoff: 'handoff text'\n")
        self.assertEqual(orch.intent_check_errors(ctx, root / "plan/summaries/ch-a.yaml"), [], "no intent_check is demanded")
        self.assertFalse(any("architecture" in e or "user_intent" in e for e in orch.h_architecture(ctx).tasks[0]["failing_checks"]))
        profile = copy.deepcopy(ep.profile_for()); profile["structure"]["chapter_end"] = ["key_points"]
        plan = Precedence.plan(None, [])
        chapter = {"id": "ch-one", "target_characters": 1800, "required_sections": []}
        self.assertEqual(ep.check_chapter(chapter, plan, profile, last=True), ep.check_chapter(chapter, plan, profile, intent=ui.overrides(), last=True))
        self.assertIn("chapter_end_missing", {f["rule"] for f in ep.blocking(ep.check_chapter(chapter, plan, profile, last=True)["findings"])})


if __name__ == "__main__":
    unittest.main(verbosity=2)

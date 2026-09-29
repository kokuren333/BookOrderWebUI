"""EditorialPlan (P0-4): section roles, devices, pauses and slots planned before drafting.

Needs Pandoc (profiles and fixture plans are YAML read with it): PANDOC or pandoc on PATH.
Usage: python tests/test_editorial_plan.py
"""
import copy
import os
from pathlib import Path
import shutil
import sys
import unittest

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "job-template"
sys.path.insert(0, str(TEMPLATE / "scripts"))
import editorial_plan as ep  # noqa: E402
import publication_profile as pp  # noqa: E402

FIXTURE = REPO / "tests/fixtures/long-replan"
BUILD_EXISTED = (TEMPLATE / ".build").exists()
A5 = {"page": {"size": "A5"}, "layout": {"density": "standard"}}
KNOWN = {f"src-{i:04d}": "fully_ingested" for i in range(1, 100)} | {"src-0099": "unavailable"}


def pandoc():
    found = os.environ.get("PANDOC") or shutil.which("pandoc")
    return found if found and Path(found).is_file() else None


def tearDownModule():
    if not BUILD_EXISTED: shutil.rmtree(TEMPLATE / ".build", ignore_errors=True)


def profile(tier, genre=None):
    return pp.resolve({"book": {"title": "t", "language": "ja"}, "profile": {"tier": tier, **({"genre": genre} if genre else {})}}, A5)


def section(sid, chars, density="medium", role="evidence", points=("a", "b"), devices=(), **extra):
    return {"id": sid, "heading": sid, "purpose": "p", "rhetorical_role": role, "intended_reader_effect": "e", "expected_density": density,
            "target_chars": chars, "summary_points": list(points), "devices": [dict(d) for d in devices], **extra}


def device(ident, kind, position="middle", **extra):
    return {"id": ident, "type": kind, "why": "the reader needs it here", "placement": {"intent": "after the point", "position": position}, **extra}


def plan(cid, sections, end=("key_points",), **extra):
    total = sum(s["target_chars"] for s in sections)
    return ep.normalize({"chapter_id": cid, "chapter_title": cid, "chapter_role": "development", "reader_before": "b", "reader_after": "a",
                         "target_chars": total, "lead": "l", "sections": sections, "chapter_end": [{"type": t} for t in end], **extra})


def chapter(cid, target, required=()):
    return {"id": cid, "target_characters": target, "required_sections": [{"id": r} for r in required]}


def run(p, prof, chapters=None, book=None, known=KNOWN):
    chapters = chapters or [chapter(p["chapter_id"], p["target_chars"])]
    return ep.check(chapters, {p["chapter_id"]: p}, prof, known, book)


def rules(result, severity=None):
    return {f["rule"] for f in ep.all_findings(result) if severity is None or f["severity"] == severity}


def load(which, cid):
    return ep.normalize(ep._coerce(__import__("common").yaml_data(FIXTURE / which / f"{cid}.yaml")))


# A section in the short tier breathes every 1,800 characters (max 2,400); a rhythm that passes.
def good_short(cid="ch-a"):
    p = plan(cid, [section("s1", 700, "light", "thesis", devices=[device(f"{cid}-kp", "key_point", "section_end")]),
                      section("s2", 1000, "heavy", devices=[device(f"tbl-{cid}", "table", information_shape={"kind": "comparison", "items": 3, "attributes": 4},
                                                                     basis="source", source_ids=["src-0001"])]),
                      section("s3", 600, "medium", "example")], end=("key_points", "check_questions"))
    p["chapter_end"].append({"type": "further_reading", "id": f"{cid}-further-reading", "source_ids": ["src-0001", "src-0002"]})
    return p


@unittest.skipUnless(pandoc(), "Pandoc not available (set PANDOC)")
class Profiles(unittest.TestCase):
    def test_short_medical_science(self):
        prof = profile("short", "medical_science")
        result = run(good_short(), prof)
        self.assertTrue(result["ok"], ep.blocking(ep.all_findings(result)))
        self.assertEqual(result["chapters"][0]["counts"]["tables"], 1)
        missing = good_short(); missing["chapter_end"] = [e for e in missing["chapter_end"] if e["type"] != "check_questions"]
        self.assertIn("chapter_end_missing", rules(run(missing, prof), "error"), "check_questions is required by medical_science")
        quoted = good_short(); quoted["sections"][2]["devices"].append({**device("pq-a", "pull_quote"), "source_ids": ["src-0002"], "quote": "..."})
        self.assertIn("device_count_over", rules(run(quoted, prof), "error"), "medical_science allows no pull quotes")

    def test_long_criticism_before_and_after(self):
        prof = profile("long", "criticism")
        chapters = [chapter("ch-2", 14800, [f"sec-2-{i}" for i in range(1, 5)]), chapter("ch-3", 17000, [f"sec-3-{i}" for i in range(1, 5)])]
        before = ep.check(chapters, {c: load("before", c) for c in ("ch-2", "ch-3")}, prof, KNOWN)
        self.assertFalse(before["ok"])
        for rule in ("pause_interval_exceeded", "visual_illustrative", "chapter_end_missing"): self.assertIn(rule, rules(before, "error"))
        for rule in ("density_monotonous", "section_too_long", "text_wall_risk", "abstract_run", "device_count_under", "chapter_lead_missing"):
            self.assertIn(rule, rules(before, "medium"))
        self.assertEqual(before["chapters"][1]["max_gap_chars"], 17000, "chapter 3: nothing between the opener and table 3.1")
        book = ep._coerce(__import__("common").yaml_data(FIXTURE / "after/book.yaml"))
        after = ep.check(chapters, {c: load("after", c) for c in ("ch-2", "ch-3")}, prof, KNOWN, book)
        self.assertTrue(after["ok"], ep.blocking(ep.all_findings(after)))
        shortage = next(f for f in after["findings"] if f["rule"] == "visual_shortage")
        self.assertTrue(shortage["waived"], "the shortage is reported and waived with a reason, not filled")
        self.assertIn("visual_shortage", rules(ep.check(chapters, {c: load("after", c) for c in ("ch-2", "ch-3")}, prof, KNOWN), "medium"))
        for result in after["chapters"]:
            self.assertLessEqual(result["max_gap_chars"], prof["rhythm"]["pause_every_chars"]["max"])
            self.assertEqual(len(set(result["density_profile"])), 3)
        ch2 = load("after", "ch-2")
        kinds = {d["id"]: d["type"] for _, d in ep.devices(ch2)}
        self.assertNotIn("fig-2-1", kinds); self.assertEqual(kinds["tbl-2-resources"], "table")
        declined = [o for s in ch2["sections"] for o in s["visual_opportunities"] if isinstance(o, dict) and o.get("declined")]
        self.assertTrue(declined and "2.1" in declined[0]["declined"], "the old concept map is declined with its reason")


@unittest.skipUnless(pandoc(), "Pandoc not available (set PANDOC)")
class Rhythm(unittest.TestCase):
    def test_light_heavy_rhythm(self):
        result = run(good_short(), profile("short"))
        self.assertNotIn("density_monotonous", rules(result))
        self.assertEqual(result["chapters"][0]["density_profile"], ["light", "heavy", "medium"])

    def test_all_heavy_warns(self):
        p = good_short()
        for s in p["sections"]: s["expected_density"] = "heavy"
        result = run(p, profile("short"))
        self.assertIn("density_monotonous", rules(result, "medium"))
        self.assertIn("density_heavy_run", rules(result, "low"))
        p["density_profile"] = ["light", "heavy", "light"]
        self.assertIn("density_profile_mismatch", rules(run(p, profile("short")), "error"))

    def test_pause_interval(self):
        prof = profile("short")  # pause every 1,800 (max 2,400); 780 characters per text page; 3 text-only pages
        wall = plan("ch-w", [section("s1", 1300, "light"), section("s2", 1300, "heavy", devices=[device("ch-w-kp", "key_point", "section_end")])])
        result = run(wall, prof)
        self.assertIn("pause_interval_exceeded", rules(result, "error"), "2,600 characters before the first pause")
        self.assertIn("text_wall_risk", rules(result, "medium"), "about 3.3 text pages")
        long = plan("ch-l", [section("s1", 1000, "light"), section("s2", 1300, "heavy", devices=[device("ch-l-kp", "key_point", "section_end")])])
        found = run(long, prof)
        self.assertNotIn("pause_interval_exceeded", rules(found)); self.assertIn("pause_interval_long", rules(found, "low"))
        gaps = found["chapters"][0]["pauses"]
        self.assertEqual([g["chars"] for g in gaps], [2300], "opener -> key point at the section end == chapter end")


@unittest.skipUnless(pandoc(), "Pandoc not available (set PANDOC)")
class DeviceConditions(unittest.TestCase):
    prof = None

    @classmethod
    def setUpClass(cls): cls.prof = profile("standard")

    def one(self, dev, **section_extra):
        p = plan("ch-d", [section("s1", 900, "light"), section("s2", 900, "heavy", devices=[dev], **section_extra), section("s3", 700, "light", "example")])
        return run(p, self.prof)

    def test_key_point_over_1500_with_three_points(self):
        p = plan("ch-k", [section("s1", 1600, "heavy", points=("a", "b", "c")), section("s2", 800, "light", "example")])
        self.assertIn("key_point_needed", rules(run(p, self.prof), "medium"))
        p["sections"][0]["devices"].append(device("ch-k-kp", "key_point", "late"))
        self.assertNotIn("key_point_needed", rules(run(p, self.prof)))
        self.assertIn("key_point_unwarranted", rules(self.one(device("ch-d-kp", "key_point")), "low"))

    def test_three_by_three_comparison_is_a_table(self):
        ok = self.one(device("tbl-d", "table", information_shape={"kind": "comparison", "items": 3, "attributes": 3}, basis="derived_from_text"))
        self.assertFalse(rules(ok, "error"))
        small = self.one(device("tbl-d", "table", information_shape={"kind": "comparison", "items": 2, "attributes": 3}, basis="derived_from_text"))
        self.assertIn("table_too_small", rules(small, "error"))
        drawn = self.one(device("fig-d", "figure", information_shape={"kind": "comparison", "items": 3, "attributes": 3}, basis="derived_from_text"))
        finding = next(f for f in ep.all_findings(drawn) if f["rule"] == "visual_not_admissible")
        self.assertEqual(finding["suggestion"], "table")
        linear = self.one(device("fig-d", "figure", information_shape={"kind": "process", "steps": 3}, basis="derived_from_text"))
        self.assertEqual(next(f for f in ep.all_findings(linear) if f["rule"] == "visual_not_admissible")["suggestion"], "prose")

    def test_three_dated_events_make_a_timeline(self):
        ok = self.one(device("fig-t", "timeline", information_shape={"kind": "chronology", "events": 3}, source_ids=["src-0003"]))
        self.assertFalse(rules(ok, "error"))
        self.assertIn("timeline_too_few_events", rules(self.one(device("fig-t", "timeline", information_shape={"kind": "chronology", "events": 2},
                                                                        source_ids=["src-0003"])), "error"))
        self.assertIn("source_required", rules(self.one(device("fig-t", "timeline", information_shape={"kind": "chronology", "events": 4})), "error"))

    def test_pull_quote_needs_an_existing_source(self):
        self.assertIn("source_required", rules(self.one(device("pq-d", "pull_quote", quote="x")), "error"))
        self.assertIn("source_unknown", rules(self.one(device("pq-d", "pull_quote", quote="x", source_ids=["src-9999"])), "error"))
        self.assertIn("source_unusable", rules(self.one(device("pq-d", "pull_quote", quote="x", source_ids=["src-0099"])), "error"))
        good = self.one(device("pq-d", "pull_quote", quote="x", source_ids=["src-0004"]))
        self.assertFalse(rules(good, "error"))

    def test_sourced_devices(self):
        self.assertIn("source_required", rules(self.one(device("cs-d", "case_study")), "error"), "a real case study cites")
        self.assertNotIn("source_required", rules(self.one(device("cs-d", "case_study", basis="hypothetical"))))
        self.assertIn("source_required", rules(self.one(device("cp-d", "counterpoint"), counterarguments=["x"]), "error"))
        self.assertNotIn("source_required", rules(self.one(device("cp-d", "counterpoint", origin="author"), counterarguments=["x"])))
        self.assertIn("visual_illustrative", rules(self.one(device("fig-d", "figure", information_shape={"kind": "relation", "nodes": 5}, basis="illustrative")), "error"))

    def test_every_device_says_why_and_where(self):
        bare = {"id": "kp-x", "type": "key_point"}
        found = rules(self.one(bare), "error")
        self.assertTrue({"device_missing_why", "device_missing_placement"} <= found)
        self.assertIn("device_unknown_type", rules(self.one(device("x", "hologram")), "error"))

    def test_definition_at_first_use(self):
        p = plan("ch-g", [section("s1", 900, "light", new_terms=["ギュ"]), section("s2", 900, "heavy", devices=[device("df-g", "definition", terms=["ギュ"])]),
                          section("s3", 600, "light", "example")])
        self.assertIn("definition_not_new", rules(run(p, self.prof), "medium"))


@unittest.skipUnless(pandoc(), "Pandoc not available (set PANDOC)")
class ChapterEnd(unittest.TestCase):
    def test_chapter_end_follows_the_profile(self):
        self.assertEqual(profile("short")["structure"]["chapter_end"], ["key_points"])
        crit = profile("long", "criticism")
        chapters = [chapter("ch-a", 2300), chapter("ch-b", 2300)]
        plans = {c["id"]: plan(c["id"], [section("s1", 1100, "light", "thesis", devices=[device(f"{c['id']}-kp", "key_point")]),
                                         section("s2", 1200, "heavy", "example")], end=("key_points",)) for c in chapters}
        found = [f for f in ep.all_findings(ep.check(chapters, plans, crit, KNOWN)) if f["rule"] == "chapter_end_missing"]
        missing = {(f["chapter"], f["detail"].split(" requires ")[1].split(" ")[0]) for f in found}
        self.assertEqual(missing, {("ch-a", "open_question"), ("ch-a", "bridge_to_next"), ("ch-b", "open_question")}, "the last chapter needs no bridge")
        plans["ch-a"]["chapter_end"] = ep.normalize({"chapter_id": "ch-a", "chapter_end": [{"type": "further_reading", "source_ids": ["src-0001", "src-0002"]}]})["chapter_end"]
        self.assertIn("further_reading_sources", rules(ep.check(chapters, plans, crit, KNOWN), "error"), "criticism expects 3+ further-reading sources")
        plans["ch-a"]["chapter_end"][0]["source_ids"].append("src-0099")
        self.assertIn("source_unusable", rules(ep.check(chapters, plans, crit, KNOWN), "error"), "unavailable sources cannot be recommended")


@unittest.skipUnless(pandoc(), "Pandoc not available (set PANDOC)")
class Slots(unittest.TestCase):
    TEXT = ("# 章 {#ch-s}\n\n## 節 {#sec-s1}\n\n本文の段落。\n\n::: {.slot #tbl-eval-axes kind=table}\n推薦・総合・実力の評価軸を比較\n:::\n\n"
            "::: {.key-point #ch-s-kp}\n要点。\n:::\n\n::: {.slot #fig-gone kind=figure}\n取り下げた図\n:::\n")

    def record(self, text):
        import manuscript
        folder = TEMPLATE / ".build/test-slots"; folder.mkdir(parents=True, exist_ok=True)
        path = folder / "01-s.md"; path.write_text(text, encoding="utf-8")
        return manuscript.analyze_file(path)

    def test_slots_enter_the_manuscript(self):
        rec = self.record(self.TEXT)
        self.assertEqual([(s["id"], s["kind"], s["section"]) for s in rec["slots"]], [("tbl-eval-axes", "table", "sec-s1"), ("fig-gone", "figure", "sec-s1")])
        self.assertNotIn("評価軸", rec["prose"], "slot text is not counted as chapter prose")
        p = plan("ch-s", [section("sec-s1", 900, "light", devices=[device("tbl-eval-axes", "table", information_shape={"kind": "comparison", "items": 3, "attributes": 3}),
                                                                   device("ch-s-kp", "key_point"), device("cp-s", "counterpoint", origin="author"),
                                                                   {**device("fig-gone", "figure"), "status": "dropped", "fallback": {"to": "prose", "reason": "linear"}}])])
        status = ep.slot_status(p, rec)
        self.assertEqual(status["open"], ["tbl-eval-axes"]); self.assertIn("ch-s-kp", status["realized"])
        self.assertIn("cp-s", status["missing"]); self.assertIn("ch-s-key-points", status["missing"], "chapter-end items are slots too")
        self.assertEqual(status["stale"], ["fig-gone"], "a dropped device's slot must leave the text")
        self.assertIn("::: {.slot #tbl-eval-axes kind=table}", ep.slot_markdown(p["sections"][0]["devices"][0]))
        self.assertTrue(any("slot tbl-eval-axes" in line for line in ep.summary_lines(p)), "drafting instructions name the slots")
        filled = self.record(self.TEXT.replace("::: {.slot #tbl-eval-axes kind=table}\n推薦・総合・実力の評価軸を比較\n:::",
                                               "| a | b | c |\n|---|---|---|\n| 1 | 2 | 3 |\n\nTable: 評価軸 {#tbl-eval-axes}"))
        self.assertIn("tbl-eval-axes", ep.slot_status(p, filled)["realized"])

    def test_open_slots_block_the_final_gate(self):
        import orchestrator
        rec = self.record(self.TEXT)
        class Ctx:
            def by_chapter(self): return {"ch-s": rec, "ch-t": None}
        self.assertEqual(orchestrator.open_slots(Ctx()), {"ch-s": ["tbl-eval-axes", "fig-gone"]})
        validate = (TEMPLATE / "scripts/validate.py").read_text(encoding="utf-8")
        self.assertIn("Unresolved slot", validate, "the final validation refuses open slots")

    def test_proof_shows_placeholders(self):
        from book_ir import create_ir, prepare_ast
        from renderers.typst import pdf_ast
        import json
        ast = json.loads(__import__("common").run([pandoc(), "-f", "markdown", "-t", "json"], self.TEXT))
        ir = create_ir(ast)
        html = json.dumps(prepare_ast(ir, "html"), ensure_ascii=False)
        self.assertIn("slot-placeholder", html); self.assertIn("［slot table: tbl-eval-axes］", html)
        self.assertIn("custom-style", json.dumps(prepare_ast(ir, "docx"), ensure_ascii=False))
        typst = json.dumps(pdf_ast(ir), ensure_ascii=False)
        self.assertIn('#book-slot(\\"table\\", \\"tbl-eval-axes\\")[', typst)
        self.assertIn("slot", (TEMPLATE / "templates/design/slots.typ").read_text(encoding="utf-8"))


@unittest.skipUnless(pandoc(), "Pandoc not available (set PANDOC)")
class Fallback(unittest.TestCase):
    def concept_map_plan(self):
        return plan("ch-f", [section("s1", 900, "light"),
                             section("s2", 1000, "heavy", devices=[device("fig-map", "figure", information_shape={"kind": "relation", "nodes": 5}, basis="source",
                                                                          source_ids=["src-0005"])]),
                             section("s3", 700, "light", "example")])

    def test_rejected_visual_falls_back_to_a_table(self):
        p = self.concept_map_plan()
        saved = ep.load_plan
        try:
            ep.load_plan = lambda cid: p if cid == "ch-f" else None
            review = {"candidates": [{"id": "fig-map", "device": None, "decision": "rejected",
                                      "rejection_reasons": [{"code": "concept_map_edge_semantics"}, {"code": "concept_map_no_structure"}]}]}
            rejected = ep.rejected_devices([{"id": "ch-f"}], review)
        finally: ep.load_plan = saved
        self.assertEqual([(r["device"], r["options"][0]) for r in rejected], [("fig-map", "table")])
        new = ep.fallback(p, "fig-map", "table", "relations are unnamed; compare the five items on their attributes", rejected[0]["codes"])
        old = next(d for _, d in ep.devices(p) if d["id"] == "fig-map")
        self.assertEqual((old["status"], old["replaced_by"], old["fallback"]["review"]), ("replaced", new, ["concept_map_edge_semantics", "concept_map_no_structure"]))
        prof = profile("standard")
        self.assertIn("table_too_small", rules(run(p, prof), "error"), "the new table must still earn its place")
        table = next(d for _, d in ep.devices(p) if d["id"] == new)
        table["information_shape"] = {"kind": "comparison", "items": 5, "attributes": 3}
        self.assertFalse(rules(run(p, prof), "error"))
        import manuscript
        with __import__("tempfile").TemporaryDirectory(dir=TEMPLATE) as folder:
            path = Path(folder) / "01-ch-f.md"
            path.write_text("# Test {#ch-f}\n\n## Comparison {#s2}\n\n| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |\n\nTable: Comparison {#" + new + "}\n\n::: {.summary #ch-f-key-points}\nSummary.\n:::\n", encoding="utf-8")
            status = ep.slot_status(p, manuscript.analyze_file(path))
        self.assertFalse(status["open"] or status["missing"] or status["stale"])
        self.assertIn(new, status["realized"])

    def test_rejected_visual_falls_back_to_prose(self):
        p = self.concept_map_plan()
        self.assertIsNone(ep.fallback(p, "fig-map", "prose", "a straight chain; the paragraph says it"))
        self.assertEqual(next(d for _, d in ep.devices(p) if d["id"] == "fig-map")["status"], "dropped")
        self.assertNotIn("fig-map", ep.expected(p)); self.assertIn("fig-map", ep.withdrawn(p))
        self.assertEqual(ep.suggest([{"code": "linear_sequence"}]), ["prose"])
        self.assertEqual(ep.suggest([{"code": "illustrative_structure"}])[:2], ["case_study", "prose"])
        self.assertEqual(ep.suggest([{"code": "shape_routes_elsewhere", "suggestion": "use table or list"}])[0], "table")
        with self.assertRaises(ValueError): ep.fallback(p, "fig-map", "table", "again")


if __name__ == "__main__":
    unittest.main(verbosity=2)

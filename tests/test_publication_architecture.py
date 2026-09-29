"""Intent-driven publication architecture (docs/INTENT_DRIVEN_PUBLICATION_ARCHITECTURE.md).

Fixes the twelve required behaviours: no automatic exercises in a practical guide; exercises with answers in exam
books; footnote and author-year citations with numbered bibliographies; evidence vs background sources; layout
references never content; uploaded figures reaching chapter and asset plans; explicit user prohibitions enforced;
visual diversity; FIXED mode = legacy template; AUTO mode allowing chapters to differ. Also checks that the settings
reach the orchestrator's tasks and packets (propagation).

Requires Pandoc (YAML, Markdown and citeproc). Run: python tests/test_publication_architecture.py
"""
import importlib
import json
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_orchestrator import make_job, write  # noqa: E402

LONG = "本文。" * 300


def job(name, arch=None, instructions="", citations=None, files=(), assets=(), usage=None, description="病棟で働く看護師のための実務書", pages=40):
    root, m = make_job(name, pages=pages, files=list(files))
    project = json.loads((root / "project.json").read_text(encoding="utf-8"))
    project["book"]["description"] = description
    project["user_instructions"] = instructions
    if arch is not None: project["publication_architecture"] = arch
    if citations is not None: project["citations"] = citations
    for i, u in enumerate(usage or []):
        if u: project["input"]["sources"][i]["usage"] = u
    if assets:
        (root / "input/assets").mkdir(parents=True, exist_ok=True)
        project["input"]["assets"] = []
        for n, (file_name, data, u) in enumerate(assets, 1):
            (root / "input/assets" / file_name).write_bytes(data)
            project["input"]["assets"].append({"id": f"asset-{n:03d}", "original_name": file_name, "path": f"input/assets/{file_name}", "size_bytes": len(data), "usage": u})
    (root / "project.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    for module in ("publication_architecture", "source_roles", "bibliography", "visual_plan", "architecture_qa", "editorial_plan", "user_intent", "publication_profile", "assets"):
        m[module] = importlib.import_module(module)
    return root, m


def chapter(cid, target=2000, **extra):
    return {"id": cid, "title": cid, "target_characters": target, "required_sections": [], **extra}


def section(sid, chars, devices=(), role="evidence", density="medium"):
    return {"id": sid, "heading": sid, "purpose": "p", "rhetorical_role": role, "intended_reader_effect": "e", "expected_density": density,
            "target_chars": chars, "summary_points": ["a"], "devices": list(devices)}


def device(ident, kind, **extra):
    return {"id": ident, "type": kind, "why": "the reader needs it here", "placement": {"intent": "after the point", "position": "middle"}, **extra}


def plan(ep, cid, sections, end=()):
    total = sum(s["target_chars"] for s in sections)
    return ep.normalize({"chapter_id": cid, "chapter_title": cid, "chapter_role": "practice", "reader_before": "b", "reader_after": "a", "target_chars": total,
                         "lead": "l", "sections": sections, "chapter_end": [e if isinstance(e, dict) else {"type": e, "why": "this chapter needs it"} for e in end]})


def check(m, chapters, plans):
    ep, pa = m["editorial_plan"], m["publication_architecture"]
    profile = m["publication_profile"].resolve(json.loads((Path(ep.ROOT) / "project.json").read_text(encoding="utf-8")), {"page": {"size": "A5"}})
    return ep.check(chapters, plans, profile, None, {}, arch=pa.load())


def rules(result, severity=None):
    return {f["rule"] for f in result["findings"] + [f for r in result["chapters"] for f in r["findings"]]
            if (severity is None or f["severity"] == severity) and not f.get("waived")}


def register_sources(m, root, notes):
    """Ingest supplied files and write research notes (title, author, role/authority estimates)."""
    m["sources"].init_supplied(); m["sources"].ingest()
    for sid, note in notes.items():
        write(root, f"research/notes/{sid}.yaml", {"source": sid, "relevance": "core", "summary": "資料全体の要約。" * 10, "key_claims": ["主張の本文がここにある"], **note})
    m["citations"].generate()


def render_html(m, markdown):
    common = m["common"]
    doc = common.combined(common.read_project(), [(None, common.parse_markdown(markdown))])
    return common.run([common.tool("pandoc"), "-f", "json", "-t", "html"], json.dumps(doc))


class ArchetypesAndExercises(unittest.TestCase):
    def test_01_practical_guide_does_not_insert_exercises(self):
        root, m = job("arch-practical", arch={"mode": "auto", "archetype": "practical_guide"})
        pa, ep = m["publication_architecture"], m["editorial_plan"]
        arch = pa.derive()
        self.assertEqual(arch["exercise_policy"], "none")
        self.assertIn("exercises", arch["block_policy"]["discouraged"])
        self.assertNotIn("exercises", arch["block_policy"]["preferred"])
        self.assertEqual(arch["block_policy"]["required_chapter_end"], [], "AUTO requires no chapter-end apparatus")
        self.assertIn("checklist", arch["block_policy"]["preferred"])
        # A chapter with no chapter end at all is a valid plan: nothing is inserted by habit.
        chapters = [chapter("ch-a"), chapter("ch-b")]
        plans = {"ch-a": plan(ep, "ch-a", [section("s1", 1000, [device("ck-a", "checklist", )], role="application"), section("s2", 1000, role="example")]),
                 "ch-b": plan(ep, "ch-b", [section("s1", 1000, role="thesis"), section("s2", 1000, [device("cs-b", "case_study", basis="hypothetical")], role="example")])}
        result = check(m, chapters, plans)
        self.assertNotIn("chapter_end_missing", rules(result))
        self.assertNotIn("missing_field", rules(result, "error"))
        # A planned quiz is discouraged for a practical guide: it needs a reason, it is never added automatically.
        plans["ch-b"] = plan(ep, "ch-b", [section("s1", 1000), section("s2", 1000)], end=["exercises", "answer_key"])
        self.assertIn("block_discouraged", rules(check(m, chapters, plans), "medium"))
        lines = "\n".join(pa.summary_lines())
        self.assertIn("plan no exercises", lines)

    def test_02_exam_preparation_has_exercises_with_answers(self):
        root, m = job("arch-exam", arch={"mode": "auto"}, instructions="国家試験対策の問題集として、各章に問題と解説を入れる。")
        pa, ep = m["publication_architecture"], m["editorial_plan"]
        arch = pa.derive()
        self.assertEqual(arch["archetype"]["primary"], "exam_preparation", "archetype read from the user's words")
        self.assertIn(arch["exercise_policy"], ("exam_focused", "where_useful"))
        self.assertIn("exercises", arch["block_policy"]["preferred"]); self.assertIn("answer_key", arch["block_policy"]["preferred"])
        chapters = [chapter("ch-a")]
        with_answers = {"ch-a": plan(ep, "ch-a", [section("s1", 1000), section("s2", 1000)], end=["exercises", "answer_key"])}
        self.assertFalse({"exercise_without_answers", "block_forbidden", "block_discouraged"} & rules(check(m, chapters, with_answers)))
        without = {"ch-a": plan(ep, "ch-a", [section("s1", 1000), section("s2", 1000)], end=["exercises"])}
        self.assertIn("exercise_without_answers", rules(check(m, chapters, without), "error"))
        # Components realise the blocks with marker classes the QA can recognise.
        qa = m["architecture_qa"]
        self.assertEqual(qa.component_block({"type": "exercise", "classes": ["exercise", "answer-key"]}), "answer_key")
        self.assertEqual(qa.component_block({"type": "exercise", "classes": ["exercise"]}), "exercises")


class CitationsAndBibliography(unittest.TestCase):
    FILES = [("guideline.md", "# 指針\n\n" + LONG), ("nurse-blog.md", "# 体験\n\n" + LONG)]
    NOTES = {"src-0001": {"bibliographic": {"title": "急性期看護ガイドライン", "authors": ["日本看護学会"], "published": "2024"}},
             "src-0002": {"bibliographic": {"title": "新人看護師の一年", "authors": ["山田花子"], "published": "2023"}}}
    OUTLINE = {"chapters": [{"id": "ch-a", "title": "A", "file": "source/manuscript/01-a.md", "purpose": "p", "target_characters": 1000,
                             "sources": {"primary": ["src-0001"], "supporting": ["src-0002"]}}]}

    def build(self, name, citations):
        root, m = job(name, arch={"mode": "auto"}, citations=citations, files=self.FILES,
                      usage=[{"role": "evidence", "authority": "guideline"}, {"role": "background", "authority": "professional_experience"}])
        register_sources(m, root, self.NOTES)
        write(root, "source/metadata/outline.yaml", self.OUTLINE)
        html = render_html(m, "# A {#ch-a}\n\n## 節 {#sec-a}\n\n観察は4時間ごとに行う [cite:src-0001]。\n")
        report = json.loads((root / "reports/bibliography.json").read_text(encoding="utf-8"))
        return root, m, html, report

    def test_03_footnote_citations_with_numbered_bibliography(self):
        root, m, html, report = self.build("bib-footnote", {"style": "note", "in_text_citation_style": "note", "footnote_style": "full", "bibliography_numbering": "numbered"})
        self.assertIn('class="footnote-ref"', html, "the text cites with a footnote")
        self.assertIn("急性期看護ガイドライン", html.split('id="footnotes"')[1], "the footnote carries the reference")
        refs = html.split('id="refs"')[1].split('id="footnotes"')[0]
        self.assertRegex(refs, r"引用文献[\s\S]*\[1\] 日本看護学会")
        self.assertRegex(refs, r"参考資料[\s\S]*\[1\] 山田花子")
        groups = {g["group"]: g for g in report["groups"]}
        self.assertTrue(groups["cited"]["numbered"]); self.assertEqual(groups["cited"]["entries"][0]["id"], "src-0001")
        self.assertEqual([e["id"] for e in groups["background"]["entries"]], ["src-0002"], "the experience article is a separate list")
        self.assertEqual(m["bibliography"].check_report(m["common"].read_project(), report), [])

    def test_04_author_year_citations_with_numbered_bibliography(self):
        root, m, html, report = self.build("bib-author-year", {"style": "author-year", "in_text_citation_style": "author-year", "bibliography_numbering": "numbered",
                                                                "numbering_scope": "continuous"})
        body = html.split('id="refs"')[0]
        self.assertRegex(body, r"日本看護学会[,、]? ?2024", "author-year form in the text")
        self.assertNotIn("[1]", body)
        refs = html.split('id="refs"')[1]
        self.assertRegex(refs, r"\[1\] 日本看護学会 \(2024年?\)")
        self.assertRegex(refs, r"\[2\] 山田花子", "continuous numbering runs across the lists")
        self.assertEqual(m["bibliography"].check_report(m["common"].read_project(), report), [])

    def test_legacy_citations_keep_the_single_list(self):
        root, m = job("bib-legacy", files=self.FILES)
        register_sources(m, root, self.NOTES)
        html = render_html(m, "# A {#ch-a}\n\n観察 [cite:src-0001]。\n")
        self.assertEqual(m["bibliography"].policy(m["common"].read_project())["builder"], "legacy")
        self.assertNotIn("引用文献", html); self.assertIn("参考文献", html)

    def test_05_06_evidence_is_citable_background_is_not(self):
        root, m = job("roles", arch={"mode": "auto"}, files=self.FILES, usage=[{"role": "evidence"}, {"role": "background"}])
        register_sources(m, root, self.NOTES)
        roles = m["source_roles"].table()
        self.assertTrue(roles["src-0001"]["citation_allowed"]); self.assertFalse(roles["src-0002"]["citation_allowed"])
        audit = m["audit"]
        write(root, "source/metadata/outline.yaml", self.OUTLINE)
        text = "# A {#ch-a}\n\n## 節 {#sec-a}\n\n2023年の調査で転倒は30%減った [cite:src-0001]。\n\n新人の3割が2024年に離職を考えた [cite:src-0002]。\n"
        write(root, "source/manuscript/01-a.md", text)
        records = {"ch-a": m["manuscript"].analyze_all()["source/manuscript/01-a.md"]}
        issues = audit.citation_issues(records, m["common"].read_project())
        role_issues = [i for i in issues if i["type"] == "source-role"]
        self.assertTrue(role_issues and all("src-0002" in (i["evidence"] or "") + i["detail"] for i in role_issues))
        self.assertTrue(all(i["severity"] == "high" for i in role_issues))
        self.assertFalse([i for i in issues if i["type"] == "source-role" and "src-0001" in (i.get("evidence") or "")], "evidence stays citable")
        # A note's estimate never overrides the user's role.
        write(root, "research/notes/src-0002.yaml", {"source": "src-0002", "relevance": "core", "summary": "x" * 70, "key_claims": ["claim text"], "source_role": "evidence"})
        self.assertEqual(m["source_roles"].table()["src-0002"]["role"], "background")


class UploadsAndReferences(unittest.TestCase):
    def test_07_layout_reference_is_never_content(self):
        pdf = (Path(__file__).parent / "fixtures/reference-1.pdf").read_bytes()
        root, m = job("layout-ref", arch={"mode": "auto"}, files=[("guideline.md", "# 指針\n\n" + LONG)],
                      assets=[("layout-sample.pdf", pdf, {"role": "layout_reference", "asset_role": "layout_reference", "notes": "余白と段組だけ参考にする"})])
        src, sr, pa = m["sources"], m["source_roles"], m["publication_architecture"]
        index = src.init_supplied()
        self.assertEqual([s["path"] for s in index["sources"]], ["input/sources/guideline.md"], "the layout reference is not a source")
        src.ingest(); m["citations"].generate()
        refs = json.loads((root / "source/references/references.json").read_text(encoding="utf-8"))
        self.assertNotIn("layout-sample", json.dumps(refs, ensure_ascii=False))
        assets = sr.write_asset_registry()
        self.assertEqual((assets[0]["role"], assets[0]["placeable_path"]), ("layout_reference", None))
        pa.seed()
        self.assertTrue(any("layout-references.yaml" in e for e in pa.check()), "composition analysis is required")
        write(root, "plan/layout-references.yaml", {"references": [{"asset": "asset-001", "content_used": False, "apply": ["広い外側余白"], "features": {
            k: "観察結果" for k in pa.VOCAB["layout_reference_fields"][:9]}}]})
        self.assertFalse([e for e in pa.check() if "layout-references" in e])
        # A reference cannot be placed in the book.
        errors = m["assets"].uploaded_asset_errors({"uploaded_assets": []}, [{"id": "fig-x", "type": "screenshot", "uploaded_asset": "asset-001"}], [], m["common"].read_project())
        self.assertTrue(any("cannot be placed" in e for e in errors))

    def test_08_uploaded_inline_figure_reaches_chapter_and_asset_plans(self):
        root, m = job("upload-figure", arch={"mode": "auto"}, files=[("guideline.md", "# 指針\n\n" + LONG)],
                      assets=[("ward-flow.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, {"role": "asset", "asset_role": "inline_figure", "intended_chapter": "第2章",
                                                                                 "notes": "第2章の病棟業務の流れを説明する場所で使用", "priority": "high"})])
        sr, ep, planning = m["source_roles"], m["editorial_plan"], m["planning"]
        items = sr.write_asset_registry()
        self.assertTrue((root / items[0]["placeable_path"]).is_file(), "the upload is copied where the manuscript can place it")
        write(root, "source/metadata/outline.yaml", {"chapters": [
            {"id": "ch-intro", "title": "導入", "file": "source/manuscript/01-intro.md", "purpose": "p", "target_characters": 2000, "content_intent": "全体像を示す", "blocks": ["callout"]},
            {"id": "ch-ward", "title": "病棟の一日", "file": "source/manuscript/02-ward.md", "purpose": "p", "target_characters": 2000, "content_intent": "業務の流れを示す", "blocks": ["workflow_diagram"]}]})
        chapters = planning.load_outline({})
        self.assertEqual([a["id"] for a in sr.for_chapter("ch-ward")], ["asset-001"], "「第2章」 resolves to the second chapter")
        self.assertEqual(sr.for_chapter("ch-intro"), [])
        packet = planning.packet(chapters[1], chapters, {})
        self.assertEqual(packet["uploaded_assets"][0]["instruction"], "第2章の病棟業務の流れを説明する場所で使用")
        plans = {"ch-ward": plan(ep, "ch-ward", [section("s1", 1000), section("s2", 1000)])}
        self.assertIn("uploaded_asset_unplanned", rules(check(m, chapters[1:], plans), "medium"))
        plans["ch-ward"]["sections"][0]["devices"].append(device("fig-ward", "figure", asset_ref="asset-001", basis="source", source_ids=["src-0001"],
                                                                 information_shape={"kind": "source_image"}))
        self.assertNotIn("uploaded_asset_unplanned", rules(check(m, chapters[1:], plans)))
        errors = m["assets"].uploaded_asset_errors({"uploaded_assets": []}, [], chapters, m["common"].read_project())
        self.assertTrue(any("asset-001" in e and "uploaded_assets" in e for e in errors), "the asset planner must decide")
        good = {"uploaded_assets": [{"asset": "asset-001", "decision": "placed", "asset_id": "fig-ward", "chapter": "ch-ward", "reason": "指示どおり第2章の業務の流れの節に配置"}]}
        figure = {"id": "fig-ward", "type": "screenshot", "chapter": "ch-ward", "path": items[0]["placeable_path"], "uploaded_asset": "asset-001"}
        self.assertEqual(m["assets"].uploaded_asset_errors(good, [figure], chapters, m["common"].read_project()), [])
        moved = dict(figure, chapter="ch-intro")
        self.assertTrue(any("wants it in ch-ward" in e for e in m["assets"].uploaded_asset_errors(good, [moved], chapters, m["common"].read_project())))


class UserIntent(unittest.TestCase):
    def test_09_explicit_prohibition_is_enforced_in_the_publication_plan(self):
        root, m = job("intent-no-exercises", arch={"mode": "auto", "archetype": "textbook"}, instructions="章末問題禁止。ケースを多く、固すぎない文章にしてほしい。")
        pa, ep, ui = m["publication_architecture"], m["editorial_plan"], m["user_intent"]
        intent = pa.interpret()
        self.assertIn("no_exercises", {s["id"] for s in intent["explicit_signals"]})
        self.assertEqual(intent["fields"]["tone"]["origin"], "user_text")
        arch = pa.derive()
        self.assertIn("exercises", arch["block_policy"]["forbidden"]); self.assertEqual(arch["exercise_policy"], "none")
        self.assertIn("case_study", arch["block_policy"]["preferred"])
        # An architecture file that tries to bring exercises back is corrected on load and rejected by the check.
        pa.seed()
        data = json.loads(json.dumps(arch)); data["block_policy"]["forbidden"] = []; data["block_policy"]["preferred"].append("exercises"); data["exercise_policy"] = "every_chapter"
        write(root, "plan/publication-architecture.yaml", data)
        self.assertIn("exercises", pa.load()["block_policy"]["forbidden"])
        self.assertEqual(pa.load()["exercise_policy"], "none")
        errors = pa.check()
        self.assertTrue(any("forbidden must include exercises" in e for e in errors)); self.assertTrue(any("exercise_policy must be none" in e for e in errors))
        # Editorial planning cannot plan them; the manuscript QA catches them.
        plans = {"ch-a": plan(ep, "ch-a", [section("s1", 1000), section("s2", 1000)], end=["check_questions", "answer_key"])}
        self.assertIn("block_forbidden", rules(check(m, [chapter("ch-a")], plans), "error"))
        write(root, "source/metadata/outline.yaml", {"chapters": [{"id": "ch-a", "title": "A", "file": "source/manuscript/01-a.md", "purpose": "p", "target_characters": 1000,
                                                                   "content_intent": "章の目的をここに書く", "blocks": ["exercises"]}]})
        self.assertTrue(any("forbidden" in e or "exercise_policy is none" in e for e in pa.check_outline(m["planning"].load_outline({}))))
        write(root, "source/manuscript/01-a.md", "# A {#ch-a}\n\n## 節 {#sec-a}\n\n本文。\n\n::: {.exercise #q-a}\n問1\n:::\n")
        qa = m["architecture_qa"].run(write=False)
        self.assertIn("forbidden_block_in_manuscript", {f["rule"] for f in qa["findings"] if f["severity"] == "high"})
        # The phase task carries the verbatim text and names the architecture files.
        orch = m["orchestrator"]; project, state = orch.load_state(); ctx = orch.Context(project, state)
        result = orch.h_publication_planning(ctx)
        item = result.tasks[0]
        self.assertEqual(item["user_intent"]["verbatim"], "章末問題禁止。ケースを多く、固すぎない文章にしてほしい。")
        self.assertIn("plan/publication-architecture.yaml", item["outputs"])


class Visuals(unittest.TestCase):
    def test_10_visual_diversity(self):
        root, m = job("visual-diversity", arch={"mode": "auto", "archetype": "practical_guide"})
        ep, vp, pa = m["editorial_plan"], m["visual_plan"], m["publication_architecture"]
        chapters = [chapter(f"ch-{c}", 4000) for c in "abcd"]
        for c in chapters:
            p = plan(ep, c["id"], [section("s1", 2000, [device(f"fig-{c['id']}-flow", "workflow_diagram", basis="source", source_ids=["src-0001"],
                                                               information_shape={"kind": "process", "steps": 5, "branches": 2})]), section("s2", 2000)])
            write(root, f"plan/editorial/{c['id']}.yaml", p)
        arch = pa.load()
        self.assertEqual(vp.seed(chapters, arch), 4)
        data = vp.load()
        self.assertEqual({v["type"] for v in data["visuals"]}, {"workflow"}, "block visual_type seeds the taxonomy type")
        for v in data["visuals"]:
            v.update(purpose="流れを把握する", content="5段階と2つの分岐", reason="分岐を一目で示す", caption_intent="分岐点に注目させる", duplication_check="本文は判断理由だけ述べる")
        write(root, "plan/visual-plan.yaml", data)
        result = vp.check(chapters, arch)
        found = {f["rule"] for f in result["findings"] if not f.get("waived")}
        self.assertIn("visual_monotony", found); self.assertIn("visual_same_type_every_chapter", found); self.assertFalse(result["ok"])
        for v, t in zip(data["visuals"], ("workflow", "decision_tree", "case_flow", "workflow")): v["type"] = t
        write(root, "plan/visual-plan.yaml", data)
        varied = vp.check(chapters, arch)
        self.assertFalse({"visual_monotony", "visual_variety_low", "visual_same_type_every_chapter"} & {f["rule"] for f in varied["findings"]})
        self.assertTrue(varied["ok"])
        self.assertTrue((root / "reports/visual-plan-qa.yaml").is_file())


class Modes(unittest.TestCase):
    def test_11_fixed_mode_keeps_the_legacy_template(self):
        root, m = job("mode-fixed")   # no publication_architecture: a legacy job
        pa, ep = m["publication_architecture"], m["editorial_plan"]
        self.assertEqual(pa.request()["mode"], "fixed"); self.assertTrue(pa.request()["legacy"])
        chapters = [chapter("ch-a")]
        plans = {"ch-a": plan(ep, "ch-a", [section("s1", 1000), section("s2", 1000)])}
        profile = m["publication_profile"].resolve(m["common"].read_project(), {"page": {"size": "A5"}})
        legacy = ep.check(chapters, plans, profile, None, {})            # the old call signature
        self.assertIn("chapter_end_missing", rules(legacy, "error"), "the profile's chapter end stays required in FIXED mode")
        self.assertEqual(rules(legacy), rules(check(m, chapters, plans)), "FIXED architecture = legacy behaviour")
        orch = m["orchestrator"]; project, state = orch.load_state(); ctx = orch.Context(project, state)
        self.assertTrue(orch.h_publication_planning(ctx).done, "legacy jobs need no publication-planning task")
        self.assertEqual(m["bibliography"].policy(project)["builder"], "legacy")
        # An explicit FIXED request behaves the same.
        root2, m2 = job("mode-fixed-explicit", arch={"mode": "fixed"})
        self.assertIn("chapter_end_missing", rules(check(m2, chapters, {"ch-a": plan(m2["editorial_plan"], "ch-a", [section("s1", 1000), section("s2", 1000)])}), "error"))

    def test_12_auto_mode_allows_chapters_to_differ(self):
        root, m = job("mode-auto", arch={"mode": "auto", "archetype": "practical_guide"})
        ep, pa = m["editorial_plan"], m["publication_architecture"]
        chapters = [chapter(c) for c in ("ch-a", "ch-b", "ch-c")]
        different = {
            "ch-a": plan(ep, "ch-a", [section("s1", 1000, [device("co-a", "callout")]), section("s2", 1000)]),
            "ch-b": plan(ep, "ch-b", [section("s1", 1000, [device("tbl-b", "decision_table", basis="source", source_ids=["src-0001"],
                                                                  information_shape={"kind": "comparison", "items": 4, "attributes": 3})]), section("s2", 1000)], end=["checklist"]),
            "ch-c": plan(ep, "ch-c", [section("s1", 1000, [device("alg-c", "algorithm_card"), device("pf-c", "pitfalls")]), section("s2", 1000)], end=["next_actions"])}
        result = check(m, chapters, different)
        self.assertFalse({"chapter_end_missing", "chapter_end_uniform", "block_forbidden", "device_unknown_type"} & rules(result))
        self.assertEqual(result["summary"]["structure_mode"], "auto")
        same = {c["id"]: plan(ep, c["id"], [section("s1", 1000), section("s2", 1000)], end=["summary", "checklist"]) for c in chapters}
        self.assertIn("chapter_end_uniform", rules(check(m, chapters, same), "medium"), "the same apparatus everywhere is flagged")
        missing_why = {"ch-a": plan(ep, "ch-a", [section("s1", 1000), section("s2", 1000)], end=[{"type": "checklist"}])}
        self.assertIn("chapter_end_missing_why", rules(check(m, chapters[:1], missing_why), "error"))
        # The outline may not clone one block set into every chapter without a reason.
        cloned = [dict(chapter(c), content_intent="この章で読者ができるようになること", blocks=["checklist", "figure"]) for c in ("ch-a", "ch-b", "ch-c", "ch-d")]
        self.assertTrue(any("same blocks" in e for e in pa.check_outline(cloned)))
        varied = [dict(c, blocks=b) for c, b in zip(cloned, (["callout"], ["timeline", "workflow_diagram"], ["algorithm_card", "decision_tree"], ["comparison_table", "checklist"]))]
        self.assertEqual(pa.check_outline(varied), [])


class Propagation(unittest.TestCase):
    def test_architecture_reaches_tasks_and_packets(self):
        instructions = "図表を多く。章末問題はいらない。"
        root, m = job("propagation", arch={"mode": "guided", "archetype": "practical_guide", "block_policy": {"preferred": ["clinical_case"], "forbidden": ["column"]}},
                      instructions=instructions)
        pa, orch = m["publication_architecture"], m["orchestrator"]
        project, state = orch.load_state(); ctx = orch.Context(project, state)
        self.assertEqual(state.get("architecture_protocol"), 1)
        task = orch.h_publication_planning(ctx).tasks[0]
        text = "\n".join(task["instructions"])
        self.assertIn("GUIDED", text); self.assertIn("block_policy", text)
        seeded = pa.load()
        self.assertEqual(set(seeded["block_policy"]["forbidden"]) >= {"column", "exercises"}, True)
        self.assertIn("clinical_case", seeded["block_policy"]["preferred"])
        self.assertEqual(seeded["visual_policy"]["density"], "high", "「図表を多く」 raises the visual density")
        # Completing the agent's part accepts the phase.
        intent = m["common"].yaml_data(root / "plan/publication-intent.yaml"); intent["reviewed_by_agent"] = True
        write(root, "plan/publication-intent.yaml", json.loads(json.dumps(intent)))
        self.assertEqual(pa.check(), [])
        self.assertTrue(orch.h_publication_planning(ctx).done)
        # Drafting and editorial-planning instructions and packets carry the architecture.
        lines = "\n".join(orch.architecture_lines({"id": "ch-a", "content_intent": "手順を示す", "blocks": ["clinical_case"]}, ctx))
        self.assertIn("FORBIDDEN", lines); self.assertIn("column", lines); self.assertIn("clinical_case", lines)
        write(root, "source/metadata/outline.yaml", {"chapters": [{"id": "ch-a", "title": "A", "file": "source/manuscript/01-a.md", "purpose": "p", "target_characters": 1000,
                                                                   "content_intent": "手順を示す", "blocks": ["clinical_case"]}]})
        chapters = m["planning"].load_outline({})
        packet = m["planning"].packet(chapters[0], chapters, {})
        self.assertEqual(packet["publication_architecture"]["planned_blocks"], ["clinical_case"])
        self.assertIn("column", packet["publication_architecture"]["forbidden_blocks"])
        self.assertTrue(any("Publication architecture (GUIDED" in l for l in orch.editorial_architecture_lines(ctx, chapters[0])))


class AuditRegressions(unittest.TestCase):
    """Fixes from the adversarial audit (docs/INTENT_DRIVEN_PUBLICATION_REVIEW.md)."""
    FILES = [(f"s{i}.md", "# x\n\n" + LONG) for i in range(1, 5)]
    NOTES = {"src-0001": {"bibliographic": {"title": "Scaling A", "authors": [{"family": "Kaplan", "given": "Jared"}], "published": "2020", "type": "article-journal",
                                            "container": "arXiv", "doi": "10.1/abc"}},
             "src-0002": {"bibliographic": {"title": "Scaling B", "authors": [{"family": "Kaplan", "given": "Jared"}], "published": "2020", "type": "article-journal", "container": "arXiv"}},
             "src-0003": {"bibliographic": {"title": "体験記", "authors": ["山田 花子"], "published": "2023"}}}
    OUTLINE = {"chapters": [{"id": "ch-a", "title": "A", "file": "source/manuscript/01-a.md", "purpose": "p", "target_characters": 1000, "sources": {"primary": ["src-0001"], "supporting": ["src-0003"]}}]}

    def build(self, name, citations):
        root, m = job(name, arch={"mode": "auto"}, citations=citations, files=self.FILES, usage=[{}, {}, {"role": "background"}, {}])
        register_sources(m, root, self.NOTES); write(root, "source/metadata/outline.yaml", self.OUTLINE)
        html = render_html(m, "# A {#ch-a}\n\n## s {#sec-a}\n\n一 [cite:src-0001]。二 [cite:src-0002]。三 [cite:src-0001]。\n")
        return m, html, json.loads((root / "reports/bibliography.json").read_text(encoding="utf-8"))

    def test_numeric_text_never_shares_numbers_with_other_lists(self):
        m, html, report = self.build("reg-numeric", {"style": "numeric", "in_text_citation_style": "numeric", "bibliography_numbering": "numbered", "numbering_scope": "per_group"})
        numbers = [e["number"] for g in report["groups"] for e in g["entries"]]
        self.assertEqual(numbers, [1, 2, 3], "参考資料 continues after the cited list")
        self.assertIn("https://doi.org/10.1/abc", html, "DOI rendered by the CSL")
        self.assertEqual(html.split('id="refs"')[0].count("[1]"), 2, "repeated citation keeps its number")

    def test_same_author_same_year_suffix_matches_the_text(self):
        m, html, report = self.build("reg-ay", {"style": "author-year", "in_text_citation_style": "author-year", "bibliography_numbering": "numbered"})
        body, refs = html.split('id="refs"')
        self.assertRegex(body, r"2020年?a"); self.assertRegex(body, r"2020年?b")
        self.assertRegex(refs, r"Kaplan \(2020年?a\)[\s\S]*Scaling A"); self.assertRegex(refs, r"Kaplan \(2020年?b\)[\s\S]*Scaling B")

    def test_guessed_archetype_does_not_prefer_exercises(self):
        root, m = job("reg-guess", arch={"mode": "auto"}, description="注意機構の原理を一貫して解説する小冊子")
        arch = m["publication_architecture"].derive()
        self.assertEqual(arch["archetype"]["primary"], "textbook")
        self.assertNotIn("exercises", arch["block_policy"]["preferred"]); self.assertEqual(arch["exercise_policy"], "optional")
        root, m = job("reg-chosen", arch={"mode": "auto", "archetype": "textbook"})
        self.assertIn("exercises", m["publication_architecture"].derive()["block_policy"]["preferred"], "an explicit textbook keeps its exercises")

    def test_pacing_never_suggests_an_excluded_block(self):
        root, m = job("reg-pacing", arch={"mode": "auto"}, instructions="章末のまとめは不要。コラムはいらない。")
        pacing = importlib.import_module("pacing")
        result = {"findings": [{"severity": "high", "chapter": "ch-a", "detail": "wall", "actions": [
            {"op": op, "at_pages": [3], "why": "w"} for op in ("insert_summary", "add_case_study", "add_pull_quote", "split_section")]}]}
        lines = "\n".join(pacing.task_lines(result, "ch-a"))
        self.assertNotIn("insert_summary", lines); self.assertIn("add_case_study", lines)

    def test_unmet_explicit_wish_blocks_until_waived(self):
        root, m = job("reg-wish", arch={"mode": "auto"}, instructions="ケースを多く入れてほしい。")
        write(root, "source/metadata/outline.yaml", {"chapters": [{"id": "ch-a", "title": "A", "file": "source/manuscript/01-a.md", "purpose": "p", "target_characters": 1000}]})
        write(root, "source/manuscript/01-a.md", "# A {#ch-a}\n\n## s {#sec-a}\n\n本文だけ。\n")
        qa = m["architecture_qa"]
        self.assertFalse(qa.run(write=False)["ok"])
        m["publication_architecture"].seed(); arch = m["publication_architecture"].derive()
        arch["qa_waivers"] = [{"rule": "user_preference_unmet", "reason": "資料に事例が一件もないため（最終報告に記載）"}]
        write(root, "plan/publication-architecture.yaml", arch)
        self.assertTrue(qa.run(write=False)["ok"])

    def test_legacy_job_agent_estimate_does_not_restrict_citation(self):
        root, m = job("reg-legacy", files=self.FILES[:1])
        register_sources(m, root, {"src-0001": {"source_role": "background", "bibliographic": {"title": "t"}}})
        entry = m["source_roles"].table()["src-0001"]
        self.assertEqual(entry["role"], "background"); self.assertTrue(entry["citation_allowed"])


if __name__ == "__main__": unittest.main()

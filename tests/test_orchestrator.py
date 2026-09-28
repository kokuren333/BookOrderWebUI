"""Deterministic unit/integration tests for the BookOrder vNext orchestration logic.

Requires Pandoc (YAML/Markdown parsing, citeproc); Typst is only needed by the design tests.
Run: python tests/test_orchestrator.py  (or python -m unittest tests/test_orchestrator.py)
"""
from functools import partial
import http.server
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import unittest

REPO = Path(__file__).resolve().parent.parent
BASE = REPO / ".test-output/unit"
MODULES = ["common", "crossref", "sources", "research", "planning", "manuscript", "assets", "audit", "citations", "orchestrator",
           "design", "diagrams", "book_ir", "schema", "validate", "build", "package", "check_env",
           "publication_profile", "pacing", "layout_metrics", "figure_spec", "figure_check", "chartkit", "visual_review", "editorial_plan", "user_intent"]


def make_job(name, pages=300, language="ja", urls=(), files=(), web_research=True, coverage=True):
    """Fresh job folder from job-template; modules are re-imported so ROOT points at it."""
    root = BASE / name
    if root.exists(): shutil.rmtree(root)
    shutil.copytree(REPO / "job-template", root, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "preview.png"))
    (root / "input/sources").mkdir(parents=True, exist_ok=True)
    for file_name, text in files: (root / "input/sources" / file_name).write_text(text, encoding="utf-8")
    project = {"format": "portable-publishing-job", "format_version": "0.2",
               "book": {"title": "Test", "description": "d", "target_readers": "r", "target_pages": pages, "language": language},
               "research": {"allow_web_research": web_research, "require_supplied_coverage": coverage}, "citations": {"style": "numeric"},
               "figures": {"tables": True, "diagrams": True, "charts": True, "generative_images": False},
               "outputs": {"canonical_markdown": True, "docx": False, "semantic_html": True, "pdf": False, "static_site": False, "epub": False},
               "input": {"urls": list(urls), "sources": [{"original_name": n, "path": f"input/sources/{n}", "size_bytes": 1} for n, _ in files]}}
    (root / "project.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    for folder in ("source/manuscript", "source/metadata", "source/references", "reports", "plan"): (root / folder).mkdir(parents=True, exist_ok=True)
    for meta, key in (("outline", "chapters"), ("glossary", "terms"), ("sources", "sources"), ("figures", "figures")):
        (root / f"source/metadata/{meta}.yaml").write_text(f"{key}: []\n", encoding="utf-8")
    scripts = str(root / "scripts")
    here = str(Path(__file__).resolve().parent)
    sys.path[:] = [scripts] + [p for p in sys.path if not p.endswith("scripts") and str(Path(p or ".").resolve()) != here]
    for module in MODULES: sys.modules.pop(module, None)
    sys.modules.pop("renderers", None); sys.modules.pop("renderers.typst", None)
    loaded = {m: importlib.import_module(m) for m in ("common", "sources", "research", "planning", "manuscript", "orchestrator", "audit", "citations", "crossref")}
    return root, loaded


def write(root, relative, text):
    path = root / relative; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if isinstance(text, str) else json.dumps(text, ensure_ascii=False), encoding="utf-8")


class Server:
    def __enter__(self):
        pages = BASE / "_web"; pages.mkdir(parents=True, exist_ok=True)
        long = "<p>" + "注意機構は入力の各位置を重み付けして参照する。" * 60 + "</p>"
        (pages / "full.html").write_text(f"<html><head><title>Full</title><meta name='author' content='A'></head><body><nav>MENU</nav><article>{long}</article><footer>FOOT</footer></body></html>", encoding="utf-8")
        (pages / "teaser.html").write_text("<html><body><article><p>続きを読むには有料会員登録が必要です。</p></article></body></html>", encoding="utf-8")
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(http.server.SimpleHTTPRequestHandler, directory=str(pages)))
        self.server.RequestHandlerClass.log_message = lambda *a: None
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        return self
    def __exit__(self, *exc): self.server.shutdown()


def ready_state(orch, root):
    project, state = orch.load_state()
    return project, state


class SourceHandling(unittest.TestCase):
    def test_all_supplied_urls_attempted_duplicates_and_unavailable(self):
        with Server() as web:
            urls = [f"{web.base}/full.html", f"{web.base}/missing.html", f"{web.base}/full.html?utm_source=x", f"{web.base}/teaser.html"]
            root, m = make_job("sources", urls=urls, files=[("notes.md", "# ノート\n\n" + "本文。" * 400)])
            src = m["sources"]
            index = src.init_supplied()
            self.assertEqual([s["id"] for s in index["sources"]], ["src-0001", "src-0002", "src-0003", "src-0004", "src-0005"])
            src.init_supplied()  # idempotent
            self.assertEqual(len(src.load_index()["sources"]), 5)
            src.ingest()
            status = {s["id"]: s for s in src.load_index()["sources"]}
            self.assertEqual(status["src-0001"]["ingest_status"], "fully_ingested")
            self.assertEqual(status["src-0002"]["ingest_status"], "fully_ingested")
            self.assertNotIn("MENU", (root / status["src-0002"]["content_path"]).read_text(encoding="utf-8"))
            self.assertEqual(status["src-0002"]["author"], "A")
            self.assertEqual(status["src-0003"]["ingest_status"], "needs_agent_fetch")
            self.assertEqual(status["src-0004"]["ingest_status"], "duplicate")
            self.assertEqual(status["src-0004"]["duplicate_of"], "src-0002")
            self.assertEqual(status["src-0005"]["ingest_status"], "partially_ingested")
            self.assertTrue(all(s["attempts"] for s in status.values()), "every supplied source attempted")
            counts = src.counts(src.load_index(), "supplied")
            self.assertEqual(counts["pending_total"], 1)
            with self.assertRaises(ValueError): src.mark_unavailable("src-0003", "")
            src.mark_unavailable("src-0003", "HTTP 404 from the publisher and archive")
            with self.assertRaises(ValueError): src.confirm_complete("src-0005", "It is complete, trust me")  # gated content
            src.accept_partial("src-0005", "Only the teaser is public; the body requires a paid account")
            self.assertEqual(src.counts(src.load_index(), "supplied")["pending_total"], 0)
            self.assertTrue((root / "research/source-status.json").is_file())

    def test_ingestion_phase_blocks_until_zero_pending(self):
        with Server() as web:
            root, m = make_job("ingest-gate", urls=[f"{web.base}/missing.html"])
            orch = m["orchestrator"]
            state, tasks, _ = orch.advance()
            self.assertEqual(state["phases"]["source_ingestion"], "running")
            self.assertEqual([t["id"] for t in tasks], ["ingest:src-0001"])
            m["sources"].mark_unavailable("src-0001", "HTTP 404 and no archive copy", "agent browser: 404")
            state, tasks, _ = orch.advance()
            self.assertEqual(state["phases"]["source_ingestion"], "complete")

    def test_unavailable_requires_an_attempt(self):
        root, m = make_job("unattempted", urls=["https://example.invalid/a"])
        m["sources"].init_supplied()
        with self.assertRaises(ValueError): m["sources"].mark_unavailable("src-0001", "Could not access the page")

    def test_agent_submission_persists_content(self):
        root, m = make_job("submit", files=[("scan.pdf", "not really a pdf")])
        m["sources"].init_supplied()
        write(root, "extract.md", "抽出した本文。" * 200)
        source = m["sources"].submit("src-0001", root / "extract.md", method="agent-ocr", title="Scan")
        self.assertEqual(source["ingest_status"], "fully_ingested")
        self.assertTrue((root / "research/supplied/src-0001/source.md").is_file())
        meta = json.loads((root / "research/supplied/src-0001/metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["title"], "Scan"); self.assertEqual(len(meta["sha256"]), 64)


class Research(unittest.TestCase):
    def test_supplementary_research_is_persisted_and_checked(self):
        root, m = make_job("research")
        research, src = m["research"], m["sources"]
        self.assertIn("Missing research/research-plan.yaml", research.check_research_plan()[0])
        entry = research.log_search("sparse attention survey", gap="gap-1", tool_name="websearch", selected=["https://example.invalid/x"])
        self.assertEqual(entry["id"], "q-0001")
        self.assertEqual(len((root / "research/search-log.jsonl").read_text(encoding="utf-8").splitlines()), 1)
        write(root, "research/research-plan.yaml", "web_research: performed\ngaps:\n  - {id: gap-1, description: 'no efficiency source', status: unresolvable, queries: [q-0001], note: 'nothing reliable found'}\n")
        self.assertEqual(research.check_research_plan(), [])
        write(root, "research/research-plan.yaml", "web_research: performed\ngaps:\n  - {id: gap-1, description: 'no efficiency source', status: unresolvable, queries: [q-0099], note: 'nothing reliable found'}\n")
        self.assertTrue(any("record the searches" in e for e in research.check_research_plan()))

    def test_disabled_web_research_rejects_discovery(self):
        root, m = make_job("no-web", web_research=False)
        m["sources"].add_discovered(url="https://example.invalid/found", query="q")
        write(root, "research/research-plan.yaml", "web_research: disabled\ngaps:\n  - {id: g, description: 'gap text', status: unresolvable, note: 'recorded as a limitation'}\n")
        self.assertTrue(any("disabled" in e for e in m["research"].check_research_plan()))

    def test_stable_ids_freeze_and_post_draft_additions(self):
        root, m = make_job("freeze", urls=["https://example.invalid/a", "https://example.invalid/b"])
        src, research = m["sources"], m["research"]
        src.init_supplied()
        lock = research.freeze()
        self.assertEqual(lock["sources"], ["src-0001", "src-0002"])
        added = src.add_discovered(url="https://example.invalid/c", reason="audit found a gap", post_draft=True, issue="audit-004")
        self.assertEqual(added["id"], "src-0003")
        self.assertEqual([s["id"] for s in src.load_index()["sources"]], ["src-0001", "src-0002", "src-0003"])
        lock = research.load_lock()
        self.assertEqual(lock["sources"], ["src-0001", "src-0002"]); self.assertEqual(lock["post_draft_additions"][0]["id"], "src-0003")
        self.assertEqual(research.check_lock(), [])
        src.add_discovered(url="https://example.invalid/d")  # untracked addition after freeze
        self.assertTrue(any("without being recorded" in e for e in research.check_lock()))
        with self.assertRaises(ValueError): src.add_discovered(url="https://example.invalid/e", post_draft=True)


class Citations(unittest.TestCase):
    def setUp(self):
        self.root, self.m = make_job("citations", pages=2)
        write(self.root, "source/references/references.json", [
            {"id": "src-0001", "type": "webpage", "title": "Alpha", "author": [{"literal": "Aoki"}], "issued": {"date-parts": [[2020]]}},
            {"id": "src-0002", "type": "webpage", "title": "Beta", "author": [{"literal": "Baba"}], "issued": {"date-parts": [[2021]]}}])

    def render(self, text, style="numeric"):
        project = self.m["common"].read_project(); project["citations"]["style"] = style
        ast = self.m["common"].parse_markdown(text)
        doc = self.m["common"].combined(project, [(None, ast)])
        return self.m["common"].run([self.m["common"].tool("pandoc"), "-f", "json", "-t", "plain"], json.dumps(doc))

    def test_semantic_ids_render_as_numbers_in_first_citation_order(self):
        text = self.render("# Ch {#ch-a}\n\nFirst [cite:src-0002]. Both [cite:src-0001,src-0002]. Again [cite:src-0002, p. 3].\n")
        self.assertIn("First [1]", text); self.assertIn("Both [1, 2]", text); self.assertIn("[1, p. 3]", text)
        self.assertIn("[1] Baba", text); self.assertIn("[2] Aoki", text)

    def test_author_year_style(self):
        text = self.render("# Ch {#ch-a}\n\nClaim [cite:src-0001].\n", "author-year")
        self.assertIn("Aoki 2020", text)

    def test_registry_generates_csl_from_sources(self):
        src = self.m["sources"]
        index = src.load_index()
        source = src.register(index, kind="url", url="https://example.invalid/x", title="Gamma")
        source.update(ingest_status="fully_ingested", published="2024-05-02", author="Chiba; Doi", retrieved_at="2026-09-01T00:00:00+00:00")
        src.save_index(index)
        entries = self.m["citations"].generate()
        self.assertEqual(entries[0]["id"], "src-0001")
        self.assertEqual(entries[0]["issued"], {"date-parts": [[2024, 5, 2]]})
        self.assertEqual([a["literal"] for a in entries[0]["author"]], ["Chiba", "Doi"])
        self.assertIn("src-0001", (self.root / "source/metadata/sources.yaml").read_text(encoding="utf-8"))


class CrossReferences(unittest.TestCase):
    def test_numbering_and_resolution(self):
        root, m = make_job("xref", pages=2)
        common = m["common"]
        one = "# One {#ch-one}\n\n## Intro {#sec-intro}\n\nSee @fig:model, @tbl:data and @eq:loss.\n\n![Model](x.png){#fig-model}\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nTable: Data {#tbl-data}\n"
        two = "# Two {#ch-two}\n\n## Loss {#sec-loss}\n\nBack to @sec:intro and @ch:one; number only [-@eq:loss].\n\n::: {.equation #eq-loss}\n$$L = x^2$$\n:::\n"
        registry = {}
        doc = common.combined(common.read_project(), [(None, common.parse_markdown(one)), (None, common.parse_markdown(two))], registry)
        self.assertEqual(registry["fig-model"]["label"], "図1.1"); self.assertEqual(registry["tbl-data"]["label"], "表1.1")
        self.assertEqual(registry["eq-loss"]["number"], "2.1"); self.assertEqual(registry["sec-loss"]["number"], "2.1")
        text = common.run([common.tool("pandoc"), "-f", "json", "-t", "plain"], json.dumps(doc))
        self.assertIn("See 図1.1, 表1.1 and 式(2.1)", text); self.assertIn("Back to 1.1節 and 第1章", text); self.assertIn("number only (2.1)", text)
        with self.assertRaises(ValueError):
            common.combined(common.read_project(), [(None, common.parse_markdown("# X {#ch-x}\n\nSee @fig:missing.\n"))])


class Length(unittest.TestCase):
    def test_page_target_to_budget(self):
        # Compatibility: a 300-page target selects the long profile; the body size is derived from the page model
        # (780 characters per A5 text page, 25% non-prose area, 6 front pages, 6% back matter).
        root, m = make_job("scale")
        scale = m["planning"].compute_scale(m["common"].read_project(), {"page": {"size": "A5"}, "layout": {"density": "standard"}})
        self.assertEqual((scale["target_characters"], scale["minimum_characters"]), (162255, 129804))
        self.assertEqual(scale["profile"]["id"], "long.general"); self.assertEqual(scale["minimum_chapters"], 7)
        self.assertLessEqual(abs(scale["requested_pages"] - 300), 1)
        self.assertTrue((root / "plan/profile.resolved.yaml").is_file())
        b5 = m["planning"].compute_scale(m["common"].read_project(), {"page": {"size": "B5"}, "layout": {"density": "standard"}})
        self.assertGreater(b5["target_characters"], 162255)
        project = m["common"].read_project(); project["book"]["language"] = "en"
        self.assertGreater(m["planning"].compute_scale(project, {})["characters_per_page"], 1400)

    def test_outline_chapter_max_is_a_hard_gate_from_scale(self):
        root, m = make_job("chapter-max", pages=30)
        scale = m["planning"].compute_scale(m["common"].read_project(), {})
        scale.update(minimum_chapters=1, maximum_chapters=2, target_characters=1)
        chapters = [{"id": f"ch-{i}", "title": f"C{i}", "file": f"source/manuscript/0{i}-c.md", "purpose": "purpose text",
                     "target_characters": 1000, "required_sections": [f"sec-{i}"], "required_topics": ["topic"]} for i in range(1, 4)]
        write(root, "source/metadata/outline.yaml", {"chapters": chapters})
        errors, _ = m["planning"].check_outline(scale)
        self.assertTrue(any("at most 2 chapters" in e for e in errors), errors)

    def test_editorial_plan_semantic_change_reopens_downstream_only(self):
        root, m = make_job("editorial-stale", pages=30)
        orch = m["orchestrator"]
        (root / "plan/editorial").mkdir(parents=True, exist_ok=True)
        write(root, "plan/editorial/ch-a.yaml", {"chapter": "ch-a", "chapter_end": ["summary"], "sections": [{"id": "sec-a", "devices": [{"id": "tbl-a", "type": "table"}]}]})
        project, state = orch.load_state()
        state["phases"]["editorial_planning"] = "complete"
        state["phases"]["architecture"] = "complete"
        for phase in orch.EDITORIAL_PLAN_DOWNSTREAM: state["phases"][phase] = "complete"
        state.setdefault("artifact_fingerprints", {})["editorial_plan"] = m["common"].editorial_plan_fingerprint()
        build_before = m["common"].fingerprint()
        # Formatting and unrelated report changes have no semantic effect.
        write(root, "plan/editorial/ch-a.yaml", "# comment\nchapter: ch-a\nchapter_end:\n  - summary\nsections:\n  - id: sec-a\n    devices:\n      - id: tbl-a\n        type: table\n")
        write(root, "reports/unrelated.json", {"changed": True})
        self.assertFalse(orch.refresh_editorial_plan_dependency(state))
        self.assertEqual(m["common"].fingerprint(), build_before, "YAML formatting and unrelated reports do not invalidate")
        # Device addition, slot replacement and chapter-end change independently invalidate consumers.
        variants = [
            {"chapter": "ch-a", "chapter_end": ["summary"], "sections": [{"id": "sec-a", "devices": [{"id": "tbl-a", "type": "table"}, {"id": "quote-a", "type": "pull_quote"}]}]},
            {"chapter": "ch-a", "chapter_end": ["summary"], "sections": [{"id": "sec-a", "devices": [{"id": "tbl-b", "type": "table"}]}]},
            {"chapter": "ch-a", "chapter_end": ["key_points", "summary"], "sections": [{"id": "sec-a", "devices": [{"id": "tbl-b", "type": "table"}]}]},
        ]
        for variant in variants:
            for phase in orch.EDITORIAL_PLAN_DOWNSTREAM: state["phases"][phase] = "complete"
            state["artifact_fingerprints"]["editorial_plan"] = m["common"].editorial_plan_fingerprint()
            write(root, "plan/editorial/ch-a.yaml", variant)
            self.assertNotEqual(m["common"].fingerprint(), build_before)
            self.assertTrue(orch.refresh_editorial_plan_dependency(state))
            self.assertEqual(state["phases"]["editorial_planning"], "complete")
            self.assertTrue(all(state["phases"][p] == "pending" for p in orch.EDITORIAL_PLAN_DOWNSTREAM))
            build_before = m["common"].fingerprint()

    def test_paragraph_policy_measures_japanese_reader_text_without_brittle_single_char_gate(self):
        root, m = make_job("paragraph-policy", pages=30)
        paragraphs = ["日" * 300 + "。"] * 19 + ["日" * 530 + "。"]
        write(root, "source/manuscript/01-a.md", "# A {#ch-a}\n\n## S {#sec-a}\n\n" + "\n\n".join(paragraphs) + "\n")
        record = m["manuscript"].analyze_all()["source/manuscript/01-a.md"]
        stats = m["planning"].paragraph_statistics(record, 450)
        self.assertEqual((stats["max_paragraph_chars"], stats["violation_count"], stats["paragraph_count"]), (531, 1, 20))
        self.assertEqual(stats["violation_ratio"], 0.05)
        self.assertTrue(stats["medium"])
        self.assertFalse(stats["high"], "a single 1.18x paragraph is a warning, not a hard failure")
        severe = m["planning"].paragraph_statistics(m["manuscript"].analyze_all()["source/manuscript/01-a.md"], 350)
        self.assertTrue(severe["high"])

    def test_rejected_visual_is_skipped_by_asset_generation(self):
        root, m = make_job("rejected-asset")
        import importlib
        diagrams = importlib.import_module("diagrams")
        visual_review = importlib.import_module("visual_review")
        assets = importlib.import_module("assets")
        source = "source/assets/diagrams/rejected.yaml"
        old_decisions, old_assets, old_specs = visual_review.decisions, assets.assets, diagrams.specs
        path = root / source; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("{}\n", encoding="utf-8")
        try:
            visual_review.decisions = lambda: {"fig-rejected": "rejected"}
            assets.assets = lambda: [{"id": "fig-rejected", "type": "diagram", "source": source}]
            diagrams.specs = lambda: [(path, {"type": "flow", "nodes": [], "edges": []})]
            result = diagrams.generate({})
            self.assertEqual(result, [])
            self.assertFalse((root / "source/assets/figures/rejected.svg").exists())
        finally:
            visual_review.decisions, assets.assets, diagrams.specs = old_decisions, old_assets, old_specs

    def test_profile_measurement_warnings_do_not_become_required_rewrites(self):
        _, modules = make_job("paragraph-warning")
        requires_rewrite = modules["orchestrator"].requires_rewrite
        self.assertFalse(requires_rewrite({"type": "paragraph-length", "severity": "medium"}))
        self.assertFalse(requires_rewrite({"type": "layout-pacing", "severity": "medium", "evidence": "book_nonprose_below_target"}))
        self.assertTrue(requires_rewrite({"type": "paragraph-length", "severity": "high"}))
        self.assertTrue(requires_rewrite({"type": "contradiction", "severity": "medium"}))

    def test_outline_budget_and_dependencies(self):
        root, m = make_job("outline", pages=30)
        scale = m["planning"].compute_scale(m["common"].read_project(), {})
        chapters = [{"id": f"ch-{i}", "title": f"C{i}", "file": f"source/manuscript/0{i}-c.md", "purpose": "purpose text",
                     "prerequisites": ([f"ch-{i-1}"] if i > 1 else []), "target_characters": 2000,
                     "required_sections": [{"id": f"sec-{i}", "title": "S"}], "required_topics": ["topic"]} for i in range(1, 4)]
        write(root, "source/metadata/outline.yaml", {"chapters": chapters})
        errors, _ = m["planning"].check_outline(scale)
        self.assertTrue(any("budgets total 6000" in e for e in errors), errors)  # 30 pages needs ~15000
        for chapter in chapters: chapter["target_characters"] = 5000
        chapters[0]["prerequisites"] = ["ch-3"]
        write(root, "source/metadata/outline.yaml", {"chapters": chapters})
        errors, _ = m["planning"].check_outline(scale)
        self.assertTrue(any("must come earlier" in e for e in errors), errors)
        chapters[0]["prerequisites"] = []
        write(root, "source/metadata/outline.yaml", {"chapters": chapters})
        errors, loaded = m["planning"].check_outline(scale)
        self.assertEqual(errors, [])
        graph = m["planning"].dependency_graph(loaded)
        self.assertEqual(graph["parallel_waves"], [["ch-1"], ["ch-2"], ["ch-3"]])

    def test_deficit_detection_and_expansion_scheduling(self):
        root, m = make_job("deficit", pages=12)
        chapters = [{"id": "ch-a", "title": "A", "file": "source/manuscript/01-a.md", "purpose": "purpose text", "target_characters": 3000,
                     "required_sections": [{"id": "sec-a", "title": "S"}], "required_topics": ["注意"], "required_references": []},
                    {"id": "ch-b", "title": "B", "file": "source/manuscript/02-b.md", "purpose": "purpose text", "target_characters": 3000,
                     "required_sections": [{"id": "sec-b", "title": "S"}], "required_topics": ["注意"]}]
        write(root, "source/metadata/outline.yaml", {"chapters": chapters})
        write(root, "source/manuscript/01-a.md", "# A {#ch-a}\n\n## S {#sec-a}\n\n" + "注意機構の説明。" * 40 + "\n")
        write(root, "source/manuscript/02-b.md", "# B {#ch-b}\n\n## S {#sec-b}\n\n" + "注意の本文。" * 400 + "\n")
        for ch in ("ch-a", "ch-b"): write(root, f"plan/summaries/{ch}.yaml", "summary: '" + "要約" * 40 + "'\nintroduced_concepts: []\nhandoff: 'next chapter assumes this'\n")
        orch = m["orchestrator"]
        project, state = orch.load_state()
        for phase in orch.PHASES[:orch.PHASES.index("chapter_review")]: state["phases"][phase] = "complete"
        orch.save_state(state)
        state, tasks, _ = orch.advance()
        self.assertEqual(state["phase"], "chapter_review")
        self.assertEqual([t["id"] for t in tasks], ["expand:ch-a"])
        contract = json.loads((root / "reports/chapter-status/ch-a.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["status"], "incomplete"); self.assertEqual(contract["deficit"], 3000 - contract["actual_characters"])
        events = [json.loads(x) for x in (root / "run-events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(any(e["event"] == "contract_failed" and e["chapter"] == "ch-a" for e in events))


class Chapters(unittest.TestCase):
    def test_contract_requires_more_than_a_file(self):
        root, m = make_job("contract", pages=4)
        outline = [{"id": "ch-a", "title": "A", "file": "source/manuscript/01-a.md", "purpose": "p", "target_characters": 1000,
                    "required_sections": [{"id": "sec-x", "title": "X"}], "required_topics": ["スケーリング則|scaling law"], "required_references": ["src-0001"]}]
        write(root, "source/metadata/outline.yaml", {"chapters": outline})
        write(root, "source/manuscript/01-a.md", "# A {#ch-a}\n\n" + "本文" * 600 + "\n")
        planning = m["planning"]; manuscript = m["manuscript"]
        chapters = planning.load_outline({"chapter_minimum_ratio": .75})
        result = planning.evaluate_contract(chapters[0], manuscript.analyze_all()["source/manuscript/01-a.md"], {})
        kinds = {r["type"] for r in result["reasons"]}
        self.assertEqual(kinds, {"topics", "sections", "references", "summary"})
        write(root, "source/manuscript/01-a.md", "# A {#ch-a}\n\n## X {#sec-x}\n\nscaling law [cite:src-0001]。" + "本文" * 600 + "\n")
        write(root, "plan/summaries/ch-a.yaml", "summary: '" + "要約" * 40 + "'\nintroduced_concepts: []\nhandoff: 'handoff text'\n")
        result = planning.evaluate_contract(chapters[0], manuscript.analyze_all()["source/manuscript/01-a.md"], {})
        self.assertEqual(result["status"], "complete", result["reasons"])

    def test_packet_shares_bible_glossary_and_prerequisite_summaries(self):
        root, m = make_job("packet", pages=4)
        outline = [{"id": "ch-a", "title": "A", "file": "source/manuscript/01-a.md", "purpose": "p", "target_characters": 1000, "introduces": ["c1"]},
                   {"id": "ch-b", "title": "B", "file": "source/manuscript/02-b.md", "purpose": "p", "target_characters": 1000, "prerequisites": ["ch-a"], "assumes": ["c1"]}]
        write(root, "source/metadata/outline.yaml", {"chapters": outline})
        write(root, "plan/summaries/ch-a.yaml", "summary: 'Chapter A explains concept one in depth for later chapters.'\nintroduced_concepts: [c1]\nhandoff: 'B may assume c1'\n")
        write(root, "plan/concept-map.yaml", "concepts:\n  - {id: c1, term: Concept One, definition: 'defined in A'}\n")
        chapters = m["planning"].load_outline({})
        packet = m["planning"].packet(chapters[1], chapters, {})
        self.assertEqual(packet["shared_state"]["book_bible"], "plan/book-bible.yaml")
        self.assertEqual(packet["shared_state"]["glossary"], "source/metadata/glossary.yaml")
        self.assertEqual(packet["prerequisite_summaries"][0]["chapter"], "ch-a")
        self.assertEqual(packet["concepts"][0]["role"], "assume")
        self.assertTrue((root / "plan/chapter-packets/ch-b.yaml").is_file())


class Completion(unittest.TestCase):
    def build_short_book(self, name, pages=300):
        root, m = make_job(name, pages=pages)
        write(root, "source/metadata/outline.yaml", {"chapters": [{"id": "ch-a", "title": "A", "file": "source/manuscript/01-a.md", "purpose": "p",
                                                                   "target_characters": 150000, "required_sections": ["sec-a"], "required_topics": ["x"]}]})
        write(root, "source/manuscript/01-a.md", "# A {#ch-a}\n\n## S {#sec-a}\n\n" + "x本文です。" * 3000 + "\n")  # ~15000 chars
        write(root, "plan/summaries/ch-a.yaml", "summary: '" + "要約" * 40 + "'\nintroduced_concepts: []\nhandoff: 'handoff text'\n")
        orch = m["orchestrator"]
        project, state = orch.load_state()
        for phase in orch.PHASES: state["phases"][phase] = "complete"
        state["status"] = "complete"
        orch.save_state(state)
        # A successful, fresh PDF build must not be mistaken for a complete publication.
        m["common"].report("build-report.json", {"ok": True, "fingerprint": m["common"].fingerprint(), "outputs": ["publish/book.pdf"]})
        (root / "publish").mkdir(exist_ok=True); (root / "publish/book.pdf").write_bytes(b"%PDF-1.7 fake")
        return root, m

    def test_pdf_success_with_short_manuscript_is_not_complete(self):
        root, m = self.build_short_book("false-completion")
        orch = m["orchestrator"]
        self.assertTrue(orch.build_fresh())
        project, state = orch.load_state()
        gates = {g["id"]: g for g in orch.completion_gates(orch.Context(project, state))}
        self.assertFalse(gates[8]["passed"]); self.assertIn("of minimum 129,804", gates[8]["detail"])
        self.assertTrue(gates[15]["passed"], "the build itself is fine")
        state, tasks, _ = orch.advance()
        self.assertNotEqual(state["status"], "complete")
        self.assertNotEqual(state["phases"]["complete"], "complete")
        summary = json.loads((root / "execution-summary.json").read_text(encoding="utf-8"))
        self.assertFalse(summary["complete"])

    def test_incomplete_supplied_coverage_fails(self):
        root, m = make_job("coverage", pages=2, urls=["https://example.invalid/a"])
        src = m["sources"]; index = src.init_supplied()
        index["sources"][0].update(ingest_status="fully_ingested", attempts=[{"method": "x"}]); src.save_index(index)
        write(root, "research/notes/src-0001.yaml", "source: src-0001\nrelevance: core\nsummary: '" + "a" * 80 + "'\nkey_claims: ['claim text here']\n")
        cov = m["research"].coverage({}, m["common"].read_project())
        self.assertEqual(cov["orphan_supplied_sources"], ["src-0001"])
        cov = m["research"].coverage({"src-0001": [{"chapter": "ch-a", "section": "sec-a"}]}, m["common"].read_project())
        self.assertEqual(cov["orphan_supplied_sources"], [])
        write(root, "research/notes/src-0001.yaml", "source: src-0001\nrelevance: background\nsummary: '" + "a" * 80 + "'\n")
        self.assertEqual(m["research"].coverage({}, m["common"].read_project())["sources"]["src-0001"]["status"], "background_only")

    def test_unresolved_high_severity_audit_issue_blocks(self):
        root, m = make_job("audit-block", pages=2)
        audit = m["audit"]
        found = [audit.issue("unsupported-claim", "high", "ch-a", "Claim lacks support", source="agent:ch-a")]
        ledger = audit.update_ledger(found, "agent", "fp")
        identifier = audit.open_issues(ledger)[0]["id"]
        with self.assertRaises(ValueError): audit.resolve(identifier, "not important enough", wontfix=True)
        self.assertEqual(len(audit.open_issues(audit.load_ledger(), ("high",))), 1)
        audit.resolve(identifier, "Added the missing citation and narrowed the claim")
        self.assertEqual(audit.open_issues(audit.load_ledger()), [])
        det = [audit.issue("repetition", "high", "ch-a", "dup paragraph")]
        ledger = audit.update_ledger(det, "audit", "fp")
        det_id = next(e["id"] for e in ledger["issues"].values() if e["type"] == "repetition")
        with self.assertRaises(ValueError): audit.resolve(det_id, "I fixed it, promise")
        ledger = audit.update_ledger([], "audit", "fp2")
        self.assertEqual(next(e for e in ledger["issues"].values() if e["id"] == det_id)["status"], "resolved")

    def test_package_refuses_without_gates(self):
        root, m = self.build_short_book("package-refuses", pages=300)
        sys.modules.pop("package", None); package = importlib.import_module("package")
        with self.assertRaises(RuntimeError): package.package()


class Persistence(unittest.TestCase):
    def test_state_roundtrip_resume_and_reopen(self):
        root, m = make_job("persist", pages=4, urls=["https://example.invalid/a"])
        orch, src = m["orchestrator"], m["sources"]
        project, state = orch.load_state()
        for phase in orch.PHASES[:6]: state["phases"][phase] = "complete"
        orch.save_state(state)
        project, again = orch.load_state()
        self.assertEqual(again["phases"]["reference_assignment"], "complete")
        self.assertEqual(again["scale"]["target_characters"], 2100)  # 4-page target, short profile page model
        orch.reopen(again, "architecture", "outline changed")
        self.assertEqual(again["phases"]["research_frozen"], "complete")
        self.assertTrue(all(again["phases"][p] == "pending" for p in orch.PHASES[4:]))
        index = src.init_supplied(); index["sources"][0]["ingest_status"] = "fetching"; src.save_index(index)
        index = src.reset_interrupted(src.load_index())
        self.assertEqual(index["sources"][0]["ingest_status"], "pending")


class EditorialPhase(unittest.TestCase):
    def test_phase_order_and_legacy_states(self):
        root, m = make_job("editorial-order", pages=4)
        orch = m["orchestrator"]; order = orch.PHASES.index
        self.assertTrue(order("reference_assignment") < order("editorial_planning") < order("drafting"))
        self.assertTrue(order("drafting") < order("asset_planning") < order("asset_generation") < order("integration") < order("layout"))
        project, state = orch.load_state()
        del state["phases"]["editorial_planning"]; state["phases"]["drafting"] = "complete"; orch.save_state(state)
        _, legacy = orch.load_state()
        self.assertEqual(legacy["phases"]["editorial_planning"], "complete", "a drafted book is not sent back to plan")
        self.assertIn("legacy", legacy["notes"]["editorial_planning"])

    def test_plans_are_required_before_drafting(self):
        root, m = make_job("editorial-plan", pages=4)
        orch = m["orchestrator"]
        write(root, "source/metadata/outline.yaml", "chapters:\n  - id: ch-one\n    title: One\n    file: source/manuscript/01-one.md\n    purpose: p\n"
              "    target_characters: 1800\n    required_sections: [{id: sec-one-a, title: A}]\n    required_topics: [a]\n")
        project, state = orch.load_state()
        ctx = orch.Context(project, state)
        result = orch.h_editorial_planning(ctx)
        self.assertEqual([t["id"] for t in result.tasks], ["editorial:ch-one"])
        self.assertTrue(any("plan_missing" in c for c in result.tasks[0]["failing_checks"]))
        self.assertTrue(any("pause" in line.lower() for line in result.tasks[0]["instructions"]))
        write(root, "plan/editorial/ch-one.yaml", {"chapter_id": "ch-one", "chapter_title": "One", "chapter_role": "introduction", "reader_before": "b",
              "reader_after": "a", "target_chars": 1800, "sections": [
                  {"id": "sec-one-a", "heading": "A", "purpose": "p", "rhetorical_role": "thesis", "intended_reader_effect": "e", "expected_density": "light",
                   "target_chars": 900, "summary_points": ["x"], "devices": [{"id": "wn-one", "type": "warning", "why": "common misreading",
                                                                               "placement": {"intent": "after x", "position": "section_end"}}]},
                  {"id": "sec-one-b", "heading": "B", "purpose": "p", "rhetorical_role": "example", "intended_reader_effect": "e", "expected_density": "heavy",
                   "target_chars": 900, "summary_points": ["y"]}],
              "chapter_end": [{"type": "key_points"}]})
        ctx.invalidate()
        book = orch.h_editorial_planning(ctx)
        self.assertEqual([t["id"] for t in book.tasks], ["editorial:book"], "a book with no visual material is asked, not filled")
        self.assertIn("visual_shortage", book.tasks[0]["failing_checks"])
        write(root, "plan/editorial/book.yaml", {"waivers": [{"rule": "visual_shortage", "reason": "a one-chapter note with nothing to compare or draw"}]})
        self.assertTrue(orch.h_editorial_planning(ctx).done)
        self.assertTrue((root / "reports/editorial-plan.yaml").is_file())


class Observability(unittest.TestCase):
    def test_stages_and_skill_invocations_are_recorded(self):
        root, m = make_job("events", pages=2, files=[("a.md", "# A\n\n" + "本文です。" * 300)])
        orch = m["orchestrator"]
        state, tasks, _ = orch.advance()
        self.assertEqual(state["phases"]["source_ingestion"], "complete")
        self.assertEqual(tasks[0]["id"], "research:supplementary")
        events = [json.loads(x) for x in (root / "run-events.jsonl").read_text(encoding="utf-8").splitlines()]
        pairs = {(e["stage"], e["event"]) for e in events}
        self.assertIn(("source_ingestion", "start"), pairs); self.assertIn(("source_ingestion", "complete"), pairs)
        self.assertTrue(any(e.get("tool") == "fetch-sources" for e in events))
        self.assertTrue(any(e.get("skill") == "skills/research/research.md" and e["event"] == "invoke" for e in events))
        orch.report_done("research:supplementary", "done")
        self.assertTrue(any(json.loads(x)["event"] == "agent_done" for x in (root / "run-events.jsonl").read_text(encoding="utf-8").splitlines()))
        summary = json.loads((root / "execution-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["sources"]["supplied"]["fully_ingested"], 1)
        self.assertIn("skills/research/research.md", summary["skills_invoked"])


class DesignTokens(unittest.TestCase):
    def test_tokens_css_fonts_themes_components_diagrams_math(self):
        root, m = make_job("design-tokens", pages=2)
        for module in ("design", "diagrams", "book_ir"): sys.modules.pop(module, None)
        design = importlib.import_module("design"); diagrams = importlib.import_module("diagrams"); book_ir = importlib.import_module("book_ir")
        themes = sorted(p.parent.name for p in (root / "themes").glob("*/theme.yaml"))
        self.assertGreaterEqual(len(themes), 5)
        for theme in themes: design.load_design(theme)
        write(root, "book.design.yaml", {"theme": "modern-technical", "typography": {"body": {"japanese": "Test Mincho X", "latin": "Test Serif X"}}})
        spec = design.load_design()
        tokens = design.normalize(spec, require_pdf=False)
        css = design.css_tokens(tokens)
        self.assertIn('--book-font-body: "Test Serif X", "Test Mincho X"', css)
        files, bundle = design.write_theme_css(tokens, root / "out")
        write(root, "custom.css", ".warning{border-width:9px}/*custom*/")
        files, bundle = design.write_theme_css(tokens, root / "out")
        self.assertTrue(bundle.read_text(encoding="utf-8").rstrip().endswith("/*custom*/"))
        self.assertEqual(files[-1].name, "custom.css")
        svg = diagrams.svg({"type": "cycle", "title": "t", "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]}, {**tokens, "typography": {**tokens["typography"], "heading": {**tokens["typography"]["heading"], "resolved_families": ["Inter"]}}})
        self.assertTrue(svg.startswith("<svg"))
        ir = book_ir.create_ir({"pandoc-api-version": [1, 23, 1], "meta": {}, "blocks": [{"t": "Div", "c": [["eq-a", ["equation"], [["data-number", "1.1"]]], [{"t": "Para", "c": [{"t": "Math", "c": [{"t": "DisplayMath"}, "x^2"]}]}]]}]})
        html_ast = book_ir.prepare_ast(ir, "html")
        self.assertIn("eq-number", json.dumps(html_ast))
        common = m["common"]
        html = common.run([common.tool("pandoc"), "-f", "json", "-t", "html5", common.math_option()], json.dumps(html_ast))
        self.assertIn("<math", html); self.assertIn("(1.1)", html)
        docx_ast = book_ir.prepare_ast(ir, "docx")
        self.assertIn("Equation", json.dumps(docx_ast))


if __name__ == "__main__":
    unittest.main(verbosity=2)

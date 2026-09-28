"""Mini-E2E: drive the real `bookorder goal` orchestration with a scripted mock agent.

The mock stands in for the model: it answers each task the orchestrator issues with fixture content
(notes, synthesis, outline, chapters, audits). Everything else — source registration, HTTP fetching and
extraction, persistence, research freeze, contracts, packets, citation registry, cross-references, audits,
Diagram IR rendering, Typst/Pandoc builds, validation, completion gates and packaging — is the production code.

Requirements: Python 3.10+, Pandoc and Typst (PANDOC / TYPST env vars or PATH). Network is only local.
Usage: python tests/mini_e2e.py [--keep]
"""
from functools import partial
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import zipfile

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tests"))
import _tools  # noqa: E402  PANDOC/TYPST from env, PATH or .tools/
if _tools.MISSING: raise SystemExit(f"Missing {', '.join(_tools.MISSING)}: set PANDOC/TYPST, add to PATH, or place them in .tools/")
FIXTURE = REPO / "tests/fixtures/mini-book"
AGENT = FIXTURE / "agent"
WORK = REPO / ".test-output/mini-e2e/publishing-job"
SUMMARIES = {
    "ch-foundations": ("固定長ベクトルの限界と、出力ごとに入力の参照先を重み付けして選び直す注意機構の考え方、文脈ベクトル、query・key・valueの一般化、注意重みの解釈上の注意を説明した。", ["attention", "context-vector"]),
    "ch-mechanism": ("自己注意とTransformer、スケール化内積注意の式と平方根で割る理由、マルチヘッド注意、位置エンコーディング、系列長の二乗に比例する計算量と効率化の方式を説明した。", ["self-attention", "multi-head"]),
    "ch-training": ("学習のウォームアップと安定化、2020年のスケーリング則と2022年の計算最適な配分による修正、その違いを生んだ実験条件と実務上の含意を説明した。", ["scaling-law"]),
    "ch-evaluation": ("パープレキシティと下流タスク評価の違い、データ汚染、多面的評価の必要性を説明し、仕組みと条件を併せて読む姿勢として本書をまとめた。", ["data-contamination"]),
}


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".md": "text/markdown", ".html": "text/html"}
    def log_message(self, *args): pass


def serve():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(FIXTURE / "web")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def setup(base):
    if WORK.exists(): shutil.rmtree(WORK)
    WORK.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO / "job-template", WORK, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "preview.png"))
    for name in ("attention-basics.md", "evaluation.txt"):
        (WORK / "input/sources").mkdir(parents=True, exist_ok=True)
        shutil.copy2(FIXTURE / "sources" / name, WORK / "input/sources" / name)
    shutil.copy2(REPO / "tests/fixtures/reference-1.pdf", WORK / "input/sources/reference-1.pdf")
    urls = [f"{base}/transformer-architecture.html", f"{base}/training-dynamics.html", f"{base}/scaling-debate.html",
            f"{base}/history.md", f"{base}/missing-article.html", f"{base}/transformer-architecture.html?utm_source=newsletter"]
    files = ["attention-basics.md", "evaluation.txt", "reference-1.pdf"]
    project = {"format": "portable-publishing-job", "format_version": "0.2",
               "book": {"title": "注意機構から大規模言語モデルへ", "description": "注意機構の原理から学習・評価までを一貫して解説する小冊子",
                        "target_readers": "機械学習の基礎を知るエンジニア", "target_pages": 8, "language": "ja", "author": "BookOrder Mini-E2E"},
               "user_instructions": "すべての供給資料を反映すること。", "research": {"allow_web_research": True, "prefer_primary_sources": True, "keep_provenance": True, "require_supplied_coverage": True},
               "citations": {"style": "numeric"},
               "figures": {"tables": True, "diagrams": True, "charts": True, "generative_images": False},
               "outputs": {"canonical_markdown": True, "docx": True, "semantic_html": True, "pdf": True, "static_site": True, "epub": True},
               "runtime": {"target": "none", "bundled": False},
               "design": {"spec": "book.design.yaml", "theme": "modern-technical", "custom_css": "custom.css"},
               "input": {"urls": urls, "sources": [{"original_name": n, "path": f"input/sources/{n}", "size_bytes": (WORK / "input/sources" / n).stat().st_size} for n in files]}}
    (WORK / "project.json").write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    (WORK / "book.design.yaml").write_text(json.dumps({"theme": "modern-technical", "art_direction": "落ち着いた技術書。アクセントは青緑。"}, ensure_ascii=False), encoding="utf-8")
    for folder in ("source/manuscript", "source/assets/figures", "source/metadata", "source/references", "reports"): (WORK / folder).mkdir(parents=True, exist_ok=True)
    for name, key in (("outline", "chapters"), ("glossary", "terms"), ("sources", "sources"), ("figures", "figures")):
        (WORK / f"source/metadata/{name}.yaml").write_text(f"{key}: []\n", encoding="utf-8")
    (WORK / "source/references/references.bib").write_text("% Add verified BibTeX records here.\n", encoding="utf-8")
    return urls


def cli(*args, expect=0):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, str(WORK / "scripts/cli.py"), *args], cwd=WORK, capture_output=True, text=True, encoding="utf-8", env=env)
    if expect is not None and result.returncode != expect:
        raise AssertionError(f"bookorder {' '.join(args)} -> {result.returncode}\n{result.stdout[-4000:]}\n{result.stderr[-4000:]}")
    return result


class MockAgent:
    def __init__(self, base):
        self.base = base; self.log = []

    def ids(self):
        index = json.loads((WORK / "research/index.json").read_text(encoding="utf-8"))
        mapping = {}
        for source in index["sources"]:
            location = source.get("url") or source.get("path")
            key = Path(location.split("?")[0]).stem
            if source.get("duplicate_of"): continue
            mapping[key] = source["id"]
        return mapping, {s["id"]: s for s in index["sources"]}

    def render(self, text, own=None):
        mapping, _ = self.ids()
        text = re.sub(r"\{\{src:([a-z0-9-]+)\}\}", lambda m: mapping[m.group(1)], text)
        return text.replace("{{id}}", own or "")

    def put(self, relative, text):
        path = WORK / relative; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def copy(self, fixture, relative, own=None):
        self.put(relative, self.render((AGENT / fixture).read_text(encoding="utf-8"), own))

    def handle(self, task):
        identifier = task["id"]; kind, _, target = identifier.partition(":")
        self.log.append(identifier)
        mapping, sources = self.ids()
        if kind == "ingest":
            source = sources[target]
            if "missing-article" in (source.get("url") or ""):
                cli("source", "unavailable", target, "--attempt", "Mock browser fetch: HTTP 404 Not Found", "--reason", "The article URL returns 404 and no archived copy exists")
            elif source["ingest_status"] == "needs_agent_extraction":
                text = (REPO / "tests/fixtures/reference-1.typ").read_text(encoding="utf-8") * 8
                scratch = WORK / ".build/mock-extract.md"; scratch.parent.mkdir(exist_ok=True); scratch.write_text(text, encoding="utf-8")
                cli("source", "submit", target, "--file", str(scratch), "--method", "mock-pdf-reader")
            else: raise AssertionError(f"Unexpected ingestion task for {source}")
        elif kind == "verify":
            cli("source", "confirm", target, "--note", "The supplied note is intentionally short; the file is the complete document")
        elif identifier == "research:supplementary":
            url = f"{self.base}/efficient-attention.html"
            cli("research", "log", "--query", "efficient attention sparse low-rank memory", "--gap", "gap-efficiency", "--tool", "mock-search", "--selected", url)
            cli("source", "add", "--url", url, "--query", "efficient attention sparse low-rank memory", "--gap", "gap-efficiency", "--reason", "Supplied sources lack efficient attention methods")
            cli("research", "log", "--query", "language model benchmark design primary source", "--gap", "gap-evaluation-depth", "--tool", "mock-search", "--note", "no usable primary source in this fixture")
            self.copy("plan/research-plan.yaml", "research/research-plan.yaml")
        elif kind == "analyze":
            by_id = {v: k for k, v in mapping.items()}
            for output in task["outputs"]:
                source_id = Path(output).stem
                self.copy(f"notes/{by_id[source_id]}.yaml", output, source_id)
        elif identifier == "synthesize":
            for name in ("book-context", "concept-map", "argument-map", "timeline", "source-clusters", "topic-synthesis"):
                self.copy(f"plan/{name}.yaml", f"plan/{name}.yaml")
            self.copy("plan/glossary.yaml", "source/metadata/glossary.yaml")
        elif identifier == "architecture":
            packet_check = []
            self.copy("plan/book-bible.yaml", "plan/book-bible.yaml")
            self.copy("plan/outline.yaml", "source/metadata/outline.yaml")
        elif kind == "editorial":
            packet = (WORK / f"plan/chapter-packets/{target}.yaml").read_text(encoding="utf-8")
            assert "editorial_plan" in packet, "packet names the editorial plan"
            self.copy(f"editorial/{target}.yaml", f"plan/editorial/{target}.yaml")
        elif kind == "draft":
            assert any("slot" in line for line in task["instructions"]), "drafting is told to reserve slots"
            packet = (WORK / f"plan/chapter-packets/{target}.yaml").read_text(encoding="utf-8")
            assert "plan/book-bible.yaml" in packet and "source/metadata/glossary.yaml" in packet, "packet lacks shared state"
            if target != "ch-foundations": assert "prerequisite_summaries" in packet and "summary:" in packet.split("prerequisite_summaries")[1], f"{target} packet lacks prerequisite summaries"
            draft = AGENT / f"chapters/{target}.draft.md"
            self.copy(f"chapters/{target}.draft.md" if draft.exists() else f"chapters/{target}.md", self.chapter_file(target))
            summary, concepts = SUMMARIES[target]
            self.put(f"plan/summaries/{target}.yaml", json.dumps({"summary": summary, "introduced_concepts": concepts, "key_terms": [], "handoff": "次章へ渡す前提を明記した。"}, ensure_ascii=False))
        elif kind in ("expand", "review"):
            self.copy(f"chapters/{target}.md", self.chapter_file(target))
        elif identifier == "integrate":
            self.copy("plan/integration-review.yaml", "plan/integration-review.yaml")
        elif identifier == "plan-assets":
            self.copy("plan/assets-plan.yaml", "plan/assets-plan.yaml")
        elif kind == "asset":
            self.copy("diagrams/attention-flow.yaml", "source/assets/diagrams/attention-flow.yaml")
        elif kind == "audit":
            fixture = AGENT / f"audit/{target}.yaml"
            if fixture.exists(): self.copy(f"audit/{target}.yaml", f"plan/audit/{target}.yaml")
            else: self.put(f"plan/audit/{target}.yaml", json.dumps({"chapter": target, "reviewed": True, "checks": ["facts vs notes", "citations", "terminology"], "issues": []}))
        elif identifier == "prose:audit":
            self.put("plan/prose-audit.yaml", json.dumps({"reviewed_chapters": ["ch-foundations", "ch-mechanism", "ch-training", "ch-evaluation"],
                "candidates": [], "lexical_comparison": [], "role_comparison": [], "protected_passages": []}, ensure_ascii=False))
        elif identifier == "prose:edit":
            self.put("plan/prose-editing.yaml", json.dumps({"reviewed_chapters": ["ch-foundations", "ch-mechanism", "ch-training", "ch-evaluation"],
                "edits": [], "preserved": [], "citation_reaudit": []}, ensure_ascii=False))
        elif kind == "rewrite":
            ledger = json.loads((WORK / "reports/audit-ledger.json").read_text(encoding="utf-8"))
            items = [e for e in ledger["issues"].values() if e["status"] == "open" and e["severity"] in ("high", "medium") and (e.get("chapter") or "book") == target]
            deterministic = [e for e in items if e["source"] == "deterministic"]
            if deterministic: raise AssertionError("Fixture should not trigger deterministic medium/high issues: " + json.dumps(deterministic, ensure_ascii=False, indent=2))
            if target == "ch-training": self.copy("chapters/ch-training.rewritten.md", self.chapter_file(target))
            for item in items: cli("audit", "resolve", item["id"], "--note", "Removed the unsupported generalization and stated the book's own position")
        elif kind == "reaudit":
            self.put(f"plan/audit/final-{target}.yaml", json.dumps({"chapter": target, "reviewed": True, "new_issues": []}))
        elif identifier == "design":
            spec = json.loads((WORK / "book.design.yaml").read_text(encoding="utf-8"))
            spec.setdefault("colors", {})["accent"] = "#0E7490"
            (WORK / "book.design.yaml").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
            self.copy("plan/design-decisions.yaml", "plan/design-decisions.yaml")
        elif identifier == "layout-review":
            pdf = WORK / "publish/book.pdf"
            info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True) if shutil.which("pdfinfo") else None
            pages = info.stdout.decode("utf-8", errors="replace") if info else "pdfinfo unavailable"
            self.put("reports/layout-review.md", "# Layout review (mini-E2E mock agent)\n\nAutomated fixture run: the mock agent cannot look at pages. "
                     "It recorded PDF metadata only; visual inspection is performed separately by a human/agent.\n\n```\n" + pages + "\n```\n")
        else:
            raise AssertionError(f"Unexpected task {identifier}:\n" + "\n".join(task["instructions"]) + "\nFailing: " + json.dumps(task.get("failing_checks"), ensure_ascii=False))

    def chapter_file(self, chapter):
        outline = (WORK / "source/metadata/outline.yaml").read_text(encoding="utf-8")
        return re.search(rf"id: {chapter}\n(?:.*\n)*?\s*file: (\S+)", outline).group(1)


def run_goal(agent, limit=120):
    seen = {}
    for step in range(limit):
        result = json.loads(cli("goal", "--json").stdout)
        if result["status"] == "complete": return result, step
        if result["status"] == "blocked": raise AssertionError("Blocked: " + json.dumps(result["blockers"], ensure_ascii=False))
        if not result["tasks"]: raise AssertionError("No tasks and not complete: " + json.dumps(result, ensure_ascii=False)[:3000])
        for item in result["tasks"]:
            seen[item["id"]] = seen.get(item["id"], 0) + 1
            if seen[item["id"]] > 4: raise AssertionError(f"Task {item['id']} repeats without progress:\n" + "\n".join(item["instructions"]) + "\n" + json.dumps(item["failing_checks"], ensure_ascii=False))
            if item["kind"] == "agent":
                agent.handle(item)
        for item in result["tasks"]:
            if item["kind"] == "agent": cli("done", item["id"], "--json")
    raise AssertionError("Step limit reached")


def assertions(agent, urls):
    summary = json.loads((WORK / "execution-summary.json").read_text(encoding="utf-8"))
    assert summary["complete"] and summary["publication_status"] == "complete", summary["publication_status"]
    assert all(p["state"] == "complete" for p in summary["phases"]), summary["phases"]
    index = json.loads((WORK / "research/index.json").read_text(encoding="utf-8"))
    supplied = [s for s in index["sources"] if s["origin"] == "supplied"]
    assert len(supplied) == 3 + len(urls), len(supplied)
    assert all(s["attempts"] for s in supplied), "every supplied source attempted"
    status = {Path((s.get("url") or s["path"]).split("?")[0]).name + ("?dup" if s.get("duplicate_of") else ""): s["ingest_status"] for s in supplied}
    assert status["missing-article.html"] == "unavailable", status
    assert status["transformer-architecture.html?dup"] == "duplicate", status
    assert status["transformer-architecture.html"] == "fully_ingested", status
    assert status["evaluation.txt"] == "fully_ingested", status  # partial -> confirmed complete by agent
    for s in supplied:
        if s["ingest_status"] in ("fully_ingested", "partially_ingested"):
            text = (WORK / s["content_path"]).read_text(encoding="utf-8")
            assert s["chars"] > 200 and s["sha256"], s["id"]
            assert "should not appear" not in text and "ナビゲーションメニュー" not in text, "boilerplate stripped"
    transformer = next(s for s in supplied if s.get("url", "") and s["url"].endswith("transformer-architecture.html"))
    assert transformer["author"] == "山田 花子" and transformer["published"] == "2023-04-12", transformer
    discovered = [s for s in index["sources"] if s["origin"] == "discovered"]
    assert len(discovered) == 1 and discovered[0]["ingest_status"] == "fully_ingested"
    log = [json.loads(x) for x in (WORK / "research/search-log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["id"] for e in log] == ["q-0001", "q-0002"]
    lock = json.loads((WORK / "research/research-lock.json").read_text(encoding="utf-8"))
    assert set(lock["sources"]) == {s["id"] for s in index["sources"]}
    for name in ("book-context", "concept-map", "argument-map", "timeline", "source-clusters", "topic-synthesis", "book-bible", "chapter-dependencies"):
        assert (WORK / f"plan/{name}.yaml").is_file(), name
    status = json.loads((WORK / "reports/chapter-status.json").read_text(encoding="utf-8"))
    assert status["complete"] == 4 and status["total_actual"] >= status["book_minimum"], status
    for chapter in ("ch-foundations", "ch-mechanism", "ch-training", "ch-evaluation"):
        contract = json.loads((WORK / f"reports/chapter-status/{chapter}.json").read_text(encoding="utf-8"))
        assert contract["status"] == "complete" and contract["actual_characters"] >= contract["minimum_characters"]
        assert (WORK / f"plan/chapter-packets/{chapter}.yaml").is_file()
    events = [json.loads(x) for x in (WORK / "run-events.jsonl").read_text(encoding="utf-8").splitlines()]
    done = [e["task"] for e in events if e["event"] == "agent_done"]
    deficits = [e for e in events if e["event"] == "contract_failed" and e["chapter"] == "ch-mechanism"]
    assert deficits and "length" in deficits[0]["reasons"], "length deficit detected"
    assert any(t in done for t in ("expand:ch-mechanism", "review:ch-mechanism")), "length deficit triggered expansion"
    assert "rewrite:ch-training" in done and "reaudit:ch-training" in done, "targeted rewrite and re-audit ran"
    assert not any(t.startswith("rewrite:ch-foundations") for t in done), "rewrite stayed targeted"
    stages = {e["stage"] for e in events if e["event"] == "complete"}
    for phase in ("source_ingestion", "supplementary_research", "corpus_analysis", "research_frozen", "architecture", "reference_assignment",
                  "editorial_planning", "drafting", "chapter_review", "asset_planning", "asset_generation", "integration", "audit", "rewrite", "prose_audit", "prose_editing", "final_audit",
                  "design", "layout", "build", "validation", "package", "complete"):
        assert phase in stages, f"phase {phase} never completed"
    skills = {e.get("skill") for e in events if e["event"] == "invoke"}
    for skill in ("skills/research/source-ingestion.md", "skills/research/research.md", "skills/authoring/book-authoring.md", "skills/editorial/editing.md", "skills/editorial/prose-audit.md", "skills/editorial/whole-book-review.md", "skills/editorial/developmental-editing.md", "skills/editorial/cadence-editing.md", "skills/design/figures.md", "skills/quality/audit.md", "skills/design/editorial-design.md"):
        assert skill in skills, f"{skill} never invoked"
    ledger = json.loads((WORK / "reports/audit-ledger.json").read_text(encoding="utf-8"))
    agent_issues = [e for e in ledger["issues"].values() if e["source"].startswith("agent")]
    assert agent_issues and all(e["status"] == "resolved" for e in agent_issues)
    assert (WORK / "reports/audit-report.yaml").is_file()
    coverage = json.loads((WORK / "reports/source-coverage.json").read_text(encoding="utf-8"))
    assert not coverage["orphan_supplied_sources"], coverage["orphan_supplied_sources"]
    used = [k for k, v in coverage["sources"].items() if v["status"] == "used"]
    assert len(used) >= 6, used
    # Citations: stable IDs in source text, numbers only in rendered output.
    manuscript = "".join(p.read_text(encoding="utf-8") for p in sorted((WORK / "source/manuscript").glob("*.md")))
    assert "[cite:src-" in manuscript and not re.search(r"\[\d+\]", manuscript)
    references = json.loads((WORK / "source/references/references.json").read_text(encoding="utf-8"))
    assert all(r["id"].startswith("src-") for r in references)
    site = (WORK / "publish/site/chapters/02-mechanism.html").read_text(encoding="utf-8")
    assert re.search(r'href="[^"]*#ref-src-\d{4}"[^>]*>\d+</a>|\[<a[^>]*>\d+</a>\]', site) or re.search(r"\[\d+(?:, \d+)*\]", site), "numeric citations rendered"
    assert "<math" in site and "eq-number" in site and "(2.1)" in site, "MathML equation with number"
    assert "図2.1" in site and "表2.1" in site and "第1章" in site, "cross references resolved"
    ir = json.loads((WORK / "interchange/book-ir.json").read_text(encoding="utf-8"))
    assert ir["crossrefs"]["eq-attention"]["number"] == "2.1" and ir["crossrefs"]["fig-attention-flow"]["label"] == "図2.1"
    with zipfile.ZipFile(WORK / "interchange/book.docx") as docx:
        assert "m:oMath" in docx.read("word/document.xml").decode("utf-8"), "DOCX native equation"
    if shutil.which("pdftotext"):
        text = subprocess.run(["pdftotext", str(WORK / "publish/book.pdf"), "-"], capture_output=True, text=True).stdout
        assert "(2.1)" in text and re.search(r"図\s?2\.1", text) and "[1]" in text, "PDF numbering/citations"
    assert (WORK / "source/assets/figures/attention-flow.svg").is_file()
    layout = json.loads((WORK / "reports/layout-metrics.json").read_text(encoding="utf-8"))
    assert layout["schema"] == "bookorder/layout-metrics@1" and len(layout["chapters"]) == 4, "layout metrics per chapter"
    assert [c["id"] for c in layout["chapters"]] == list(SUMMARIES), "chapters identified by outline id"
    assert layout["totals"]["elements"]["figure"] == 1 and layout["totals"]["elements"]["table"] == 1 and layout["totals"]["elements"]["equation"] == 1
    assert layout["totals"]["callouts"] >= 3 and len(layout["pages"]) == layout["totals"]["pages"]
    assert json.loads((WORK / "reports/build-report.json").read_text(encoding="utf-8"))["layout"]["ok"]
    figures = json.loads((WORK / "reports/figure-check.json").read_text(encoding="utf-8"))
    flow = next(f for f in figures["figures"] if f["id"] == "fig-attention-flow")
    assert flow["status"] == "ok" and flow["planned_width_mm"] == 96 and abs(flow["scale"] - 1) < 0.01, flow
    assert flow["min_text_pt"] >= figures["tokens"]["min_label_pt"], "diagram text prints at token size"
    placed = [e for p in layout["pages"] for e in p["elements"] if e.get("label") == "fig-attention-flow"]
    walls = json.loads((WORK / "reports/pacing-report.json").read_text(encoding="utf-8"))
    assert walls["verdict"] == "pass" and walls["limits"]["tier"] == "short", walls["limits"]
    assert placed and placed[0]["geometry"]["width_mm"] == 96 and placed[0]["geometry"]["legibility"] == "ok", placed
    assert (WORK / "publish/result.zip").is_file()
    gates = json.loads((WORK / "reports/completion-gates.json").read_text(encoding="utf-8"))
    assert gates["passed"] and len(gates["gates"]) == 21 and all(g["passed"] for g in gates["gates"] if g["id"] in (17, 18, 19, 20, 21))
    plan = (WORK / "reports/editorial-plan.yaml").read_text(encoding="utf-8")
    assert 'schema: "bookorder/editorial-plan@1"' in plan and "ok: true" in plan, "editorial plan report"
    assert "editorial:ch-mechanism" in done and done.index("editorial:ch-mechanism") < done.index("draft:ch-mechanism"), "planned before drafting"
    manuscript_final = (WORK / "source/manuscript/02-mechanism.md").read_text(encoding="utf-8")
    assert ".slot" not in manuscript_final and "{#tbl-attention-variants}" in manuscript_final, "the table slot was filled"
    return summary


def real_pdf_pacing_loop():
    """Run gate 17 fail -> deterministic editorial pause -> fresh Typst proof -> pass."""
    target = WORK.parent / "pacing-e2e-job"
    if target.exists(): shutil.rmtree(target)
    shutil.copytree(WORK, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    chapter = target / "source/manuscript/01-foundations.md"
    original = chapter.read_text(encoding="utf-8")
    paras = ["この長い説明段落は、概念の前提、観察できる条件、反例との違いを順に示し、読者が一つの論点を追い続けるための統合試験用本文です。" * 5 for _ in range(14)]
    wall = "\n\n".join(paras)
    # Put the intentionally long uninterrupted run before the existing chapter summary.
    marker = "::: {.summary #ch-foundations-key-points}"
    assert marker in original
    chapter.write_text(original.replace(marker, wall + "\n\n" + marker), encoding="utf-8")

    script = ("import json, orchestrator; p,s=orchestrator.load_state(); c=orchestrator.Context(p,s); "
              "r=orchestrator.h_layout(c); g=orchestrator.completion_gates(c,include_package=False); "
              "print(json.dumps({'tasks':[t['id'] for t in r.tasks], 'gate17':next(x for x in g if x['id']==17)['passed']}))")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": str(target / "scripts") + os.pathsep + os.environ.get("PYTHONPATH", "")}
    def run_layout():
        result = subprocess.run([sys.executable, "-c", script], cwd=target, capture_output=True, text=True, encoding="utf-8", env=env)
        if result.returncode: raise AssertionError("pacing E2E orchestration failed:\n" + result.stdout[-3000:] + result.stderr[-3000:])
        return json.loads(next(line for line in reversed(result.stdout.splitlines()) if line.startswith("{")))

    prior = json.loads((target / "reports/layout-metrics.json").read_text(encoding="utf-8"))["generated_at"]
    failed = run_layout()
    assert not failed["gate17"] and "pacing:ch-foundations" in failed["tasks"], failed
    first_metrics = json.loads((target / "reports/layout-metrics.json").read_text(encoding="utf-8"))
    first_pacing = json.loads((target / "reports/pacing-report.json").read_text(encoding="utf-8"))
    assert first_metrics["generated_at"] != prior and first_pacing["verdict"] == "fail"

    # Deterministic agent-fix simulation: preserve the paragraphs, add a short editorial summary pause every two.
    pauses = []
    for i in range(0, len(paras), 2):
        pauses.extend(paras[i:i + 2])
        pauses.append(f"\n\n::: {{.summary #pacing-pause-{i // 2 + 1}}}\n\n" +
                      "この節では、前提と観察条件を合わせて読み、論点の違いを確認しました。" * 2 + "\n:::")
    chapter.write_text(original.replace(marker, "\n\n".join(pauses) + "\n\n" + marker), encoding="utf-8")
    passed = run_layout()
    assert passed["gate17"] and not any(t.startswith("pacing:") for t in passed["tasks"]), passed
    second_metrics = json.loads((target / "reports/layout-metrics.json").read_text(encoding="utf-8"))
    second_pacing = json.loads((target / "reports/pacing-report.json").read_text(encoding="utf-8"))
    build = json.loads((target / "reports/build-report.json").read_text(encoding="utf-8"))
    assert second_metrics["generated_at"] != first_metrics["generated_at"]
    assert build["layout"]["generated_at"] == second_metrics["generated_at"] == second_pacing["metrics_generated_at"]
    assert second_pacing["verdict"] == "pass"
    shutil.rmtree(target)
    return {"first": {"gate17": failed["gate17"], "task": "pacing:ch-foundations", "metrics_at": first_metrics["generated_at"]},
            "fixed": {"gate17": passed["gate17"], "metrics_at": second_metrics["generated_at"], "verdict": second_pacing["verdict"]}}


def main():
    server, base = serve()
    try:
        urls = setup(base)
        agent = MockAgent(base)
        result, steps = run_goal(agent)
        summary = assertions(agent, urls)
        pacing_result = real_pdf_pacing_loop()
        print(f"PASS mini-E2E in {steps} goal iterations; tasks handled: {len(agent.log)}")
        print(json.dumps({k: summary[k] for k in ("publication_status", "sources", "chapters", "rewrite_passes", "renderer_outputs")}, ensure_ascii=False, indent=2))
        print("PASS real-PDF pacing E2E:", json.dumps(pacing_result, ensure_ascii=False))
        print("Workspace:", WORK)
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()

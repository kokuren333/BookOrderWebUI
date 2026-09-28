"""Layout pacing gate (P0-2): text walls measured on typeset pages decide completion gate 17.

Books are described page by page, turned into probe data, measured by layout_metrics.compute (the same code the
build runs) and judged by pacing.evaluate, so the pause rules are tested end to end. Pure Python.
Usage: python tests/test_pacing.py
"""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "job-template/scripts"))
import layout_metrics as lm  # noqa: E402
import pacing  # noqa: E402

TOKENS = {"page": {"size": "A5", "margin": {"top": "18mm", "bottom": "20mm", "inner": "20mm", "outer": "17mm"}},
          "typography": {"body": {"size": "9.5pt", "line_height": 1.7}}}
TOP = 51.02
SHORT = {"tier": "short", "max_text_only_pages": 3, "source": "test"}
LONG = {"tier": "long", "max_text_only_pages": 4, "source": "test"}


def at(page, y, **value): return {"page": page, "y": y, "folio": page, **value}


def probe(*chapters):
    """chapters: (id, pages) where pages is a list of page contents, first page = opener.
    A page is "" (prose only) or one of figure / table / callout / tiny-callout / summary / pull-quote /
    heading / list / code / equation, placed mid-page between two paragraphs."""
    data = {"version": 1, "pars": [], "headings": [], "figures": [], "tables": [], "equations": [], "quotes": [], "code": [],
            "lists": [], "outlines": [], "marks": [], "ends": []}
    page = 1
    data["pars"].append(at(1, 200, chars=20))  # title page (front matter)
    for cid, pages in chapters:
        for index, content in enumerate(pages):
            page += 1
            if index == 0:
                data["marks"].append(at(page, 0, el="chapter", id=cid, number=cid[-1], label=cid))
                data["headings"].append(at(page, 90, level=1, outlined=True, text=cid, label=cid))
            data["pars"].append(at(page, 120 if index == 0 else TOP, chars=450))
            if content == "figure":
                data["figures"].append(at(page, 320, kind="image", label=f"fig-{page}")); data["ends"].append(at(page, 470, el="figure"))
            elif content == "table":
                data["figures"].append(at(page, 320, kind="table")); data["tables"].append(at(page, 330))
                data["ends"] += [at(page, 460, el="table"), at(page, 470, el="figure")]
            elif content in ("callout", "summary", "pull-quote", "tiny-callout"):
                sub = {"callout": "warning", "tiny-callout": "note"}.get(content, content)
                data["marks"] += [at(page, 320, el="begin", sub=sub), at(page, 330 if content == "tiny-callout" else 420, el="end", sub=sub)]
            elif content == "heading":
                data["headings"].append(at(page, 320, level=2, outlined=True, text=f"節{page}", label=f"sec-{page}"))
            elif content in ("list", "code", "equation"):
                key = {"list": "lists", "code": "code", "equation": "equations"}[content]
                data[key].append(at(page, 320)); data["ends"].append(at(page, 440, el=content))
            data["pars"].append(at(page, 480, chars=100))
    data["marks"].append(at(page, 530, el="doc-end"))
    return data


def judge(limits, *chapters):
    metrics = lm.compute(probe(*chapters), TOKENS)
    return metrics, pacing.evaluate(metrics, limits)


def rules(result, severity="high"):
    return sorted(f["rule"] for f in result["findings"] if f["severity"] == severity)


def text(n): return [""] * n


class Limits(unittest.TestCase):
    def test_tiers_from_page_target_and_overrides(self):
        tier = lambda pages, **extra: pacing.limits({"book": {"target_pages": pages}, **extra})
        self.assertEqual((tier(50)["tier"], tier(50)["max_text_only_pages"]), ("short", 3))
        self.assertEqual((tier(150)["tier"], tier(150)["max_text_only_pages"]), ("standard", 4))
        self.assertEqual((tier(300)["tier"], tier(300)["max_text_only_pages"]), ("long", 4))
        self.assertEqual((tier(600)["tier"], tier(600)["max_text_only_pages"]), ("monograph", 6))
        self.assertEqual(tier(300, profile="monograph")["max_text_only_pages"], 6)
        self.assertEqual(tier(300, pacing={"max_text_only_pages": 5})["max_text_only_pages"], 5)


class Runs(unittest.TestCase):
    def test_three_pages_is_the_short_boundary(self):
        metrics, result = judge(SHORT, ("ch1", ["", *text(3)]))
        self.assertEqual(metrics["totals"]["max_text_only_run"], 3)
        self.assertEqual(result["verdict"], "pass"); self.assertIn("run_near_limit", rules(result, "medium"))

    def test_four_pages_fail_short(self):
        _, result = judge(SHORT, ("ch1", ["", *text(4)]))
        self.assertEqual(result["verdict"], "fail"); self.assertEqual(rules(result), ["run_over_limit"])

    def test_four_pages_is_the_long_boundary(self):
        _, result = judge(LONG, ("ch1", ["", *text(4)]))
        self.assertEqual(result["verdict"], "pass"); self.assertIn("run_near_limit", rules(result, "medium"))

    def test_five_pages_fail_long(self):
        _, result = judge(LONG, ("ch1", ["", *text(5)]))
        self.assertEqual(result["verdict"], "fail")
        finding = next(f for f in result["findings"] if f["rule"] == "run_over_limit")
        self.assertEqual((finding["run"]["start"], finding["run"]["end"], finding["run"]["length"]), (3, 7, 5))
        self.assertEqual(finding["chapter"], "ch1")


class Pauses(unittest.TestCase):
    def wall_with(self, content, limits=LONG):
        # 3 text pages, the tested page, 3 text pages: 7 pages if the page does not pause, 3 + 3 if it does.
        return judge(limits, ("ch1", ["", *text(3), content, *text(3)]))

    def test_figure_table_callout_summary_pull_quote_break_the_run(self):
        for content in ("figure", "table", "callout", "summary", "pull-quote"):
            metrics, result = self.wall_with(content)
            self.assertEqual(metrics["totals"]["max_text_only_run"], 3, content)
            self.assertEqual(result["verdict"], "pass", content)

    def test_heading_list_code_equation_and_tiny_box_do_not(self):
        for content in ("heading", "list", "code", "equation", "tiny-callout"):
            metrics, result = self.wall_with(content)
            self.assertEqual(metrics["totals"]["max_text_only_run"], 7, content)
            self.assertEqual(result["verdict"], "fail", content)

    def test_chapter_opener_breaks_and_runs_do_not_merge_across_chapters(self):
        metrics, result = judge(LONG, ("ch1", ["", *text(4)]), ("ch2", ["", *text(4)]))
        runs = [(r["start"], r["end"], r["chapter"]) for r in metrics["text_only_runs"]]
        self.assertEqual(sorted(runs), [(3, 6, "ch1"), (8, 11, "ch2")])
        self.assertEqual(result["verdict"], "pass", "each chapter is at the limit, not over it")
        self.assertIn("walls_in_several_chapters", rules(result, "medium"))

    def test_repeated_walls_in_one_chapter_are_high(self):
        _, result = judge(LONG, ("ch1", ["", *text(4), "figure", *text(4)]))
        self.assertEqual(rules(result), ["repeated_walls_in_chapter"])

    def test_crossing_a_chapter_boundary_is_high(self):
        metrics = lm.compute(probe(("ch1", ["", *text(4)]), ("ch2", ["", *text(1)])), TOKENS)
        metrics["text_only_runs"].append({"start": 5, "end": 8, "length": 4, "chapter": "ch1"})
        for page in metrics["pages"]:
            if page["page"] == 7: page["chapter"] = "ch2"
        self.assertIn("run_crosses_chapters", rules(pacing.evaluate(metrics, LONG)))

    def test_nonprose_target_is_warning_not_quota(self):
        metrics = lm.compute(probe(("ch1", ["", "", ""])), TOKENS)
        limits = {**LONG, "nonprose_share_target": 0.30}
        result = pacing.evaluate(metrics, limits)
        self.assertEqual(result["verdict"], "pass")
        finding = next(f for f in result["findings"] if f["rule"] == "book_nonprose_below_target")
        self.assertEqual(finding["severity"], "medium")
        self.assertFalse(finding["corroborated_by_text_wall"])
        self.assertIn("target alone does not call for adding devices", finding["detail"])


class Actions(unittest.TestCase):
    def test_candidates_name_chapter_pages_and_break_points(self):
        _, result = judge(LONG, ("ch1", ["", "heading", *text(14)]))
        finding = next(f for f in result["findings"] if f["rule"] == "run_over_limit")
        self.assertEqual(finding["run"]["length"], 15)
        ops = [a["op"] for a in finding["actions"]]
        self.assertEqual(ops[0], "split_section", "the long section is named first")
        self.assertEqual(finding["actions"][0]["section"], "sec-3")
        self.assertTrue({"convert_comparison_to_table", "add_visual", "insert_summary", "add_case_study", "add_counterpoint", "add_pull_quote"} <= set(ops))
        self.assertEqual(finding["actions"][0]["at_pages"], [7, 12, 17])  # three pauses leave stretches of <= 4
        issues = pacing.ledger_issues(result)
        self.assertTrue(all(i["type"] == "layout-pacing" for i in issues))
        self.assertTrue(any(i.get("actions") for i in issues if i["severity"] == "high"))
        self.assertTrue(any("split_section" in line for line in pacing.task_lines(result, "ch1")))

    def test_dense_pages_suggest_shorter_paragraphs(self):
        data = probe(("ch1", ["", *text(5)]), ("ch2", ["", "figure", "", "figure"]))
        for par in data["pars"]:
            if 3 <= par["page"] <= 7: par["chars"] = 1400
        result = pacing.evaluate(lm.compute(data, TOKENS), LONG)
        ops = [a["op"] for f in result["findings"] if f["rule"] == "run_over_limit" for a in f["actions"]]
        self.assertIn("shorten_paragraphs", ops)


class MissingMetrics(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp()); self.saved = (pacing.BUILD_REPORT, pacing.METRICS, pacing.REPORT)
        pacing.BUILD_REPORT, pacing.METRICS, pacing.REPORT = (self.folder / "build-report.json", self.folder / "layout-metrics.json", self.folder / "pacing-report.json")
        self.project = {"book": {"target_pages": 300}}

    def tearDown(self):
        pacing.BUILD_REPORT, pacing.METRICS, pacing.REPORT = self.saved; shutil.rmtree(self.folder)

    def write(self, build=None, metrics=None):
        if build is not None: pacing.BUILD_REPORT.write_text(json.dumps(build), encoding="utf-8")
        if metrics is not None: pacing.METRICS.write_text(json.dumps(metrics), encoding="utf-8")

    def test_missing_failed_or_stale_metrics_block(self):
        self.assertEqual(pacing.check(self.project)["verdict"], "fail")  # no build at all
        self.write(build={"ok": True, "layout": {"ok": False, "error": "typst eval failed"}})
        result = pacing.check(self.project)
        self.assertEqual(result["verdict"], "fail"); self.assertEqual(rules(result), ["layout_unmeasured"])
        self.assertIn("typst eval failed", result["findings"][0]["detail"])
        metrics = lm.compute(probe(("ch1", ["", *text(2)])), TOKENS)
        self.write(build={"ok": True, "layout": {"ok": True, "generated_at": "earlier"}}, metrics=metrics)
        self.assertIn("does not belong", pacing.check(self.project)["findings"][0]["detail"])
        self.write(build={"ok": True, "layout": {"ok": True, "generated_at": metrics["generated_at"]}})
        self.assertEqual(pacing.check(self.project)["verdict"], "pass")
        self.assertTrue(pacing.REPORT.is_file())

    def test_unmeasured_can_be_waived_explicitly(self):
        self.write(build={"ok": True, "layout": {"ok": False, "error": "x"}})
        result = pacing.check({**self.project, "pacing": {"allow_unmeasured": True}})
        self.assertEqual(result["verdict"], "pass"); self.assertEqual(rules(result, "medium"), ["layout_unmeasured"])


class Ledger(unittest.TestCase):
    def test_audit_runs_do_not_resolve_layout_findings(self):
        import audit
        folder = Path(tempfile.mkdtemp()); saved = (audit.LEDGER, audit.REPORT)
        audit.LEDGER, audit.REPORT = folder / "ledger.json", folder / "report.yaml"
        try:
            _, result = judge(LONG, ("ch1", ["", *text(5)]))
            audit.update_ledger(pacing.ledger_issues(result), "layout", "f1")
            audit.update_ledger([], "audit", "f1")
            self.assertTrue(any(e["type"] == "layout-pacing" and e["severity"] == "high" for e in audit.open_issues()))
            audit.update_ledger([], "layout", "f2")
            self.assertFalse([e for e in audit.open_issues() if e["type"] == "layout-pacing"])
        finally:
            audit.LEDGER, audit.REPORT = saved; shutil.rmtree(folder)


class Orchestrator(unittest.TestCase):
    def test_layout_phase_turns_walls_into_chapter_tasks(self):
        import audit, orchestrator
        # Other test modules re-import the job runtime for temporary jobs. Patch the
        # module that orchestrator imports now, not a stale collection-time reference.
        import importlib
        active_pacing = importlib.import_module("pacing")
        folder = Path(tempfile.mkdtemp()); saved = (audit.LEDGER, audit.REPORT, active_pacing.check, orchestrator.log_event)
        audit.LEDGER, audit.REPORT = folder / "ledger.json", folder / "report.yaml"
        _, result = judge(LONG, ("ch1", ["", *text(6)]), ("ch2", ["", *text(3)]))
        active_pacing.check = lambda project=None: result
        orchestrator.log_event = lambda *args, **fields: None  # keep run-events.jsonl out of the template

        class Ctx:
            project = {"book": {"target_pages": 300}}
            def outline(self): return [{"id": "ch1", "file": "source/manuscript/01-a.md"}, {"id": "ch2", "file": "source/manuscript/02-b.md"}]
            def manuscript_fingerprint(self): return "f"
        try:
            outcome = orchestrator.layout_pacing(Ctx())
        finally:
            audit.LEDGER, audit.REPORT, active_pacing.check, orchestrator.log_event = saved
        shutil.rmtree(folder)
        self.assertEqual([t["id"] for t in outcome.tasks], ["pacing:ch1"])
        task = outcome.tasks[0]
        self.assertEqual(task["outputs"], ["source/manuscript/01-a.md"])
        body = "\n".join(task["instructions"])
        self.assertIn("pp. 3–8", body); self.assertIn("candidate", body)


BUILD_EXISTED = (REPO / "job-template/.build").exists()


def tearDownModule():
    # Profile resolution caches parsed YAML under job-template/.build; never leave it in the shipped template.
    if not BUILD_EXISTED: shutil.rmtree(REPO / "job-template/.build", ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

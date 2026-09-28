"""Visual rejection rules (P0-6): candidates are accepted, rejected or pending for stated reasons.

Pure Python: Diagram IR is supplied in memory. The last class re-judges the four concept figures of the long
sample book, reconstructed from its PDF (nodes, edge labels and captions as printed).
Usage: python tests/test_visual_review.py
"""
from pathlib import Path
import sys
import unittest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "job-template/scripts"))
import visual_review as vr  # noqa: E402

PROFILE = {"id": "long.criticism", "genre": "criticism", "devices": {"visuals_per_10k": {"min": 1.44, "target": 2.0, "max": 4.0}},
           "art_direction": {"generative_images": {"allowed": ["chapter_opener", "part_opener"], "max_total": 18}}}
CHAPTERS = [{"id": f"ch{i}", "target_characters": 15000} for i in range(1, 9)]
IR = {}  # source path -> Diagram IR


def load(asset):
    return IR.get(asset.get("source"))


vr._load_diagram = load


def diagram(ident, chapter, kind, nodes, edges=(), claim=("reveal_structure",), shape=None, caption="図", basis="source", sources=("src-1",), **extra):
    source = f"source/assets/diagrams/{ident}.yaml"
    IR[source] = {"type": kind, "title": caption, "nodes": [{"id": f"n{i}", "label": label} for i, label in enumerate(nodes)],
                  "edges": [{"from": f"n{a}", "to": f"n{b}", **({"label": l} if l else {})} for a, b, l in edges]}
    return {"id": ident, "chapter": chapter, "type": "diagram", "source": source, "caption": caption,
            "information_shape": shape or {"kind": "relation"}, "improvement_claim": {"kinds": list(claim), "statement": "本文だけでは追いにくい関係の構造を一目で示す。"},
            "factual_basis": basis, "source_ids": list(sources), **extra}


def other(ident, chapter, kind, shape, claim, basis="source", sources=("src-1",), **extra):
    return {"id": ident, "chapter": chapter, "type": kind, "caption": "表", "information_shape": shape,
            "improvement_claim": {"kinds": list(claim), "statement": "並んだ値や属性を一覧にして、読者が頭の中で表を組み直さずに済むようにする。"},
            "factual_basis": basis, "source_ids": list(sources), **extra}


def judge(*assets, chapters=CHAPTERS, profile=PROFILE):
    result = vr.review(list(assets), chapters, profile)
    return result, {c["id"]: c for c in result["candidates"]}


def codes(candidate): return {r["code"] for r in candidate["rejection_reasons"]}


class Accepted(unittest.TestCase):
    def test_representations_that_fit_their_shape(self):
        result, c = judge(
            other("tbl-a", "ch1", "table", {"kind": "comparison", "items": 3, "attributes": 4}, ["reduce_working_memory"]),
            other("fig-chart", "ch2", "chart", {"kind": "quantity", "values": 6}, ["show_quantity_shape"], basis="data", chart_type="bar"),
            diagram("fig-branch", "ch3", "flow", ["受付", "審査", "承認", "差し戻し", "完了"], [(0, 1, ""), (1, 2, "適合"), (1, 3, "不備"), (3, 1, "再提出"), (2, 4, "")],
                    shape={"kind": "process", "branching": True, "cycle": True}),
            diagram("fig-timeline", "ch4", "timeline", ["2019 導入", "2021 改訂", "2024 廃止"], shape={"kind": "chronology", "events": 3}, claim=("anchor_abstraction",)),
            diagram("fig-dag", "ch5", "network", ["重症度", "治療選択", "転帰"], [(0, 1, "影響"), (0, 2, "影響"), (1, 2, "効果")],
                    shape={"kind": "causal", "confounders": 1}),
            {"id": "fig-opener", "chapter": "ch6", "type": "image", "role": "chapter_opener", "caption": "", "information_shape": {"kind": "abstract"},
             "improvement_claim": {"kinds": ["orient_reader"], "statement": "制度論から未来設計へ、視点が局所から俯瞰に切り替わることを示す。"}})
        for ident, cand in c.items():
            self.assertEqual(cand["decision"], "accepted", (ident, cand["rejection_reasons"]))
            self.assertTrue(cand["generate"])
        self.assertEqual(c["fig-dag"]["structure"]["merging"], True)
        self.assertEqual(result["summary"], {"accepted": 6, "rejected": 0, "pending": 0})

    def test_diagram_before_its_ir_is_judged_on_its_shape(self):
        # At asset planning the Diagram IR does not exist yet; the drawn structure is judged once it does.
        _, c = judge(other("fig-plan", "ch1", "diagram", {"kind": "process", "merging": True, "steps": 7}, ["reveal_structure"]),
                     other("fig-chain", "ch2", "diagram", {"kind": "process", "steps": 3}, ["reveal_structure"]))
        self.assertEqual(c["fig-plan"]["decision"], "accepted", c["fig-plan"]["rejection_reasons"])
        self.assertIn("list_sufficient", codes(c["fig-chain"]))

    def test_pending_is_kept_but_not_generated(self):
        _, c = judge({"id": "fig-op", "chapter": "ch1", "type": "image", "role": "chapter_opener", "information_shape": {"kind": "abstract"},
                      "improvement_claim": {"kinds": ["orient_reader"], "statement": "章の主題への入口として視点の転換を示す挿絵。"}, "decision": "pending"})
        self.assertEqual((c["fig-op"]["decision"], c["fig-op"]["generate"]), ("pending", False))


class Rejected(unittest.TestCase):
    def test_two_node_concept_map(self):
        _, c = judge(diagram("fig-x", "ch1", "concept-map", ["A", "B"], [(0, 1, "支える")]))
        self.assertEqual(c["fig-x"]["decision"], "rejected")
        self.assertTrue({"too_few_nodes", "concept_map_few_edges"} <= codes(c["fig-x"]))

    def test_linear_flow(self):
        _, c = judge(diagram("fig-abc", "ch1", "flow", ["入力", "処理", "出力"], [(0, 1, ""), (1, 2, "")], shape={"kind": "process"}))
        self.assertIn("linear_sequence", codes(c["fig-abc"]))
        self.assertIn("list_sufficient", codes(c["fig-abc"]))
        self.assertEqual(next(r for r in c["fig-abc"]["rejection_reasons"] if r["code"] == "linear_sequence")["suggestion"], "numbered list")

    def test_concept_map_without_edge_labels(self):
        _, c = judge(diagram("fig-star", "ch1", "concept-map", ["中心", "A", "B", "C"], [(0, 1, ""), (0, 2, ""), (0, 3, "")]))
        self.assertIn("concept_map_edge_semantics", codes(c["fig-star"]))
        _, ok = judge(diagram("fig-star", "ch1", "concept-map", ["中心", "A", "B", "C"], [(0, 1, ""), (0, 2, ""), (0, 3, "")],
                              shape={"kind": "relation", "edge_semantics": "矢印は「〜に資源を渡す」を表す"}))
        self.assertEqual(ok["fig-star"]["decision"], "accepted")

    def test_binary_comparison_as_concept_map(self):
        _, c = judge(diagram("fig-vs", "ch1", "concept-map", ["内申", "学力"], [(0, 1, "対比")], shape={"kind": "comparison", "items": 2, "attributes": 3}))
        self.assertIn("shape_routes_elsewhere", codes(c["fig-vs"]))
        self.assertIn("table", next(r for r in c["fig-vs"]["rejection_reasons"] if r["code"] == "shape_routes_elsewhere")["suggestion"])

    def test_duplicate_type_and_claim_in_one_chapter(self):
        a = other("tbl-a", "ch1", "table", {"kind": "comparison", "items": 3, "attributes": 3}, ["reduce_working_memory"])
        b = other("tbl-b", "ch1", "table", {"kind": "comparison", "items": 4, "attributes": 3}, ["reduce_working_memory"])
        _, c = judge(a, b)
        self.assertEqual((c["tbl-a"]["decision"], c["tbl-b"]["decision"]), ("accepted", "rejected"))
        self.assertIn("duplicate_in_chapter", codes(c["tbl-b"]))

    def test_same_template_once_per_chapter(self):
        figures = [diagram(f"fig-{i}", f"ch{i}", "cycle", ["観察", "仮説", "検証", "改訂", "共有"], shape={"kind": "process", "cycle": True},
                           claim=("reveal_structure",)) for i in range(1, 9)]
        result, c = judge(*figures)
        self.assertEqual(c["fig-1"]["decision"], "accepted")
        self.assertTrue(all("repeated_composition" in codes(c[f"fig-{i}"]) for i in range(2, 9)))
        rules = {f["rule"] for f in result["plan_as_written"]}
        self.assertTrue({"template_repeated", "one_identical_visual_per_chapter", "same_type_consecutive_chapters"} <= rules)

    def test_causal_diagram_without_evidence(self):
        _, c = judge(diagram("fig-cause", "ch1", "network", ["SNS", "孤立", "発狂"], [(0, 1, "引き起こす"), (1, 2, "引き起こす"), (0, 2, "影響")],
                             shape={"kind": "causal"}, basis="derived_from_text", sources=()))
        self.assertIn("causal_without_evidence", codes(c["fig-cause"]))

    def test_visual_for_density_only(self):
        a = other("tbl-pad", "ch1", "table", {"kind": "comparison", "items": 3, "attributes": 3}, ["reduce_working_memory"])
        a["improvement_claim"]["statement"] = "文章壁を避けるため、ページに視覚的な変化を加える。"
        _, c = judge(a)
        self.assertIn("density_only", codes(c["tbl-pad"]))

    def test_disclaimer_caption_and_missing_claim(self):
        a = diagram("fig-d", "ch1", "cycle", ["A", "B", "C", "D"], shape={"kind": "process", "cycle": True},
                    caption="この図は記事にある概念関係を編集部が整理したもので、実証的な因果モデルではない。")
        b = other("tbl-n", "ch2", "table", {"kind": "comparison", "items": 3, "attributes": 3}, [])
        _, c = judge(a, b)
        self.assertIn("disclaimer_caption", codes(c["fig-d"])); self.assertIn("missing_improvement_claim", codes(c["tbl-n"]))

    def test_withdrawn_candidates_keep_their_reason(self):
        a = other("tbl-w", "ch1", "table", {"kind": "comparison", "items": 3, "attributes": 3}, ["reduce_working_memory"], decision="rejected",
                  decision_reason="本文の比較が二項だけになったので文章に戻した")
        _, c = judge(a)
        self.assertEqual(c["tbl-w"]["decision"], "rejected"); self.assertEqual(c["tbl-w"]["rejection_reasons"][0]["code"], "withdrawn")

    def test_images_outside_the_profile(self):
        _, c = judge({"id": "fig-i", "chapter": "ch1", "type": "image", "role": "editorial_illustration", "information_shape": {"kind": "abstract"},
                      "improvement_claim": {"kinds": ["anchor_abstraction"], "statement": "抽象的な「界隈」を具体的な情景に結びつける挿絵。"}})
        self.assertIn("image_role_not_allowed", codes(c["fig-i"]))


class BookLevel(unittest.TestCase):
    def test_density_shortfall_asks_for_a_plan_review_not_figures(self):
        result, _ = judge(other("tbl-a", "ch1", "table", {"kind": "comparison", "items": 3, "attributes": 3}, ["reduce_working_memory"]))
        finding = next(f for f in result["findings"] if f["rule"] == "visual_opportunities_insufficient")
        self.assertEqual(finding["severity"], "medium")
        self.assertIn("do not add figures", finding["detail"])

    def test_repeated_data_charts_are_expected_in_technical_books(self):
        charts = [other(f"fig-c{i}", f"ch{i}", "chart", {"kind": "quantity", "values": 8}, ["show_quantity_shape"], basis="data", chart_type="line") for i in range(1, 6)]
        technical = dict(PROFILE, genre="technical")
        result, c = judge(*charts, profile=technical)
        self.assertTrue(all(x["decision"] == "accepted" for x in c.values()))
        self.assertTrue(all(f["severity"] in ("low", "info") for f in result["findings"] if f["rule"] in ("template_repeated", "same_type_consecutive_chapters")))
        result, _ = judge(*charts)
        self.assertIn("medium", {f["severity"] for f in result["findings"] if f["rule"] in ("template_repeated", "same_type_consecutive_chapters")})

    def test_completeness_is_a_plan_error(self):
        self.assertIn("improvement_claim.kinds", vr.completeness({"id": "fig-a", "type": "diagram", "purpose": "p"})[0])
        self.assertEqual(vr.completeness({"id": "fig-a", "type": "diagram", "decision": "rejected"}), [])
        self.assertTrue(any("BookOrder decides" in m for m in vr.completeness({"id": "t", "type": "table", "decision": "accepted"})))


class LongBookFigures(unittest.TestCase):
    """The four concept figures of the long sample (pp. 32, 72, 93, 120), as printed."""
    DISCLAIMER = "この図は記事にある概念関係を編集部が整理したもので、実証的な因果モデルではない。"

    def figures(self):
        return [
            diagram("fig-2-1", "ch2", "concept-map", ["家庭・地域", "学校・受験", "大学・都市", "仕事・職場", "回復地点"],
                    [(0, 1, "資源"), (1, 2, "選抜"), (2, 3, "進路"), (3, 4, "時間・負担"), (0, 4, "つながり"), (4, 0, "作り直す")],
                    caption="移動に伴って変わる資源と回復地点。" + self.DISCLAIMER, basis="illustrative", sources=()),
            diagram("fig-5-1", "ch5", "cycle", ["仮説と条件", "観測指標を決める", "現実の結果を記録", "予測との差を比較", "仮定・制度を更新"],
                    shape={"kind": "process", "cycle": True}, caption="予測を観察と訂正につなぐ循環。" + self.DISCLAIMER, basis="illustrative", sources=()),
            diagram("fig-6-1", "ch6", "network", ["投稿・経験", "共通語彙", "参加・応答", "共有知・変形", "歓迎・境界管理"],
                    [(0, 1, ""), (1, 2, ""), (2, 3, ""), (3, 0, ""), (2, 4, ""), (4, 1, "意味を選ぶ")],
                    caption="共通語彙が結び、境界も作る。" + self.DISCLAIMER, basis="illustrative", sources=()),
            diagram("fig-7-1", "ch7", "cycle", ["仕事・生活の負担", "消耗に気づく", "休息・人・制度", "回復と余白", "納得できる選択"],
                    shape={"kind": "process", "cycle": True}, caption="消耗から回復と選択へ。" + self.DISCLAIMER, basis="illustrative", sources=())]

    def test_all_four_are_rejected(self):
        result, c = judge(*self.figures())
        for ident in ("fig-2-1", "fig-5-1", "fig-6-1", "fig-7-1"):
            self.assertEqual(c[ident]["decision"], "rejected", ident)
            self.assertIn("disclaimer_caption", codes(c[ident]))
            self.assertIn("illustrative_structure", codes(c[ident]))
        for ident in ("fig-5-1", "fig-6-1", "fig-7-1"): self.assertIn("repeated_composition", codes(c[ident]))
        self.assertIn("template_repeated", {f["rule"] for f in result["plan_as_written"]})
        self.assertIn("visual_opportunities_insufficient", {f["rule"] for f in result["findings"]})


if __name__ == "__main__":
    unittest.main(verbosity=2)

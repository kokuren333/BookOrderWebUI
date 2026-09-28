"""Offline full-orchestrator imagegen E2E using the existing mini-book agent.

Adds two editorial image intents and one source-grounded chart. The original
mini-book already has a diagram and a table. No external image API is used.
"""
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import zlib

import mini_e2e as mini

ROOT = mini.REPO / ".test-output/imagegen-e2e/publishing-job"
mini.WORK = ROOT

DEVICES = {
    "ch-foundations": ("sec-foundations-bottleneck", """    devices:
      - id: fig-chapter-opener
        type: figure
        why: 抽象的な章の入口を示し、注意機構の説明へ読者を導く
        placement: {intent: 注意機構の考え方へ入る前, position: early}
        information_shape: {kind: abstract}
        basis: illustrative
"""),
    "ch-training": ("sec-training-scaling", """    devices:
      - id: fig-training-demo
        type: chart
        why: 六つの模式値の増減を一度に見せ、数量の変化を読みやすくする
        placement: {intent: スケーリング則の説明の後, position: middle}
        information_shape: {kind: quantity, values: 6}
        basis: derived_from_text
        source_ids: ['{{src:training-dynamics}}']
"""),
    "ch-evaluation": ("sec-evaluation-metrics", """    devices:
      - id: fig-evaluation-concept
        type: figure
        why: 評価を複数の観点から見るという抽象的な読み方を補助する
        placement: {intent: 複数の評価観点の説明の後, position: middle}
        information_shape: {kind: abstract}
        basis: illustrative
"""),
}

ASSETS = """
  - id: fig-chapter-opener
    device: fig-chapter-opener
    chapter: ch-foundations
    section: sec-foundations-idea
    placement: 注意機構の考え方へ入る前
    purpose: 抽象的な章の入口を示し、注意機構の説明へ読者を導く
    type: image
    role: chapter_opener
    subject: 参照先を選び直す概念を表す抽象的な線と面
    context: 技術書の章扉、実在する装置や数値の描写は不要
    must_show: [複数の経路が一つの焦点へ向かう抽象的な構図]
    path: source/assets/images/fig-chapter-opener.png
    geometry: {placement: column, width_mm: 70, aspect_ratio: '3:2'}
    information_shape: {kind: abstract}
    improvement_claim:
      kinds: [orient_reader]
      statement: 章の主題を抽象的な構図として先に示し、注意機構の説明への入口を作る。
    factual_basis: illustrative
    factuality: conceptual
    caption: 注意機構への視覚的な入口
    provenance: BookOrder fake provider fixture, factual claimsなし
  - id: fig-training-demo
    device: fig-training-demo
    chapter: ch-training
    section: sec-training-scaling
    placement: スケーリング則の説明の後
    purpose: 六つの模式値の増減を示し、数量の変化を読みやすくする
    type: chart
    chart_type: bar
    data: source/assets/data/training-demo.csv
    path: source/assets/figures/training-demo.svg
    geometry: {placement: column, width_mm: 90, aspect_ratio: '3:2'}
    information_shape: {kind: quantity, values: 6}
    improvement_claim:
      kinds: [show_quantity_shape]
      statement: 六つの模式値を棒の長さに変換し、本文だけでは追いにくい増減を示す。
    factual_basis: derived_from_text
    source_ids: ['{{src:training-dynamics}}']
    caption: 学習配分の模式値
    provenance: fixture data, illustrative values, source context {{src:training-dynamics}}
  - id: fig-evaluation-concept
    device: fig-evaluation-concept
    chapter: ch-evaluation
    section: sec-evaluation-metrics
    placement: 複数の評価観点の説明の後
    purpose: 評価を複数の観点から見るという抽象的な読み方を補助する
    type: image
    role: editorial_illustration
    subject: 一つの対象を複数方向から見る抽象的な面と光
    context: 評価章の概念イラスト、グラフや数値を描かない
    must_show: [重なる視点を表す抽象的な構図]
    path: source/assets/images/fig-evaluation-concept.png
    geometry: {placement: column, width_mm: 70, aspect_ratio: '3:2'}
    information_shape: {kind: abstract}
    improvement_claim:
      kinds: [anchor_abstraction]
      statement: 単一の得点では捉えられない複数の評価観点を抽象的な構図で印象付ける。
    factual_basis: illustrative
    factuality: conceptual
    caption: 評価を複数の視点から見るための概念図
    provenance: BookOrder fake provider fixture, factual claimsなし
"""

FIGURES = {
    "ch-foundations": ("## 固定長ベクトルの限界 {#sec-foundations-bottleneck}",
                       "![注意機構への視覚的な入口](source/assets/images/fig-chapter-opener.png){#fig-chapter-opener}"),
    "ch-training": ("## スケーリング則とその修正 {#sec-training-scaling}",
                    "![学習配分の模式値](source/assets/figures/training-demo.svg){#fig-training-demo}"),
    "ch-evaluation": ("## 評価指標 {#sec-evaluation-metrics}",
                      "![評価を複数の視点から見るための概念図](source/assets/images/fig-evaluation-concept.png){#fig-evaluation-concept}"),
}

CHART = """<svg xmlns="http://www.w3.org/2000/svg" width="255.12pt" height="170.08pt" viewBox="0 0 255.12 170.08">
<rect width="255.12" height="170.08" fill="#FFFFFF"/>
<path d="M 28 12 L 28 143 L 244 143" fill="none" stroke="#164E63" stroke-width="0.6"/>
<g fill="#164E63"><rect x="40" y="103" width="22" height="40"/><rect x="74" y="88" width="22" height="55"/>
<rect x="108" y="76" width="22" height="67"/><rect x="142" y="62" width="22" height="81"/>
<rect x="176" y="45" width="22" height="98"/><rect x="210" y="29" width="22" height="114"/></g>
<g font-family="Noto Sans JP, sans-serif" font-size="8" fill="#18181B">
<text x="40" y="158">1</text><text x="74" y="158">2</text><text x="108" y="158">3</text>
<text x="142" y="158">4</text><text x="176" y="158">5</text><text x="210" y="158">6</text></g></svg>
"""


def chart_png():
    """Raster fallback drawn directly from the six fixture values, outside imagegen."""
    width, height = 1080, 720
    compressor = zlib.compressobj(6); parts = []
    bars = [3, 4, 5, 6, 7, 8]
    for y in range(height):
        row = bytearray(b"\x00")
        for x in range(width):
            color = (255, 255, 255)
            if (118 <= x <= 1010 and 600 <= y <= 604) or (118 <= x <= 122 and 80 <= y <= 604): color = (22, 78, 99)
            for i, value in enumerate(bars):
                left = 170 + i * 140
                if left <= x < left + 78 and 600 - value * 58 <= y < 600: color = (22, 78, 99)
            row.extend(color)
        parts.append(compressor.compress(bytes(row)))
    parts.append(compressor.flush())
    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", b"".join(parts)) + chunk(b"IEND", b""))


class Agent(mini.MockAgent):
    def copy(self, fixture, relative, own=None):
        text = self.render((mini.AGENT / fixture).read_text(encoding="utf-8"), own)
        if fixture.startswith("editorial/"):
            chapter = Path(fixture).stem
            if chapter in DEVICES:
                section, block = DEVICES[chapter]
                marker = "  - id: " + section
                at = text.find(marker)
                assert at >= 0, (chapter, section)
                next_section = text.find("\n  - id: ", at + len(marker))
                end = next_section + 1 if next_section >= 0 else text.find("chapter_end:", at)
                assert end >= 0
                if "    devices:" in text[at:end]: block = block.replace("    devices:\n", "", 1)
                text = text[:end] + block + text[end:]
        elif fixture.startswith("chapters/") and fixture.endswith(".md"):
            chapter = Path(fixture).stem.split(".")[0]
            if chapter in FIGURES:
                marker, figure = FIGURES[chapter]
                assert marker in text, (fixture, marker)
                text = text.replace(marker, marker + "\n\n" + figure, 1)
        elif fixture == "plan/assets-plan.yaml":
            text += self.render(ASSETS)
            data = mini.WORK / "source/assets/data/training-demo.csv"
            data.parent.mkdir(parents=True, exist_ok=True)
            data.write_text("step,value\n1,3\n2,4\n3,5\n4,6\n5,7\n6,8\n", encoding="utf-8")
            image = mini.WORK / "source/assets/figures/training-demo.svg"
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_text(CHART, encoding="utf-8")
            image.with_suffix(".png").write_bytes(chart_png())
        self.put(relative, self.render(text))


def run_goal(agent, limit=120):
    seen = {}
    for step in range(limit):
        output = mini.cli("goal", "--json").stdout
        start = output.rfind('{\n  "status"')
        if start < 0: raise AssertionError("Goal JSON missing:\n" + output[-3000:])
        result = json.loads(output[start:])
        if result["status"] == "complete": return result, step
        if result["status"] == "blocked": raise AssertionError("Blocked: " + json.dumps(result["blockers"], ensure_ascii=False))
        if not result["tasks"]: raise AssertionError("No tasks and not complete: " + output[-2000:])
        for item in result["tasks"]:
            seen[item["id"]] = seen.get(item["id"], 0) + 1
            if seen[item["id"]] > 4:
                raise AssertionError(f"Task {item['id']} repeats without progress:\n" + "\n".join(item["instructions"]))
            if item["kind"] == "agent": agent.handle(item)
        for item in result["tasks"]:
            if item["kind"] == "agent": mini.cli("done", item["id"], "--json")
    raise AssertionError("Step limit reached")


def main():
    server, base = mini.serve()
    try:
        urls = mini.setup(base)
        project_path = ROOT / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["figures"]["generative_images"] = True
        project["image_generation"] = {"provider": "fake"}
        project["profile"] = {"overrides": {"art_direction": {"generative_images":
                     {"allowed": ["chapter_opener", "editorial_illustration"], "max_total": 2}},
                     "devices": {"visuals_per_10k": {"min": 2, "target": 6, "max": 12}}}}
        project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
        agent = Agent(base)
        result, steps = run_goal(agent)
        assert result["status"] == "complete", result
        report_path = ROOT / "reports/image-assets-check.yaml"
        assert report_path.is_file()
        sys.path.insert(0, str(ROOT / "scripts"))
        from common import yaml_data
        report = yaml_data(report_path)
        assert report["summary"]["status"] == "pass", report["checks"]
        assert int(report["provider_activity"]["real_api_requests"]) == 0
        assert set(report["routed_to_imagegen"]) == {"fig-chapter-opener", "fig-evaluation-concept"}
        assert {item["id"] for item in report["not_routed"]} >= {"fig-attention-flow", "fig-training-demo", "tbl-attention-variants"}
        for ident in report["routed_to_imagegen"]:
            asset = json.loads((ROOT / f"source/assets/generated/{ident}.json").read_text(encoding="utf-8"))
            assert asset["accepted"] and asset["effective_dpi"] >= 300 and asset["provider"] == "fake"
        metrics = json.loads((ROOT / "reports/layout-metrics.json").read_text(encoding="utf-8"))
        labels = {e.get("label") for page in metrics["pages"] for e in page["elements"]}
        assert {"fig-chapter-opener", "fig-evaluation-concept", "fig-training-demo", "fig-attention-flow", "tbl-attention-variants"} <= labels
        art = yaml_data(ROOT / "reports/art-direction-check.yaml")
        assert int(art["summary"]["high"]) == 0, art["checks"]
        embedded = art["measurement"]["generated_images"]
        assert len(embedded) == 2 and all(item["pdf_image_bbox_pt"] and item["pdf_image_pixels"] for item in embedded), embedded
        gates = json.loads((ROOT / "reports/completion-gates.json").read_text(encoding="utf-8"))
        assert gates["passed"] and len(gates["gates"]) == 22, [g for g in gates["gates"] if not g["passed"]]
        assert all(g["passed"] for g in gates["gates"] if g["id"] in (10, 15, 20, 21))
        print(json.dumps({"status": "pass", "steps": steps, "pages": metrics["totals"]["pages"],
                          "routed_to_imagegen": report["routed_to_imagegen"],
                          "not_routed": report["not_routed"], "real_api_requests": report["provider_activity"]["real_api_requests"],
                          "art_direction_high": art["summary"]["high"]}, ensure_ascii=False))
    finally:
        server.shutdown()


if __name__ == "__main__": main()

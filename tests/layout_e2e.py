"""Real BookOrder two-column PDF regression built from the completed mini E2E job.

Run `python tests/mini_e2e.py --keep` first, then `python tests/layout_e2e.py`.
The deliberate equation edit is fixture-only: the original formula needs a wider measure.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tests"))
import _tools  # noqa: E402  PANDOC/TYPST from env, PATH or .tools/; UTF-8 child output
if _tools.MISSING: raise SystemExit(f"Missing {', '.join(_tools.MISSING)}: set PANDOC/TYPST, add to PATH, or place them in .tools/")
BASE = REPO / ".test-output/mini-e2e/publishing-job"
WORK = REPO / ".test-output/layout-e2e/publishing-job"


def require(condition, message):
    if not condition: raise AssertionError(message)


def main():
    require((BASE / "publish/book.pdf").is_file(), "Run python tests/mini_e2e.py --keep first")
    require(WORK.resolve().is_relative_to((REPO / ".test-output").resolve()), "work path escaped test output")
    if WORK.exists(): shutil.rmtree(WORK)
    WORK.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(BASE, WORK, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    project_path = WORK / "project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project["outputs"].update({"docx": False, "semantic_html": False, "static_site": False, "epub": False})
    project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # The mini job may have been built from a prior template revision.
    for folder in ("scripts", "templates", "themes", "schemas", "tools"):
        source, target = REPO / "job-template" / folder, WORK / folder
        if target.exists():
            require(target.resolve().is_relative_to(WORK.resolve()), "target escaped job")
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    sys.path.insert(0, str(WORK / "scripts"))
    from common import yaml_data, write_yaml, fingerprint

    spec_path = WORK / "plan/layout-spec.yaml"
    spec = yaml_data(spec_path)
    before = fingerprint()
    spec["body"]["columns"] = 2
    spec["body"]["gutter_mm"] = 6
    spec["spans"]["callout"] = 2
    write_yaml(spec_path, spec)
    require(fingerprint() != before, "LayoutSpec change must invalidate downstream work")

    assets_path = WORK / "plan/assets-plan.yaml"
    assets = yaml_data(assets_path)
    by_id = {a["id"]: a for a in assets["assets"]}
    by_id["fig-attention-flow"]["geometry"] = {"placement": "column", "span": 2, "width_mm": 96}
    by_id["tbl-attention-variants"]["geometry"] = {"placement": "full-width", "span": "full"}
    # A separate narrow, legible SVG exercises the actual BookOrder span-1 figure path.
    narrow = dict(by_id["fig-attention-flow"])
    narrow.update(id="fig-column-probe", type="screenshot", path="source/assets/figures/column-probe.svg",
                  caption="一列幅の図版", purpose="二段組の片列で判読できる図版を確認する。",
                  provenance="deterministic layout fixture", geometry={"placement": "column", "span": 1, "width_mm": 52.5})
    narrow.pop("source", None)
    assets["assets"].append(narrow)
    write_yaml(assets_path, assets)
    svg = WORK / narrow["path"]
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="52.5mm" height="18mm" viewBox="0 0 525 180">'
                   '<rect x="1" y="1" width="523" height="178" fill="#e9f2f8" stroke="#386580"/>'
                   '<text x="40" y="105" font-size="32" fill="#123947">一列幅の図</text></svg>', encoding="utf-8")
    import assets as asset_module
    asset_module.sync_figure_registry()
    from planning import load_outline
    require(not asset_module.check_plan(load_outline(), project), "fixture asset plan invalid")

    chapter = WORK / "source/manuscript/02-mechanism.md"
    text = chapter.read_text(encoding="utf-8")
    original = r"\operatorname{Attention}(Q, K, V) = \operatorname{softmax}\left(\frac{QK^{\top}}{\sqrt{d_k}}\right) V"
    require(original in text, "mini E2E equation changed")
    text = text.replace(original, r"A = \operatorname{softmax}(QK^{\top})V")
    anchor = '![スケール化内積注意の計算の流れ](source/assets/figures/attention-flow.svg){#fig-attention-flow}'
    require(anchor in text, "fixture figure anchor changed")
    text = text.replace(anchor, anchor + '\n\n![一列幅の図版](source/assets/figures/column-probe.svg){#fig-column-probe}')
    chapter.write_text(text, encoding="utf-8")

    result = subprocess.run([sys.executable, "scripts/build.py"], cwd=WORK, capture_output=True, text=True, encoding="utf-8", errors="replace")
    require(result.returncode == 0, result.stdout + "\n" + result.stderr)
    metrics = json.loads((WORK / "reports/layout-metrics.json").read_text(encoding="utf-8"))
    figure = json.loads((WORK / "reports/figure-check.json").read_text(encoding="utf-8"))
    capabilities = json.loads((WORK / "reports/layout-capabilities.json").read_text(encoding="utf-8"))
    require(metrics["page_geometry"]["columns"] == 2, "PDF metrics did not use two columns")
    require(any(col["paragraphs"] for p in metrics["pages"] for col in p["columns"][1:]), "no text flowed into column 2")
    require(any(e.get("geometry", {}).get("span") == "2" for p in metrics["pages"] for e in p["elements"] if e["kind"] == "figure"),
            "two-column figure span missing")
    require(any(e.get("geometry", {}).get("span") == "1" for p in metrics["pages"] for e in p["elements"] if e["kind"] == "figure"),
            "one-column figure span missing")
    require(any(e.get("geometry", {}).get("span") == "full" for p in metrics["pages"] for e in p["elements"] if e["kind"] == "table"),
            "full-width table span missing")
    require(figure["summary"]["fail"] == 0 and figure["summary"]["min_text_pt"] >= 6.5,
            "figure legibility regression")
    require(capabilities["renderers"]["pdf"]["status"] == "supported", "PDF capability wrong")
    require(metrics["area_accuracy"] == "approximate", "two-column metric limit not declared")
    specimen = subprocess.run([sys.executable, "tools/layout-specimen.py"], cwd=WORK,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
    require(specimen.returncode == 0 and (WORK / "publish/layout-specimen.pdf").is_file(),
            specimen.stdout + "\n" + specimen.stderr)
    print(json.dumps({"ok": True, "pages": metrics["totals"]["pages"], "two_column_text": True,
                      "figure_spans": [1, 2], "table_span": "full", "min_figure_text_pt": figure["summary"]["min_text_pt"],
                      "pdf": str(WORK / "publish/book.pdf"), "specimen": str(WORK / "publish/layout-specimen.pdf")}, ensure_ascii=False))


if __name__ == "__main__": main()

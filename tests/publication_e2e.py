"""P1-UI E2E: WebUI publication settings -> project.json -> existing resolvers -> Typst PDF.

Run `python tests/mini_e2e.py --keep` first, then `python tests/publication_e2e.py`.

Each case asks the real WebUI modules (tests/webui_cli.ts -> src/job.ts) for the job ZIP a user would download with
those settings, takes its project.json publication request and book.design.yaml, and applies them to the completed
mini E2E manuscript. The plan artifacts are deleted so the job resolves them itself, exactly as a fresh job does.
The PDF is then checked with the existing layout metrics (Typst probe), figure check and StyleBible reports.
No image API or other paid API is involved (FakeImageProvider policy unchanged).
"""
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

REPO = Path(__file__).resolve().parent.parent
BASE = REPO / ".test-output/mini-e2e/publishing-job"
OUT = REPO / ".test-output/publication-e2e"
PT = 72 / 25.4
PUBLICATION_KEYS = ("profile", "layout_preset", "layout_spec", "style_preset", "style_controls")

CASES = {
    "case-a": {"preset": "standard-book", "publication": {"tier": "short", "genre": "technical", "stylePreset": "technical-clean"}},
    "case-b": {"preset": "medical-scientific", "publication": {"tier": "short", "genre": "medical_science", "stylePreset": "medical-evidence",
                                                             "figureSpan": "auto", "tableSpan": "auto"}},
}


def require(condition, message):
    if not condition: raise AssertionError(message)


def webui_job(name, spec):
    archive = OUT / f"{name}-webui.zip"
    result = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", "tests/webui_cli.ts", "zip", json.dumps(spec), str(archive)],
                            cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    require(result.returncode == 0, result.stdout + result.stderr)
    with zipfile.ZipFile(archive) as z:
        project = json.loads(z.read("publishing-job/project.json"))
        design = json.loads(z.read("publishing-job/book.design.yaml"))
        require(not any(n.startswith("publishing-job/plan/") and n.endswith(".yaml") for n in z.namelist()), "template shipped resolved plans")
    return project, design


def prepare(name, spec):
    work = OUT / name / "publishing-job"
    require(work.resolve().is_relative_to((REPO / ".test-output").resolve()), "work path escaped test output")
    if work.parent.exists(): shutil.rmtree(work.parent)
    shutil.copytree(BASE, work, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for folder in ("scripts", "templates", "themes", "schemas", "styles", "profiles", "tools"):
        target = work / folder
        if target.exists(): shutil.rmtree(target)
        shutil.copytree(REPO / "job-template" / folder, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    webui_project, webui_design = webui_job(name, spec)
    project = json.loads((work / "project.json").read_text(encoding="utf-8"))
    for key in PUBLICATION_KEYS:
        project.pop(key, None)
        if key in webui_project: project[key] = webui_project[key]
    project["outputs"].update({"docx": False, "semantic_html": False, "static_site": False, "epub": False})
    (work / "project.json").write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    design = json.loads((work / "book.design.yaml").read_text(encoding="utf-8")) if (work / "book.design.yaml").is_file() else {}
    design.setdefault("page", {})
    design["page"] = {**design["page"], **webui_design["page"]}
    (work / "book.design.yaml").write_text(json.dumps(design, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for artifact in ("plan/profile.resolved.yaml", "plan/layout-spec.yaml", "plan/style-bible.yaml"):
        (work / artifact).unlink(missing_ok=True)
    return work, webui_project


def fixture_edits(work, wide_table):
    """Same fixture-only edit as tests/layout_e2e.py (the long formula needs a one-column measure); CASE B also widens
    the comparison table to five columns so the automatic table span has something to decide."""
    chapter = work / "source/manuscript/02-mechanism.md"
    text = chapter.read_text(encoding="utf-8")
    original = r"\operatorname{Attention}(Q, K, V) = \operatorname{softmax}\left(\frac{QK^{\top}}{\sqrt{d_k}}\right) V"
    require(original in text, "mini E2E equation changed")
    text = text.replace(original, r"A = \operatorname{softmax}(QK^{\top})V")
    if wide_table:
        rows = re.findall(r"(?m)^\|.*\|$", text)
        require(len(rows) >= 3, "fixture table missing")
        widened = [row + (" 方向 | 備考 |" if i == 0 else ":-----|:-----|" if i == 1 else " 双方向 | — |") for i, row in enumerate(rows)]
        for old, new in zip(rows, widened): text = text.replace(old, new, 1)
    chapter.write_text(text, encoding="utf-8")


def build(work):
    result = subprocess.run([sys.executable, "scripts/build.py"], cwd=work, capture_output=True, text=True, encoding="utf-8")
    require(result.returncode == 0, result.stdout[-3000:] + "\n" + result.stderr[-3000:])
    sys.path.insert(0, str(work / "scripts"))
    for module in [m for m in list(sys.modules) if m in ("common", "layout_metrics", "layout_spec", "pdf_visual_probe")]: del sys.modules[module]
    import layout_metrics, pdf_visual_probe
    probe = layout_metrics.probe(root=work)
    sys.path.pop(0)
    yaml = lambda rel: json.loads(subprocess.run([sys.executable, "-c", "import sys,json; sys.path.insert(0,'scripts'); from common import yaml_data; print(json.dumps(yaml_data(sys.argv[1])))", rel],
                                                 cwd=work, capture_output=True, text=True, encoding="utf-8").stdout)
    reports = {name: json.loads((work / "reports" / name).read_text(encoding="utf-8"))
               for name in ("layout-metrics.json", "figure-check.json", "layout-capabilities.json", "build-report.json")}
    tokens = json.loads((work / ".build/design-tokens.json").read_text(encoding="utf-8"))
    pdf = pdf_visual_probe.inspect(work / "publish/book.pdf")  # existing PDF-level probe (vector streams)
    require(pdf["status"] == "measured", pdf.get("reason"))
    sizes = {(round(p["width_pt"], 1), round(p["height_pt"], 1)) for p in pdf["pages"]}
    colors = {item["color"] for p in pdf["pages"] for key in ("text", "strokes", "fills") for item in p[key] if item.get("color")}
    return {"probe": probe, "reports": reports, "tokens": tokens, "sizes": sizes, "colors": colors, "yaml": yaml,
            "validate": subprocess.run([sys.executable, "scripts/validate.py"], cwd=work, capture_output=True, text=True, encoding="utf-8")}


def measured_gutter(probe, geometry):
    """Gutter measured from typeset paragraph positions: right-column start minus left-column start minus column width."""
    column_w = geometry["column_width_pt"]; gutters = []
    by_page = {}
    for par in probe["pars"]: by_page.setdefault(par["page"], []).append(par["x"])
    for page, xs in by_page.items():
        left = geometry["margin_inner_pt"] if page % 2 else geometry["margin_outer_pt"]
        split = left + column_w + geometry["gutter_pt"] / 2
        first = [x for x in xs if x < split]; second = [x for x in xs if x >= split]
        if first and second: gutters.append(min(second) - min(first) - column_w)
    return gutters


def main():
    require((BASE / "publish/book.pdf").is_file(), "Run python tests/mini_e2e.py --keep first")
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}

    # ---------------- CASE A: A5 · 1 column · technical · Technical Clean
    work, request = prepare("case-a", CASES["case-a"])
    require(request.get("layout_preset") == "standard-book" and request.get("style_preset") == "technical-clean", request)
    fixture_edits(work, wide_table=False)
    a = build(work)
    spec, profile, style = a["yaml"]("plan/layout-spec.yaml"), a["yaml"]("plan/profile.resolved.yaml"), a["yaml"]("plan/style-bible.yaml")
    geo = a["reports"]["layout-metrics.json"]["page_geometry"]
    require((spec["page_size"], str(spec["body"]["columns"])) == ("A5", "1"), spec)
    require((profile["tier"], profile["genre"]) == ("short", "technical"), profile["id"])
    require(style.get("preset") == "technical-clean" and style["genre"] == "technical", style.get("preset"))
    require(geo["columns"] == 1 and abs(geo["width_pt"] - 148 * PT) < .5 and abs(geo["height_pt"] - 210 * PT) < .5, geo)
    require(a["sizes"] == {(419.53, 595.28)} or a["sizes"] == {(419.5, 595.3)}, f"PDF pages are not A5: {a['sizes']}")
    require(a["tokens"]["style"]["genre"] == "technical", "StyleBible not compiled into design tokens")
    require(a["reports"]["figure-check.json"]["summary"]["fail"] == 0, "figure legibility regression")
    require(json.loads(a["validate"].stdout)["ok"], a["validate"].stdout)
    summary["case_a"] = {"page": "A5 148×210", "columns": 1, "profile": profile["id"], "style_preset": style["preset"],
                         "pages": a["reports"]["layout-metrics.json"]["totals"]["pages"], "pdf": str(work / "publish/book.pdf")}

    # ---------------- CASE B: B5 · 2 columns · medical_science · Medical Evidence · automatic span
    work, request = prepare("case-b", CASES["case-b"])
    require(request.get("layout_preset") == "medical-scientific" and request.get("style_preset") == "medical-evidence", request)
    fixture_edits(work, wide_table=True)
    b = build(work)
    spec, profile, style = b["yaml"]("plan/layout-spec.yaml"), b["yaml"]("plan/profile.resolved.yaml"), b["yaml"]("plan/style-bible.yaml")
    metrics = b["reports"]["layout-metrics.json"]; geo = metrics["page_geometry"]
    require((spec["page_size"], str(spec["body"]["columns"]), float(spec["body"]["gutter_mm"])) == ("B5", "2", 7.0), spec)
    require(spec["span_policy"] == {"figure": "auto", "table": "auto"}, spec.get("span_policy"))
    require((profile["tier"], profile["genre"]) == ("short", "medical_science"), profile["id"])
    require(style.get("preset") == "medical-evidence" and style["palette"]["accent"] == "#116B78", style.get("preset"))
    # Body really is two columns in the PDF, with the configured gutter.
    require(geo["columns"] == 2 and abs(geo["width_pt"] - 176 * PT) < .5 and abs(geo["gutter_pt"] - 7 * PT) < .1, geo)
    require(b["sizes"] == {(498.9, 708.7)}, f"PDF pages are not B5: {b['sizes']}")
    require(any(col["paragraphs"] for p in metrics["pages"] for col in p["columns"][1:]), "no text flowed into column 2")
    gutters = measured_gutter(b["probe"], geo)
    require(gutters and all(abs(g - geo["gutter_pt"]) < 1.5 for g in gutters), f"measured gutter differs: {gutters[:5]} vs {geo['gutter_pt']}")
    # Automatic span: the 96 mm diagram exceeds a 67.5 mm column, the five-column table needs the width.
    spans = {(e["kind"], e.get("id")): e.get("geometry", {}).get("span") for p in metrics["pages"] for e in p["elements"] if e["kind"] in ("figure", "table")}
    require(any(kind == "figure" and span == "full" for (kind, _), span in spans.items()), f"automatic figure span missing: {spans}")
    require(any(kind == "table" and span == "full" for (kind, _), span in spans.items()), f"automatic table span missing: {spans}")
    figure = b["reports"]["figure-check.json"]
    require(figure["summary"]["fail"] == 0 and figure["summary"]["min_text_pt"] >= 6.5, "figure legibility regression")
    require(b["reports"]["layout-capabilities.json"]["renderers"]["pdf"]["status"] == "supported", "PDF capability wrong")
    tokens = b["tokens"]
    require(tokens["colors"]["accent"] == "#116B78" and tokens["style"]["genre"] == "medical_science", "StyleBible preset not in design tokens")
    require(tokens["style"]["adaptation"]["column_width_mm"] == 67.5, tokens["style"]["adaptation"])
    style_report = b["yaml"]("reports/style-check.yaml")
    require(int(style_report["summary"]["high"]) == 0, style_report["summary"])
    require("#116B78" in b["colors"], f"Medical Evidence accent not drawn in the PDF: {sorted(b['colors'])[:12]}")
    require(json.loads(b["validate"].stdout)["ok"], b["validate"].stdout)
    summary["case_b"] = {"page": "B5 176×250", "columns": geo["columns"], "gutter_mm": round(geo["gutter_pt"] / PT, 2),
                         "column_width_mm": round(geo["column_width_pt"] / PT, 2), "measured_gutter_mm": round(sum(gutters) / len(gutters) / PT, 2),
                         "spans": {f"{k[0]}:{k[1]}": v for k, v in spans.items()}, "profile": profile["id"], "style_preset": style["preset"],
                         "accent_in_pdf": "#116B78" in b["colors"], "pages": metrics["totals"]["pages"], "pdf": str(work / "publish/book.pdf")}
    summary["real_api_requests"] = 0
    print(json.dumps({"ok": True, **summary}, ensure_ascii=False))


if __name__ == "__main__": main()

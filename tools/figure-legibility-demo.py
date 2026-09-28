"""Development check for P0-5: redraw the representative charts of the short sample book at printed size.

Draws five charts (histogram, confidence intervals, RR/ARR/NNT bars, Kaplan–Meier, ROC) with
job-template/scripts/chartkit.py at the A5 text-column width, checks them with figure_check (the same check the
build runs), places them in an A5 Typst page at 100 % and measures the printed text with pdfplumber.
With --before <old book.pdf> it also measures the text inside the figures of the previous PDF.
Data are fictitious, shaped like the sample book's figures.

Usage: python tools/figure-legibility-demo.py [--before short.pdf] [--out .test-output/figure-demo]
Requires: matplotlib, Typst (TYPST or PATH); pdfplumber for printed measurements.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "job-template/scripts"))
import chartkit  # noqa: E402
import figure_check  # noqa: E402
from design import load_design  # noqa: E402
from figure_spec import resolve  # noqa: E402

# Pages of the previous short book that hold these figures (physical page numbers).
BEFORE_PAGES = {"histogram": 7, "confidence-intervals": 11, "rr-arr-nnt": 21, "kaplan-meier": 29, "roc": 35, "forest": 38}


def charts(tokens, out):
    import numpy as np
    rng = np.random.default_rng(7)
    made = {}

    def done(name, fig):
        path = out / f"{name}.svg"; made[name] = (path, chartkit.save(fig, path, name)); return path

    fig, ax = chartkit.figure(tokens=tokens, aspect_ratio="16:9")
    days = [2, 3, 3, 3, 3, 4, 4, 4, 5, 8]
    ax.hist(days, bins=range(1, 10), color=chartkit.palette(fig._bookorder["tokens"])[0], edgecolor="white", alpha=.8)
    for x, y, label, style, side in ((np.median(days), 3.7, "中央値 = 3.5", "-", "right"), (np.mean(days), 3.2, "平均 = 3.9", "--", "left")):
        ax.axvline(x, color="#444444", linestyle=style, linewidth=fig._bookorder["tokens"]["stroke_width_pt"])
        ax.annotate(label, (x, y), xytext=(-3 if side == "right" else 3, 0), textcoords="offset points", ha=side)
    ax.set_xlabel("入院日数（日）"); ax.set_ylabel("患者数（人）"); ax.set_ylim(0, 4.2)
    done("histogram", fig)

    fig, ax = chartkit.figure(tokens=tokens, aspect_ratio="16:9")
    rows = [("リスク比", 0.62, 0.45, 0.85, 1), ("平均差", -1.8, -4.9, 1.3, 0), ("広い区間", 0.9, -2.0, 3.8, 0), ("狭い区間", 1.1, 0.6, 1.6, 0)]
    for i, (name, est, lo, hi, _) in enumerate(rows):
        ax.errorbar(est, i, xerr=[[est - lo], [hi - est]], fmt="o", capsize=2)
    ax.axvline(0, linestyle=":", color="#9E3B3B"); ax.axvline(1, linestyle=":", color="#9E3B3B")
    ax.set_yticks(range(len(rows)), [r[0] for r in rows]); ax.set_xlabel("効果推定値と 95% 信頼区間（模式的な共通表示）")
    done("confidence-intervals", fig)

    fig, ax = chartkit.figure(tokens=tokens, aspect_ratio="16:9")
    groups = [("対照 2% → 治療 1%", 2, 1), ("対照 20% → 治療 10%", 20, 10)]
    for i, (name, control, treated) in enumerate(groups):
        ax.barh([i + .18], [control], height=.32, label="対照群" if i == 0 else None)
        ax.barh([i - .18], [treated], height=.32, label="治療群" if i == 0 else None)
        ax.annotate(f"ARR {control - treated} pt / NNT {round(100 / (control - treated))}", (control, i + .18), xytext=(4, -3), textcoords="offset points")
    ax.set_yticks(range(len(groups)), [g[0] for g in groups]); ax.set_xlim(0, 32); ax.set_xlabel("イベントのリスク（%）")
    ax.legend(loc="lower right")
    done("rr-arr-nnt", fig)

    fig, ax = chartkit.figure(tokens=tokens, aspect_ratio="16:10")
    for name, scale in (("治療群", 30), ("対照群", 18)):
        times = np.sort(rng.exponential(scale, 40)); surv = np.cumprod(1 - 1 / np.arange(40, 0, -1))
        ax.step(np.r_[0, times], np.r_[1, surv], where="post", label=name)
        ax.plot(times[::6], surv[::6], "|", markersize=5, color="#444444")
    ax.set_xlabel("追跡期間（月）"); ax.set_ylabel("生存割合"); ax.set_ylim(0, 1.02); ax.legend()
    done("kaplan-meier", fig)

    fig, ax = chartkit.figure(tokens=tokens, aspect_ratio="1:1", width_mm=70)
    fpr = np.linspace(0, 1, 50); tpr = 1 - (1 - fpr) ** 3.2
    ax.plot(fpr, tpr, label="検査 A（AUC 0.81）"); ax.plot([0, 1], [0, 1], linestyle=":", color="#888888", label="偶然")
    ax.set_xlabel("偽陽性率（1 − 特異度）"); ax.set_ylabel("感度"); ax.legend(loc="lower right"); ax.set_aspect("equal")
    done("roc", fig)
    return made


def typeset(made, tokens, out):
    """An A5 page per chart, the chart placed at its drawn width (what the renderer does with declared geometry)."""
    page = tokens["page"]["margin"]
    lines = [f'#set page(paper: "a5", margin: (top: {page["top"]}, bottom: {page["bottom"]}, inside: {page["inner"]}, outside: {page["outer"]}))',
             '#set text(size: 9.5pt, lang: "ja", font: ("Noto Serif CJK JP", "Noto Sans CJK JP"))']
    for name, (path, record) in made.items():
        lines += [f"== {name}", f'#figure(image("{path.name}", width: {record["width_mm"]}mm), caption: [{name}])', "#pagebreak()"]
    source = out / "demo.typ"; source.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    typst = os.environ.get("TYPST") or shutil.which("typst")
    subprocess.run([typst, "compile", "--root", out, source, out / "demo.pdf"], check=True)
    subprocess.run([typst, "compile", "--root", out, "--ppi", "150", source, out / "demo-{p}.png"], check=True)
    return out / "demo.pdf"


def printed_sizes(pdf_path, pages, exclude=()):
    """Point sizes of text inside the figure area of each page (between the first graphic and the caption)."""
    import pdfplumber
    result = {}
    with pdfplumber.open(pdf_path) as pdf:
        for name, number in pages.items():
            page = pdf.pages[number - 1]
            shapes = page.rects + page.curves + page.lines + page.images
            shapes = [s for s in shapes if s["width"] < page.width * 0.95 and s["top"] > 30]
            if not shapes: continue
            top = min(s["top"] for s in shapes) - 12; bottom = max(s["bottom"] for s in shapes) + 4
            chars = [c for c in page.chars if c["text"].strip() and top <= c["top"] <= bottom and round(c["size"], 1) not in exclude]
            sizes = Counter(round(c["size"], 1) for c in chars)
            result[name] = {"page": number, "min_pt": min(sizes) if sizes else None, "sizes": dict(sorted(sizes.items()))}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--before"); parser.add_argument("--out", default=str(REPO / ".test-output/figure-demo"))
    args = parser.parse_args()
    out = Path(args.out); shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
    build = REPO / "job-template/.build"; existed = build.exists()
    tokens = load_design("medical-textbook")
    made = charts(tokens, out)
    report = {"tokens": chartkit.spec(tokens=tokens)["tokens"] | {"colors": None}, "after": {}}
    for name, (path, record) in made.items():
        geometry = resolve({"width_mm": record["width_mm"]}, tokens, "chart") | {"declared": True}
        check = figure_check.check_figure(name, path, geometry, tokens)
        report["after"][name] = {"width_mm": record["width_mm"], "height_mm": record["height_mm"], "declared_min_pt": record["min_text_pt"],
                                 "svg_check_min_pt": check.get("min_text_pt"), "status": check["status"]}
    try:
        pdf = typeset(made, tokens, out)
        printed = printed_sizes(pdf, {name: i + 1 for i, name in enumerate(made)})
        for name, measured in printed.items(): report["after"][name]["printed"] = measured
    except ImportError: report["note"] = "pdfplumber missing: printed sizes not measured"
    if args.before:
        # Body text and captions of the old page are outside the figure area; running heads are above it.
        report["before"] = printed_sizes(args.before, BEFORE_PAGES)
    if not existed: shutil.rmtree(build, ignore_errors=True)  # load_design's YAML cache must not stay in the template
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

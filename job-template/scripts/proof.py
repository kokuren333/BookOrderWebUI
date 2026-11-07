"""`bookorder proof`: typeset the real manuscript with the current design and export selected pages as PNG.

Used in the design conversation: Claude (and the user) look at actual pages, not at a theme sample. By default the
pages are chosen from the measured layout so one proof shows the design's hard cases: the contents page, a chapter
opener and the spread after it, the longest text-only run, and the first pages with a figure, a table, a callout and
code. `--pages 12,30-31` picks pages explicitly. The PDF-only proof build never counts as the final build.

    bookorder proof [--pages LIST] [--ppi 110] [--no-build] [--label name]
"""
from datetime import datetime
import json
from pathlib import Path
import re

from common import ROOT, run, tool

PROOFS = ROOT / "proofs"
SOURCE = ROOT / ".build/book.typ"


def _metrics():
    path = ROOT / "reports/layout-metrics.json"
    if not path.is_file(): return None
    try: return json.loads(path.read_text(encoding="utf-8"))
    except ValueError: return None


def auto_pages(limit=8):
    """Representative pages with a reason each, from reports/layout-metrics.json (falls back to the first pages)."""
    metrics = _metrics()
    if not metrics or not metrics.get("pages"):
        return [(1, "first page"), (2, "second page"), (3, "third page"), (4, "fourth page")]
    pages = metrics["pages"]; total = len(pages); chosen = {}

    def pick(page, reason):
        if page and 1 <= page <= total and page not in chosen and len(chosen) < limit: chosen[page] = reason

    front = [p for p in pages if p.get("region") == "front"]
    if front: pick(front[min(1, len(front) - 1)]["page"], "front matter / contents")
    openers = [p for p in pages if p.get("opener")]
    if openers:
        first = openers[0]["page"]
        pick(first, "chapter opener"); pick(first + 1, "page after the opener (spread)")
        if len(openers) > 2: pick(openers[len(openers) // 2]["page"], "a later chapter opener")
    runs = sorted((r for r in metrics.get("text_only_runs", []) if isinstance(r, dict) and r.get("start")),
                  key=lambda r: -r.get("length", 0))
    if runs: pick(runs[0]["start"], f"longest text-only run ({runs[0].get('length')} pages)")
    else:
        text = [p for p in pages if p.get("text_only")]
        if text: pick(text[len(text) // 2]["page"], "text-only page")
    for kind, reason in (("figure", "figure"), ("table", "table"), ("callout", "callout / box"), ("code", "code"), ("equation", "equation")):
        page = next((p["page"] for p in pages if any(e.get("kind") == kind for e in p.get("elements", []))), None)
        pick(page, reason)
    back = [p for p in pages if p.get("region") == "back"]
    if back: pick(back[0]["page"], "back matter / references")
    return sorted(chosen.items())


def parse_pages(text):
    result = []
    for part in re.split(r"[,\s]+", text.strip()):
        if not part: continue
        if "-" in part:
            a, b = part.split("-", 1); result += [(n, "requested") for n in range(int(a), int(b) + 1)]
        else: result.append((int(part), "requested"))
    return sorted(dict(result).items())


def make(pages=None, ppi=110, build=True, label=None):
    if build:
        from build import build as do_build
        do_build(proof=True)
    if not SOURCE.is_file(): raise RuntimeError("No typeset book yet (.build/book.typ); run `bookorder proof` without --no-build")
    selected = parse_pages(pages) if pages else auto_pages()
    metrics = _metrics(); total = len(metrics["pages"]) if metrics and metrics.get("pages") else None
    if total: selected = [(n, r) for n, r in selected if 1 <= n <= total]
    if not selected: raise ValueError("No valid pages selected" + (f" (the book has {total} pages)" if total else ""))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = PROOFS / (stamp + ("-" + re.sub(r"[^A-Za-z0-9_-]+", "-", label)[:40] if label else ""))
    folder.mkdir(parents=True, exist_ok=True)
    numbers = ",".join(str(n) for n, _ in selected)
    run([tool("typst"), "compile", "--root", ROOT, "--format", "png", "--ppi", str(ppi), "--pages", numbers,
         SOURCE, folder / "page-{0p}.png"])
    files = sorted(folder.glob("page-*.png"))
    index = []
    for (number, reason) in selected:
        match = next((f for f in files if int(re.search(r"(\d+)", f.stem).group(1)) == number), None)
        if match: index.append({"page": number, "reason": reason, "file": match.relative_to(ROOT).as_posix()})
    design = {}
    try: design = json.loads((ROOT / "book.design.yaml").read_text(encoding="utf-8"))
    except (OSError, ValueError): pass
    manifest = {"created": stamp, "label": label, "theme": design.get("theme"), "total_pages": total, "pages": index}
    (folder / "proof.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compare_sheet(folder, index)
    latest = PROOFS / "latest.json"
    latest.write_text(json.dumps({"folder": folder.relative_to(ROOT).as_posix(), **manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest, folder


def compare_sheet(folder, pages):
    """proofs/<run>/compare.html: this proof's pages beside the reference-book samples in design/references/."""
    refs = sorted(p for p in (ROOT / "design/references").rglob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))         if (ROOT / "design/references").is_dir() else []
    up = "../../"
    def fig(src, label): return f'<figure><img src="{src}" loading="lazy"><figcaption>{label}</figcaption></figure>'
    proof_cards = "".join(fig(up + p["file"], f"p.{p['page']} · {p['reason']}") for p in pages)
    ref_cards = "".join(fig(up + r.relative_to(ROOT).as_posix(), r.parent.name + " / " + r.stem) for r in refs) or "<p>No reference samples yet (bookorder delegate design-refs).</p>"
    html = ("<!doctype html><meta charset=utf-8><title>Proof vs references</title><style>body{font:14px system-ui;margin:20px;background:#ecebe8}"
            "section{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin-bottom:28px}"
            "figure{margin:0;background:#fff;padding:8px;box-shadow:0 1px 3px #0002}img{width:100%;display:block}</style>"
            f"<h2>Proof</h2><section>{proof_cards}</section><h2>Reference books</h2><section>{ref_cards}</section>")
    (folder / "compare.html").write_text(html, encoding="utf-8")


def summary(manifest, folder):
    lines = [f"PROOF {folder.relative_to(ROOT).as_posix()} — theme {manifest.get('theme')}, {manifest.get('total_pages') or '?'} pages in the book"]
    for item in manifest["pages"]: lines.append(f"  p.{item['page']:>4}  {item['reason']:<38} {item['file']}")
    lines.append(f"Open these PNGs and look at them before describing the design to the user. Side by side with the reference books: "
                 f"{folder.relative_to(ROOT).as_posix()}/compare.html. Full PDF: publish/book.pdf")
    return "\n".join(lines)

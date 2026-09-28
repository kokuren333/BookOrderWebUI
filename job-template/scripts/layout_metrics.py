"""Page-level layout metrics measured from the typeset book (reports/layout-metrics.json).

The Typst renderer leaves invisible marks in the book (templates/design/layout-marks.typ and marks emitted by
renderers/typst.py). `typst eval` reads the page position of every paragraph and element back
(templates/design/layout-probe.typ); this module turns those positions into pages, spreads and chapter metrics.
Only the bundled Typst is needed at runtime.
"""
from datetime import datetime, timezone
import json
import re
from pathlib import Path

from common import ROOT, run, tool

SCHEMA = "bookorder/layout-metrics@1"
REPORT = ROOT / "reports/layout-metrics.json"

# Component classes (schemas/components.json) grouped by what they are on the page.
CALLOUTS = {"key-point", "note", "tip", "warning", "definition", "example", "exercise", "checklist",
            "sidebar", "step-by-step", "glossary-term", "counterpoint"}
COMPONENT_KIND = {**{name: "callout" for name in CALLOUTS}, "summary": "summary", "case-study": "case-study",
                  "pull-quote": "pull-quote", "quote": "quote", "lead": "lead",
                  "chapter-opener": "opener", "section-opener": "opener", "code-listing": "code", "terminal-session": "code"}
# Figure-like components wrap a real figure/table, which is counted itself.
WRAPPERS = {"figure", "full-width-figure", "table", "comparison", "timeline"}

# What interrupts running prose on a page (the pacing gate). Deliberately closed: a heading, a list, a code
# block, a display equation, a plain block quote, a lead paragraph, white space or a rule does NOT count.
PAUSE = {"figure", "table", "callout", "pull-quote", "case-study", "summary", "opener"}
# A pause must take real space on the page (a thumbnail or a one-line box does not rest the eye).
MIN_PAUSE_LINES = 3
# Page area that is not running prose: the editorial devices, plus code, equations and quotes. Headings and
# lists are text; chapter-opener space is structural and reported separately as opener_share.
NONPROSE = (PAUSE - {"opener"}) | {"code", "equation", "quote", "lead"}
VISUAL = {"figure", "table"}
ELEMENT_KINDS = ("figure", "table", "equation", "callout", "summary", "case-study", "pull-quote", "quote", "code", "list", "lead")
TEXT_KINDS = {"prose", "heading", "list"}

PAPER_MM = {"A5": (148, 210), "A4": (210, 297), "B5": (176, 250), "B6": (125, 176), "Letter": (215.9, 279.4)}
UNIT_PT = {"pt": 1.0, "mm": 72 / 25.4, "cm": 72 / 2.54, "in": 72.0}


def length_pt(value, default):
    match = re.fullmatch(r"\s*([0-9.]+)\s*(pt|mm|cm|in)\s*", str(value or ""))
    return float(match.group(1)) * UNIT_PT[match.group(2)] if match else default


def geometry(tokens):
    page = tokens.get("page", {}); margin = page.get("margin", {})
    layout_page = (tokens.get("layout_spec") or {}).get("page") or {}
    if layout_page.get("width_mm") and layout_page.get("height_mm"):  # LayoutSpec is the geometry authority (B6, custom)
        width, height = (float(layout_page[k]) * UNIT_PT["mm"] for k in ("width_mm", "height_mm"))
    else:
        width, height = (x * UNIT_PT["mm"] for x in PAPER_MM.get(page.get("size", "A5"), PAPER_MM["A5"]))
        if page.get("orientation") == "landscape": width, height = height, width
    body = tokens.get("typography", {}).get("body", {})
    top = length_pt(margin.get("top"), 56.0); bottom = length_pt(margin.get("bottom"), 56.0)
    inner = length_pt(margin.get("inner"), 56.0); outer = length_pt(margin.get("outer"), 48.0)
    font = length_pt(body.get("size"), 10.0)
    layout_body = (tokens.get("layout_spec") or {}).get("body") or {}
    columns = int(layout_body.get("columns", 1))
    gutter = float(layout_body.get("gutter_mm", 0)) * UNIT_PT["mm"] if columns > 1 else 0.0
    body_width = width - inner - outer
    return {"size": page.get("size", "A5"), "width_pt": round(width, 2), "height_pt": round(height, 2),
            "body_top_pt": round(top, 2), "body_bottom_pt": round(height - bottom, 2), "body_width_pt": round(width - inner - outer, 2),
            "margin_inner_pt": round(inner, 2), "margin_outer_pt": round(outer, 2),
            "columns": columns, "gutter_pt": round(gutter, 2),
            "column_width_pt": round((body_width - gutter * (columns - 1)) / columns, 2),
            "body_font_pt": font, "line_pitch_pt": round(font * float(body.get("line_height", 1.7)), 2)}


def column_of(point, geo):
    if geo["columns"] == 1 or point.get("x") is None: return 1
    left = geo["margin_inner_pt"] if point["page"] % 2 else geo["margin_outer_pt"]
    pitch = geo["column_width_pt"] + geo["gutter_pt"]
    return max(1, min(geo["columns"], 1 + int(max(0, point["x"] - left + 0.2) / pitch)))


def probe(source=None, root=None):
    """Positions of every paragraph and element in the typeset book, via `typst eval`. The probe module must sit
    at <root>/.build/layout-probe.typ (the renderer copies it there)."""
    root = Path(root or ROOT); source = Path(source or root / ".build/book.typ")
    output = run([tool("typst"), "eval", "--in", source, "--root", root,
                  '{ import "/.build/layout-probe.typ": collect; collect() }'])
    return json.loads(output)


# ---------------------------------------------------------------- element reconstruction

def _key(item):
    return (item["page"], item["y"])


def _pair(starts, ends, geo):
    """Match each start with its end mark (same element type, nesting-aware, in document order)."""
    events = [(_key(s), 1, i) for i, s in enumerate(starts)] + [(_key(e), 0, j) for j, e in enumerate(ends)]
    events.sort()
    stack, pairs = [], {}
    for _, is_start, index in events:
        if is_start: stack.append(index)
        elif stack: pairs[stack.pop()] = ends[index]
    result = []
    for i, start in enumerate(starts):
        end = pairs.get(i, start)
        page, y = end["page"], end["y"]
        # An end mark pushed to the top of the next page belongs to the bottom of the previous one.
        if page > start["page"] and y <= geo["body_top_pt"] + 2: page, y = page - 1, geo["body_bottom_pt"]
        result.append({**start, "end_page": page, "end_y": y})
    return result


def elements(data, geo):
    ends = {}
    for end in data.get("ends", []): ends.setdefault(end["el"], []).append(end)
    items = []
    figures = _pair(data.get("figures", []), ends.get("figure", []), geo)
    for figure in figures:
        kind = {"image": "figure", "table": "table", "code": "code"}.get(figure.get("kind"), "figure")
        items.append({**figure, "kind": kind, "sub": figure.get("kind")})
    def inside(point, spans):
        return any(_key(s) <= _key(point) <= (s["end_page"], s["end_y"]) for s in spans)
    for table in _pair(data.get("tables", []), ends.get("table", []), geo):
        if not inside(table, figures): items.append({**table, "kind": "table", "sub": "bare"})
    for name, kind in (("equations", "equation"), ("quotes", "quote"), ("code", "code")):
        for item in _pair(data.get(name, []), ends.get(kind, []), geo):
            if kind == "code" and inside(item, figures): continue
            items.append({**item, "kind": kind, "sub": kind})
    list_ends = ends.get("list", []) + ends.get("enum", []) + ends.get("terms", [])
    for item in _pair(data.get("lists", []), sorted(list_ends, key=_key), geo): items.append({**item, "kind": "list", "sub": "list"})
    marks = data.get("marks", [])
    begins = [m for m in marks if m.get("el") == "begin"]
    finishes = [m for m in marks if m.get("el") == "end"]
    for component in _pair(begins, finishes, geo):
        sub = component.get("sub", "")
        if sub in WRAPPERS: continue
        items.append({**component, "kind": COMPONENT_KIND.get(sub, "callout"), "sub": sub})
    for outline in data.get("outlines", []): items.append({**outline, "kind": "outline", "sub": "toc", "point": True})
    # Printed geometry of each figure (renderers/typst.py, from reports/figure-check.json), joined by figure id.
    placed = {m.get("id"): m for m in marks if m.get("el") == "figure-geometry"}
    for item in items:
        geometry = placed.get(item.get("label"))
        if geometry:
            item["geometry"] = {"placement": geometry.get("placement"), "width_mm": _number(geometry.get("width_mm")),
                                "span": geometry.get("span", "1"), "region": geometry.get("region"),
                                "min_text_pt": _number(geometry.get("min_text_pt")), "legibility": geometry.get("status") or None}
        item["column"] = column_of(item, geo)
    return sorted(items, key=_key)


def _number(value):
    try: return float(value)
    except (TypeError, ValueError): return None


# ---------------------------------------------------------------- page segmentation

def segment(data, items, geo, total_pages):
    """Assign every vertical stretch of the text block to the element occupying it; returns per-page areas (pt)
    and prose characters per page. Paragraphs split across pages share their characters by area."""
    top, bottom = geo["body_top_pt"], geo["body_bottom_pt"]
    events = []  # (page, y, order, type, payload)
    for item in items:
        if item.get("point"):  # no end mark: occupies the page until the next boundary
            events.append((item["page"], item["y"], 1, "point", item)); continue
        events.append((item["page"], item["y"], 1, "start", item))
        events.append((item["end_page"], item["end_y"], 3 if _key(item) == (item["end_page"], item["end_y"]) else 0, "end", item))
    for index, par in enumerate(data.get("pars", [])): events.append((par["page"], par["y"], 2, "par", {**par, "index": index}))
    for heading in data.get("headings", []):
        events.append((heading["page"], heading["y"], 2, "heading", heading))
    for mark in data.get("marks", []):
        if mark.get("el") in ("chapter", "back-matter", "doc-end"): events.append((mark["page"], mark["y"], 0, mark["el"], mark))
    events.sort(key=lambda e: (e[0], e[1], e[2]))
    areas = {page: {} for page in range(1, total_pages + 1)}
    par_area = {}
    stack, current, current_par, in_back = [], "blank", None, False
    trailing = False  # current kind is only the spacing below a block that just ended

    def add(page, kind, amount, par):
        if amount <= 0 or page not in areas: return
        areas[page][kind] = areas[page].get(kind, 0.0) + amount
        if par is not None and kind == "prose": par_area.setdefault(par["index"], {}).setdefault(page, 0.0); par_area[par["index"]][page] += amount

    def fill(from_page, from_y, to_page, to_y, next_type):
        from_y, to_y = min(max(from_y, top), bottom), min(max(to_y, top), bottom)
        kind = stack[-1]["kind"] if stack else current
        par = current_par if not stack else None
        if trailing and not stack:
            # Spacing below a block belongs to it, but only about a line of it; it never continues onto the next page.
            gap = (to_y if to_page == from_page else bottom) - from_y
            spacing = min(gap, 1.5 * geo["line_pitch_pt"])
            add(from_page, kind, spacing, par); add(from_page, "blank", gap - spacing, None); return
        if to_page == from_page:
            add(from_page, kind, to_y - from_y, par); return
        tail = bottom - from_y
        if kind == "prose" and par is not None and next_type in ("chapter", "back-matter", "doc-end"):
            # The last paragraph before a page break: estimate its height instead of claiming the empty rest.
            lines = -(-par["chars"] // max(1, int(geo["body_width_pt"] / geo["body_font_pt"])))
            tail = min(tail, lines * geo["line_pitch_pt"])
            add(from_page, kind, tail, par); return
        if next_type in ("chapter", "back-matter", "doc-end"):
            add(from_page, kind, min(tail, 2 * geo["line_pitch_pt"]) if kind in TEXT_KINDS else tail, par); return
        add(from_page, kind, tail, par)
        for page in range(from_page + 1, to_page): add(page, kind, bottom - top, par)
        add(to_page, kind, to_y - top, par)

    previous = None
    for page, y, _, kind, payload in events:
        if previous is not None: fill(previous[0], previous[1], page, y, kind)
        previous = (page, y)
        if in_back: continue  # bibliography and other back matter are not measured as prose or devices
        trailing = False
        if kind == "start": stack.append(payload)
        elif kind == "point":
            if not stack: current, current_par = payload["kind"], None
        elif kind == "end":
            if payload in stack: stack.remove(payload)
            if not stack: current, current_par, trailing = payload["kind"], None, True  # spacing below a block belongs to it
        elif kind == "par":
            if not stack: current, current_par = "prose", payload
        elif kind == "heading":
            if not stack: current, current_par = ("opener" if payload["level"] == 1 and payload["outlined"] else "heading"), None
        elif kind == "chapter": current, current_par = "opener", None
        elif kind in ("back-matter", "doc-end"): current, current_par, in_back, stack = "back", None, True, []
    if previous is not None and not in_back: fill(previous[0], previous[1], total_pages, bottom, "doc-end")
    chars = {page: 0.0 for page in areas}
    for index, par in enumerate(data.get("pars", [])):
        spread = par_area.get(index)
        if not spread: continue
        total = sum(spread.values())
        for page, amount in spread.items(): chars[page] += par["chars"] * amount / total
    return areas, chars


# ---------------------------------------------------------------- metrics

def _share(area, kinds=NONPROSE):
    """Share of the used text block taken by `kinds`; opener space counts only when it is being measured."""
    excluded = {"blank", "back", "outline"} | (set() if "opener" in kinds else {"opener"})
    used = sum(v for k, v in area.items() if k not in excluded)
    part = sum(v for k, v in area.items() if k in kinds)
    return round(part / used, 3) if used else 0.0


def _runs(pages, flags):
    """Maximal runs of consecutive pages whose flag is set."""
    runs, current = [], []
    for page in pages:
        if flags.get(page) and current and page == current[-1] + 1: current.append(page)
        else:
            if current: runs.append(current)
            current = [page] if flags.get(page) else []
    if current: runs.append(current)
    return [{"start": r[0], "end": r[-1], "length": len(r)} for r in runs]


def compute(data, tokens, outline_chapters=None):
    geo = geometry(tokens)
    items = elements(data, geo)
    marks = data.get("marks", [])
    every = [p["page"] for p in data.get("pars", [])] + [i.get("end_page", i["page"]) for i in items] + [m["page"] for m in marks] + [h["page"] for h in data.get("headings", [])]
    total_pages = max(every) if every else 0
    folio = {}
    for point in sorted(data.get("pars", []) + data.get("headings", []) + items + marks, key=_key):
        folio.setdefault(point["page"], point.get("folio"))
    areas, chars = segment(data, items, geo, total_pages)

    chapter_marks = [m for m in marks if m.get("el") == "chapter"]
    back = next((m for m in marks if m.get("el") == "back-matter"), None)
    main_start = chapter_marks[0]["page"] if chapter_marks else 1
    back_page = back["page"] if back else total_pages + 1
    # The bibliography page belongs to the main matter when main-matter prose ends on it.
    back_start = back_page + 1 if back and chars.get(back_page, 0) >= 1 else back_page
    titles = {c.get("id"): c.get("title") for c in (outline_chapters or [])}
    headings = data.get("headings", [])

    chapters = []
    for index, mark in enumerate(chapter_marks):
        first = mark["page"]
        last = (chapter_marks[index + 1]["page"] - 1) if index + 1 < len(chapter_marks) else back_start - 1
        last = max(first, min(last, total_pages))
        heading = next((h for h in headings if h["level"] == 1 and h["page"] == first and h["outlined"]), None)
        chapters.append({"id": mark.get("id") or None, "number": mark.get("number", ""), "label": mark.get("label", ""),
                         "title": titles.get(mark.get("id")) or (heading or {}).get("text", ""), "pages": [first, last]})

    def chapter_of(page):
        return next((c["id"] or c["label"] for c in chapters if c["pages"][0] <= page <= c["pages"][1]), None)

    def region(page):
        if page < main_start: return "front"
        if page >= back_start: return "back"
        return "main"

    pages = []
    pause_flags, text_only = {}, {}
    for page in range(1, total_pages + 1):
        area = areas.get(page, {})
        on_page = [i for i in items if i["page"] <= page <= i.get("end_page", i["page"])]
        opener = any(c["pages"][0] == page for c in chapters)
        pause_area = sum(v for k, v in area.items() if k in PAUSE - {"opener"})
        if geo["columns"] > 1:
            # The old vertical segmenter cannot reconstruct simultaneous columns. Measure pauses from
            # their own physical extents; use page-level results while exposing approximate area shares.
            pause_area = sum(max(0, min(geo["body_bottom_pt"], i.get("end_y", i["y"]) if i.get("end_page", i["page"]) == page
                                        else geo["body_bottom_pt"]) -
                                 max(geo["body_top_pt"], i["y"] if i["page"] == page else geo["body_top_pt"]))
                             for i in on_page if i["kind"] in PAUSE - {"opener"})
        pause = opener or pause_area >= MIN_PAUSE_LINES * geo["line_pitch_pt"]
        used = sum(v for k, v in area.items() if k not in ("blank",))
        is_text_only = region(page) == "main" and not pause and used > 0
        pause_flags[page] = pause; text_only[page] = is_text_only
        column_data = [{"index": index,
                        "paragraphs": sum(1 for p in data.get("pars", []) if p["page"] == page and column_of(p, geo) == index),
                        "elements": sum(1 for i in on_page if i["column"] == index and i["kind"] != "outline")}
                       for index in range(1, geo["columns"] + 1)]
        pages.append({"page": page, "folio": folio.get(page), "region": region(page), "chapter": chapter_of(page),
                      "columns": column_data, "area_accuracy": "approximate" if geo["columns"] > 1 else "measured",
                      "prose_chars": round(chars.get(page, 0)), "pause": pause, "text_only": is_text_only,
                      "pause_area_pt": round(pause_area, 1), "opener": opener,
                      "headings": [{"level": h["level"], "text": h["text"][:60], "x": round(h.get("x", 0), 1), "y": round(h.get("y", 0), 1), **({"label": h["label"]} if h.get("label") else {})}
                                   for h in headings if h["page"] == page and h["level"] <= 3 and h["outlined"]],
                      "nonprose_share": _share(area),
                      "areas_pt": {k: round(v, 1) for k, v in sorted(area.items())},
                      "elements": [{"kind": i["kind"], "sub": i.get("sub"), "x": round(i.get("x", 0), 1), "y": round(i["y"], 1),
                                    "end_y": round(i.get("end_y", i["y"]), 1) if i.get("end_page", i["page"]) == page else None,
                                    "column": i["column"],
                                    **({"continued": True} if i["page"] < page else {}),
                                    **({"label": i["label"]} if i.get("label") else {}),
                                    **({"geometry": i["geometry"]} if i.get("geometry") else {})} for i in on_page if i["kind"] != "outline"]})

    main_pages = [p["page"] for p in pages if p["region"] == "main"]
    runs = [dict(r, chapter=chapter_of(r["start"]), folios=[folio.get(r["start"]), folio.get(r["end"])]) for r in _runs(main_pages, text_only)]
    runs.sort(key=lambda r: (-r["length"], r["start"]))

    def count(kind, first, last):
        return sum(1 for i in items if i["kind"] == kind and first <= i["page"] <= last)

    for chapter in chapters:
        first, last = chapter["pages"]
        span = [p for p in pages if first <= p["page"] <= last]
        prose = sum(p["prose_chars"] for p in span)
        area = {}
        for p in span:
            for k, v in p["areas_pt"].items(): area[k] = area.get(k, 0) + v
        kinds = {k: count(k, first, last) for k in ELEMENT_KINDS}
        visuals = kinds["figure"] + kinds["table"]
        chapter_runs = [r for r in runs if first <= r["start"] <= last]
        chapter.update({
            "page_count": last - first + 1, "folios": [folio.get(first), folio.get(last)],
            "prose_chars": prose, "chars_per_page": round(prose / (last - first + 1)),
            "headings": {f"h{level}": sum(1 for h in headings if h["level"] == level and first <= h["page"] <= last) for level in (2, 3, 4)},
            "elements": kinds, "visuals": visuals, "callouts": kinds["callout"],
            "visuals_per_10k_chars": round(visuals * 10000 / prose, 2) if prose else None,
            "nonprose_share": _share(area), "opener_share": _share(area, {"opener"}),
            "text_only_pages": sum(1 for p in span if p["text_only"]),
            "max_text_only_run": max((r["length"] for r in chapter_runs), default=0),
        })

    spreads = []
    for left in range(0, total_pages + 1, 2):
        members = [p for p in (left, left + 1) if 1 <= p <= total_pages]
        span = [pages[p - 1] for p in members]
        area = {}
        for p in span:
            for k, v in p["areas_pt"].items(): area[k] = area.get(k, 0) + v
        pause_elements = {(e["kind"], e["y"], p["page"]) for p in span for e in p["elements"] if e["kind"] in PAUSE and not e.get("continued")}
        spreads.append({"pages": members, "folios": [folio.get(p) for p in members], "region": "/".join(sorted({p["region"] for p in span})),
                        "chapter": span[-1]["chapter"], "pause_elements": len(pause_elements),
                        "visuals": sum(1 for p in span for e in p["elements"] if e["kind"] in VISUAL and not e.get("continued")),
                        "text_only": all(p["text_only"] for p in span), "nonprose_share": _share(area)})

    prose_total = sum(p["prose_chars"] for p in pages if p["region"] == "main")
    main_area = {}
    for p in pages:
        if p["region"] == "main":
            for k, v in p["areas_pt"].items(): main_area[k] = main_area.get(k, 0) + v
    counts = {k: sum(1 for i in items if i["kind"] == k and region(i["page"]) == "main") for k in ELEMENT_KINDS}
    longest = runs[0] if runs else None
    totals = {
        "pages": total_pages, "front_matter_pages": sum(1 for p in pages if p["region"] == "front"),
        "main_pages": len(main_pages), "back_matter_pages": sum(1 for p in pages if p["region"] == "back"),
        "chapters": len(chapters), "prose_chars": prose_total,
        "chars_per_main_page": round(prose_total / len(main_pages)) if main_pages else 0,
        "nonprose_share": _share(main_area), "elements": counts,
        "visuals": counts["figure"] + counts["table"], "callouts": counts["callout"],
        "visuals_per_10k_chars": round((counts["figure"] + counts["table"]) * 10000 / prose_total, 2) if prose_total else None,
        "text_only_pages": sum(1 for p in pages if p["text_only"]),
        "max_text_only_run": longest["length"] if longest else 0,
        "text_only_runs_at_least": {str(n): sum(1 for r in runs if r["length"] >= n) for n in (3, 4, 5, 8)},
        "text_only_spreads": sum(1 for s in spreads if s["text_only"] and s["region"] == "main"),
        "figures_below_min_text": sum(1 for i in items if (i.get("geometry") or {}).get("legibility") == "fail"),
        "min_figure_text_pt": min((i["geometry"]["min_text_pt"] for i in items if (i.get("geometry") or {}).get("min_text_pt")), default=None),
    }
    definitions = {"pause_kinds": sorted(PAUSE), "min_pause_area_pt": round(MIN_PAUSE_LINES * geo["line_pitch_pt"], 1),
                   "not_pauses": ["heading", "list", "code", "equation", "quote", "lead", "blank", "rule"]}
    return {"schema": SCHEMA, "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "method": "typst-eval",
            "area_accuracy": "approximate" if geo["columns"] > 1 else "measured",
            "definitions": definitions, "page_geometry": geo, "totals": totals,
            "max_text_only_run": longest, "text_only_runs": runs, "chapters": chapters, "spreads": spreads, "pages": pages}


def summary(metrics):
    t = metrics["totals"]; run_ = metrics.get("max_text_only_run")
    where = f" (pp. {run_['start']}–{run_['end']})" if run_ else ""
    return (f"layout: {t['pages']} pages, {t['chars_per_main_page']} prose chars/main page, non-prose share {t['nonprose_share']:.0%}, "
            f"{t['visuals']} visuals, {t['callouts']} callouts, max text-only run {t['max_text_only_run']}{where}")


def measure(tokens, source=None, outline_chapters=None):
    metrics = compute(probe(source), tokens, outline_chapters)
    metrics["source"] = "publish/book.pdf"
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metrics


def main():
    """`bookorder layout`: re-measure the last PDF build without rebuilding."""
    tokens = json.loads((ROOT / ".build/design-tokens.json").read_text(encoding="utf-8"))
    try:
        from planning import load_outline
        outline = load_outline()
    except Exception: outline = None
    metrics = measure(tokens, outline_chapters=outline)
    print(summary(metrics))
    return metrics

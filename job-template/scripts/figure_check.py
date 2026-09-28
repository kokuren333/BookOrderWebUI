"""Printed text size of every figure (reports/figure-check.json).

For SVG figures the text is read from the file itself: font sizes (attributes, CSS, inherited, transformed) are
converted to points at the size the figure is placed in the book. Raster charts carry a render record
(`<image>.render.json`, written by scripts/chartkit.py) and are checked from the size they were drawn at.
A figure whose smallest printed text is below `min_label_pt` fails; the audit turns failures into issues.
"""
import json
import re
import xml.etree.ElementTree as ET

from common import ROOT, walk
from figure_spec import PT_PER_MM, figure_tokens, frames, length_mm, planned_geometry, resolve

SCHEMA = "bookorder/figure-check@1"
REPORT = ROOT / "reports/figure-check.json"
RENDER_SUFFIX = ".render.json"
UNIT_PT = {"pt": 1.0, "px": 0.75, "": 0.75, "mm": PT_PER_MM, "cm": PT_PER_MM * 10, "in": 72.0, "pc": 12.0}
TEXT_TAGS = {"text", "tspan", "textPath"}


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _length_pt(value):
    match = re.fullmatch(r"\s*([-0-9.eE]+)\s*(pt|px|mm|cm|in|pc)?\s*", str(value or ""))
    return float(match.group(1)) * UNIT_PT[match.group(2) or ""] if match else None


def _style(element):
    result = {}
    for part in (element.get("style") or "").split(";"):
        if ":" in part:
            key, value = part.split(":", 1); result[key.strip()] = value.strip()
    return result


def _font_size(element, inherited):
    """Font size in SVG user units (px), following CSS: px/unitless = user units, pt = 4/3 px, em/% relative."""
    style = _style(element)
    raw = style.get("font-size") or element.get("font-size")
    if raw is None and "font" in style:
        match = re.search(r"([0-9.]+)(px|pt|em|%)?\s", style["font"] + " ")
        raw = match.group(0).strip() if match else None
    if raw is None: return inherited
    match = re.fullmatch(r"\s*([0-9.]+)\s*(px|pt|em|%|mm)?\s*", raw)
    if not match: return inherited
    value, unit = float(match.group(1)), match.group(2) or "px"
    return {"px": value, "pt": value * 4 / 3, "mm": value * 96 / 25.4, "em": value * (inherited or 16), "%": value / 100 * (inherited or 16)}[unit]


def _transform_scale(value):
    """Uniform scale of an SVG transform list (square root of the linear part's determinant)."""
    if not value: return 1.0
    total = 1.0
    for name, args in re.findall(r"(matrix|scale|rotate|translate|skewX|skewY)\s*\(([^)]*)\)", value):
        numbers = [float(x) for x in re.findall(r"[-0-9.eE]+", args)]
        if name == "scale" and numbers: total *= abs(numbers[0] * (numbers[1] if len(numbers) > 1 else numbers[0])) ** 0.5
        elif name == "matrix" and len(numbers) == 6: total *= abs(numbers[0] * numbers[3] - numbers[1] * numbers[2]) ** 0.5
    return total


def inspect_svg(path):
    """Natural size (pt), viewBox, and every text run / stroke in user units with its transform scale."""
    root = ET.parse(path).getroot()
    view = [float(x) for x in re.findall(r"[-0-9.eE]+", root.get("viewBox") or "")]
    width_pt, height_pt = _length_pt(root.get("width")), _length_pt(root.get("height"))
    if len(view) != 4:
        if width_pt is None: return {"error": "SVG has neither viewBox nor absolute width"}
        view = [0, 0, width_pt / 0.75, (height_pt or width_pt) / 0.75]
    if width_pt is None or str(root.get("width", "")).endswith("%"):
        width_pt = view[2] * 0.75
        height_pt = view[3] * 0.75
    user_pt = width_pt / view[2]  # points per user unit at natural size
    texts, strokes, glyph_paths = [], [], False

    def visit(element, size, scale):
        tag = _local(element.tag)
        scale *= _transform_scale(element.get("transform"))
        size = _font_size(element, size)
        style = _style(element)
        if tag in TEXT_TAGS:
            own = (element.text or "").strip()
            if own: texts.append({"text": own[:40], "user_size": (size or 16) * scale})
        stroke = style.get("stroke", element.get("stroke"))
        width = style.get("stroke-width", element.get("stroke-width"))
        if stroke and stroke != "none" and tag not in ("svg", "g", "marker") and width is not None:
            match = re.fullmatch(r"\s*([0-9.eE]+)\s*(px|pt)?\s*", str(width))
            if match: strokes.append(float(match.group(1)) * (4 / 3 if match.group(2) == "pt" else 1) * scale)
        if tag == "defs" and any(_local(child.tag) == "path" and "id" in child.attrib and re.search(r"-[0-9a-f]{2,}$", child.get("id", "")) for child in element):
            nonlocal glyph_paths; glyph_paths = True
        for child in element:
            if _local(child.tag) in ("title", "desc", "metadata", "style"): continue
            if _local(child.tag) == "defs" and tag != "svg": continue
            visit(child, size, scale)
            if tag in TEXT_TAGS and child.tail and child.tail.strip():
                texts.append({"text": child.tail.strip()[:40], "user_size": (size or 16) * scale})

    visit(root, 16.0, 1.0)
    return {"natural_width_pt": width_pt, "natural_height_pt": height_pt, "view_width": view[2], "user_pt": user_pt,
            "texts": texts, "strokes": strokes, "text_as_paths": glyph_paths and not texts}


def render_record(path):
    record = path.with_name(path.name + RENDER_SUFFIX)
    return json.loads(record.read_text(encoding="utf-8")) if record.is_file() else None


def check_figure(identifier, path, geometry, tokens, ft=None):
    """Printed sizes for one figure placed in the book."""
    ft = ft or figure_tokens(tokens); column = frames(tokens)["column"]["width_mm"]
    entry = {"id": identifier, "path": path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path),
             "placement": geometry["placement"], "span": geometry.get("span", 1), "region": geometry.get("region"),
             "planned_width_mm": geometry["width_mm"] if geometry.get("declared") else None,
             "warnings": list(geometry.get("warnings", []))}
    if not path.is_file():
        return entry | {"method": "missing", "status": "unverified"}
    record = render_record(path)
    if path.suffix.lower() == ".svg":
        facts = inspect_svg(path)
        if "error" in facts: return entry | {"method": "svg", "status": "unverified", "warnings": entry["warnings"] + [facts["error"]]}
        natural_mm = facts["natural_width_pt"] / PT_PER_MM
        # Declared geometry sets the width explicitly; otherwise Typst shows the natural size, capped at the column.
        placed_mm = geometry["width_mm"] if geometry.get("declared") else min(natural_mm, geometry["width_mm"])
        factor = facts["user_pt"] * placed_mm / natural_mm
        sizes = [(t["user_size"] * factor, t["text"]) for t in facts["texts"]]
        placed_height = (facts["natural_height_pt"] or 0) / PT_PER_MM * placed_mm / natural_mm
        limit = frames(tokens)[geometry.get("region", geometry["placement"])]["max_height_mm"]
        if placed_height > limit + 0.5:
            entry["warnings"].append(f"prints {placed_height:.0f} mm tall, more than the {geometry['placement']} frame allows ({limit:g} mm); "
                                     "split the figure or place it full-page")
        entry.update(method="svg", natural_width_mm=round(natural_mm, 1), placed_width_mm=round(placed_mm, 1), placed_height_mm=round(placed_height, 1),
                     scale=round(placed_mm / natural_mm, 3), text_runs=len(sizes))
        if facts["strokes"]: entry["min_stroke_pt"] = round(min(facts["strokes"]) * factor, 3)
        if sizes:
            smallest = min(sizes)
            entry.update(min_text_pt=round(smallest[0], 2), max_text_pt=round(max(sizes)[0], 2),
                         below_min=[{"text": text, "pt": round(pt, 2)} for pt, text in sorted(sizes) if pt < ft["min_label_pt"] - 0.01][:12])
        elif facts["text_as_paths"] and not record:
            return entry | {"status": "unverified", "warnings": entry["warnings"] + ["text is drawn as outlines; render with chartkit (svg.fonttype none) or add a render record"]}
    if record and "min_text_pt" not in entry:
        drawn = float(record.get("width_mm") or 0)
        placed_mm = geometry["width_mm"] if geometry.get("declared") else min(drawn or column, geometry["width_mm"])
        scale = placed_mm / drawn if drawn else 1.0
        entry.update(method="render-record", renderer=record.get("renderer"), drawn_width_mm=drawn, placed_width_mm=round(placed_mm, 1),
                     scale=round(scale, 3), min_text_pt=round(float(record.get("min_text_pt", 0)) * scale, 2))
        entry["below_min"] = [] if entry["min_text_pt"] >= ft["min_label_pt"] - 0.01 else [{"text": "(smallest text in render record)", "pt": entry["min_text_pt"]}]
    if "min_text_pt" not in entry:
        if "text_runs" in entry: return entry | {"status": "ok", "note": "no text in figure"}
        return entry | {"method": entry.get("method", "raster"), "status": "unverified"}
    status = "fail" if entry["below_min"] else "ok"
    if entry.get("scale") and entry["scale"] < 0.98 and not geometry.get("declared"):
        entry["warnings"].append(f"drawn {entry.get('natural_width_mm', entry.get('drawn_width_mm'))} mm wide and shrunk to {entry['placed_width_mm']} mm; draw it at its printed size")
    return entry | {"status": status}


def manuscript_figures(records):
    """(figure id, image path, chapter) for every figure in the manuscript."""
    found = []
    for record in records:
        for node in walk(record["ast"]["blocks"]):
            if node["t"] != "Figure": continue
            for inner in walk(node["c"][2]):
                if inner["t"] == "Image":
                    found.append((node["c"][0][0], inner["c"][2][0], record["id"])); break
    return found


def check(tokens, records=None):
    """Check every manuscript figure; writes reports/figure-check.json."""
    if records is None:
        from manuscript import analyze_all
        records = [r for r in analyze_all().values() if r]
    ft = figure_tokens(tokens); planned = planned_geometry(); kinds = {}
    try:
        from assets import assets
        kinds = {str(a.get("id")): a.get("type") for a in assets()}
    except Exception: pass
    figures = []
    for identifier, source, chapter in manuscript_figures(records):
        geometry = resolve(planned.get(identifier), tokens, kinds.get(identifier))
        geometry["declared"] = identifier in planned
        path = (ROOT / source.lstrip("/")).resolve()
        figures.append(check_figure(identifier, path, geometry, tokens, ft) | {"chapter": chapter, "type": kinds.get(identifier)})
    summary = {"figures": len(figures), "ok": sum(f["status"] == "ok" for f in figures),
               "fail": sum(f["status"] == "fail" for f in figures), "unverified": sum(f["status"] == "unverified" for f in figures),
               "min_text_pt": min((f["min_text_pt"] for f in figures if "min_text_pt" in f), default=None)}
    report = {"schema": SCHEMA, "tokens": {k: ft[k] for k in ("min_label_pt", "preferred_label_pt", "axis_label_pt", "tick_label_pt",
              "annotation_pt", "legend_pt", "stroke_width_pt", "node_padding_mm")} | {"sources": ft["sources"]},
              "frames": frames(tokens), "summary": summary, "figures": figures}
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report

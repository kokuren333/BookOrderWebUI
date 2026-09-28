"""Print-size figure specification shared by every figure renderer (Diagram IR, charts, hand-made SVG, images).

Figures are specified at their final printed size: a placement on the page (column, full-width, margin,
full-page, spread) resolves to millimetres, and text, strokes and padding are given in points/millimetres as they
will appear in print. Renderers draw at that size, so the book never shrinks a figure after the fact.

Token precedence (later wins): BookOrder provisional defaults → design line_weight → book.design.yaml
`figures.print` → plan/style-bible.yaml `figures.print` (the future Style Bible). `figure_tokens()` records which
sources were applied.
"""
import json
import re

from common import ROOT, yaml_data

SCHEMA = "bookorder/figure-tokens@1"
PT_PER_MM = 72 / 25.4
PLACEMENTS = ("column", "full-width", "margin", "full-page", "spread")

# Provisional print defaults (A5/B5 books, 9–10.5pt body). The Style Bible replaces them; keep the keys stable.
DEFAULTS = {
    "min_label_pt": 6.5,        # nothing printed inside a figure may be smaller
    "preferred_label_pt": 8.0,  # node labels, bar labels, primary annotations
    "axis_label_pt": 7.5,
    "tick_label_pt": 7.0,
    "annotation_pt": 7.0,
    "legend_pt": 7.0,
    "stroke_width_pt": 0.6,     # regular line; hairline/strong derive from it unless set
    "hairline_pt": 0.35,
    "strong_pt": 1.0,
    "min_stroke_pt": 0.25,      # print-safe minimum line
    "node_padding_mm": 2.0,
    "node_gap_mm": 4.0,
    "corner_radius_mm": 1.0,
    "marker_size_pt": 4.0,
    "line_height": 1.25,
}
LINE_WEIGHT = {"thin": 0.45, "regular": 0.6, "bold": 0.9}
DEFAULT_ASPECT = {"diagram": None, "chart": "16:10", "image": "3:2", "screenshot": None}

PAPER_MM = {"A5": (148, 210), "A4": (210, 297), "B5": (176, 250), "Letter": (215.9, 279.4)}
UNIT_MM = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72}
SAFE_EDGE_MM = 5.0
CAPTION_RESERVE_MM = 22.0


def length_mm(value, default=None):
    match = re.fullmatch(r"\s*([0-9.]+)\s*(mm|cm|in|pt)?\s*", str(value)) if value is not None else None
    if not match: return default
    return float(match.group(1)) * UNIT_MM[match.group(2) or "mm"]


def _number(value):
    """YAML files read through Pandoc yield strings; accept numbers written either way."""
    if isinstance(value, bool): return None
    try: return float(value)
    except (TypeError, ValueError): return None


def _style_bible():
    path = ROOT / "plan/style-bible.yaml"
    if not path.is_file(): return {}
    data = yaml_data(path) or {}
    return ((data.get("figures") or {}).get("print") or {}) if isinstance(data, dict) else {}


def figure_tokens(tokens=None):
    """Final-print figure typography, strokes and spacing."""
    tokens = tokens or {}
    figures = tokens.get("figures", {}) if isinstance(tokens, dict) else {}
    result = dict(DEFAULTS); sources = ["bookorder-defaults"]
    if figures.get("line_weight") in LINE_WEIGHT:
        base = LINE_WEIGHT[figures["line_weight"]]
        result.update(stroke_width_pt=base, hairline_pt=round(base * 0.6, 2), strong_pt=round(base * 1.65, 2))
        sources.append("design.figures.line_weight")
    for name, override in (("design.figures.print", figures.get("print") or {}), ("plan/style-bible.yaml", _style_bible())):
        known = {k: _number(v) for k, v in override.items() if k in DEFAULTS and _number(v) is not None}
        if known: result.update(known); sources.append(name)
    style = tokens.get("style") or {}
    if style:
        typ = style["typography"]; lines = style["lines"]; geo = style["geometry"]
        result.update(min_label_pt=max(6.5, float(style["print"]["minimum_text_pt"]), float(typ["minimum_print_pt"])),
                      preferred_label_pt=typ["figure_label"]["size_pt"],
                      axis_label_pt=typ["axis_label"]["size_pt"], tick_label_pt=typ["tick_label"]["size_pt"],
                      annotation_pt=typ["figure_label"]["size_pt"], legend_pt=typ["figure_label"]["size_pt"],
                      stroke_width_pt=lines["normal_pt"], hairline_pt=lines["hairline_pt"],
                      strong_pt=lines["strong_pt"], min_stroke_pt=style["print"]["minimum_line_pt"],
                      node_padding_mm=geo["node_padding_mm"], corner_radius_mm=geo["corner_radius_mm"],
                      line_height=typ["figure_label"]["line_height"])
        sources.append("plan/style-bible.yaml@1")
    for key in ("preferred_label_pt", "axis_label_pt", "tick_label_pt", "annotation_pt", "legend_pt"):
        result[key] = max(result[key], result["min_label_pt"])
    families = ([style["typography"]["figure_label"]["family"]] if style else
                (tokens.get("typography", {}).get("caption", {}) or {}).get("resolved_families") or ["Noto Sans CJK JP", "Noto Sans JP"])
    colors = tokens.get("colors", {})
    return {"schema": SCHEMA, **result, "font_families": families, "monochrome": figures.get("style") == "monochrome",
            "chart_grammar": ((style.get("visual_grammar") or {}).get("chart") or {}),
            "colors": {k: colors.get(k) for k in ("text", "primary", "accent", "muted", "secondary", "surface") if colors.get(k)},
            "sources": sources}


def page_frame(tokens=None):
    page = (tokens or {}).get("page", {}); margin = page.get("margin", {})
    width, height = PAPER_MM.get(page.get("size", "A5"), PAPER_MM["A5"])
    if page.get("orientation") == "landscape": width, height = height, width
    m = {k: length_mm(margin.get(k), d) for k, d in (("top", 20), ("bottom", 20), ("inner", 20), ("outer", 17))}
    return {"page_width_mm": width, "page_height_mm": height, "text_width_mm": round(width - m["inner"] - m["outer"], 2),
            "text_height_mm": round(height - m["top"] - m["bottom"], 2), **{f"margin_{k}_mm": v for k, v in m.items()}}


def frames(tokens=None):
    """Width and maximum height (mm) available to each placement."""
    f = page_frame(tokens); text_w, text_h = f["text_width_mm"], f["text_height_mm"]
    layout = (tokens or {}).get("layout_spec") or {}
    body = layout.get("body") or {}
    columns = int(body.get("columns", 1))
    gutter = float(body.get("gutter_mm", 0)) if columns > 1 else 0.0
    column_w = (text_w - gutter * (columns - 1)) / columns
    reach = max(0.0, min(f["margin_inner_mm"], f["margin_outer_mm"]) - SAFE_EDGE_MM)
    return {
        "column": {"width_mm": round(column_w, 2), "max_height_mm": round(text_h * 0.6, 2)},
        "span-2": {"width_mm": round(2 * column_w + gutter, 2), "max_height_mm": round(text_h * 0.6, 2)},
        # One-column legacy reach extends into both margins. In columns, the parent float
        # spans the body frame, so its true printable width is the body width.
        "full-width": {"width_mm": round(text_w if columns > 1 else text_w + 2 * reach, 2),
                       "max_height_mm": round(text_h * 0.6, 2)},
        "margin": {"width_mm": round(max(0.0, f["margin_outer_mm"] - 4.0), 2), "max_height_mm": 60.0,
                   "note": "sized for the outer margin; rendered in the text column until margin layout exists"},
        "full-page": {"width_mm": text_w, "max_height_mm": round(text_h - CAPTION_RESERVE_MM, 2)},
        "spread": {"width_mm": text_w, "max_height_mm": round(text_h - CAPTION_RESERVE_MM, 2),
                   "note": "two-page spreads are not supported yet; laid out as full-page"},
    }


def _ratio(value):
    match = re.fullmatch(r"\s*([0-9.]+)\s*[:/x]\s*([0-9.]+)\s*", str(value or ""))
    return float(match.group(1)) / float(match.group(2)) if match and float(match.group(2)) else None


def resolve(geometry=None, tokens=None, kind=None):
    """Normalized print geometry: placement, width_mm, height_mm (None = content decides), aspect_ratio."""
    geometry = dict(geometry or {}); warnings = []
    layout = (tokens or {}).get("layout_spec") or {}
    columns = int((layout.get("body") or {}).get("columns", 1))
    category = "table" if kind == "table" else "figure"
    default_span = (layout.get("spans") or {}).get(category, 1)
    placement = geometry.get("placement") or "column"
    if placement not in PLACEMENTS: warnings.append(f"unknown placement {placement!r}; using column"); placement = "column"
    span = geometry.get("span", "full" if placement == "full-width" else default_span)
    if isinstance(span, str) and span.isdigit(): span = int(span)
    if span != "full" and (not isinstance(span, int) or span < 1 or span > columns):
        raise ValueError(f"figure span {span!r} exceeds LayoutSpec body.columns={columns}")
    if columns > 1 and span != 1 and not ((layout.get("regions") or {}).get("full_width") or {}).get("enabled", True):
        raise ValueError("multi-column figure span requires LayoutSpec regions.full_width.enabled")
    if placement == "column": frame_name = ("span-2" if columns > 1 else "full-width") if span == "full" else "span-2" if span == 2 else "column"
    elif placement == "full-width" and columns > 1: frame_name = "span-2"
    else: frame_name = placement
    frame = frames(tokens)[frame_name]
    width = length_mm(geometry.get("width_mm"))
    if width is None: width = frame["width_mm"]
    if width > frame["width_mm"] + 0.01:
        warnings.append(f"width_mm {width:g} exceeds the {frame_name} frame ({frame['width_mm']:g} mm); clamped")
        width = frame["width_mm"]
    aspect = geometry.get("aspect_ratio") or DEFAULT_ASPECT.get(kind)
    height = length_mm(geometry.get("height_mm"))
    if height is None and _ratio(aspect): height = width / _ratio(aspect)
    if height is not None and height > frame["max_height_mm"] + 0.01:
        warnings.append(f"height {height:.1f} mm exceeds the {placement} frame ({frame['max_height_mm']:g} mm); clamped")
        height = frame["max_height_mm"]
    if frame.get("note"): warnings.append(frame["note"])
    region = "full-width" if span == "full" else frame_name
    return {"placement": placement, "span": span, "region": region, "width_mm": round(width, 2), "height_mm": round(height, 2) if height else None,
            "aspect_ratio": aspect, "declared": bool(geometry), "warnings": warnings}


def planned_geometry():
    """Figure id -> declared geometry, from plan/assets-plan.yaml (`geometry:` on each asset)."""
    from assets import assets
    return {str(a.get("id")): dict(a.get("geometry") or {}) for a in assets() if a.get("id") and isinstance(a.get("geometry"), dict)}


def check_geometry(geometry):
    """Validation messages for a declared `geometry:` block."""
    errors = []
    if not isinstance(geometry, dict): return ["geometry must be a mapping"]
    unknown = set(geometry) - {"placement", "span", "width_mm", "height_mm", "aspect_ratio"}
    if unknown: errors.append("geometry: unknown keys " + ", ".join(sorted(unknown)))
    if geometry.get("placement") and geometry["placement"] not in PLACEMENTS: errors.append(f"geometry.placement must be one of {', '.join(PLACEMENTS)}")
    if "span" in geometry and geometry["span"] not in (1, 2, "1", "2", "full"):
        errors.append("geometry.span must be 1, 2, or full")
    for key in ("width_mm", "height_mm"):
        if key in geometry and (length_mm(geometry[key]) or 0) <= 0: errors.append(f"geometry.{key} must be a positive length in mm")
    if geometry.get("aspect_ratio") and not _ratio(geometry["aspect_ratio"]): errors.append("geometry.aspect_ratio must look like 16:9")
    return errors


def profile_policy(profile=None):
    """The figure-related part of the PublicationProfile (plan/profile.resolved.yaml): how many visuals the book
    should carry and which generated images its art direction allows. Visual style (sizes, strokes) stays in the
    tokens above until the Style Bible exists."""
    if profile is None:
        try:
            import publication_profile
            profile = publication_profile.load_resolved()
        except Exception: profile = None
    if not profile: return None
    devices, art = profile["devices"], profile["art_direction"]
    return {"profile": profile["id"], "visuals_per_10k": devices["visuals_per_10k"], "tables_per_chapter": devices["tables_per_chapter"],
            "art_direction_weight": art["weight"], "ornament_level": art["ornament_level"], "generative_images": art["generative_images"]}


def write_reference(tokens):
    """.build/figure-tokens.json: the resolved tokens and frames, for chart scripts and agents."""
    data = {**figure_tokens(tokens), "frames": frames(tokens), "page": page_frame(tokens), "publication_profile": profile_policy()}
    path = ROOT / ".build/figure-tokens.json"; path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data

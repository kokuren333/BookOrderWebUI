"""LayoutSpec: paper geometry and writing flow, independent of PublicationProfile and visual style.

The resolved artifact is plan/layout-spec.yaml. Existing jobs start from the page settings in their
Design Spec; after creation the LayoutSpec is the authority for geometry and writing mode.
"""
import copy
import json
import re

from common import ROOT, read_project, yaml_data, write_yaml
from schema import validate_schema

SCHEMA = "bookorder/layout-spec@1"
PATH = ROOT / "plan/layout-spec.yaml"
PAPER_MM = {"A5": (148.0, 210.0), "B5": (176.0, 250.0), "A4": (210.0, 297.0), "Letter": (215.9, 279.4)}
UNIT_MM = {"mm": 1.0, "cm": 10.0, "pt": 25.4 / 72, "in": 25.4}
GENRE_DEFAULTS = {"technical": ("horizontal-tb", 1), "medical_science": ("horizontal-tb", 1),
                  "practical": ("horizontal-tb", 1), "criticism": ("horizontal-tb", 1),
                  "essay": ("horizontal-tb", 1),
                  # A future profile can use this without registering a new P0 genre now.
                  "novel": ("vertical-rl", 1)}


def _mm(value, default):
    match = re.fullmatch(r"\s*([0-9.]+)\s*(mm|cm|pt|in)?\s*", str(value)) if value is not None else None
    if not match: return default
    return round(float(match[1]) * UNIT_MM[match[2] or "mm"], 3)


def _coerce(value):
    if isinstance(value, dict): return {key: _coerce(item) for key, item in value.items()}
    if isinstance(value, list): return [_coerce(item) for item in value]
    if isinstance(value, str) and re.fullmatch(r"\d+", value): return int(value)
    if value == "true": return True
    if value == "false": return False
    return value


def _merge(base, patch):
    result = copy.deepcopy(base)
    for key, value in patch.items():
        result[key] = _merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else copy.deepcopy(value)
    return result


def defaults(project=None, profile=None, design=None):
    """Deterministic initial LayoutSpec. Genre chooses a starting flow, never constrains the schema."""
    project = project or read_project(); design = design or {}
    if profile is None:
        try:
            import publication_profile
            profile = publication_profile.load_resolved() or publication_profile.resolve(project, design)
        except Exception: profile = None
    genre = (profile or {}).get("genre", "general")
    mode, columns = GENRE_DEFAULTS.get(genre, ("horizontal-tb", 1))
    legacy = design.get("page") or {}
    size = legacy.get("size", "A5"); orientation = legacy.get("orientation", "portrait")
    width, height = PAPER_MM.get(size, PAPER_MM["A5"])
    if orientation == "landscape": width, height = height, width
    margins = legacy.get("margin") or {}
    spec = {
        "schema": SCHEMA, "id": "book-layout", "page_size": size, "orientation": orientation,
        "writing_mode": mode, "text_direction": "ltr",
        "page": {"width_mm": width, "height_mm": height,
                 "margin_top_mm": _mm(margins.get("top"), 20), "margin_bottom_mm": _mm(margins.get("bottom"), 20),
                 "margin_inner_mm": _mm(margins.get("inner"), 20), "margin_outer_mm": _mm(margins.get("outer"), 17),
                 "bleed_mm": 0},
        "body": {"columns": columns, "gutter_mm": 6, "baseline_grid": "none",
                 "column_balance": "none", "paragraph_flow": "continuous"},
        "regions": {"header": {"enabled": True}, "footer": {"enabled": True},
                    "margin_notes": {"enabled": False}, "chapter_opener": {"span": "full"},
                    "full_width": {"enabled": True}, "full_page": {"enabled": True}},
        "spans": {"figure": 1, "table": 1, "callout": 1, "quote": 1, "code": 1, "equation": 1},
        "writing": {"horizontal": {"text_direction": "ltr"},
                    "vertical": {"figure_orientation": "horizontal", "table_orientation": "horizontal",
                                 "caption_orientation": "horizontal"}},
        "vertical": {"enabled": mode == "vertical-rl", "line_direction": "top-to-bottom", "page_progression": "right-to-left",
                     "punctuation_policy": "locale", "latin_rotation": "auto", "numeral_policy": "auto",
                     "ruby_policy": "auto"},
    }
    return spec


def validate(value):
    schema = json.loads((ROOT / "schemas/layout-spec.schema.json").read_text(encoding="utf-8"))
    spec = validate_schema(_coerce(value), schema, coerce=True)
    width, height = PAPER_MM[spec["page_size"]]
    if spec["orientation"] == "landscape": width, height = height, width
    if abs(spec["page"]["width_mm"] - width) > .1 or abs(spec["page"]["height_mm"] - height) > .1:
        raise ValueError("LayoutSpec page.width_mm/height_mm must match page_size and orientation")
    p = spec["page"]
    if p["width_mm"] - p["margin_inner_mm"] - p["margin_outer_mm"] < 50:
        raise ValueError("LayoutSpec margins leave less than 50mm body width")
    if p["height_mm"] - p["margin_top_mm"] - p["margin_bottom_mm"] < 50:
        raise ValueError("LayoutSpec margins leave less than 50mm body height")
    if spec["body"]["gutter_mm"] * (spec["body"]["columns"] - 1) >= p["width_mm"] - p["margin_inner_mm"] - p["margin_outer_mm"]:
        raise ValueError("LayoutSpec gutters consume the entire body width")
    if spec["writing_mode"] == "vertical-rl" and not spec["vertical"]["enabled"]:
        raise ValueError("LayoutSpec vertical-rl requires vertical.enabled: true")
    if spec["writing_mode"] == "horizontal-tb" and spec["vertical"]["enabled"]:
        raise ValueError("LayoutSpec vertical.enabled requires vertical-rl")
    if spec["writing_mode"] == "horizontal-tb" and spec["text_direction"] != spec["writing"]["horizontal"]["text_direction"]:
        raise ValueError("LayoutSpec text_direction and writing.horizontal.text_direction disagree")
    for kind, span in spec["spans"].items():
        if isinstance(span, int) and span > spec["body"]["columns"]:
            raise ValueError(f"LayoutSpec spans.{kind}={span} exceeds body.columns")
    return spec


def resolve(project=None, profile=None, design=None, override=None):
    project = project or read_project()
    spec = defaults(project, profile, design)
    chosen = override if override is not None else (project.get("layout_spec") or {})
    return validate(_merge(spec, chosen))


def load_or_create(project=None, profile=None, design=None):
    if PATH.is_file(): return validate(yaml_data(PATH))
    spec = resolve(project, profile, design)
    write_yaml(PATH, spec, "LayoutSpec: geometry and writing flow. Edit this file after initial resolution.")
    return spec


def apply_to_tokens(tokens, spec):
    """Bridge for the P0 design consumers; LayoutSpec is the geometry authority."""
    result = copy.deepcopy(tokens); p = spec["page"]
    result["layout_spec"] = spec
    result["page"] = {"size": spec["page_size"], "orientation": spec["orientation"],
                      "margin": {"top": f"{p['margin_top_mm']}mm", "bottom": f"{p['margin_bottom_mm']}mm",
                                 "inner": f"{p['margin_inner_mm']}mm", "outer": f"{p['margin_outer_mm']}mm"}}
    return result

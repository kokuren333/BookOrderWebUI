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
PRESETS_PATH = ROOT / "schemas/publication-presets.json"


def presets():
    """Shared publication presets (page sizes, limits, layout presets); the WebUI reads the same file."""
    return json.loads(PRESETS_PATH.read_text(encoding="utf-8"))


_PRESETS = presets()
PAPER_MM = {name: tuple(float(v) for v in dims) for name, dims in _PRESETS["page_sizes"].items()}
LIMITS = _PRESETS["limits"]
LAYOUT_PRESETS = _PRESETS["layout_presets"]
SPAN_POLICIES = tuple(_PRESETS["span_policies"])


class LayoutSpecError(ValueError):
    """Invalid LayoutSpec geometry. `issues` carries field-level entries: {code, field, message}."""
    def __init__(self, issues):
        self.issues = issues
        super().__init__("; ".join(issue["message"] for issue in issues))


def page_dimensions(size, orientation="portrait", width=None, height=None):
    """(width_mm, height_mm) for a named size, or the given custom dimensions."""
    if size == "custom": w, h = float(width), float(height)
    else: w, h = PAPER_MM[size]
    return (h, w) if orientation == "landscape" and size != "custom" else (w, h)


def column_width_mm(spec):
    p, body = spec["page"], spec["body"]
    usable = p["width_mm"] - p["margin_inner_mm"] - p["margin_outer_mm"]
    gutter = body["gutter_mm"] if body["columns"] > 1 else 0
    return round((usable - gutter * (body["columns"] - 1)) / body["columns"], 2)


def summary(spec):
    """Resolved geometry the WebUI and reports display (derived, never an input)."""
    p, body = spec["page"], spec["body"]
    return {"page_size": spec["page_size"], "orientation": spec["orientation"],
            "width_mm": p["width_mm"], "height_mm": p["height_mm"], "columns": body["columns"],
            "gutter_mm": body["gutter_mm"] if body["columns"] > 1 else 0,
            "body_width_mm": round(p["width_mm"] - p["margin_inner_mm"] - p["margin_outer_mm"], 2),
            "body_height_mm": round(p["height_mm"] - p["margin_top_mm"] - p["margin_bottom_mm"], 2),
            "column_width_mm": column_width_mm(spec),
            "margins_mm": {k: p[f"margin_{k}_mm"] for k in ("top", "bottom", "inner", "outer")},
            "writing_mode": spec["writing_mode"], "spans": {k: spec["spans"][k] for k in ("figure", "table")},
            "span_policy": spec.get("span_policy")}
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
    width, height = page_dimensions(size if size in PAPER_MM else "A5", orientation)
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


def geometry_issues(spec):
    """Every geometry/consistency problem of a schema-valid LayoutSpec as {code, field, message}."""
    issues = []
    def add(code, field, message): issues.append({"code": code, "field": field, "message": message})
    p, body = spec["page"], spec["body"]
    if spec["page_size"] == "custom":
        low, high = LIMITS["custom_page_min_mm"], LIMITS["custom_page_max_mm"]
        for key in ("width_mm", "height_mm"):
            if not low <= p[key] <= high:
                add("custom_page_invalid", f"page.{key}", f"LayoutSpec custom page {key} {p[key]:g}mm must be between {low} and {high}mm")
    else:
        width, height = page_dimensions(spec["page_size"], spec["orientation"])
        if abs(p["width_mm"] - width) > .1 or abs(p["height_mm"] - height) > .1:
            add("page_size_mismatch", "page.width_mm", "LayoutSpec page.width_mm/height_mm must match page_size and orientation")
    usable_w = p["width_mm"] - p["margin_inner_mm"] - p["margin_outer_mm"]
    usable_h = p["height_mm"] - p["margin_top_mm"] - p["margin_bottom_mm"]
    if usable_w <= 0:
        add("margins_exceed_page", "page.margin_inner_mm", f"LayoutSpec inner+outer margins ({p['margin_inner_mm'] + p['margin_outer_mm']:g}mm) exceed the page width ({p['width_mm']:g}mm)")
    if usable_h <= 0:
        add("margins_exceed_page", "page.margin_top_mm", f"LayoutSpec top+bottom margins ({p['margin_top_mm'] + p['margin_bottom_mm']:g}mm) exceed the page height ({p['height_mm']:g}mm)")
    if usable_w < LIMITS["min_body_width_mm"]:
        add("body_width_insufficient", "page.margin_outer_mm", f"LayoutSpec margins leave less than {LIMITS['min_body_width_mm']}mm body width ({usable_w:g}mm)")
    if usable_h < LIMITS["min_body_height_mm"]:
        add("body_height_insufficient", "page.margin_bottom_mm", f"LayoutSpec margins leave less than {LIMITS['min_body_height_mm']}mm body height ({usable_h:g}mm)")
    columns, gutter = body["columns"], body["gutter_mm"]
    if columns > 1:
        if gutter * (columns - 1) >= usable_w:
            add("gutter_consumes_body", "body.gutter_mm", "LayoutSpec gutters consume the entire body width")
        elif gutter < LIMITS["min_gutter_mm"]:
            add("gutter_too_small", "body.gutter_mm", f"LayoutSpec gutter {gutter:g}mm is below {LIMITS['min_gutter_mm']}mm; columns would touch")
        elif gutter > LIMITS["max_gutter_mm"]:
            add("gutter_too_large", "body.gutter_mm", f"LayoutSpec gutter {gutter:g}mm exceeds {LIMITS['max_gutter_mm']}mm")
        width = (usable_w - gutter * (columns - 1)) / columns
        if usable_w > 0 and 0 < width < LIMITS["min_column_width_mm"]:
            add("column_too_narrow", "body.columns", f"LayoutSpec {columns}-column body leaves {width:.1f}mm per column (minimum {LIMITS['min_column_width_mm']}mm); the page is too narrow for {columns} columns")
    if spec["writing_mode"] == "vertical-rl" and not spec["vertical"]["enabled"]:
        add("vertical_flag", "vertical.enabled", "LayoutSpec vertical-rl requires vertical.enabled: true")
    if spec["writing_mode"] == "horizontal-tb" and spec["vertical"]["enabled"]:
        add("vertical_flag", "vertical.enabled", "LayoutSpec vertical.enabled requires vertical-rl")
    if spec["writing_mode"] == "horizontal-tb" and spec["text_direction"] != spec["writing"]["horizontal"]["text_direction"]:
        add("text_direction_conflict", "text_direction", "LayoutSpec text_direction and writing.horizontal.text_direction disagree")
    for kind, span in spec["spans"].items():
        if isinstance(span, int) and span > columns:
            add("span_exceeds_columns", f"spans.{kind}", f"LayoutSpec spans.{kind}={span} exceeds body.columns")
    policy = spec.get("span_policy") or {}
    for kind, value in policy.items():
        if value == "full" and columns == 1:
            add("span_policy_single_column", f"span_policy.{kind}", f"LayoutSpec span_policy.{kind}=full needs two columns; a one-column body has no column span")
        expected = "full" if value == "full" else 1
        if spec["spans"][kind] != expected:
            add("span_policy_conflict", f"spans.{kind}", f"LayoutSpec spans.{kind}={spec['spans'][kind]!r} contradicts span_policy.{kind}={value}")
    return issues


def validate(value):
    schema = json.loads((ROOT / "schemas/layout-spec.schema.json").read_text(encoding="utf-8"))
    spec = validate_schema(_coerce(value), schema, coerce=True)
    issues = geometry_issues(spec)
    if issues: raise LayoutSpecError(issues)
    return spec


def request(project):
    """The project's layout request: `layout_preset` (schemas/publication-presets.json) and/or a `layout_spec` patch."""
    name = project.get("layout_preset")
    patch = {}
    if name:
        if name not in LAYOUT_PRESETS:
            raise LayoutSpecError([{"code": "unknown_preset", "field": "layout_preset",
                                    "message": f"Unknown layout preset {name!r}; choose one of {', '.join(LAYOUT_PRESETS)}"}])
        patch = copy.deepcopy(LAYOUT_PRESETS[name]["layout"])
    override = project.get("layout_spec") or {}
    if not isinstance(override, dict): raise ValueError("project.layout_spec must be a mapping")
    return _merge(patch, override)


def _materialize(spec, chosen):
    """Derive dependent values of a request: page dimensions from page_size, spans from span_policy, vertical flag."""
    size = spec["page_size"]
    page = chosen.get("page") or {}
    if size != "custom" and size in PAPER_MM and "width_mm" not in page and "height_mm" not in page:
        spec["page"]["width_mm"], spec["page"]["height_mm"] = page_dimensions(size, spec["orientation"])
    if "writing_mode" in chosen and "enabled" not in (chosen.get("vertical") or {}):
        spec["vertical"]["enabled"] = spec["writing_mode"] == "vertical-rl"
    for kind, value in (spec.get("span_policy") or {}).items():
        if kind not in (chosen.get("spans") or {}):
            spec["spans"][kind] = "full" if value == "full" else 1
    return spec


def resolve(project=None, profile=None, design=None, override=None):
    project = project or read_project()
    spec = defaults(project, profile, design)
    chosen = override if override is not None else request(project)
    return validate(_materialize(_merge(spec, chosen), chosen))


def requested(project):
    """True when project.json itself asks for a layout (WebUI or hand-written), not just the Design Spec defaults."""
    return bool(project.get("layout_preset") or project.get("layout_spec"))


def renderer_issues(spec, renderer="typst"):
    """Layout choices the PDF renderer cannot honour, as field-level issues. Never a silent fallback."""
    from renderers import assess_layout
    verdict = assess_layout(renderer, spec)
    if verdict["status"] != "unsupported": return []
    issues = []
    for reason in verdict["reasons"]:
        vertical = "writing_mode" in reason
        issues.append({"code": "vertical_unsupported" if vertical else "renderer_unsupported",
                       "field": "writing_mode" if vertical else "layout_spec",
                       "message": ("Current Typst renderer does not support vertical writing (writing_mode vertical-rl); "
                                   "choose horizontal-tb" if vertical else f"PDF ({renderer}) cannot render the requested layout: {reason}")})
    return issues


def load_or_create(project=None, profile=None, design=None):
    project = project or read_project()
    marker = PATH.with_name('layout-request.json')
    inputs = {'request': request(project), 'design_page': (design or {}).get('page', {})}
    previous = json.loads(marker.read_text(encoding='utf-8')) if marker.is_file() else None
    if PATH.is_file() and (previous is None or previous == inputs):
        if previous is None:
            marker.write_text(json.dumps(inputs, ensure_ascii=False, sort_keys=True), encoding='utf-8')
        return validate(yaml_data(PATH))
    spec = resolve(project, profile, design)
    if requested(project) and (project.get("outputs") or {}).get("pdf", True):
        issues = renderer_issues(spec)
        if issues: raise LayoutSpecError(issues)
    write_yaml(PATH, spec, "LayoutSpec: geometry and writing flow. Edit this file after initial resolution.")
    marker.write_text(json.dumps(inputs, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    return spec


def apply_to_tokens(tokens, spec):
    """Bridge for the P0 design consumers; LayoutSpec is the geometry authority."""
    result = copy.deepcopy(tokens); p = spec["page"]
    result["layout_spec"] = spec
    result["page"] = {"size": spec["page_size"], "orientation": spec["orientation"],
                      "width_mm": p["width_mm"], "height_mm": p["height_mm"],
                      "margin": {"top": f"{p['margin_top_mm']}mm", "bottom": f"{p['margin_bottom_mm']}mm",
                                 "inner": f"{p['margin_inner_mm']}mm", "outer": f"{p['margin_outer_mm']}mm"}}
    return result

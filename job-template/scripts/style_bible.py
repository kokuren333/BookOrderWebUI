"""Book-level visual language; LayoutSpec owns geometry and this module owns appearance.

The resolved plan/style-bible.yaml is generated from visual defaults, a genre template,
PublicationProfile.art_direction and project.style_bible. A matching resolved artifact may be
edited by hand; changed upstream inputs re-resolve it. Renderer tokens adapt it to LayoutSpec.
"""
import copy
import hashlib
import json
import re

from common import ROOT, read_project, yaml_data, write_yaml
from schema import validate_schema
import visual_grammar

SCHEMA = "bookorder/style-bible@1"
PATH = ROOT / "plan/style-bible.yaml"
GENRES = ("technical", "medical_science", "practical", "criticism", "essay")
SECTIONS = {
    "tone": "overall formality density restraint abstraction ornament whitespace",
    "palette": "ink muted accent secondary_accent background surface warning success",
    "typography": "body heading_1 heading_2 heading_3 chapter_number figure_label figure_emphasis axis_label tick_label caption table callout code minimum_print_pt",
    "lines": "hairline_pt normal_pt strong_pt arrow_pt arrowhead_mm",
    "spacing": "micro_mm small_mm medium_mm large_mm section_gap_mm figure_gap_mm caption_gap_mm",
    "geometry": "corner_radius_mm node_padding_mm",
    "diagram": "node_style edge_style hierarchy_style causal_style label_position emphasis_strategy",
    "chart": "axis_style grid_style legend_style direct_labeling max_series emphasis_strategy annotation_style",
    "table": "border_style header_style row_spacing zebra numeric_alignment note_style",
    "callout": "variants border_style fill_style title_style icon_policy spacing",
    "caption": "prefix_style numbering_style punctuation source_style alignment",
    "chapter_opener": "chapter_number_style title_style lead_style visual_relationship",
    "imagery": "allowed_roles realism abstraction composition texture lighting people_policy text_in_image recurring_motifs palette_relationship",
    "accessibility": "grayscale_safe minimum_contrast color_independent_encoding alt_text_required",
    "print": "minimum_line_pt minimum_text_pt",
}
SECTIONS = {key: set(value.split()) for key, value in SECTIONS.items()}
EXEMPLARS = ("chapter_opener", "h1", "h2", "h3", "body_paragraph", "table", "chart", "diagram",
             "key_point", "warning", "definition", "caption")
TYPE_ROLES = tuple(role for role in SECTIONS["typography"] if role != "minimum_print_pt")
HEX = re.compile(r"#[0-9A-Fa-f]{6}")
LAYOUT_KEYS = {"columns", "writing_mode", "page_size", "margin", "margins", "gutter_mm", "page_geometry", "spans", "regions"}


def merge(base, patch):
    result = copy.deepcopy(base)
    for key, value in patch.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else copy.deepcopy(value)
    return result


def _pt(value, default):
    match = re.fullmatch(r"\s*([0-9.]+)\s*(?:pt)?\s*", str(value or ""))
    return float(match[1]) if match else default


def _role(design, source, size, weight=None):
    item = (design.get("typography") or {}).get(source) or {}
    family = item.get("japanese") or item.get("family") or item.get("latin") or "Noto Sans CJK JP"
    return {"family": family, "size_pt": round(size, 2), "weight": weight if weight is not None else int(item.get("weight", 400)),
            "line_height": float(item.get("line_height", 1.4))}


def visual_defaults(design=None):
    design = design or {}; colors = design.get("colors") or {}; typography = design.get("typography") or {}
    body = _pt((typography.get("body") or {}).get("size"), 9.5)
    heading = _pt((typography.get("heading") or {}).get("size"), 18)
    caption = _pt((typography.get("caption") or {}).get("size"), 7.8)
    roles = {
        "body": _role(design, "body", body), "heading_1": _role(design, "heading", heading * 1.18),
        "heading_2": _role(design, "heading", heading * .74), "heading_3": _role(design, "heading", body * 1.1),
        "chapter_number": _role(design, "heading", heading * 3.4, 700),
        "figure_label": _role(design, "caption", 8, 500), "figure_emphasis": _role(design, "caption", 8.5, 700),
        "axis_label": _role(design, "caption", 7.5), "tick_label": _role(design, "caption", 7),
        "caption": _role(design, "caption", caption), "table": _role(design, "body", body * .92),
        "callout": _role(design, "body", body), "code": _role(design, "code", _pt((typography.get("code") or {}).get("size"), 8.3)),
        "minimum_print_pt": 6.5,
    }
    return {
        "schema": SCHEMA, "id": "book-style", "genre": "general", "art_direction_weight": "standard", "inputs_fingerprint": "",
        "tone": {"overall": "clear and restrained", "formality": "standard", "density": "balanced", "restraint": "high",
                 "abstraction": "medium", "ornament": "low", "whitespace": "balanced"},
        "palette": {"ink": colors.get("text", "#18181B"), "muted": colors.get("muted", "#71717A"),
                    "accent": colors.get("accent", "#0891B2"), "secondary_accent": colors.get("primary", "#164E63"),
                    "background": "#FFFFFF", "surface": colors.get("surface", "#F4F7F8"),
                    "warning": "#9A4D12", "success": "#2F6B55"},
        "typography": roles,
        "lines": {"hairline_pt": .35, "normal_pt": .6, "strong_pt": 1, "arrow_pt": .6, "arrowhead_mm": 1.4},
        "spacing": {"micro_mm": .7, "small_mm": 1.5, "medium_mm": 3, "large_mm": 6,
                    "section_gap_mm": 5, "figure_gap_mm": 4, "caption_gap_mm": 1.4},
        "geometry": {"corner_radius_mm": 1, "node_padding_mm": 2},
        "diagram": {"node_style": "outline", "edge_style": "semantic-arrow", "hierarchy_style": "levels",
                    "causal_style": "labelled", "label_position": "inside", "emphasis_strategy": "weight-and-label"},
        "chart": {"axis_style": "quiet", "grid_style": "major-only", "legend_style": "compact", "direct_labeling": True,
                  "max_series": 6, "emphasis_strategy": "weight-and-pattern", "annotation_style": "outside-data"},
        "table": {"border_style": "horizontal", "header_style": "rule-and-weight", "row_spacing": "standard",
                  "zebra": False, "numeric_alignment": "decimal", "note_style": "below"},
        "callout": {"variants": {"key-point": "primary-rule", "warning": "warning-rule", "definition": "quiet-box"},
                    "border_style": "left-rule", "fill_style": "surface", "title_style": "small-bold", "icon_policy": "none", "spacing": "medium"},
        "caption": {"prefix_style": "accent-bold", "numbering_style": "chapter-sequence", "punctuation": "space",
                    "source_style": "below-muted", "alignment": "left"},
        "chapter_opener": {"chapter_number_style": "large-muted", "title_style": "editorial",
                           "lead_style": "plain", "visual_relationship": "below-title"},
        "imagery": {"allowed_roles": ["chapter-opener"], "realism": "low", "abstraction": "medium", "composition": "spacious",
                    "texture": "minimal", "lighting": "neutral", "people_policy": "avoid", "text_in_image": False,
                    "recurring_motifs": [], "palette_relationship": "inherit"},
        "accessibility": {"grayscale_safe": True, "minimum_contrast": 4.5, "color_independent_encoding": True, "alt_text_required": True},
        "print": {"minimum_line_pt": .25, "minimum_text_pt": 6.5},
        "grammar": {"accent": "Use accent only for meaningful emphasis and navigation.",
                    "headings": "Use size and weight to establish hierarchy; avoid a one-character final line.",
                    "diagram_edges": "Arrow direction and label express a relation, not decoration.",
                    "chart_categories": "Never encode a category by color alone; label it directly.",
                    "table_headers": "Distinguish the header with weight and a rule.",
                    "callouts": "Key point, warning and definition have distinct semantic treatments.",
                    "captions": "Prefix, chapter number and source note follow one syntax.",
                    "source_notes": "Keep source notes adjacent to the referenced visual."},
        "visual_grammar": visual_grammar.defaults(),
        "exemplars": {"chapter_opener": "第2章　仕組みを読む", "h1": "自己注意とTransformer", "h2": "計算量と効率化",
                      "h3": "実験条件の違い", "body_paragraph": "結論を先に示し、根拠と適用範囲を続ける。",
                      "table": "方式｜条件｜含意", "chart": "系列Aと系列Bを直接ラベルで比較", "diagram": "入力→処理→出力",
                      "key_point": "要点：比較条件を揃える。", "warning": "注意：相関を因果と読まない。",
                      "definition": "定義：使用する語の意味を固定する。", "caption": "図2.1　計算の流れ"},
    }


def _publication_presets():
    return json.loads((ROOT / "schemas/publication-presets.json").read_text(encoding="utf-8"))


def template_genre(project, profile):
    """Genre template to start from: project.style_preset (WebUI StyleBible preset) or the profile genre."""
    name = project.get("style_preset")
    if not name: return (profile or {}).get("genre", "general")
    presets = _publication_presets()["style_presets"]
    if name not in presets: raise ValueError(f"project.style_preset {name!r} is not one of {', '.join(presets)}")
    return presets[name]["template"]


def apply_controls(style, controls):
    """High-level StyleBible controls (schemas/publication-presets.json style_controls) -> StyleBible fields."""
    if not controls: return style
    if not isinstance(controls, dict): raise ValueError("project.style_controls must be a mapping")
    table = _publication_presets()["style_controls"]
    for name, choice in controls.items():
        if name not in table: raise ValueError(f"project.style_controls.{name} is not one of {', '.join(table)}")
        options = table[name]["options"]
        if choice not in options: raise ValueError(f"project.style_controls.{name}={choice!r} is not one of {', '.join(options)}")
        option = options[choice]
        style = merge(style, option.get("patch") or {})
        for component, fields in (option.get("components") or {}).items():
            style["visual_grammar"]["components"][component].update(fields)
        if option.get("spacing_scale", 1) != 1:
            style["spacing"] = {key: round(float(value) * option["spacing_scale"], 2) for key, value in style["spacing"].items()}
        if option.get("type_scale", 1) != 1:
            for role in TYPE_ROLES:
                size = float(style["typography"][role]["size_pt"]) * option["type_scale"]
                style["typography"][role]["size_pt"] = round(max(style["print"]["minimum_text_pt"], size), 2)
    return style


def inputs_fingerprint(project, profile, design):
    genre = template_genre(project, profile)
    template = ROOT / "styles/genres" / f"{genre}.yaml"
    basis = {"resolver_version": "p1-2", "genre_template": template.read_text(encoding="utf-8") if template.is_file() else "",
             "genre": genre, "art_direction": (profile or {}).get("art_direction", {}),
             "design_visual": {key: (design or {}).get(key) for key in ("colors", "typography", "components", "figures", "art_direction")},
             "project_override": project.get("style_bible") or {}}
    # Only present when requested, so existing jobs keep their fingerprint.
    if project.get("style_preset"): basis["style_preset"] = project["style_preset"]
    if project.get("style_controls"): basis["style_controls"] = project["style_controls"]
    return hashlib.sha256(json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def resolve(project=None, profile=None, design=None):
    project = project or read_project(); design = design or {}
    if profile is None:
        try:
            import publication_profile
            profile = publication_profile.load_resolved() or publication_profile.resolve(project, design)
        except Exception: profile = {}
    profile = profile or {}; genre = profile.get("genre", "general")
    style = visual_defaults(design)
    template = ROOT / "styles/genres" / f"{template_genre(project, profile)}.yaml"
    if template.is_file(): style = merge(style, yaml_data(template))
    style["genre"] = genre
    art = profile.get("art_direction") or {}
    style["art_direction_weight"] = art.get("weight", "standard")
    if art.get("ornament"): style["tone"]["ornament"] = art["ornament"]
    if art.get("ornament_level"): style["tone"]["ornament"] = art["ornament_level"]
    imagery = art.get("generative_images") or {}
    if isinstance(imagery, dict): style["imagery"]["allowed_roles"] = list(imagery.get("allowed") or [])
    if design.get("art_direction"): style["tone"]["overall"] = str(design["art_direction"])
    if project.get("style_preset"): style["preset"] = project["style_preset"]
    style = apply_controls(style, project.get("style_controls"))
    override = project.get("style_bible") or {}
    if not isinstance(override, dict): raise ValueError("project.style_bible must be a mapping")
    style = merge(style, override)
    style["inputs_fingerprint"] = inputs_fingerprint(project, profile, design)
    return validate(style)


def validate(style):
    schema = json.loads((ROOT / "schemas/style-bible.schema.json").read_text(encoding="utf-8"))
    value = validate_schema(style, schema, coerce=True)
    allowed_top = {"schema", "id", "genre", "preset", "art_direction_weight", "inputs_fingerprint", "grammar", "exemplars", "visual_grammar"} | set(SECTIONS)
    unknown = set(value) - allowed_top
    if unknown: raise ValueError("StyleBible unknown keys: " + ", ".join(sorted(unknown)))
    for section, allowed in SECTIONS.items():
        extra = set(value[section]) - allowed
        missing = allowed - set(value[section])
        if extra or missing: raise ValueError(f"StyleBible {section}: unknown {sorted(extra)}, missing {sorted(missing)}")
    if set(value) & LAYOUT_KEYS or any(set(value[section]) & LAYOUT_KEYS for section in SECTIONS):
        raise ValueError("Layout geometry belongs in LayoutSpec, not StyleBible")
    for key, color in value["palette"].items():
        if not isinstance(color, str) or not HEX.fullmatch(color): raise ValueError(f"StyleBible palette.{key} must be #RRGGBB")
    for role in TYPE_ROLES:
        item = value["typography"][role]
        if set(item) != {"family", "size_pt", "weight", "line_height"}: raise ValueError(f"StyleBible typography.{role} has invalid fields")
        item["size_pt"] = float(item["size_pt"]); item["weight"] = int(item["weight"]); item["line_height"] = float(item["line_height"])
        if not item["family"] or not 4 <= item["size_pt"] <= 100 or not 100 <= item["weight"] <= 900 or not 1 <= item["line_height"] <= 3:
            raise ValueError(f"StyleBible typography.{role} invalid")
    value["typography"]["minimum_print_pt"] = float(value["typography"]["minimum_print_pt"])
    for key in SECTIONS["lines"] | SECTIONS["spacing"] | SECTIONS["geometry"] | SECTIONS["print"]:
        section = next(name for name in ("lines", "spacing", "geometry", "print") if key in SECTIONS[name])
        value[section][key] = float(value[section][key])
    value["chart"]["max_series"] = int(value["chart"]["max_series"])
    if value["print"]["minimum_text_pt"] < 6.5 or value["typography"]["minimum_print_pt"] < 6.5:
        raise ValueError("StyleBible cannot lower the 6.5pt printed-text minimum")
    if set(value["exemplars"]) != set(EXEMPLARS): raise ValueError("StyleBible exemplars must contain the canonical sample set")
    visual_grammar.validate(value["visual_grammar"])
    return value


def load_or_resolve(project=None, profile=None, design=None):
    project = project or read_project()
    current = resolve(project, profile, design)
    if PATH.is_file():
        existing = yaml_data(PATH) or {}
        if existing.get("schema") == SCHEMA and existing.get("visual_grammar") and existing.get("inputs_fingerprint") == current["inputs_fingerprint"]:
            return validate(existing)
    write_yaml(PATH, current, "Resolved StyleBible. Override through project.style_bible; geometry stays in plan/layout-spec.yaml.")
    return current


def compile_tokens(style, layout, tokens):
    """Compile semantic appearance for renderers; geometry remains exclusively in LayoutSpec."""
    result = copy.deepcopy(tokens)
    page = layout["page"]; body = layout["body"]
    width = (page["width_mm"] - page["margin_inner_mm"] - page["margin_outer_mm"] -
             body["gutter_mm"] * (body["columns"] - 1)) / body["columns"]
    narrow = body["columns"] > 1 and width < 62
    typography = copy.deepcopy(style["typography"])
    for role, design_role in (("body", "body"), ("heading_1", "heading"), ("heading_2", "heading"),
                              ("heading_3", "heading"), ("chapter_number", "heading"),
                              ("figure_label", "caption"), ("figure_emphasis", "caption"),
                              ("axis_label", "caption"), ("tick_label", "caption"),
                              ("caption", "caption"), ("table", "body"), ("callout", "body"), ("code", "code")):
        design_type = ((tokens.get("typography") or {}).get(design_role) or {})
        resolved = design_type.get("resolved_families") or []
        requested = {design_type.get("japanese"), design_type.get("family"), design_type.get("latin")}
        if resolved and typography[role]["family"] in requested and typography[role]["family"] not in resolved:
            typography[role]["family"] = resolved[0]
    adaptation = {"column_width_mm": round(width, 2), "narrow_column": narrow, "adjustments": []}
    if narrow:
        for role, limit in (("heading_2", 11.7), ("heading_3", 10.0), ("caption", 7.5), ("table", 8.0)):
            before = typography[role]["size_pt"]
            typography[role]["size_pt"] = round(min(before, limit), 2)
            if typography[role]["size_pt"] != before: adaptation["adjustments"].append(f"{role}: {before:g}→{typography[role]['size_pt']:g}pt")
    padding = 2.2 if narrow else style["spacing"]["medium_mm"]
    palette = style["palette"]
    result.setdefault("colors", {}).update(text=palette["ink"], muted=palette["muted"], primary=palette["secondary_accent"],
                            secondary=palette["surface"], accent=palette["accent"], surface=palette["surface"])
    result["style"] = {"id": style["id"], "genre": style["genre"], "tone": style["tone"], "palette": palette,
                       "typography": typography, "lines": style["lines"], "spacing": style["spacing"],
                       "geometry": style["geometry"], "diagram": style["diagram"], "chart": style["chart"],
                       "table": style["table"], "callout": style["callout"], "caption": style["caption"],
                       "chapter_opener": style["chapter_opener"], "imagery": style["imagery"],
                       "visual_grammar": style["visual_grammar"],
                       "accessibility": style["accessibility"], "print": style["print"],
                       "callout_padding_mm": padding, "adaptation": adaptation}
    return result

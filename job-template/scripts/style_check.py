"""Mechanical StyleBible lint. Taste remains editorial judgment, not a hard gate."""
import re
import unicodedata
from pathlib import Path

from common import ROOT, write_yaml, yaml_data

SCHEMA = "bookorder/style-check@1"
HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
CALLOUT_VARIANTS = {"key-point", "warning", "definition", "note", "tip", "example", "exercise", "checklist",
                    "sidebar", "step-by-step", "glossary-term", "counterpoint", "summary", "case-study", "pull-quote"}


def _rgb(value):
    return tuple(int(value[index:index + 2], 16) / 255 for index in (1, 3, 5))


def luminance(value):
    channels = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in _rgb(value)]
    return sum(a * b for a, b in zip(channels, (.2126, .7152, .0722)))


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + .05) / (lo + .05)


def _issue(issues, code, severity, detail, evidence=None, suggestion=None):
    item = {"code": code, "severity": severity, "detail": detail}
    if evidence: item["evidence"] = evidence
    if suggestion: item["suggestion"] = suggestion
    issues.append(item)


def _heading_chars(text):
    return sum(1 if unicodedata.east_asian_width(char) in ("W", "F") else .55 for char in text)


def _headings(root):
    for path in sorted((root / "source/manuscript").glob("*.md")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = re.match(r"^(#{2,3})\s+(.+?)(?:\s+\{#[^}]+\})?\s*$", line)
            if match: yield path, number, len(match[1]), match[2]


def lint(style, tokens, known_fonts=None, root=None, renderer_source=None, font_fallbacks=None):
    root = Path(root or ROOT); issues = []; palette = style["palette"]; appearance = tokens.get("style") or {}
    allowed = {value.lower() for value in palette.values()}
    # Design-to-renderer conversion must not retain colors outside the semantic palette.
    for name, color in (tokens.get("colors") or {}).items():
        if isinstance(color, str) and HEX.fullmatch(color) and color.lower() not in allowed:
            _issue(issues, "palette-outside", "medium", f"Renderer color {name} is outside the StyleBible palette", color)
    for file in (root / "custom.typ", root / "custom.css"):
        if file.is_file():
            for color in sorted(set(HEX.findall(file.read_text(encoding="utf-8")))):
                if color.lower() not in allowed:
                    _issue(issues, "palette-outside", "medium", f"Custom styling uses {color} outside the StyleBible palette", str(file.relative_to(root)))

    source = renderer_source
    if source is None:
        path = root / "themes" / str(tokens.get("theme", "modern-technical")) / "typst/theme.typ"
        source = path.read_text(encoding="utf-8") if path.is_file() else ""
    literal = re.findall(r"\brgb\(\s*\"#[0-9A-Fa-f]{6}\"|\bluma\(|\bfill:\s*white\b", source)
    if literal:
        _issue(issues, "renderer-default-color", "medium", "Typst theme contains a literal color outside semantic tokens",
               ", ".join(sorted(set(literal))[:6]), "Use StyleBible palette tokens in the active renderer path")

    min_text = max(6.5, float(style["print"]["minimum_text_pt"]))
    for role, settings in style["typography"].items():
        if role == "minimum_print_pt": continue
        if float(settings["size_pt"]) < min_text - .01:
            _issue(issues, "minimum-print-text", "high", f"{role} {settings['size_pt']}pt is below {min_text:g}pt")
        if known_fonts is not None and settings["family"] not in known_fonts:
            fallback = next((item for item in (font_fallbacks or []) if f": {settings['family']} -> " in item), None)
            _issue(issues, "font-fallback" if fallback else "unknown-font", "low" if fallback else "high",
                   f"{role} requests unavailable font {settings['family']}", fallback)
    line_min = max(.25, float(style["print"]["minimum_line_pt"]))
    for role in ("hairline_pt", "normal_pt", "arrow_pt"):
        if float(style["lines"][role]) < line_min - .001:
            _issue(issues, "minimum-line", "high", f"{role} is below {line_min:g}pt")

    if contrast(palette["ink"], palette["background"]) < float(style["accessibility"]["minimum_contrast"]):
        _issue(issues, "contrast", "high", "Ink/background contrast is below the declared minimum")
    if contrast(palette["accent"], palette["background"]) < 3:
        _issue(issues, "accent-contrast", "medium", "Accent/background contrast is weak for small labels")
    if style["accessibility"]["grayscale_safe"] and abs(luminance(palette["accent"]) - luminance(palette["secondary_accent"])) < .06:
        _issue(issues, "grayscale-unsafe", "medium", "Accent colors collapse to a similar grayscale value",
               suggestion="Use weight, pattern and direct labels as independent signals")
    if not style["accessibility"]["color_independent_encoding"] or not style["chart"]["direct_labeling"]:
        _issue(issues, "color-only-chart", "high", "Chart categories may depend on color alone")
    if palette["accent"].lower() in {palette["warning"].lower(), palette["success"].lower()}:
        _issue(issues, "excessive-accent", "medium", "General accent duplicates a semantic status color")

    if style["chart"]["max_series"] > 8:
        _issue(issues, "chart-series-count", "medium", "Chart max_series is high for a book figure")
    for record in sorted((root / "source/assets/figures").glob("*.render.json")):
        try:
            import json
            value = json.loads(record.read_text(encoding="utf-8"))
            if int(value.get("series_count", 0)) > style["chart"]["max_series"]:
                _issue(issues, "chart-series-count", "medium", f"{record.name} exceeds chart.max_series",
                       str(value["series_count"]))
        except (ValueError, KeyError): pass

    if not style["imagery"]["text_in_image"]:
        path = root / "plan/assets-plan.yaml"
        if path.is_file():
            try:
                for asset in (yaml_data(path) or {}).get("assets", []):
                    if asset.get("type") == "image" and re.search(r"text|letter|文字|看板", str(asset.get("prompt", "")), re.I):
                        _issue(issues, "text-in-image", "medium", f"{asset.get('id')} prompt may request text in an image")
            except ValueError: pass
    if style["caption"]["punctuation"] not in ("space", "colon", "period"):
        _issue(issues, "caption-format", "medium", "Caption punctuation has no renderer mapping")
    for kind in style["callout"]["variants"]:
        if kind not in CALLOUT_VARIANTS:
            _issue(issues, "callout-variant", "medium", f"Unknown callout variant {kind}")
    grammar = style.get("visual_grammar") or {}
    components = grammar.get("components") or {}
    prominent = ("key_point", "warning", "definition")
    filled = [name for name in prominent if (components.get(name) or {}).get("treatment") == "filled-box"]
    if len(filled) > 1:
        _issue(issues, "box-fatigue", "medium", "Several common callouts use filled boxes",
               ", ".join(filled), "Use a side rule, inset paragraph or plain emphasis for some roles")

    width = (appearance.get("adaptation") or {}).get("column_width_mm")
    typography = appearance.get("typography") or style["typography"]
    if width:
        for role in ("heading_2", "heading_3"):
            size = typography[role]["size_pt"]
            capacity = width * 72 / 25.4 / size
            if capacity < 8:
                _issue(issues, "oversize-heading", "medium", f"{role} leaves fewer than eight Japanese glyphs per line",
                       f"{width:g}mm / {size:g}pt")
        for path, line, level, title in _headings(root):
            role = "heading_2" if level == 2 else "heading_3"
            capacity = width * 72 / 25.4 / typography[role]["size_pt"]
            used = _heading_chars(title)
            remainder = used % capacity if capacity else 0
            if used > capacity and 0 < remainder <= 2.2:
                _issue(issues, "ugly-heading-wrap", "medium", f"{title} may leave one or two glyphs on the final line",
                       f"{path.relative_to(root)}:{line}",
                       "Rephrase, break at a semantic unit, use a full-span heading, or choose an allowed smaller tier")
    summary = {severity: sum(i["severity"] == severity for i in issues) for severity in ("low", "medium", "high")}
    return {"schema": SCHEMA, "style_id": style["id"], "layout_id": (tokens.get("layout_spec") or {}).get("id"),
            "summary": summary, "issues": issues}


def run(style, tokens, known_fonts=None):
    fallbacks = []
    if known_fonts is None:
        path = ROOT / "reports/design-report.json"
        if path.is_file():
            import json
            record = json.loads(path.read_text(encoding="utf-8"))
            known_fonts = set(record.get("available_fonts") or [])
            fallbacks = record.get("font_fallbacks") or []
    result = lint(style, tokens, known_fonts, font_fallbacks=fallbacks)
    write_yaml(ROOT / "reports/style-check.yaml", result,
               "Mechanical style lint; medium/low findings are revision evidence, not taste gates.")
    return result

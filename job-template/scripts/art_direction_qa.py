"""Book-wide art direction consistency audit after rendering.

Source/renderer checks and PDF-vector measurements are reported separately.
The probe is intentionally conservative: uncertain visual judgments are warnings,
while explicit token/semantic contradictions can block completion.
"""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from common import ROOT, fingerprint, write_yaml, yaml_data
from pdf_visual_probe import inspect as inspect_pdf
from style_check import contrast
import visual_grammar
from schema import validate_schema

SCHEMA = "bookorder/art-direction-check@1"
REPORT = ROOT / "reports/art-direction-check.yaml"
CATEGORIES = {"palette_drift", "typography_drift", "line_weight_drift", "spacing_drift",
              "component_treatment_drift", "caption_drift", "table_drift", "diagram_drift",
              "chart_drift", "hierarchy_drift", "density_drift", "visual_monotony", "image_asset_drift"}
NUM = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")
HEX = re.compile(r"#[0-9A-Fa-f]{6}")


def _issue(checks, category, severity, expected, observed, detail, *, page=None,
           component=None, suggested_fix="Review the resolved StyleBible and renderer token.", scope="source"):
    checks.append({"id": f"ad-{len(checks)+1:04d}", "category": category, "severity": severity,
                   "page": page, "component": component, "expected": expected, "observed": observed,
                   "detail": detail, "suggested_fix": suggested_fix, "scope": scope})


def _distance(a, b):
    return sum((int(a[index:index+2], 16) - int(b[index:index+2], 16)) ** 2 for index in (1, 3, 5)) ** .5


def _near_colors(colors, palette):
    all_colors = sorted(colors | set(palette.values()))
    return [(a, b) for i, a in enumerate(all_colors) for b in all_colors[i+1:] if a != b and _distance(a, b) <= 5]


def _semantic_shade(color, palette):
    """Allow the theme's light/dark variants of a semantic token, not arbitrary hues."""
    channels = [int(color[i:i+2], 16) for i in (1, 3, 5)]
    for base in palette.values():
        source = [int(base[i:i+2], 16) for i in (1, 3, 5)]
        for target in (0, 255):
            delta = [target - value for value in source]
            denominator = sum(value * value for value in delta)
            if not denominator: continue
            factor = sum((actual - initial) * change for actual, initial, change in zip(channels, source, delta)) / denominator
            if .025 <= factor <= .3 and max(abs(actual - (initial + factor * change)) for actual, initial, change in zip(channels, source, delta)) <= 7:
                return True
    return False


def _component_key(value):
    if not value: return None
    return {"summary": "chapter_summary", "glossary-term": "glossary"}.get(value, value.replace("-", "_"))


def _expected_size(style, tokens, role):
    return float((((tokens.get("style") or {}).get("typography") or {}).get(role) or
                  style["typography"][role])["size_pt"])


def _check_source(style, tokens, checks, root):
    compiled = tokens.get("style") or {}
    palette = style["palette"]
    if not compiled:
        _issue(checks, "component_treatment_drift", "high", "compiled StyleBible", "missing",
               "Renderer tokens omit the resolved StyleBible")
        return
    for role, expected in palette.items():
        observed = (compiled.get("palette") or {}).get(role)
        if observed != expected:
            _issue(checks, "palette_drift", "high", expected, observed, f"Compiled palette.{role} differs from StyleBible")
    for role, expected in style["typography"].items():
        if role == "minimum_print_pt": continue
        actual = (compiled.get("typography") or {}).get(role) or {}
        expected_size = float(expected["size_pt"])
        if (compiled.get("adaptation") or {}).get("narrow_column"):
            expected_size = min(expected_size, {"heading_2": 11.7, "heading_3": 10, "caption": 7.5, "table": 8}.get(role, expected_size))
        if abs(float(actual.get("size_pt", 0)) - expected_size) > .15:
            category = "caption_drift" if role == "caption" else "typography_drift"
            _issue(checks, category, "high", expected_size, actual.get("size_pt"), f"Compiled {role} size differs from resolved style", component=role)
    for role, expected in style["lines"].items():
        if role.endswith("_pt") and abs(float((compiled.get("lines") or {}).get(role, 0)) - float(expected)) > .05:
            _issue(checks, "line_weight_drift", "high", expected, (compiled.get("lines") or {}).get(role),
                   f"Compiled {role} differs from StyleBible")
    actual_grammar = compiled.get("visual_grammar") or {}
    expected_grammar = style["visual_grammar"]
    for name, rule in expected_grammar["components"].items():
        observed = (actual_grammar.get("components") or {}).get(name) or {}
        for field in ("treatment", "priority", "space_before_mm", "space_after_mm"):
            if observed.get(field) != rule[field]:
                category = "spacing_drift" if field.startswith("space_") else "component_treatment_drift"
                _issue(checks, category, "high", rule[field], observed.get(field),
                       f"Compiled {name}.{field} differs from resolved grammar", component=name)
    for section, category in (("table", "table_drift"), ("diagram", "diagram_drift"),
                              ("chart", "chart_drift"), ("caption", "caption_drift"),
                              ("rhythm", "spacing_drift")):
        if actual_grammar.get(section) != expected_grammar[section]:
            _issue(checks, category, "high", expected_grammar[section], actual_grammar.get(section),
                   f"Compiled {section} grammar differs from StyleBible")

    # Diagram IR and chartkit render records are compared with the same resolved grammar.
    for path in sorted((root / "source/assets/diagrams").glob("*.yaml")):
        svg = root / "source/assets/figures" / f"{path.stem}.svg"
        if not svg.is_file(): continue
        body = svg.read_text(encoding="utf-8")
        shape = expected_grammar["diagram"]["node_shape"]
        radii = [float(v) for v in re.findall(r"<rect\b[^>]*\brx=\"([0-9.]+)\"", body)]
        if radii and shape == "rectangle" and any(v > .05 for v in radii):
            _issue(checks, "diagram_drift", "medium", "rectangle nodes", radii[:4],
                   f"{svg.name} uses rounded nodes", component=path.stem)
        if radii and shape != "rectangle" and all(v < .05 for v in radii):
            _issue(checks, "diagram_drift", "medium", shape, "square nodes",
                   f"{svg.name} node shape differs", component=path.stem)
        edge_paths = re.findall(r"<path\b[^>]*\bstroke=\"[^\"]+\"[^>]*>", body)
        if expected_grammar["diagram"]["edge_emphasis"] == "directional" and any("marker-end=" not in edge for edge in edge_paths):
            _issue(checks, "diagram_drift", "medium", "directional edges", "edge without arrow marker",
                   f"{svg.name} edge treatment differs", component=path.stem)
        allowed_widths = [float(style["lines"][key]) for key in ("hairline_pt", "normal_pt", "strong_pt", "arrow_pt")]
        observed_widths = [float(v) for v in re.findall(r"\bstroke-width=\"([0-9.]+)\"", body)]
        if any(min(abs(v - target) for target in allowed_widths) > .2 for v in observed_widths):
            _issue(checks, "diagram_drift", "medium", allowed_widths, sorted(set(observed_widths)),
                   f"{svg.name} uses a line width outside the StyleBible scale", component=path.stem)
        label_sizes = [float(v) for v in re.findall(r"<text\b[^>]*\bfont-size=\"([0-9.]+)\"", body)]
        allowed_sizes = [float(style["typography"][key]["size_pt"]) for key in ("figure_label", "figure_emphasis")]
        if any(min(abs(v - target) for target in allowed_sizes) > .45 for v in label_sizes):
            _issue(checks, "diagram_drift", "medium", allowed_sizes, sorted(set(label_sizes)),
                   f"{svg.name} label sizes differ from figure typography", component=path.stem)
    for path in sorted((root / "source/assets/figures").glob("*.render.json")):
        try: record = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError): continue
        if record.get("renderer", "").startswith("matplotlib") and record.get("chart_grammar") != expected_grammar["chart"]:
            _issue(checks, "chart_drift", "medium", expected_grammar["chart"], record.get("chart_grammar"),
                   f"{path.name} was rendered with different chart grammar", component=record.get("asset"))


def _check_observations(style, tokens, observations, checks):
    palette = style["palette"]; allowed = {v.upper() for v in palette.values()}
    grammar = style["visual_grammar"]
    for item in observations or []:
        page = item.get("page"); name = _component_key(item.get("component"))
        role = item.get("role") or name
        color = item.get("color")
        if color and color.upper() not in allowed:
            nearest = min(palette.values(), key=lambda value: _distance(color.upper(), value.upper()))
            severity = "medium" if _distance(color.upper(), nearest.upper()) <= 5 else "high"
            _issue(checks, "palette_drift", severity, nearest, color, "Observed color is outside the palette",
                   page=page, component=name, scope="rendered", suggested_fix="Use a semantic palette role instead of a literal color.")
        if role in style["typography"] and role != "minimum_print_pt" and item.get("font_size_pt") is not None:
            expected = _expected_size(style, tokens, role)
            observed = float(item["font_size_pt"])
            if abs(expected - observed) > .45:
                category = "caption_drift" if role == "caption" else "typography_drift"
                severity = "high" if abs(expected - observed) > 1.5 else "medium"
                _issue(checks, category, severity, expected, observed, f"{role} rendered at a different size",
                       page=page, component=name or role, scope="rendered")
        if item.get("line_width_pt") is not None:
            value = float(item["line_width_pt"])
            allowed_lines = [float(style["lines"][key]) for key in ("hairline_pt", "normal_pt", "strong_pt", "arrow_pt")]
            if min(abs(value - target) for target in allowed_lines) > .18:
                _issue(checks, "line_weight_drift", "medium", allowed_lines, value,
                       "Rendered line weight is outside the StyleBible scale", page=page, component=name, scope="rendered")
        if name in grammar["components"]:
            rule = grammar["components"][name]
            if item.get("treatment") and item["treatment"] != rule["treatment"]:
                _issue(checks, "component_treatment_drift", "high", rule["treatment"], item["treatment"],
                       f"{name} treatment differs from the resolved grammar", page=page, component=name, scope="rendered")
            for field in ("space_before_mm", "space_after_mm"):
                if item.get(field) is not None and abs(float(item[field]) - float(rule[field])) > 1.5:
                    _issue(checks, "spacing_drift", "medium", rule[field], item[field],
                           f"{name} {field} varies", page=page, component=name, scope="rendered")
        for section, category in (("table", "table_drift"), ("diagram", "diagram_drift"), ("chart", "chart_drift"),
                                  ("caption", "caption_drift")):
            if item.get(section) and item[section] != grammar[section]:
                _issue(checks, category, "medium", grammar[section], item[section],
                       f"Rendered {section} policy differs", page=page, component=name, scope="rendered")


def _check_pdf(style, tokens, pdf, checks):
    if pdf["status"] != "measured": return {"status": pdf["status"], "reason": pdf.get("reason")}
    allowed = {value.upper() for value in style["palette"].values()}
    found = defaultdict(set); sizes = Counter(); lines = Counter(); out = []
    for page in pdf["pages"]:
        for field in ("text", "strokes", "fills"):
            for item in page[field]:
                if item.get("color"): found[item["color"].upper()].add(page["page"])
        sizes.update(item["size_pt"] for item in page["text"])
        lines.update(item["width_pt"] for item in page["strokes"])
    for color, pages in sorted(found.items()):
        if color in allowed: continue
        if _semantic_shade(color, style["palette"]): continue
        nearest = min(allowed, key=lambda value: _distance(color, value))
        severity = "medium" if _distance(color, nearest) <= 5 else "high" if color == "#000000" else "medium"
        _issue(checks, "palette_drift", severity, nearest, color,
               "PDF vector color is outside the resolved palette", page=min(pages), scope="pdf",
               suggested_fix="Trace the literal color in the renderer or figure asset and use a semantic palette role.")
    for a, b in _near_colors(set(found), style["palette"]):
        if (a not in allowed or b not in allowed) and not (_semantic_shade(a, style["palette"]) or _semantic_shade(b, style["palette"])):
            _issue(checks, "palette_drift", "medium", a, b, "Near-identical colors coexist in the PDF",
                   scope="pdf", suggested_fix="Normalize near colors to one StyleBible role.")
    expected_body = _expected_size(style, tokens, "body")
    if sizes and not any(abs(float(size) - expected_body) <= .2 for size in sizes):
        _issue(checks, "typography_drift", "high", expected_body, sorted(sizes),
               "Expected body text size is absent from the rendered PDF", component="body", scope="pdf")
    expected_lines = [float(style["lines"][key]) for key in ("hairline_pt", "normal_pt", "strong_pt", "arrow_pt")]
    for width, count in lines.items():
        if count >= 3 and min(abs(width - value) for value in expected_lines) > .2:
            _issue(checks, "line_weight_drift", "medium", expected_lines, width,
                   f"PDF contains {count} strokes outside the resolved line scale", scope="pdf")
    return {"status": "measured", "pages": len(pdf["pages"]), "colors": {color: sorted(pages) for color, pages in sorted(found.items())},
            "font_sizes_pt": dict(sorted(sizes.items())), "line_widths_pt": dict(sorted(lines.items())),
            "text_runs": sum(len(page["text"]) for page in pdf["pages"]),
            "strokes": sum(len(page["strokes"]) for page in pdf["pages"]),
            "fills": sum(len(page["fills"]) for page in pdf["pages"]),
            "images": sum(len(page.get("images", [])) for page in pdf["pages"])}


def _pdf_components(style, metrics, pdf):
    """Associate Typst layout marks with PDF vector boxes/rules by page and y extent."""
    if not metrics or pdf.get("status") != "measured": return []
    found = []
    for page in metrics.get("pages", []):
        number = page.get("page", 0)
        if not 1 <= number <= len(pdf["pages"]): continue
        vectors = pdf["pages"][number - 1]
        for element in page.get("elements", []):
            name = _component_key(element.get("sub"))
            if name not in style["visual_grammar"]["components"]: continue
            start, end = element.get("y"), element.get("end_y")
            if start is None or end is None or end <= start: continue
            height = end - start
            shapes = []
            for fill in vectors["fills"]:
                box = fill.get("bbox_pt")
                if not box: continue
                overlap = min(end, box[3]) - max(start, box[1])
                if overlap > 0 and overlap >= min(height, box[3] - box[1]) * .35:
                    shapes.append((box[2] - box[0], box[3] - box[1], box, fill["color"]))
            wide_fill = next((item for item in shapes if item[0] >= 20 and item[1] >= height * .5
                              and item[3] != style["palette"]["background"]), None)
            side = next((item for item in shapes if item[0] <= 4 and item[1] >= height * .5), None)
            top = next((item for item in shapes if item[0] >= 20 and item[1] <= 3 and abs(item[2][1] - start) <= 12), None)
            treatment = "filled-box" if wide_fill else "side-rule" if side else "top-rule" if top else None
            item = {"page": number, "component": name, "x_pt": element.get("x"),
                    "bbox_pt": [element.get("x"), start, None, end], "treatment": treatment,
                    "evidence": (wide_fill or side or top)[2] if treatment else None,
                    "internal_padding_top_pt": round(start - wide_fill[2][1], 2) if wide_fill else None,
                    "area_pt2": round((wide_fill or side or top)[0] * (wide_fill or side or top)[1], 2) if treatment else 0,
                    "color": (wide_fill or side or top)[3] if treatment else None}
            found.append(item)
    return found


def _check_internal_padding(items, checks):
    groups = defaultdict(list)
    for item in items:
        if item.get("internal_padding_top_pt") is not None:
            groups[item["component"]].append(item)
    for name, group in groups.items():
        if len(group) < 2: continue
        values = sorted(item["internal_padding_top_pt"] for item in group)
        median = values[len(values) // 2]
        for item in group:
            if abs(item["internal_padding_top_pt"] - median) > 4:
                _issue(checks, "spacing_drift", "medium", median, item["internal_padding_top_pt"],
                       f"{name} internal top padding differs from other instances",
                       page=item["page"], component=name, scope="pdf")


def _pdf_role_samples(metrics, pdf):
    """Map locatable headings/components to the PDF text runs nearest their layout marks."""
    if not metrics or pdf.get("status") != "measured": return []
    samples = []
    for page in metrics.get("pages", []):
        number = page.get("page", 0)
        if not 1 <= number <= len(pdf["pages"]): continue
        runs = pdf["pages"][number - 1]["text"]
        for heading in page.get("headings", []):
            level = heading.get("level")
            if level not in (2, 3): continue
            x, y = heading.get("x"), heading.get("y")
            if x is None or y is None: continue
            found = [run for run in runs if run["x_pt"] is not None and run["y_pt"] is not None
                     and x - 2 <= run["x_pt"] <= x + 220 and y <= run["y_pt"] <= y + 20]
            if found:
                size = max(run["size_pt"] for run in found)
                samples.append({"page": number, "component": f"heading_{level}", "role": f"heading_{level}",
                                "font_size_pt": size, "scope": "pdf"})
        for element in page.get("elements", []):
            kind = element.get("kind")
            if kind == "figure" and element.get("end_y") is not None:
                x, top, bottom = element.get("x"), element.get("y"), element.get("end_y")
                if x is None or top is None or bottom is None or bottom <= top: continue
                relevant = [run for run in runs if run["x_pt"] is not None and run["y_pt"] is not None
                            and x - 3 <= run["x_pt"] <= x + 450 and top <= run["y_pt"] <= bottom + 4]
                for role, selected in (("figure_label", [run for run in relevant if run["y_pt"] < bottom - 30]),
                                       ("caption", [run for run in relevant if bottom - 30 <= run["y_pt"] <= bottom + 4])):
                    if len(selected) >= 2:
                        size = Counter(run["size_pt"] for run in selected).most_common(1)[0][0]
                        samples.append({"page": number, "component": element.get("label") or role, "role": role,
                                        "font_size_pt": size, "scope": "pdf"})
                continue
            if kind not in ("callout", "summary", "case-study", "table") or element.get("end_y") is None: continue
            x, top, bottom = element.get("x"), element.get("y"), element.get("end_y")
            if x is None or top is None or bottom is None or bottom <= top: continue
            found = [run for run in runs if run["x_pt"] is not None and run["y_pt"] is not None
                     and x - 3 <= run["x_pt"] <= x + 220 and top <= run["y_pt"] <= bottom + 4]
            if len(found) >= 2:
                size = Counter(run["size_pt"] for run in found).most_common(1)[0][0]
                role = "table" if kind == "table" else "callout"
                samples.append({"page": number, "component": element.get("sub") or kind, "role": role,
                                "font_size_pt": size, "scope": "pdf"})
    return samples


def _check_metrics(style, metrics, checks):
    if not metrics: return {"status": "unavailable", "reason": "layout metrics missing"}
    pages = [page for page in metrics.get("pages", []) if page.get("region") == "main"]
    rhythm = style["visual_grammar"]["rhythm"]
    for page in pages:
        share = page.get("nonprose_share", 0)
        if share > (.78 if rhythm["pattern"] == "compact" else .7):
            _issue(checks, "density_drift", "medium", "balanced device area", share,
                   "Page is unusually dense with visual blocks", page=page["page"], scope="layout",
                   suggested_fix="Review block sizing and spacing; do not add or remove devices just to hit a quota.")
    # Eight repeated pages is a visual-rhythm warning, not the P0 duplicate-visual check.
    run, previous = [], None
    threshold = 6 if style["genre"] == "criticism" else 10 if style["genre"] == "essay" else 8
    for page in pages + [{"page": None, "elements": []}]:
        treatments = [style["visual_grammar"]["components"][_component_key(e.get("sub"))]["treatment"]
                      for e in page.get("elements", []) if _component_key(e.get("sub")) in style["visual_grammar"]["components"]]
        current = treatments[0] if treatments and len(set(treatments)) == 1 else None
        if current and current == previous and run and page["page"] == run[-1] + 1: run.append(page["page"])
        else:
            if len(run) >= threshold:
                _issue(checks, "visual_monotony", "medium", f"fewer than {threshold} repeated pages", run,
                       f"The same {previous} treatment repeats across {len(run)} pages", page=run[0], scope="layout",
                       suggested_fix="Vary the presentation of already planned devices where editorially justified.")
            run = [page["page"]] if current else []
        previous = current
    return {"status": "measured", "pages": len(pages), "area_accuracy": metrics.get("area_accuracy")}


def _hierarchy(style, observations, checks):
    groups = defaultdict(list)
    for item in observations or []:
        key = _component_key(item.get("component"))
        rule = style["visual_grammar"]["components"].get(key)
        if not rule: continue
        size = float(item.get("font_size_pt") or style["typography"]["callout"]["size_pt"])
        area = float(item.get("area_pt2") or 0)
        color = item.get("color") or style["palette"]["ink"]
        background = style["palette"]["background"]
        strength = size + min(area / 1000, 4) + min(contrast(color, background) / 4, 3)
        groups[rule["priority"]].append((strength, item))
    if groups.get("quiet") and groups.get("primary"):
        quiet = max(groups["quiet"], key=lambda pair: pair[0])
        primary = min(groups["primary"], key=lambda pair: pair[0])
        if quiet[0] > primary[0] * 1.18:
            _issue(checks, "hierarchy_drift", "medium", "primary stronger than quiet",
                   {"quiet": round(quiet[0], 2), "primary": round(primary[0], 2)},
                   "Quiet component has a stronger size/contrast/area proxy than a primary component",
                   page=quiet[1].get("page"), component=quiet[1].get("component"), scope="rendered")


def _generated_images(style, root, metrics, pdf, checks):
    """Connect VisualAsset provenance, style and PDF-built layout marks."""
    folder = root / "source/assets/generated"
    observed = []
    plan_path = root / "plan/assets-plan.yaml"
    plan = yaml_data(plan_path) if plan_path.is_file() else {}
    image_ids = {str(item.get("id")) for item in (plan.get("assets") or [])
                 if isinstance(item, dict) and item.get("type") == "image" and item.get("decision") != "rejected"}
    image_hashes = {}
    positions = defaultdict(list)
    for page in (metrics or {}).get("pages", []):
        for element in page.get("elements", []):
            if element.get("kind") == "figure" and element.get("label"):
                positions[element["label"]].append((page["page"], element))
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        if path.name.endswith(".request.json"): continue
        try: asset = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError): continue
        if asset.get("kind") != "generated-image": continue
        ident = asset.get("asset_id")
        if ident not in image_ids: continue
        request_path = folder / f"{ident}.request.json"
        try: request = json.loads(request_path.read_text(encoding="utf-8"))
        except (ValueError, OSError): request = {}
        if not request or request.get("art_direction", {}).get("palette") != style["palette"] or request.get("art_direction", {}).get("imagery") != style["imagery"]:
            _issue(checks, "image_asset_drift", "high", "current StyleBible image direction", request.get("art_direction"),
                   "Image request has stale or missing art direction", component=ident, scope="source")
        if request and request.get("semantic_role") not in style["imagery"].get("allowed_roles", []):
            _issue(checks, "image_asset_drift", "high", style["imagery"].get("allowed_roles"), request.get("semantic_role"),
                   "Image semantic role is not allowed by the StyleBible", component=ident, scope="source")
        if asset.get("generation_status") == "generated" and (asset.get("qa_status") != "pass" or not asset.get("accepted")):
            _issue(checks, "image_asset_drift", "high", "accepted print-safe asset", asset.get("qa_status"),
                   "Generated image is not accepted by image QA", component=ident, scope="source")
        import image_assets
        try: image_file = root / image_assets._safe_image_path(asset.get("file_path"))
        except ValueError:
            _issue(checks, "image_asset_drift", "high", "image under source/assets/images/", asset.get("file_path"),
                   "VisualAsset has an unsafe image path", component=ident, scope="source")
            continue
        if image_file.is_file():
            digest = hashlib.sha256(image_file.read_bytes()).hexdigest()
            if digest in image_hashes:
                _issue(checks, "image_asset_drift", "medium", "distinct image for distinct intent", image_hashes[digest],
                       "Identical generated image reused for another asset", component=ident, scope="source")
            image_hashes[digest] = ident
        if ident in positions:
            if len(positions[ident]) > 1:
                _issue(checks, "image_asset_drift", "medium", "one deliberate placement", len(positions[ident]),
                       "The same generated image repeats across the book", component=ident, scope="layout")
            page, element = positions[ident][0]
            geo = element.get("geometry") or {}
            rendered_width = geo.get("width_mm")
            expected_width = request.get("final_width_mm")
            if rendered_width is not None and expected_width is not None and abs(float(rendered_width) - float(expected_width)) > 2:
                _issue(checks, "image_asset_drift", "high" if abs(float(rendered_width) - float(expected_width)) > 5 else "medium",
                       expected_width, rendered_width, "Generated image width differs from its print request",
                       page=page, component=ident, scope="layout")
            if geo.get("placement") and request.get("placement") and geo["placement"] != request["placement"]:
                _issue(checks, "image_asset_drift", "medium", request["placement"], geo["placement"],
                       "Generated image placement differs from its print request", page=page, component=ident, scope="layout")
            x, y, end = element.get("x"), element.get("y"), element.get("end_y")
            mark_bbox = [x, y, end] if x is not None and y is not None else None
            candidates = (pdf["pages"][page - 1].get("images") or []) if pdf.get("status") == "measured" and page <= len(pdf["pages"]) else []
            matching = [image for image in candidates if image.get("bbox_pt") and y is not None and end is not None
                        and y - 3 <= image["bbox_pt"][1] <= end + 3]
            selected = min(matching, key=lambda image: abs((image["bbox_pt"][2] - image["bbox_pt"][0]) * 25.4 / 72 - float(expected_width or 0))) if matching else None
            pdf_bbox = selected["bbox_pt"] if selected else None
            if pdf.get("status") == "measured" and not selected:
                _issue(checks, "image_asset_drift", "high", "embedded image XObject", "missing",
                       "Generated image has no matching PDF image object", page=page, component=ident, scope="pdf")
            if selected and expected_width is not None:
                actual_width = (pdf_bbox[2] - pdf_bbox[0]) * 25.4 / 72
                actual_height = (pdf_bbox[3] - pdf_bbox[1]) * 25.4 / 72
                import image_assets
                expected_ratio = image_assets._ratio(request.get("preferred_aspect_ratio"))
                if expected_ratio and abs(actual_width / actual_height / expected_ratio - 1) > .08:
                    _issue(checks, "image_asset_drift", "high", request.get("preferred_aspect_ratio"),
                           round(actual_width / actual_height, 3), "PDF image aspect ratio differs from request",
                           page=page, component=ident, scope="pdf")
                if abs(actual_width - float(expected_width)) > 2:
                    _issue(checks, "image_asset_drift", "high" if abs(actual_width - float(expected_width)) > 5 else "medium",
                           expected_width, round(actual_width, 2), "PDF image width differs from request",
                           page=page, component=ident, scope="pdf")
                if selected.get("dimensions_px"):
                    pixels = selected["dimensions_px"]
                    dpi = min(pixels["width"] / actual_width, pixels["height"] / actual_height) * 25.4
                    if dpi < image_assets.MIN_DPI - .1:
                        _issue(checks, "image_asset_drift", "high", image_assets.MIN_DPI, round(dpi, 1),
                               "Embedded PDF image is below print DPI", page=page, component=ident, scope="pdf")
            observed.append({"asset_id": ident, "page": page, "layout_mark_pt": mark_bbox,
                             "pdf_image_bbox_pt": pdf_bbox, "pdf_image_pixels": selected.get("dimensions_px") if selected else None,
                             "planned_width_mm": expected_width, "rendered_width_mm": rendered_width,
                             "method": "Typst PDF image XObject and layout mark"})
    return observed


def audit(style, tokens, *, metrics=None, pdf_path=None, observations=None, root=None, check_source=True):
    root = Path(root or ROOT); checks = []
    if check_source: _check_source(style, tokens, checks, root)
    pdf = inspect_pdf(pdf_path) if pdf_path else {"status": "unavailable", "reason": "PDF not requested", "pages": []}
    measured_components = _pdf_components(style, metrics, pdf)
    _check_internal_padding(measured_components, checks)
    role_samples = _pdf_role_samples(metrics, pdf)
    _check_observations(style, tokens, list(observations or []) + measured_components + role_samples, checks)
    _hierarchy(style, list(observations or []) + measured_components, checks)
    image_geometry = _generated_images(style, root, metrics, pdf, checks)
    pdf_summary = _check_pdf(style, tokens, pdf, checks)
    pdf_summary["component_geometry"] = measured_components[:250]
    pdf_summary["role_samples"] = role_samples[:250]
    layout_summary = _check_metrics(style, metrics, checks)
    counts = {level: sum(item["severity"] == level for item in checks) for level in ("low", "medium", "high")}
    counts["status"] = "fail" if counts["high"] else "warn" if counts["medium"] else "pass"
    result = {"schema": SCHEMA, "style_id": style["id"], "genre": style["genre"],
            "inputs_fingerprint": style.get("inputs_fingerprint"), "summary": counts, "checks": checks,
            "measurement": {"source_level": "checked" if check_source else "not supplied",
                            "pdf_level": pdf_summary, "layout_level": layout_summary,
                            "generated_images": image_geometry},
            "scope_note": "PDF vector values are measured; semantic role assignment uses renderer marks or explicit observations."}
    schema = json.loads((ROOT / "schemas/art-direction-check.schema.json").read_text(encoding="utf-8"))
    validate_schema(result, schema)
    if any(item["category"] not in CATEGORIES for item in checks): raise ValueError("Unknown art direction QA category")
    return result


def run(style, tokens, *, pdf_path=None, metrics=None, path=None, root=None):
    root = Path(root or ROOT)
    if metrics is None:
        target = root / "reports/layout-metrics.json"
        if target.is_file():
            try: metrics = json.loads(target.read_text(encoding="utf-8"))
            except ValueError: pass
    if pdf_path is None and (root / "publish/book.pdf").is_file(): pdf_path = root / "publish/book.pdf"
    result = audit(style, tokens, metrics=metrics, pdf_path=pdf_path, root=root)
    waiver_path = root / "reports/art-direction-waivers.yaml"
    if waiver_path.is_file():
        waivers = (yaml_data(waiver_path) or {}).get("waivers") or []
        for waiver in waivers:
            if not isinstance(waiver, dict) or not waiver.get("category") or not str(waiver.get("reason") or "").strip():
                raise ValueError("Art direction waiver requires category and reason")
            for item in result["checks"]:
                if item["severity"] != "medium": continue
                if all(str(waiver.get(key)) == str(item.get(key)) for key in ("category", "page", "component") if key in waiver):
                    item["waiver"] = waiver["reason"]
        result["summary"]["waived_medium"] = sum(item.get("waiver") is not None for item in result["checks"])
        result["summary"]["medium_unwaived"] = result["summary"]["medium"] - result["summary"]["waived_medium"]
    result["build_fingerprint"] = fingerprint() if root == ROOT else None
    result["pdf_sha256"] = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest() if pdf_path and Path(pdf_path).is_file() else None
    write_yaml(path or root / "reports/art-direction-check.yaml", result,
               "Book-wide visual consistency; high blocks completion, medium is reviewable, low is informational.")
    return result


def compare_genres(styles, audits=None):
    if len(styles) < 2: raise ValueError("At least two resolved styles are required")
    values = list(styles.values())
    categories = ("components", "hierarchy", "rhythm", "table", "diagram", "chart", "caption", "chapter_opener")
    differences = {category: values[0]["visual_grammar"][category] != values[1]["visual_grammar"][category]
                   for category in categories}
    counts = sum(differences.values())
    check = []
    if counts < 4:
        _issue(check, "component_treatment_drift", "high", "4+ non-palette grammar differences", counts,
               "Cross-genre specimens differ mainly by palette")
    pdf_difference = None
    if audits is not None:
        measured = [(audits.get(name) or {}).get("measurement", {}).get("pdf_level", {}) for name in styles]
        if len(measured) != 2 or any(item.get("status") != "measured" for item in measured):
            _issue(check, "component_treatment_drift", "high", "two measured specimen PDFs", measured,
                   "Cross-genre PDF comparison is unavailable")
        else:
            pdf_difference = {key: measured[0].get(key) != measured[1].get(key)
                              for key in ("font_sizes_pt", "line_widths_pt", "strokes", "fills")}
            if not any(pdf_difference.values()):
                _issue(check, "component_treatment_drift", "high", "non-palette PDF differences", pdf_difference,
                       "The two rendered specimens differ only in palette")
    return {"schema": "bookorder/art-direction-comparison@1", "genres": list(styles),
            "same_layout_required": True, "non_palette_differences": differences,
            "pdf_non_palette_differences": pdf_difference,
            "summary": {"status": "fail" if check else "pass", "high": len(check), "medium": 0, "low": 0},
            "checks": check}

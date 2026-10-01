"""Layout-aware estimates and measured PDF page feedback; no agent/provider dependency."""
import hashlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

from common import ROOT, write_json


def length_mm(value, default):
    match = re.fullmatch(r"\s*([0-9.]+)\s*(mm|cm|pt|in)\s*", str(value or ""))
    return float(match[1]) * {"mm": 1, "cm": 10, "pt": 25.4 / 72, "in": 25.4}[match[2]] if match else default


def layout_inputs(project, design, resolved_layout=None, resolved_style=None):
    import layout_spec
    # Supplying a profile avoids the profile -> layout -> profile resolution cycle.
    raw_profile = project.get('profile')
    genre = raw_profile.get('genre', project.get('genre', 'general')) if isinstance(raw_profile, dict) else project.get('genre', 'general')
    layout = resolved_layout or layout_spec.resolve(project, profile={"genre": genre}, design=design)
    page, body = layout["page"], layout["body"]
    typography = (design.get("typography") or {}).get("body") or {}
    style_body = ((resolved_style or project.get("style_bible") or {}).get("typography") or {}).get("body") or {}
    return {"page": page, "body": body, "writing_mode": layout["writing_mode"],
            "font_size_mm": float(style_body["size_pt"]) * 25.4 / 72 if "size_pt" in style_body else length_mm(typography.get("size"), 10 * 25.4 / 72),
            "line_height": float(style_body.get("line_height", typography.get("line_height", 1.7))),
            "font_family": style_body.get("family") or typography.get("family") or typography.get("japanese"),
            "style_request": {k: project.get(k) for k in ("style_preset", "style_controls")}}


def estimated_capacity(inputs, baseline):
    """Scale an A5 10pt/1.7 baseline by usable area and line pitch. Columns do not double page area."""
    page, body = inputs["page"], inputs["body"]
    width = page["width_mm"] - page["margin_inner_mm"] - page["margin_outer_mm"]
    height = page["height_mm"] - page["margin_top_mm"] - page["margin_bottom_mm"]
    usable = width - body["gutter_mm"] * (body["columns"] - 1)
    reference_area = (148 - 20 - 17) * (210 - 18 - 20)
    font = inputs["font_size_mm"]
    return max(100, round(baseline * usable * height / reference_area * (10 * 25.4 / 72 / font) ** 2 * 1.7 / inputs["line_height"]))


def pdf_pages(path):
    """Read actual PDF page objects, independent of layout marks (including trailing blank pages).

    Supports the uncompressed page dictionaries produced by the bundled Typst. Other PDFs use pdfinfo
    if available; compressed object trees without that tool return an explicit error.
    """
    path = Path(path)
    data = path.read_bytes()
    if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
        raise ValueError("PDF is missing a valid header/end marker")
    from pdf_visual_probe import OBJECT, PAGE
    objects = list(OBJECT.finditer(data))
    if not any(re.search(rb"/Type\s*/ObjStm\b", m[2]) for m in objects):
        count = sum(bool(PAGE.search(m[2].split(b"stream", 1)[0])) for m in objects)
        tree_counts = [int(n) for m in objects if re.search(rb"/Type\s*/Pages\b", m[2])
                       for n in re.findall(rb"/Count\s+(\d+)\b", m[2])]
        if count and tree_counts and max(tree_counts) == count:
            return count, "pdf-page-tree"
    executable = shutil.which("pdfinfo")
    if executable:
        result = subprocess.run([executable, str(path)], capture_output=True, text=True, check=True)
        match = re.search(r"(?m)^Pages:\s*(\d+)\s*$", result.stdout)
        if match: return int(match[1]), "pdfinfo"
    raise ValueError("PDF page tree cannot be measured; provide pdfinfo for this PDF encoding")


def measure(project, pdf_path=None, root=None):
    root = Path(root or ROOT); path = Path(pdf_path or root / "publish/book.pdf")
    target = (project.get("book") or {}).get("target_pages")
    if target is not None and (isinstance(target, bool) or int(target) != float(target) or int(target) <= 0):
        raise ValueError('target_pages must be a positive integer')
    options = project.get("page_feedback") or {}
    ratio = float(options.get("tolerance_ratio", .15)); absolute = int(options.get("tolerance_pages", 3))
    if not 0 <= ratio <= 1 or absolute < 0: raise ValueError("Invalid page_feedback tolerance")
    result = {"schema": "bookorder/page-count@1", "target_pages": int(target) if target else None,
              "actual_pages": None, "difference": None, "difference_ratio": None,
              "tolerance_pages": max(absolute, math.ceil(int(target) * ratio)) if target else None,
              "status": "unavailable", "pdf": "publish/book.pdf"}
    try:
        actual, method = pdf_pages(path)
        result.update(actual_pages=actual, method=method, pdf_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if target:
            difference = actual - int(target)
            result.update(difference=difference, difference_ratio=round(difference / int(target), 4),
                          status="within_target" if abs(difference) <= result["tolerance_pages"] else "over_target" if difference > 0 else "under_target")
        else: result["status"] = "measured"
    except (OSError, ValueError, subprocess.SubprocessError) as exc: result["error"] = str(exc)
    write_json(root / "reports/page-count.json", result)
    return result


def summary(result):
    if result.get("actual_pages") is None: return "PDF pages: unavailable — " + result.get("error", "not rendered")
    line = f"PDF pages: {result['actual_pages']}"
    if result.get("target_pages"):
        line += f" / target {result['target_pages']} (difference {result['difference']:+d}, {result['difference_ratio']:+.1%}; {result['status']})"
    return line

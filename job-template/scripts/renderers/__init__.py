"""Renderer interface and explicit LayoutSpec capability negotiation."""
from typing import Protocol
from pathlib import Path

class PdfRenderer(Protocol):
    def render(self, ir: dict, tokens: dict, output: Path, layout: dict) -> None: ...


CAPABILITIES = {
    "typst": {"writing_modes": ["horizontal-tb"], "columns": {"max": 2},
              "spans": {"figure": [1, 2, "full"], "table": [1, 2, "full"], "callout": [1, 2, "full"],
                        "quote": [1], "code": [1], "equation": [1]},
              "vertical_text": False, "margin_notes": False},
    "html": {"writing_modes": ["horizontal-tb"], "columns": {"max": 1}, "spans": {}, "vertical_text": False, "margin_notes": False},
    "epub": {"writing_modes": ["horizontal-tb"], "columns": {"max": 1}, "spans": {}, "vertical_text": False, "margin_notes": False},
    "docx": {"writing_modes": ["horizontal-tb"], "columns": {"max": 1}, "spans": {}, "vertical_text": False, "margin_notes": False},
}


def assess_layout(name, layout):
    """Return supported/degraded/unsupported with concrete reasons for this renderer."""
    if name not in CAPABILITIES: raise ValueError(f"Unknown layout renderer {name}")
    cap = CAPABILITIES[name]; unsupported = []; degraded = []
    mode = layout["writing_mode"]; columns = layout["body"]["columns"]
    if mode not in cap["writing_modes"]:
        unsupported.append(f"writing_mode {mode} is not supported by {name}")
    if layout["text_direction"] != "ltr":
        unsupported.append(f"text_direction {layout['text_direction']} is not supported by {name} in this adapter")
    if columns > cap["columns"]["max"]:
        message = f"{columns} body columns exceed {name} maximum {cap['columns']['max']}"
        (unsupported if name == "typst" else degraded).append(message + ("; output remains single-column" if name != "typst" else ""))
    if layout["regions"]["margin_notes"]["enabled"] and not cap["margin_notes"]:
        unsupported.append(f"margin notes are not supported by {name}")
    if layout["page"]["bleed_mm"] and name == "typst":
        unsupported.append("nonzero page bleed is not supported by Typst adapter")
    if name == "typst":
        for key in ("baseline_grid", "column_balance"):
            if layout["body"][key] != "none": unsupported.append(f"body.{key}={layout['body'][key]} is not supported by Typst adapter")
        for kind, span in layout["spans"].items():
            if span not in cap["spans"][kind]: unsupported.append(f"default {kind} span {span} is not supported by Typst adapter")
        if columns > 1 and not layout["regions"]["full_width"]["enabled"] and any(
            value != 1 for value in layout["spans"].values()):
            unsupported.append("multi-column spans require regions.full_width.enabled")
    elif columns > 1 or any(value != 1 for value in layout["spans"].values()):
        degraded.append("column and span geometry is not applied to this output")
    status = "unsupported" if unsupported else "degraded" if degraded else "supported"
    return {"status": status, "reasons": unsupported + degraded, "capabilities": cap}


def assess_outputs(layout, outputs, pdf_backend="typst"):
    mapping = {"pdf": pdf_backend, "semantic_html": "html", "static_site": "html", "epub": "epub", "docx": "docx"}
    result = {output: assess_layout(name, layout) for output, name in mapping.items() if outputs.get(output)}
    failed = {output: entry["reasons"] for output, entry in result.items() if entry["status"] == "unsupported"}
    return {"schema": "bookorder/layout-capabilities@1", "layout_id": layout["id"], "renderers": result,
            "ok": not failed, "errors": failed}

def renderer(name):
    # New adapters register here; no backend-specific values enter IR/schema.
    if name == 'typst':
        from .typst import TypstRenderer
        return TypstRenderer()
    raise ValueError(f'PDF backend not installed: {name}')

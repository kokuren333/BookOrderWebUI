"""Print-size matplotlib charts for BookOrder books.

A chart is drawn at the size it will be printed (from its `geometry:` in plan/assets-plan.yaml, default: the text
column) with the book's figure tokens, so the book never has to shrink it. Use it from a chart script:

    import sys; sys.path.insert(0, "scripts")
    import chartkit
    fig, ax = chartkit.figure("fig-rr-vs-arr")        # size and typography from the plan and design tokens
    ax.barh(...)
    chartkit.save(fig, "source/assets/figures/rr-vs-arr.svg", "fig-rr-vs-arr")

`save` refuses a chart whose smallest text would print below `min_label_pt`, writes SVG with real text (so the
build can measure it), and records the render size next to the file (`<file>.render.json`).
matplotlib is only needed by chart scripts; the rest of BookOrder does not import it.
"""
from datetime import datetime, timezone
import json
from pathlib import Path

from figure_spec import PT_PER_MM, figure_tokens, planned_geometry, resolve

MM_PER_IN = 25.4
FALLBACK_FONTS = ["Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic", "Hiragino Sans", "Yu Gothic", "DejaVu Sans"]


def _design():
    try:
        from design import load_design
        from common import ROOT, yaml_data
        from style_bible import compile_tokens
        design = load_design()
        style_path = ROOT / "plan/style-bible.yaml"
        layout_path = ROOT / "plan/layout-spec.yaml"
        if style_path.is_file() and layout_path.is_file():
            from layout_spec import apply_to_tokens
            layout = yaml_data(layout_path)
            return compile_tokens(yaml_data(style_path), layout, apply_to_tokens(design, layout))
        return design
    except Exception:
        return {}


def spec(asset_id=None, tokens=None, **geometry):
    """Resolved print geometry and figure tokens for one chart. Keyword geometry overrides the plan."""
    tokens = tokens if tokens is not None else _design()
    declared = dict(planned_geometry().get(asset_id, {})) if asset_id else {}
    declared.update({k: v for k, v in geometry.items() if v is not None})
    resolved = resolve(declared, tokens, "chart")
    return {"geometry": resolved, "tokens": figure_tokens(tokens)}


def palette(ft):
    colors = ft.get("colors", {})
    ordered = [colors.get(k) for k in ("primary", "accent", "muted", "secondary")]
    return [c for c in ordered if c] or ["#2F6B55", "#B5651D", "#6B7477", "#A9B1B3"]


def grammar_params(ft):
    """Pure chart grammar adapter, usable even when matplotlib is not installed."""
    grammar = ft.get("chart_grammar") or {}
    grid = grammar.get("grid_intensity", "light")
    axis = grammar.get("axis_emphasis", "regular")
    baseline = grammar.get("baseline_emphasis", "regular")
    return {"axes.linewidth": ft["strong_pt"] if axis == "strong" else ft["hairline_pt"],
            "grid.linewidth": ft["hairline_pt"] * (.6 if grid == "light" else 1),
            "grid.alpha": 0 if grid == "none" else .25 if grid == "light" else .5,
            "axes.spines.bottom": baseline != "none", "axes.grid": grid != "none"}


def rc_params(ft):
    """matplotlib rcParams in printed points; the same tokens drive Diagram IR and Typst."""
    return {
        "svg.fonttype": "none", "pdf.fonttype": 42,
        "font.family": "sans-serif", "font.sans-serif": list(dict.fromkeys(ft["font_families"] + FALLBACK_FONTS)),
        "font.size": ft["annotation_pt"], "axes.titlesize": ft["preferred_label_pt"], "axes.labelsize": ft["axis_label_pt"],
        "xtick.labelsize": ft["tick_label_pt"], "ytick.labelsize": ft["tick_label_pt"], "legend.fontsize": ft["legend_pt"],
        "legend.title_fontsize": ft["legend_pt"], "figure.titlesize": ft["preferred_label_pt"],
        "patch.linewidth": ft["hairline_pt"],
        "lines.linewidth": ft["strong_pt"], "lines.markersize": ft["marker_size_pt"],
        "xtick.major.width": ft["hairline_pt"], "ytick.major.width": ft["hairline_pt"], "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "xtick.minor.size": 1.5, "ytick.minor.size": 1.5, "axes.labelpad": 2.5, "xtick.major.pad": 2, "ytick.major.pad": 2,
        "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
        "axes.prop_cycle": __import__("matplotlib").cycler(color=palette(ft)),
        "axes.edgecolor": ft.get("colors", {}).get("text", "#222222"), "text.color": ft.get("colors", {}).get("text", "#222222"),
        "axes.labelcolor": ft.get("colors", {}).get("text", "#222222"),
        "figure.constrained_layout.use": True, "figure.constrained_layout.h_pad": 0.02, "figure.constrained_layout.w_pad": 0.02,
        "savefig.bbox": "standard", "savefig.dpi": 300, "savefig.transparent": False,
        **grammar_params(ft),
    }


def figure(asset_id=None, nrows=1, ncols=1, tokens=None, **geometry):
    """A matplotlib figure at printed size with book typography. Returns (fig, axes)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    chart = spec(asset_id, tokens, **geometry)
    g = chart["geometry"]; height = g["height_mm"] or g["width_mm"] / 1.6
    plt.rcParams.update(rc_params(chart["tokens"]))
    fig, axes = plt.subplots(nrows, ncols, figsize=(g["width_mm"] / MM_PER_IN, height / MM_PER_IN))
    fig._bookorder = {"asset": asset_id, **chart}
    return fig, axes


def text_sizes(fig):
    """(points, text) for every visible, non-empty text the figure will print, at its drawn size."""
    import matplotlib.text
    fig.canvas.draw()
    return sorted((float(t.get_fontsize()), t.get_text().strip()[:40]) for t in fig.findobj(matplotlib.text.Text)
                  if t.get_visible() and t.get_text().strip() and t.get_figure() is fig)


def save(fig, path, asset_id=None):
    """Save at printed size (no tight bounding box), refuse text below min_label_pt, write the render record."""
    import matplotlib
    meta = getattr(fig, "_bookorder", None) or {"asset": asset_id, **spec(asset_id)}
    asset_id = asset_id or meta.get("asset"); ft = meta["tokens"]
    sizes = text_sizes(fig)
    small = [(pt, text) for pt, text in sizes if pt < ft["min_label_pt"] - 0.01]
    if small:
        raise ValueError(f"{asset_id or path}: text below {ft['min_label_pt']}pt at printed size: "
                         + ", ".join(f"{text!r} {pt:g}pt" for pt, text in small[:6]))
    width_in, height_in = fig.get_size_inches()
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format=path.suffix.lstrip(".").lower() or "svg")
    record = {"schema": "bookorder/figure-render@1", "asset": asset_id, "renderer": f"matplotlib {matplotlib.__version__}",
              "width_mm": round(width_in * MM_PER_IN, 2), "height_mm": round(height_in * MM_PER_IN, 2),
              "placement": meta["geometry"]["placement"], "min_text_pt": sizes[0][0] if sizes else None,
              "max_text_pt": sizes[-1][0] if sizes else None, "min_label_pt": ft["min_label_pt"],
              "token_sources": ft["sources"], "chart_grammar": ft.get("chart_grammar") or {},
              "series_count": max((len(ax.get_legend_handles_labels()[1]) for ax in fig.axes), default=0),
              "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
    path.with_name(path.name + ".render.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def width_pt(asset_id=None, **geometry):
    """Printed width in points (for scripts that draw SVG by hand)."""
    return spec(asset_id, **geometry)["geometry"]["width_mm"] * PT_PER_MM

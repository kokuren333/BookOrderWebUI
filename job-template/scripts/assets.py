"""Figure / table / equation / image planning through stable asset IDs, and realization checks."""
import json
from pathlib import Path

from common import ROOT, read_project, yaml_data, write_yaml, as_list
import research

PLAN_FILE = ROOT / "plan/assets-plan.yaml"
TYPES = {"diagram": "fig-", "chart": "fig-", "image": "fig-", "screenshot": "fig-", "table": "tbl-", "equation": "eq-", "cover": "cover"}
POLICY = {"diagram": "diagrams", "chart": "charts", "table": "tables", "image": "generative_images"}
GENERATED_META = ROOT / "source/assets/generated"


def load_plan():
    if not PLAN_FILE.is_file(): return None
    data = yaml_data(PLAN_FILE)
    return data


def assets(plan=None):
    plan = plan if plan is not None else load_plan() or {}
    return [a for a in as_list(plan.get("assets")) if isinstance(a, dict)]


def check_plan(chapters, project=None):
    project = project or read_project(); errors = []
    plan = load_plan()
    if plan is None: return ["Missing plan/assets-plan.yaml"]
    items = assets(plan)
    if not items and not research.nonempty(plan.get("none_needed"), 20): errors.append("assets-plan.yaml: plan assets, or explain none_needed (20+ characters)")
    chapter_ids = {c["id"] for c in chapters}; ids = []
    policy = project.get("figures", {})
    for asset in items:
        identifier = str(asset.get("id") or ""); kind = asset.get("type"); ids.append(identifier)
        if kind not in TYPES: errors.append(f"{identifier}: type must be one of {', '.join(TYPES)}"); continue
        if not identifier.startswith(TYPES[kind]): errors.append(f"{identifier}: {kind} asset IDs must start with {TYPES[kind]}")
        if kind != "cover" and asset.get("chapter") not in chapter_ids: errors.append(f"{identifier}: unknown chapter {asset.get('chapter')}")
        if not research.nonempty(asset.get("purpose"), 10): errors.append(f"{identifier}: purpose must say what the reader gains")
        if kind not in ("equation",) and not research.nonempty(asset.get("caption"), 3): errors.append(f"{identifier}: caption is required")
        if not research.nonempty(asset.get("provenance"), 3): errors.append(f"{identifier}: provenance is required")
        if POLICY.get(kind) and policy.get(POLICY[kind]) is False: errors.append(f"{identifier}: project figure policy disables {POLICY[kind]}")
        if kind == "diagram" and not str(asset.get("source", "")).startswith("source/assets/diagrams/"): errors.append(f"{identifier}: diagram source must be source/assets/diagrams/<name>.yaml (Diagram IR)")
        if kind in ("image", "cover") and not research.nonempty(asset.get("prompt"), 10) and kind == "image": errors.append(f"{identifier}: generated images need a prompt")
        if kind in ("chart", "image", "screenshot", "cover") and not str(asset.get("path", "")).startswith("source/assets/"): errors.append(f"{identifier}: path must be under source/assets/")
    if len(ids) != len(set(ids)): errors.append("assets-plan.yaml: asset IDs must be unique")
    for chapter in chapters:
        for expected in chapter["expected_assets"]:
            if expected not in ids: errors.append(f"{chapter['id']}: expected asset {expected} from outline.yaml is not planned")
    return errors


def diagram_output(asset):
    return "source/assets/figures/" + Path(asset["source"]).stem + ".svg"


def check_generation(chapters, records):
    """Every planned asset exists as a file (when it has one) and appears in its planned chapter."""
    from manuscript import by_chapter
    errors = []; mapped = by_chapter(records, chapters)
    image_paths = {}
    for chapter_id, record in mapped.items():
        if record:
            from common import walk
            for node in walk(record["ast"]["blocks"]):
                if node["t"] == "Figure":
                    for inner in walk(node["c"][2]):
                        if inner["t"] == "Image": image_paths[node["c"][0][0]] = inner["c"][2][0]
    for asset in assets():
        identifier = asset.get("id"); kind = asset.get("type"); chapter = mapped.get(asset.get("chapter"))
        if kind == "diagram":
            source = ROOT / str(asset.get("source"))
            if not source.is_file(): errors.append(f"{identifier}: Diagram IR {asset.get('source')} is missing"); continue
            if chapter and image_paths.get(identifier) != diagram_output(asset):
                errors.append(f"{identifier}: {asset.get('chapter')} must contain ![caption]({diagram_output(asset)}){{#{identifier}}}")
        elif kind in ("chart", "image", "screenshot"):
            path = ROOT / str(asset.get("path"))
            if not path.is_file(): errors.append(f"{identifier}: {asset.get('path')} does not exist")
            if kind == "chart" and not (asset.get("data") and (ROOT / str(asset.get("data"))).is_file()): errors.append(f"{identifier}: charts need their data file (data: source/assets/data/...)")
            if kind == "image":
                meta = GENERATED_META / f"{identifier}.json"
                if not meta.is_file(): errors.append(f"{identifier}: record generation metadata in source/assets/generated/{identifier}.json (prompt, generator, created_at)")
            if chapter and image_paths.get(identifier) != asset.get("path"): errors.append(f"{identifier}: {asset.get('chapter')} must show {asset.get('path')} with {{#{identifier}}}")
        elif kind == "cover":
            if not (ROOT / str(asset.get("path"))).is_file(): errors.append(f"cover: {asset.get('path')} does not exist")
        elif kind == "table":
            if not chapter or identifier not in chapter["tables"]: errors.append(f"{identifier}: table with caption ID {identifier} missing from {asset.get('chapter')}")
        elif kind == "equation":
            if not chapter or identifier not in chapter["equations"]: errors.append(f"{identifier}: ::: {{.equation #{identifier}}} missing from {asset.get('chapter')}")
    return errors


def unplanned(records):
    planned = {a.get("id") for a in assets()}
    found = []
    for record in records.values():
        for identifier in record["figures"] + [t for t in record["tables"] if t] + [e for e in record["equations"] if e]:
            if identifier not in planned: found.append((record["id"], identifier))
    return found


def sync_figure_registry():
    """source/metadata/figures.yaml is derived from the asset plan (kept for validators and DTP)."""
    figures = []
    for asset in assets():
        if asset.get("type") in ("diagram", "chart", "image", "screenshot"):
            path = diagram_output(asset) if asset.get("type") == "diagram" else asset.get("path")
            figures.append({"id": asset.get("id"), "chapter": asset.get("chapter"), "type": asset.get("type"), "path": path,
                            "caption": asset.get("caption"), "provenance": asset.get("provenance")})
    write_yaml(ROOT / "source/metadata/figures.yaml", {"figures": figures}, "Generated from plan/assets-plan.yaml. Edit the plan, not this file.")
    return figures

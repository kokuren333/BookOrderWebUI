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
        if kind == "image" and not research.nonempty(asset.get("subject") or asset.get("prompt"), 10):
            errors.append(f"{identifier}: generated images need a provider-neutral subject (or legacy prompt)")
        if kind in ("chart", "image", "screenshot", "cover") and not str(asset.get("path", "")).startswith("source/assets/"): errors.append(f"{identifier}: path must be under source/assets/")
        from visual_review import completeness
        missing = completeness(asset)
        if missing: errors.append(f"{identifier}: visual candidate needs {', '.join(missing)} (skills/design/figures.md)")
        if "geometry" in asset:
            from figure_spec import check_geometry
            errors.extend(f"{identifier}: {message}" for message in check_geometry(asset["geometry"]))
    if len(ids) != len(set(ids)): errors.append("assets-plan.yaml: asset IDs must be unique")
    for chapter in chapters:
        for expected in chapter["expected_assets"]:
            if expected not in ids: errors.append(f"{chapter['id']}: expected asset {expected} from outline.yaml is not planned")
    errors += uploaded_asset_errors(plan, items, chapters, project)
    import editorial_plan
    linked = {str(a.get("device") or a.get("id")) for a in items}
    for chapter, device in editorial_plan.visual_devices(chapters):
        if device["id"] not in linked:
            errors.append(f"{device['id']}: the editorial plan of {chapter} has a {device['type']} intent here with no candidate (id {device['id']} or device: {device['id']})")
    return errors


UPLOAD_DECISIONS = ("placed", "redrawn", "reference_only", "not_used")


def uploaded_asset_errors(plan, items, chapters, project):
    """Every uploaded asset the user gave a role is considered, and its instruction is respected (plan/uploaded-assets.yaml)."""
    import source_roles
    errors = []
    uploads = {a["id"]: a for a in source_roles.uploaded_assets(project)}
    decisions = {str(d.get("asset")): d for d in as_list(plan.get("uploaded_assets")) if isinstance(d, dict)}
    by_id = {str(a.get("id")): a for a in items}
    for asset in uploads.values():
        d = decisions.get(asset["id"])
        placed_as = [a for a in items if str(a.get("uploaded_asset") or "") == asset["id"]]
        if asset["role"] in ("layout_reference", "style_reference", "visual_reference"):
            if placed_as: errors.append(f"{asset['id']} is a {asset['role']} (composition/appearance only) and cannot be placed in the book ({', '.join(str(a.get('id')) for a in placed_as)})")
            continue
        if not asset["requires_decision"]: continue
        note = f" — user: \"{asset['instruction']}\"" if asset.get("instruction") else ""
        if not d:
            errors.append(f"{asset['id']} ({asset['label']}, {asset['asset_role']}): record uploaded_assets: [{{asset: {asset['id']}, decision: {'|'.join(UPLOAD_DECISIONS)}, "
                          f"asset_id, chapter, reason}}] in plan/assets-plan.yaml{note}")
            continue
        decision = d.get("decision")
        if decision not in UPLOAD_DECISIONS: errors.append(f"{asset['id']}: decision must be one of {', '.join(UPLOAD_DECISIONS)}"); continue
        if not research.nonempty(d.get("reason"), 5): errors.append(f"{asset['id']}: reason is required (how the user's instruction was followed){note}")
        target = by_id.get(str(d.get("asset_id") or ""))
        if decision in ("placed", "redrawn") and not target: errors.append(f"{asset['id']}: {decision} needs asset_id of the planned figure/table in plan/assets-plan.yaml")
        if decision == "placed" and target:
            if str(target.get("uploaded_asset") or "") != asset["id"]: errors.append(f"{target.get('id')}: set uploaded_asset: {asset['id']}")
            if target.get("type") in ("chart", "image", "screenshot", "cover") and str(target.get("path")) != asset["placeable_path"]:
                errors.append(f"{target.get('id')}: path must be {asset['placeable_path']} (the uploaded file)")
            if target.get("type") == "cover" and asset["asset_role"] != "cover_candidate": errors.append(f"{asset['id']} is not a cover candidate; the user did not offer it for the cover")
        if decision == "redrawn" and not asset.get("redraw_allowed"): errors.append(f"{asset['id']}: the user did not allow redrawing this file")
        if decision == "placed" and asset["asset_role"] in ("diagram_source", "table_source", "redraw_source") and asset.get("use_verbatim") is False:
            errors.append(f"{asset['id']}: the user asked to redraw the information, not to paste the file (decision redrawn)")
        wanted = source_roles.chapter_ref(asset.get("intended_chapter"), chapters)
        if decision in ("placed", "redrawn") and target and wanted and target.get("chapter") != wanted and not research.nonempty(d.get("deviation_reason"), 10):
            errors.append(f"{asset['id']}: the user wants it in {wanted} but {target.get('id')} is in {target.get('chapter')}; move it or give deviation_reason")
        if decision == "not_used" and asset.get("priority") == "high" and not research.nonempty(d.get("reason"), 20):
            errors.append(f"{asset['id']}: a high-priority upload is not used; explain why in reason (20+ characters)")
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
    import visual_review
    decided = visual_review.decisions() or {}
    for asset in assets():
        identifier = asset.get("id"); kind = asset.get("type"); chapter = mapped.get(asset.get("chapter"))
        decision = decided.get(str(identifier), "accepted")
        if decision != "accepted":
            # Rejected and pending candidates stay in the plan but are not generated and may not be printed.
            if chapter and (identifier in chapter["figures"] or identifier in [t for t in chapter["tables"] if t]):
                reasons = next((c["rejection_reasons"] for c in visual_review.run(write=False)["candidates"] if c["id"] == str(identifier)), [])
                hint = "; ".join(f"{r['code']}: {r.get('suggestion') or r['detail']}" for r in reasons[:2])
                errors.append(f"{identifier}: {decision} visual is still in {asset.get('chapter')}; replace it in the text" + (f" ({hint})" if hint else ""))
            continue
        if kind == "diagram":
            source = ROOT / str(asset.get("source"))
            if not source.is_file(): errors.append(f"{identifier}: Diagram IR {asset.get('source')} is missing"); continue
            if chapter and image_paths.get(identifier) != diagram_output(asset):
                errors.append(f"{identifier}: {asset.get('chapter')} must contain ![caption]({diagram_output(asset)}){{#{identifier}}}")
        elif kind in ("chart", "image", "screenshot"):
            if kind == "image" and str(asset.get("optional", "")).lower() in ("true", "yes", "1") and image_paths.get(identifier) is None:
                continue
            path = ROOT / str(asset.get("path"))
            if not path.is_file(): errors.append(f"{identifier}: {asset.get('path')} does not exist")
            if kind == "chart" and not (asset.get("data") and (ROOT / str(asset.get("data"))).is_file()): errors.append(f"{identifier}: charts need their data file (data: source/assets/data/...)")
            if kind == "image":
                meta = GENERATED_META / f"{identifier}.json"
                if not meta.is_file(): errors.append(f"{identifier}: VisualAsset metadata is missing")
                else:
                    try: record = json.loads(meta.read_text(encoding="utf-8"))
                    except ValueError: record = {}
                    if record.get("generation_status") != "generated" or record.get("qa_status") != "pass" or not record.get("accepted"):
                        errors.append(f"{identifier}: generated image is pending, failed or rejected by image QA")
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
    import visual_review
    figures = []; decided = visual_review.decisions() or {}
    for asset in assets():
        if asset.get("type") in ("diagram", "chart", "image", "screenshot"):
            path = diagram_output(asset) if asset.get("type") == "diagram" else asset.get("path")
            entry = {"id": asset.get("id"), "chapter": asset.get("chapter"), "type": asset.get("type"), "path": path,
                     "caption": asset.get("caption"), "provenance": asset.get("provenance"), "decision": decided.get(str(asset.get("id")), "accepted")}
            if isinstance(asset.get("geometry"), dict): entry["geometry"] = asset["geometry"]
            figures.append(entry)
    write_yaml(ROOT / "source/metadata/figures.yaml", {"figures": figures}, "Generated from plan/assets-plan.yaml. Edit the plan, not this file.")
    return figures

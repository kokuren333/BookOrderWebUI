"""Source Classifier: SOURCE_ROLE and SOURCE_AUTHORITY for every source, and the uploaded-asset registry.

Inputs are never all "sources". project.json keeps two lists (written by the WebUI):

    input.sources[]  content files (evidence, background, structure_reference, redraw_source …) → research registry
    input.assets[]   files that are NOT content (layout / style / visual references, figures, logos, cover
                     candidates, chapter openers …) → plan/uploaded-assets.yaml, never ingested, never citable

Each entry may carry `usage` (label, role, asset_role, authority, citation_allowed, intended_usage, intended_chapter,
intended_section, priority, caption, crop_allowed, redraw_allowed, transform_allowed, use_verbatim, notes,
role_origin: user | inferred). The user's explicit role and authority win; otherwise the agent's estimate in
research/notes/<id>.yaml (`source_role`, `authority`); otherwise the default (evidence, unknown authority).
Authority is advisory: role, the user's choices and context decide what may be cited.

plan/source-roles.yaml is the resolved table (generated, deterministic).
"""
import json
import shutil

from common import ROOT, as_list, read_project, write_yaml

VOCAB = json.loads((ROOT / "schemas/publication-architecture.json").read_text(encoding="utf-8"))
ROLES = VOCAB["source_roles"]
AUTHORITY = VOCAB["source_authority"]
ASSET_ROLES = VOCAB["asset_roles"]
CITABLE = tuple(VOCAB["citable_roles"])
TABLE = ROOT / "plan/source-roles.yaml"
ASSETS = ROOT / "plan/uploaded-assets.yaml"
UPLOADED_DIR = ROOT / "source/assets/uploaded"
USAGE_FLAGS = ("crop_allowed", "redraw_allowed", "transform_allowed", "use_verbatim", "citation_allowed")
# Roles that ask the asset planner for an explicit decision (placed / redrawn / not used, with the reason).
DECISION_ROLES = ("cover_candidate", "chapter_opener", "inline_figure", "diagram_source", "table_source", "background_motif", "logo", "redraw_source")


def _bool(value):
    if isinstance(value, bool): return value
    if isinstance(value, str) and value.lower() in ("true", "false"): return value.lower() == "true"
    return None


def usage(entry):
    raw = (entry or {}).get("usage") if isinstance((entry or {}).get("usage"), dict) else {}
    out = {k: raw.get(k) for k in ("label", "role", "asset_role", "authority", "intended_usage", "intended_chapter", "intended_section",
                                   "priority", "caption", "notes", "role_origin") if raw.get(k) not in (None, "")}
    for flag in USAGE_FLAGS:
        value = _bool(raw.get(flag))
        if value is not None: out[flag] = value
    return out


def validate_usage(item, where):
    errors = []
    u = usage(item)
    if u.get("role") and u["role"] not in ROLES: errors.append(f"{where}: role {u['role']!r} is not one of {', '.join(ROLES)}")
    if u.get("asset_role") and u["asset_role"] not in ASSET_ROLES: errors.append(f"{where}: asset_role {u['asset_role']!r} is not one of {', '.join(ASSET_ROLES)}")
    if u.get("authority") and u["authority"] not in AUTHORITY: errors.append(f"{where}: authority {u['authority']!r} is not one of {', '.join(AUTHORITY)}")
    if u.get("role") and not ROLES[u["role"]]["content"] and where.startswith("input.sources"):
        errors.append(f"{where}: role {u['role']} is not content; the file belongs in input.assets")
    return errors


# ---------------------------------------------------------------- uploaded assets

def uploaded_assets(project=None):
    """Every uploaded non-content file (and every content file that also has an asset role) with a stable id."""
    project = project if project is not None else read_project()
    items = []
    entries = [("assets", e) for e in as_list((project.get("input") or {}).get("assets"))]
    entries += [("sources", e) for e in as_list((project.get("input") or {}).get("sources")) if usage(e).get("asset_role")]
    for number, (origin, entry) in enumerate(entries, 1):
        if not isinstance(entry, dict): continue
        u = usage(entry)
        asset_role = u.get("asset_role") or {"layout_reference": "layout_reference", "style_reference": "style_reference",
                                             "visual_reference": "visual_reference", "redraw_source": "redraw_source"}.get(u.get("role"), "inline_figure")
        role = u.get("role") if u.get("role") in ROLES and origin == "assets" else ASSET_ROLES[asset_role]["source_role"]
        items.append({"id": entry.get("id") or f"asset-{number:03d}", "path": entry.get("path"), "original_name": entry.get("original_name"),
                      "label": u.get("label") or entry.get("original_name"), "role": role, "asset_role": asset_role,
                      "also_content": origin == "sources", "intended_usage": u.get("intended_usage"), "intended_chapter": u.get("intended_chapter"),
                      "intended_section": u.get("intended_section"), "priority": u.get("priority") or "normal", "caption": u.get("caption"),
                      "crop_allowed": u.get("crop_allowed", True), "redraw_allowed": u.get("redraw_allowed", role in ("redraw_source", "visual_reference")),
                      "transform_allowed": u.get("transform_allowed", True), "use_verbatim": u.get("use_verbatim", asset_role in ("inline_figure", "logo")),
                      "instruction": u.get("notes"), "role_origin": u.get("role_origin") or "user",
                      "requires_decision": asset_role in DECISION_ROLES,
                      "placeable_path": f"source/assets/uploaded/{(entry.get('path') or '').rsplit('/', 1)[-1]}" if ROLES[role]["group"] == "visual" or asset_role in DECISION_ROLES else None})
    return items


def write_asset_registry(project=None):
    """plan/uploaded-assets.yaml, and placeable uploads copied to source/assets/uploaded/ (never content sources)."""
    project = project if project is not None else read_project()
    items = uploaded_assets(project)
    for item in items:
        if item.get("placeable_path") and item.get("path"):
            src = ROOT / item["path"]; dest = ROOT / item["placeable_path"]
            if src.is_file() and (not dest.is_file() or dest.stat().st_size != src.stat().st_size):
                dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dest)
    write_yaml(ASSETS, {"schema": "bookorder/uploaded-assets@1", "assets": items},
               "Generated by BookOrder from project.json input.assets (per-file roles set in the WebUI). The user's instruction per asset "
               "is binding: record a decision for each in plan/assets-plan.yaml uploaded_assets.")
    return items


def chapter_ref(value, chapters):
    """The outline chapter an intended_chapter refers to: an id, a number (「第2章」, "2", "chapter 2") or a title."""
    import re, unicodedata
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not text or not chapters: return None
    for c in chapters:
        if text == c["id"]: return c["id"]
    number = re.search(r"(\d+)", text)
    if number and re.fullmatch(r"(第)?\s*\d+\s*(章)?|(chapter|ch\.?)\s*\d+", text, re.I):
        index = int(number.group(1)) - 1
        return chapters[index]["id"] if 0 <= index < len(chapters) else None
    for c in chapters:
        if c.get("title") and (text in str(c["title"]) or str(c["title"]) in text): return c["id"]
    return None


def outline_chapters():
    try:
        import planning
        return planning.load_outline({})
    except Exception: return []


def for_chapter(chapter_id, project=None, chapters=None):
    chapters = chapters if chapters is not None else outline_chapters()
    return [a for a in uploaded_assets(project) if chapter_ref(a.get("intended_chapter"), chapters) == chapter_id]


# ---------------------------------------------------------------- content sources

def resolve(source, note=None, legacy=False):
    """(role, role_origin, authority, authority_origin, citation_allowed) for one registry source. In a legacy job
    (no publication_architecture) the agent's role estimate is recorded but does not restrict citation, so FIXED
    jobs made before the role system cite exactly as before; the user's own role choice always applies."""
    u = source.get("usage") or {}
    note = note or {}
    if u.get("role") in ROLES and u.get("role_origin") != "inferred": role, role_origin = u["role"], "user"
    elif note.get("source_role") in ROLES: role, role_origin = note["source_role"], "agent_estimate"
    elif u.get("role") in ROLES: role, role_origin = u["role"], "webui_estimate"
    else: role, role_origin = "evidence", "default"
    if u.get("authority") in AUTHORITY: authority, authority_origin = u["authority"], "user"
    elif note.get("authority") in AUTHORITY: authority, authority_origin = note["authority"], "agent_estimate"
    else: authority, authority_origin = "unknown", "default"
    explicit = u.get("citation_allowed")
    allowed = explicit if isinstance(explicit, bool) else ROLES[role]["citation_allowed"]
    if legacy and role_origin != "user" and ROLES[role]["content"] and not isinstance(explicit, bool): allowed = True
    if not ROLES[role]["content"]: allowed = False
    return {"role": role, "role_origin": role_origin, "authority": authority, "authority_origin": authority_origin,
            "citation_allowed": bool(allowed), "citation_allowed_origin": "user" if isinstance(explicit, bool) else "role",
            "group": ROLES[role]["group"] if not (allowed and role == "background") else "cited"}


def table(index=None, notes=None, write=True):
    """source id -> resolved roles (written to plan/source-roles.yaml)."""
    import research, sources as registry
    index = index or registry.load_index(); notes = notes if notes is not None else research.load_notes()
    out = {}
    try: legacy = not isinstance(read_project().get("publication_architecture"), (dict, str))
    except Exception: legacy = False
    for s in index["sources"]:
        entry = resolve(s, notes.get(s["id"]), legacy)
        biblio = (notes.get(s["id"]) or {}).get("bibliographic") or {}
        entry.update({"title": (biblio.get("title") if isinstance(biblio, dict) else None) or s.get("title") or s.get("original_name") or s.get("url"),
                      "origin": s["origin"], "status": s["ingest_status"]})
        u = s.get("usage") or {}
        for key in ("intended_usage", "intended_chapter", "intended_section", "priority", "notes"):
            if u.get(key): entry[key] = u[key]
        out[s["id"]] = entry
    if write:
        write_yaml(TABLE, {"schema": "bookorder/source-roles@1", "citable_roles": list(CITABLE),
                           "rule": "evidence may support factual claims; background informs but is not cited for facts; layout/style/visual "
                                   "references are never content (they live in plan/uploaded-assets.yaml).", "sources": out},
                   "Generated by BookOrder (Source Classifier). Change a role in the WebUI or with source_role/authority in research/notes/<id>.yaml.")
    return out


def citable(source_id, roles=None):
    roles = roles if roles is not None else table(write=False)
    entry = roles.get(source_id)
    return True if entry is None else entry["citation_allowed"]


def check_note_fields(identifier, note):
    errors = []
    if note.get("source_role") not in (None, "") and note["source_role"] not in ROLES:
        errors.append(f"{identifier}: source_role must be one of {', '.join(ROLES)}")
    elif note.get("source_role") and not ROLES[note["source_role"]]["content"]:
        errors.append(f"{identifier}: source_role {note['source_role']} is not a content role; a reference-only file is uploaded as an asset")
    if note.get("authority") not in (None, "") and note["authority"] not in AUTHORITY:
        errors.append(f"{identifier}: authority must be one of {', '.join(AUTHORITY)}")
    return errors


def summary_lines(roles=None):
    roles = roles if roles is not None else table(write=False)
    by_role = {}
    for sid, entry in roles.items():
        if entry["status"] in ("fully_ingested", "partially_ingested"): by_role.setdefault(entry["role"], []).append(sid)
    if not by_role: return []
    lines = ["Source roles (plan/source-roles.yaml): cite only sources whose citation_allowed is true for facts, numbers, definitions and recommendations."]
    for role, ids in by_role.items():
        lines.append(f"- {role} ({'citable' if ROLES[role]['citation_allowed'] else 'not citable for facts'}): {', '.join(ids[:30])}")
    return lines

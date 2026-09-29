"""Visual Planner: what must be seen, where, and why — decided before drafting (plan/visual-plan.yaml).

Visuals are not decoration added after the text. Every visual intent in the editorial plans (figures, charts,
tables, timelines, and visual component blocks such as algorithm cards) gets a VisualPlan entry:

    id, chapter, section, type (visual taxonomy, schemas/publication-architecture.json), purpose, content, reason
    (why seeing it beats reading it), source_requirements, generation_method, importance, caption_intent,
    duplication_check (how it avoids repeating the prose), uploaded_asset (optional)

The book-level QA (reports/visual-plan-qa.yaml) looks for monotony (one type dominating, the same type in every
chapter — the "box-and-arrow everywhere" failure), too few distinct types, avoided types, chapters that need a
visual and have none, and preferred types that were never considered. Medium findings block until the plan is
changed or a reasoned waiver is recorded (waivers: [{rule, reason}]). In FIXED mode the plan is seeded and
reported but never blocks (legacy behaviour).
"""
import json

from common import ROOT, as_list, write_yaml, yaml_data

VOCAB = json.loads((ROOT / "schemas/publication-architecture.json").read_text(encoding="utf-8"))
TYPES = VOCAB["visual_types"]
METHODS = tuple(VOCAB["generation_methods"])
IMPORTANCE = tuple(VOCAB["visual_importance"])
PLAN = ROOT / "plan/visual-plan.yaml"
REPORT = ROOT / "reports/visual-plan-qa.yaml"
REQUIRED = ("type", "purpose", "content", "reason", "generation_method", "importance", "caption_intent", "duplication_check")
SHAPE_TYPE = {"comparison": "comparison_table", "quantity": "data_chart", "chronology": "timeline", "hierarchy": "hierarchy_chart",
              "process": "process_diagram", "causal": "process_diagram", "relation": "relationship_map", "sequence": "workflow",
              "abstract": "summary_infographic", "source_image": "annotated_image", "formula": "process_diagram"}
DEVICE_METHOD = {"figure": "diagram_ir", "chart": "chart_code", "table": "native_table", "timeline": "diagram_ir"}


def guess_type(device):
    if device.get("visual_type") in TYPES: return device["visual_type"]
    block = VOCAB["blocks"].get(str(device.get("block") or ""), {})
    if block.get("visual_type"): return block["visual_type"]
    shape = device.get("information_shape") if isinstance(device.get("information_shape"), dict) else {}
    if device.get("type") == "table": return "comparison_table"
    if device.get("type") == "chart": return "data_chart"
    if device.get("type") == "timeline": return "timeline"
    return SHAPE_TYPE.get(shape.get("kind"), "")


def intents(chapters):
    """(chapter id, section id, device) for every live visual intent, including visual component blocks."""
    import editorial_plan as ep
    out = []
    for c in chapters:
        plan = ep.load_plan(c["id"])
        if not plan: continue
        for s, d in ep.devices(plan):
            if not ep.live(d): continue
            if ep.CATALOG.get(d["type"], {}).get("visual") or d.get("visual_type") or VOCAB["blocks"].get(str(d.get("block") or ""), {}).get("visual_type"):
                out.append((c["id"], s.get("id"), d))
    return out


def load():
    if not PLAN.is_file(): return {}
    try: return yaml_data(PLAN)
    except ValueError: return {}


def seed(chapters, arch=None):
    """Create or extend plan/visual-plan.yaml with an entry per visual intent (existing entries are kept)."""
    data = load() or {}
    entries = [e for e in as_list(data.get("visuals")) if isinstance(e, dict)]
    known = {str(e.get("id")) for e in entries}
    added = 0
    for chapter, section, d in intents(chapters):
        if d["id"] in known: continue
        entries.append({"id": d["id"], "chapter": chapter, "section": section, "type": guess_type(d), "purpose": str(d.get("why") or ""),
                        "content": "", "reason": "", "source_requirements": [str(s) for s in as_list(d.get("source_ids"))] or ["derived_from_text"],
                        "generation_method": "uploaded_asset" if d.get("asset_ref") else DEVICE_METHOD.get(d["type"], "component"),
                        "importance": "helpful", "caption_intent": "", "duplication_check": "",
                        **({"uploaded_asset": d["asset_ref"]} if d.get("asset_ref") else {})})
        added += 1
    if added or not PLAN.is_file():
        data = {"schema": "bookorder/visual-plan@1", "strategy": data.get("strategy") or "", "text_only_chapters": as_list(data.get("text_only_chapters")),
                "visuals": entries, "waivers": as_list(data.get("waivers"))}
        write_yaml(PLAN, data, "VisualPlan: what must be seen and why (seeded by BookOrder from plan/editorial/*.yaml; complete every field).")
    return added


def finding(rule, severity, detail, chapter=None, visual=None):
    return {"rule": rule, "severity": severity, "detail": detail, "chapter": chapter, "visual": visual}


def check(chapters, arch, profile=None, data=None):
    """{ok, findings, summary} for the visual plan."""
    data = data if data is not None else load()
    findings = []
    visuals = [e for e in as_list(data.get("visuals")) if isinstance(e, dict)]
    by_id = {str(e.get("id")): e for e in visuals}
    wanted = intents(chapters)
    live_ids = {d["id"] for _, _, d in wanted}
    import source_roles
    uploads = {a["id"]: a for a in source_roles.uploaded_assets()}
    for chapter, section, d in wanted:
        entry = by_id.get(d["id"])
        if not entry: findings.append(finding("visual_plan_missing", "error", f"{d['id']} has no entry in plan/visual-plan.yaml", chapter, d["id"])); continue
        for key in REQUIRED:
            if not str(entry.get(key) or "").strip(): findings.append(finding("visual_field_missing", "error", f"{d['id']}: {key} is required", chapter, d["id"]))
        if entry.get("type") and entry["type"] not in TYPES:
            findings.append(finding("visual_type_unknown", "error", f"{d['id']}: type {entry['type']!r} is not in the visual taxonomy ({', '.join(TYPES)})", chapter, d["id"]))
        elif entry.get("type"):
            kind = TYPES[entry["type"]]["device"]
            if kind not in ("component",) and d["type"] in ("figure", "chart", "table", "timeline") and kind != d["type"] and not (kind == "figure" and d["type"] == "timeline"):
                findings.append(finding("visual_type_device_mismatch", "error", f"{d['id']}: a {entry['type']} is realised as a {kind}, not a {d['type']}", chapter, d["id"]))
        if entry.get("generation_method") and entry["generation_method"] not in METHODS:
            findings.append(finding("visual_method_unknown", "error", f"{d['id']}: generation_method must be one of {', '.join(METHODS)}", chapter, d["id"]))
        if entry.get("importance") and entry["importance"] not in IMPORTANCE:
            findings.append(finding("visual_importance_unknown", "error", f"{d['id']}: importance must be one of {', '.join(IMPORTANCE)}", chapter, d["id"]))
        if not as_list(entry.get("source_requirements")): findings.append(finding("visual_field_missing", "error", f"{d['id']}: source_requirements is required", chapter, d["id"]))
        asset = entry.get("uploaded_asset")
        if asset and asset not in uploads: findings.append(finding("visual_asset_unknown", "error", f"{d['id']}: uploaded_asset {asset} is not in plan/uploaded-assets.yaml", chapter, d["id"]))
        if asset in uploads and entry.get("generation_method") == "redraw_from_asset" and not uploads[asset].get("redraw_allowed"):
            findings.append(finding("visual_redraw_not_allowed", "error", f"{d['id']}: the user did not allow redrawing {asset}", chapter, d["id"]))
        if asset in uploads and entry.get("generation_method") == "uploaded_asset" and uploads[asset]["role"] in ("layout_reference", "style_reference", "visual_reference"):
            findings.append(finding("visual_reference_placed", "error", f"{d['id']}: {asset} is a {uploads[asset]['role']}; it may guide the design but is never placed", chapter, d["id"]))
    for e in visuals:
        if str(e.get("id")) not in live_ids and not e.get("withdrawn"):
            findings.append(finding("visual_stale", "low", f"{e.get('id')} is not a live visual intent any more (mark withdrawn: true or remove it)", e.get("chapter"), e.get("id")))
    live = [by_id[i] for i in live_ids if i in by_id and by_id[i].get("type") in TYPES]
    policy = arch.get("visual_policy") or {}
    types = [e["type"] for e in live]
    counts = {t: types.count(t) for t in dict.fromkeys(types)}
    if len(live) >= 4:
        top, top_n = max(counts.items(), key=lambda kv: kv[1])
        share = top_n / len(live)
        if share > float(policy.get("max_share_per_type", 0.5)):
            findings.append(finding("visual_monotony", "medium", f"{top_n} of {len(live)} visuals are {top} ({share:.0%}); vary the visual grammar "
                                    "(decision_tree, comparison_table, timeline, case_flow, dos_and_donts, algorithm_card …) where the content has that shape"))
        minimum = int(float(policy.get("min_distinct_types", 1)))
        if len(counts) < minimum:
            findings.append(finding("visual_variety_low", "medium", f"{len(counts)} distinct visual types; the visual policy expects at least {minimum}"))
        chapters_with = {}
        for e in live: chapters_with.setdefault(e["type"], set()).add(e.get("chapter"))
        visual_chapters = {e.get("chapter") for e in live}
        for t, where in chapters_with.items():
            if len(visual_chapters) >= 3 and where == visual_chapters and t in ("workflow", "process_diagram"):
                findings.append(finding("visual_same_type_every_chapter", "medium", f"every chapter with visuals uses a {t}; a flow is not the default visual"))
    for t in policy.get("avoid_types") or []:
        if t in counts: findings.append(finding("visual_type_avoided", "medium", f"{counts[t]} visuals use {t}, which the visual policy avoids"))
    preferred = [t for t in policy.get("preferred_types") or [] if t not in counts]
    if live and preferred: findings.append(finding("visual_preferred_unused", "low", "preferred visual types not planned: " + ", ".join(preferred[:8])))
    need = policy.get("density") in ("high", "very_high")
    excused = {str(x.get("chapter")) for x in as_list(data.get("text_only_chapters")) if isinstance(x, dict) and str(x.get("reason") or "").strip()}
    for c in chapters:
        has = any(e.get("chapter") == c["id"] for e in live)
        if not has and need and int(c.get("target_characters") or 0) >= 3000 and c["id"] not in excused:
            findings.append(finding("visual_gap", "medium", f"{c['id']} ({int(c.get('target_characters') or 0):,} characters) plans no visual although the book's visual need is "
                                    f"{policy.get('density')}; plan what the reader must see, or list the chapter in text_only_chapters with the reason", c["id"]))
    waivers = [w for w in as_list(data.get("waivers")) if isinstance(w, dict) and str(w.get("reason") or "").strip()]
    for f in findings:
        if f["severity"] == "medium" and any(w.get("rule") == f["rule"] for w in waivers): f["waived"] = next(w["reason"] for w in waivers if w.get("rule") == f["rule"])
    blocking = [f for f in findings if f["severity"] == "error" or (f["severity"] == "medium" and not f.get("waived"))]
    fixed = arch.get("mode") == "fixed"
    summary = {"visuals": len(live), "types": counts, "distinct_types": len(counts), "errors": sum(f["severity"] == "error" for f in findings),
               "medium": sum(f["severity"] == "medium" and not f.get("waived") for f in findings), "mode": arch.get("mode")}
    result = {"schema": "bookorder/visual-plan-qa@1", "ok": fixed or not blocking, "advisory_only": fixed, "summary": summary, "findings": findings}
    REPORT.parent.mkdir(exist_ok=True)
    write_yaml(REPORT, result, "Generated by BookOrder from plan/visual-plan.yaml and plan/editorial/*.yaml.")
    return result

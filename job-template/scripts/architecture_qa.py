"""Publication architecture QA (reports/publication-architecture-qa.yaml, completion gate 23).

Checks that the book was *designed* for its purpose rather than poured into a template:

    structure       the same chapter structure / chapter-end apparatus repeated mechanically; template dominating content
    exercises       exercises without answers or explanations; exercises the book should not have; forbidden blocks in the text
    visuals         visual monotony (one type dominating, flows everywhere), figures that merely repeat the prose
    assets          every uploaded asset considered as instructed; references never placed or cited
    sources         evidence vs background confusion; factual claims supported only by background sources
    bibliography    citation and bibliography built as configured; cited vs background lists separated
    intent          explicit user wishes reflected (forbidden blocks absent, requested emphasis present)

Severity: high blocks completion (it reopens the phase in `phase`), medium and low are reported. In FIXED mode the
structural checks are advisory (low); source, asset and bibliography integrity still apply.
"""
import json
import re

from common import ROOT, as_list, plain, walk, write_yaml, yaml_data

REPORT = ROOT / "reports/publication-architecture-qa.yaml"
SCHEMA = "bookorder/publication-architecture-qa@1"
APPARATUS = {"summary": "summary", "exercise": "exercises", "checklist": "checklist", "sidebar": "column", "note": "callout"}


def finding(rule, severity, detail, phase, chapter=None, category="structure"):
    return {"rule": rule, "severity": severity, "detail": detail, "phase": phase, "chapter": chapter, "category": category}


def component_block(component):
    """The block-library id a manuscript component realises (marker class first, then component class)."""
    import publication_architecture as pa
    classes = component.get("classes") or [component.get("type")]
    for block, spec in pa.BLOCKS.items():
        if spec.get("marker_class") and spec["marker_class"] in classes: return block
    kind = classes[0]
    return {"exercise": "exercises", "summary": "summary", "checklist": "checklist", "sidebar": "column", "warning": "warning_box",
            "key-point": "key_point", "case-study": "case_study", "counterpoint": "counterpoint", "pull-quote": "pull_quote",
            "definition": "definition", "note": "callout", "tip": "callout", "step-by-step": "algorithm_card", "example": "template_forms"}.get(kind, kind)


def chapter_blocks(record):
    return [component_block(c) for c in record.get("components", [])] if record else []


def ending(record):
    """Apparatus blocks among the last components after the final section heading."""
    if not record: return ()
    comps = record.get("components", [])
    last_section = next((h["id"] for h in reversed(record["headings"]) if h["level"] == 2), None)
    tail = [component_block(c) for c in comps if c.get("section") == last_section or c.get("section") == record["id"]]
    import publication_architecture as pa
    closing = {b for b, spec in pa.BLOCKS.items() if "chapter_end" in spec.get("positions", [])} | {"column"}
    return tuple(sorted({b for b in tail[-3:] if b in closing}))


def run(ctx_chapters=None, records=None, project=None, write=True):
    import publication_architecture as pa
    from common import read_project
    project = project or read_project()
    arch = pa.load(project)
    adaptive = not arch.get("legacy") and arch["mode"] in ("auto", "guided")
    structural = "medium" if adaptive else "low"
    if ctx_chapters is None:
        import planning
        ctx_chapters = planning.load_outline({})
    if records is None:
        from manuscript import analyze_all, by_chapter
        records = by_chapter(analyze_all(), ctx_chapters)
    findings = []
    recs = [(c, records.get(c["id"])) for c in ctx_chapters if records.get(c["id"])]
    # --- structure
    endings = [ending(r) for _, r in recs]
    reason = str((arch.get("chapter_strategy") or {}).get("uniform_structure_reason") or "").strip()
    practice = arch.get("exercise_policy") in ("every_chapter", "exam_focused")
    if len(recs) >= 3 and endings[0] and len(set(endings)) == 1 and not reason and not (practice and set(endings[0]) <= {"exercises", "answer_key"}):
        findings.append(finding("mechanical_chapter_end", "high" if adaptive else "low", f"all {len(recs)} chapters end with the same apparatus ({', '.join(endings[0])})", "rewrite"))
    shapes = [tuple(sorted(set(chapter_blocks(r)))) for _, r in recs]
    if len(recs) >= 4 and shapes[0] and len(set(shapes)) == 1 and not reason:
        findings.append(finding("template_dominates", structural, f"every chapter uses exactly the same block set ({', '.join(shapes[0])}); chapters were not designed from their content", "rewrite"))
    # --- exercises and forbidden blocks
    forbidden = set(arch["block_policy"].get("forbidden") or [])
    book_answers = any("answer_key" in chapter_blocks(r) for _, r in recs)
    for c, r in recs:
        blocks = chapter_blocks(r)
        for b in dict.fromkeys(blocks):
            if b in forbidden:
                findings.append(finding("forbidden_block_in_manuscript", "high", f"{c['id']} contains {b}, which is forbidden ({pa.reason(arch, b) or 'block policy'})", "rewrite", c["id"], "intent"))
        if "exercises" in blocks and arch.get("exercise_policy") == "none" and "exercises" not in forbidden:
            findings.append(finding("unneeded_exercises", "high" if adaptive else "low", f"{c['id']} has exercises although the exercise policy is none", "rewrite", c["id"]))
        if "exercises" in blocks and "answer_key" not in blocks and not book_answers:
            findings.append(finding("exercise_without_answers", "high" if adaptive else "low", f"{c['id']} has exercises without answers or explanations the reader can find", "rewrite", c["id"]))
    # --- visuals
    try:
        import visual_plan
        vq = visual_plan.check(ctx_chapters, arch) if (ROOT / "plan/visual-plan.yaml").is_file() else None
    except Exception: vq = None
    if vq:
        for f in vq["findings"]:
            if f["rule"] in ("visual_monotony", "visual_variety_low", "visual_same_type_every_chapter", "visual_type_avoided") and not f.get("waived"):
                findings.append(finding(f["rule"], structural, f["detail"], "visual_planning", f.get("chapter"), "visual"))
    diagram_types = []
    for path in sorted((ROOT / "source/assets/diagrams").glob("*.yaml")):
        try: diagram_types.append(str(yaml_data(path).get("type")))
        except ValueError: pass
    if len(diagram_types) >= 4:
        flows = sum(t in ("flow", "process") for t in diagram_types)
        if flows / len(diagram_types) > 0.6:
            findings.append(finding("flow_diagram_monotony", structural, f"{flows} of {len(diagram_types)} diagrams are flow/process diagrams", "visual_planning", None, "visual"))
    findings += duplication_findings(recs)
    # --- uploaded assets and reference separation
    try:
        import assets as asset_module, planning
        plan = asset_module.load_plan()
        if plan is not None:
            for error in asset_module.uploaded_asset_errors(plan, asset_module.assets(plan), ctx_chapters, project):
                findings.append(finding("uploaded_asset_instruction", "high", error, "asset_planning", None, "assets"))
    except Exception as exc: findings.append(finding("uploaded_asset_check_failed", "low", str(exc)[:200], "asset_planning", None, "assets"))
    import source_roles
    uploads = source_roles.uploaded_assets(project)
    reference_paths = {a["path"] for a in uploads if a["role"] in ("layout_reference", "style_reference", "visual_reference") and a.get("path")}
    import sources as registry
    reference_urls = {registry.normalize_url(a["url"]) for a in uploads if a["role"] in ("layout_reference", "style_reference", "visual_reference") and a.get("url")}
    for s in registry.load_index()["sources"]:
        if s.get("path") in reference_paths or (s.get("url") and s.get("normalized") in reference_urls):
            findings.append(finding("reference_as_content", "high", f"{s['id']} is a layout/style/visual reference but was registered as a content source", "source_ingestion", None, "sources"))
    # --- sources and citations
    roles = source_roles.table(write=False)
    for c, r in recs:
        for cite in r["cites"]:
            entry = roles.get(cite["key"])
            if entry and not entry["citation_allowed"]:
                findings.append(finding("non_citable_source_cited", "high", f"{c['id']} cites {cite['key']} ({entry['role']})", "rewrite", c["id"], "sources"))
    import audit
    ledger = audit.load_ledger()
    for e in audit.open_issues(ledger, ("high",)):
        if e.get("type") == "source-role": findings.append(finding("background_only_claim", "high", e["detail"], "rewrite", e.get("chapter"), "sources"))
    # --- bibliography
    import bibliography
    for p in bibliography.check_report(project):
        findings.append(finding(p["rule"], p["severity"] if p["rule"] != "bibliography_not_built" else "low", p["detail"], "build", None, "bibliography"))
    # --- user intent
    if adaptive:
        for s in pa.user_signals(project):
            wanted = [pa.canonical(b) for b in s["effect"].get("prefer", []) if pa.canonical(b) not in forbidden]
            if wanted and recs:
                # One wish may be met by any of its blocks (「ケースを多く」: case study, clinical case or case reflection).
                used = sum(sum(chapter_blocks(r).count(b) for b in wanted) for _, r in recs)
                if used == 0:
                    findings.append(finding("user_preference_unmet", "high", f"the user asked 「{s['quote']}」 but the manuscript has none of: {', '.join(wanted)}", "rewrite", None, "intent"))
            if s["effect"].get("visual_density") in ("high", "very_high") and recs:
                bare = [c["id"] for c, r in recs if not r["figures"] and not [t for t in r["tables"] if t]]
                if len(bare) > len(recs) // 2:
                    findings.append(finding("user_visual_wish_unmet", "high", f"the user asked 「{s['quote']}」 but {len(bare)} of {len(recs)} chapters have no figure or table", "validation", None, "intent"))
    # A high finding may stand only with a recorded reason (plan/publication-architecture.yaml qa_waivers:
    # [{rule, reason}]) — e.g. the source material has no case for a wish. It stays in the report, marked waived.
    waivers = {str(w.get("rule")): str(w.get("reason")).strip() for w in as_list(arch.get("qa_waivers")) if isinstance(w, dict) and len(str(w.get("reason") or "").strip()) >= 10}
    for f in findings:
        if f["rule"] in waivers and f["category"] in ("structure", "intent", "visual"): f["waived"] = waivers[f["rule"]]
    blocking = [f for f in findings if f["severity"] == "high" and not f.get("waived")]
    summary = {"mode": arch["mode"], "archetype": (arch.get("archetype") or {}).get("primary"), "high": len(blocking),
               "medium": sum(f["severity"] == "medium" for f in findings), "low": sum(f["severity"] == "low" for f in findings),
               "chapters": len(recs), "chapter_endings": {c["id"]: list(e) for (c, _), e in zip(recs, endings)},
               "exercise_policy": arch.get("exercise_policy"), "forbidden_blocks": sorted(forbidden)}
    result = {"schema": SCHEMA, "ok": not blocking, "summary": summary, "findings": findings}
    if write:
        REPORT.parent.mkdir(exist_ok=True)
        write_yaml(REPORT, result, "Generated by BookOrder (publication architecture QA). Fix the plan or manuscript, not this file.")
    return result


def duplication_findings(recs):
    """A diagram whose labels all appear, in order, in the paragraphs right before it adds nothing to the prose."""
    out = []
    specs = {}
    for path in sorted((ROOT / "source/assets/diagrams").glob("*.yaml")):
        try: specs["source/assets/figures/" + path.stem + ".svg"] = yaml_data(path)
        except ValueError: pass
    for c, r in recs:
        blocks = r["ast"]["blocks"]
        for i, block in enumerate(blocks):
            if block["t"] != "Figure": continue
            src = next((n["c"][2][0] for n in walk(block["c"][2]) if n["t"] == "Image"), None)
            spec = specs.get(src)
            if not spec: continue
            labels = [str(n.get("label") or "") for n in as_list(spec.get("nodes")) if isinstance(n, dict) and len(str(n.get("label") or "")) >= 4]
            before = "".join(plain(b["c"]) for b in blocks[max(0, i - 2):i] if b["t"] in ("Para", "Plain"))
            if len(labels) >= 3 and sum(1 for l in labels if l in before) / len(labels) >= 0.8:
                out.append(finding("visual_duplicates_text", "low", f"{block['c'][0][0]} in {c['id']}: its labels restate the preceding paragraphs; make the figure show "
                                   "structure the prose does not (or shorten the prose)", "rewrite", c["id"], "visual"))
    return out


def phase_of(result):
    import orchestrator
    high = [f for f in result["findings"] if f["severity"] == "high" and not f.get("waived")]
    return min((f["phase"] for f in high), key=orchestrator.PHASES.index) if high else "validation"


def ledger_issues(result):
    """High manuscript findings become audit ledger issues so targeted rewrite tasks fix them."""
    import audit
    return [audit.issue("publication-architecture", "high", f.get("chapter"), f"{f['rule']}: {f['detail']}")
            for f in result["findings"] if f["severity"] == "high" and not f.get("waived") and f["phase"] == "rewrite" and f["category"] != "sources"]

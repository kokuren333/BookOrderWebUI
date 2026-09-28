"""Scale budgets, Book Bible, book architecture, chapter contracts and chapter research packets."""
import math
import statistics
import re
from pathlib import Path

from common import ROOT, read_project, yaml_data, write_yaml, write_json, as_list, as_int
import research
import sources as registry

PLAN = ROOT / "plan"
BIBLE = PLAN / "book-bible.yaml"
OUTLINE = ROOT / "source/metadata/outline.yaml"
SUMMARIES = PLAN / "summaries"
PACKETS = PLAN / "chapter-packets"
STATUS_DIR = ROOT / "reports/chapter-status"
CHAPTER_ID = re.compile(r"ch-[a-z0-9][a-z0-9-]*")

def compute_scale(project, design=None, write=True):
    """Budgets derived from the PublicationProfile (scripts/publication_profile.py): the profile is resolved from
    tier, genre and project overrides, written to plan/profile.resolved.yaml, and the scale is derived from it."""
    import publication_profile
    profile = publication_profile.resolve(project, design or {})
    if write: publication_profile.write(profile)
    return publication_profile.scale(profile)


# ---------------------------------------------------------------- Book Bible

BIBLE_REQUIRED = {"title": 1, "purpose": 20, "audience": 10, "tone": 5, "central_thesis": 20}


def check_bible():
    if not BIBLE.is_file(): return ["Missing plan/book-bible.yaml"]
    bible = yaml_data(BIBLE); errors = []
    for key, minimum in BIBLE_REQUIRED.items():
        if not research.nonempty(bible.get(key), minimum): errors.append(f"book-bible.yaml: {key} is required")
    scope = bible.get("scope") or {}
    if not as_list(scope.get("included")) or not as_list(scope.get("excluded")): errors.append("book-bible.yaml: scope.included and scope.excluded are required")
    terminology = bible.get("terminology") or {}
    if not (as_list(terminology.get("preferred_terms")) or terminology.get("definitions")): errors.append("book-bible.yaml: terminology.preferred_terms or definitions is required")
    rules = bible.get("editorial_rules") or {}
    for key in ("voice", "citation_style", "repetition_policy"):
        if not research.nonempty(rules.get(key)): errors.append(f"book-bible.yaml: editorial_rules.{key} is required")
    narrative = bible.get("global_narrative") or {}
    for key in ("opening", "development", "conclusion"):
        if not research.nonempty(narrative.get(key), 10): errors.append(f"book-bible.yaml: global_narrative.{key} is required")
    if not bible.get("design_intent"): errors.append("book-bible.yaml: design_intent is required")
    return errors


# ---------------------------------------------------------------- outline / architecture

def _topics(value):
    topics = []
    for item in as_list(value):
        if isinstance(item, dict):
            term = item.get("term") or item.get("topic") or ""
            alternatives = [term] + [str(x) for x in as_list(item.get("aliases"))]
        else:
            alternatives = [x.strip() for x in str(item).split("|")]
        alternatives = [x for x in alternatives if x]
        if alternatives: topics.append({"term": alternatives[0], "alternatives": alternatives})
    return topics


def _sections(value):
    sections = []
    for item in as_list(value):
        if isinstance(item, dict): sections.append({"id": item.get("id"), "title": item.get("title") or item.get("id")})
        else: sections.append({"id": str(item) if str(item).startswith("sec-") else None, "title": str(item)})
    return sections


def load_outline(scale=None):
    if not OUTLINE.is_file(): return []
    data = yaml_data(OUTLINE); scale = scale or {}
    language = scale.get("language", "ja")
    ratio = scale.get("chapter_minimum_ratio", 0.75)
    chapters = []
    for raw in as_list(data.get("chapters")):
        if not isinstance(raw, dict): continue
        target = as_int(raw.get("target_characters"), 0)
        if not target and raw.get("target_words"):
            words = as_int(raw.get("target_words"))
            target = words if language in ("ja", "zh", "ko") else words * 5
        srcs = raw.get("sources") or {}
        primary = as_list(srcs.get("primary")) if isinstance(srcs, dict) else as_list(srcs)
        supporting = as_list(srcs.get("supporting")) if isinstance(srcs, dict) else []
        primary += [x for x in as_list(raw.get("assigned_sources")) if x not in primary]
        chapters.append({
            "id": raw.get("id"), "title": raw.get("title"), "file": raw.get("file"), "purpose": raw.get("purpose"), "part": raw.get("part"),
            "prerequisites": as_list(raw.get("prerequisites")), "introduces": as_list(raw.get("introduces")),
            "develops": as_list(raw.get("develops")), "assumes": as_list(raw.get("assumes")),
            "hands_off_to": as_list(raw.get("hands_off_to")), "target_characters": target,
            "minimum_characters": math.ceil(target * ratio) if target else 0,
            "required_sections": _sections(raw.get("required_sections")), "required_topics": _topics(raw.get("required_topics")),
            "primary_sources": primary, "supporting_sources": supporting,
            "required_references": as_list(raw.get("required_references")),
            "expected_assets": as_list(raw.get("expected_assets") or raw.get("expected_figures")),
            "must_not_repeat": as_list(raw.get("must_not_repeat")), "handoff": raw.get("handoff")})
    return chapters


def check_outline(scale, project=None):
    project = project or read_project(); errors = []
    chapters = load_outline(scale)
    if not chapters: return ["source/metadata/outline.yaml must list chapters"], chapters
    # States created before profiles existed carry no minimum_chapters; keep their old rule.
    minimum_chapters = scale.get("minimum_chapters") or (2 if scale["requested_pages"] < 60 else max(4, scale["requested_pages"] // 40))
    maximum_chapters = scale.get("maximum_chapters")
    label = f"The {scale['profile']['id']} profile" if scale.get("profile") else f"A {scale['requested_pages']}-page book"
    if len(chapters) < minimum_chapters: errors.append(f"{label} needs at least {minimum_chapters} chapters (found {len(chapters)})")
    if maximum_chapters is not None and len(chapters) > maximum_chapters:
        errors.append(f"{label} allows at most {maximum_chapters} chapters (found {len(chapters)})")
    ids = [c["id"] for c in chapters]
    if len(set(ids)) != len(ids): errors.append("Chapter IDs must be unique")
    index = registry.load_index(); known = registry.by_id(index)
    position = {c["id"]: i for i, c in enumerate(chapters)}
    files = []
    introduced = {}
    for i, chapter in enumerate(chapters):
        name = chapter["id"] or f"#{i + 1}"
        if not chapter["id"] or not CHAPTER_ID.fullmatch(str(chapter["id"])): errors.append(f"{name}: id must match ch-[a-z0-9-]+ (so @ch:name references resolve)")
        for key in ("title", "file", "purpose"):
            if not research.nonempty(chapter.get(key)): errors.append(f"{name}: {key} is required")
        if chapter["file"] and not re.fullmatch(r"source/manuscript/[0-9]{2,3}-[A-Za-z0-9_-]+\.md", str(chapter["file"])):
            errors.append(f"{name}: file must be source/manuscript/NN-name.md")
        files.append(chapter["file"])
        if chapter["target_characters"] < 800: errors.append(f"{name}: target_characters must be at least 800")
        if chapter["target_characters"] > 60000: errors.append(f"{name}: target_characters over 60000; split the chapter")
        if not chapter["required_sections"]: errors.append(f"{name}: list required_sections")
        elif chapter["target_characters"] >= 8000 and len(chapter["required_sections"]) < 3: errors.append(f"{name}: long chapters need 3+ required_sections")
        if not chapter["required_topics"]: errors.append(f"{name}: list required_topics")
        for key in ("prerequisites",):
            for other in chapter[key]:
                if other not in position: errors.append(f"{name}: unknown prerequisite {other}")
                elif position[other] >= i: errors.append(f"{name}: prerequisite {other} must come earlier in reading order")
        for other in chapter["hands_off_to"]:
            if other not in position: errors.append(f"{name}: unknown hands_off_to {other}")
            elif position[other] <= i: errors.append(f"{name}: hands_off_to {other} must come later")
        for concept in chapter["introduces"]:
            if concept in introduced: errors.append(f"{name}: concept {concept} is already introduced by {introduced[concept]}")
            introduced[concept] = name
        for identifier in chapter["primary_sources"] + chapter["supporting_sources"] + chapter["required_references"]:
            if identifier not in known: errors.append(f"{name}: unknown source {identifier}")
            elif known[identifier]["ingest_status"] not in registry.USABLE: errors.append(f"{name}: {identifier} is {known[identifier]['ingest_status']} and cannot support the chapter")
        for identifier in chapter["required_references"]:
            if identifier not in chapter["primary_sources"] + chapter["supporting_sources"]: errors.append(f"{name}: required reference {identifier} must also be assigned")
    if files != sorted(files): errors.append("Chapter files must sort in reading order")
    total = sum(c["target_characters"] for c in chapters)
    if total < scale["target_characters"] * 0.95:
        errors.append(f"Chapter budgets total {total} characters; the {scale['requested_pages']}-page target needs about {scale['target_characters']} (minimum plan {math.ceil(scale['target_characters'] * 0.95)})")
    if project["research"].get("require_supplied_coverage", True):
        notes = research.load_notes()
        assigned = {x for c in chapters for x in c["primary_sources"] + c["supporting_sources"]}
        for source in index["sources"]:
            if source["origin"] == "supplied" and notes.get(source["id"], {}).get("relevance") in ("core", "supporting") and source["id"] not in assigned:
                errors.append(f"Relevant supplied source {source['id']} is not assigned to any chapter")
    return errors, chapters


def dependency_graph(chapters):
    """Topological waves: chapters in the same wave have all prerequisites in earlier waves."""
    level = {}
    for chapter in chapters:
        level[chapter["id"]] = 1 + max([level.get(p, 0) for p in chapter["prerequisites"]], default=0)
    waves = {}
    for identifier, value in level.items(): waves.setdefault(value, []).append(identifier)
    graph = {"chapters": [{"id": c["id"], "prerequisites": c["prerequisites"], "hands_off_to": c["hands_off_to"], "wave": level[c["id"]]} for c in chapters],
             "parallel_waves": [waves[k] for k in sorted(waves)]}
    write_yaml(PLAN / "chapter-dependencies.yaml", graph, "Generated from outline.yaml. Chapters in one wave may be drafted in parallel.")
    parts = {}
    for chapter in chapters:
        if chapter.get("part"): parts.setdefault(chapter["part"], []).append(chapter["id"])
    write_yaml(PLAN / "parts.yaml", {"parts": [{"title": k, "chapters": v} for k, v in parts.items()]}, "Generated from outline.yaml part fields.")
    return graph


# ---------------------------------------------------------------- summaries, contracts, packets

def summary_path(identifier):
    return SUMMARIES / f"{identifier}.yaml"


def check_summary(identifier):
    path = summary_path(identifier)
    if not path.is_file(): return [f"Missing plan/summaries/{identifier}.yaml"]
    data = yaml_data(path); errors = []
    if not research.nonempty(data.get("summary"), 60): errors.append(f"{identifier} summary: summary must be 60+ characters")
    if "introduced_concepts" not in data: errors.append(f"{identifier} summary: list introduced_concepts")
    if not research.nonempty(data.get("handoff"), 10): errors.append(f"{identifier} summary: handoff is required")
    return errors


def paragraph_lengths(record):
    """Reader-facing paragraph lengths; reserved slots are excluded until realised."""
    from common import plain
    from manuscript import count_chars
    found = []
    def visit(value):
        if isinstance(value, list):
            for item in value: visit(item)
            return
        if not isinstance(value, dict) or "t" not in value: return
        kind = value["t"]
        if kind == "Div" and "slot" in value["c"][0][1]: return
        if kind in ("Para", "Plain"):
            length = count_chars(plain(value.get("c", [])))
            if length: found.append(length)
            return
        content = value.get("c")
        if isinstance(content, (dict, list)): visit(content)
    if record: visit(record["ast"].get("blocks", []))
    return found


def paragraph_statistics(record, maximum):
    values = paragraph_lengths(record)
    over = [n for n in values if n > maximum]
    return {"paragraph_chars_max": maximum, "max_paragraph_chars": max(values, default=0),
            "median_paragraph_chars": statistics.median(values) if values else 0,
            "p90_paragraph_chars": sorted(values)[max(0, math.ceil(len(values) * 0.9) - 1)] if values else 0,
            "violation_count": len(over), "paragraph_count": len(values),
            "violation_ratio": len(over) / len(values) if values else 0,
            "high": bool(values and (max(values) > maximum * 1.5 or len(over) / len(values) >= 0.10)),
            "medium": bool(values and any(n > maximum * 1.15 for n in values))}


def evaluate_contract(chapter, record, scale):
    """A chapter file existing is not completion: size, topics, sections, references and summary all count."""
    reasons = []
    status = {"id": chapter["id"], "file": chapter["file"], "target_characters": chapter["target_characters"],
              "minimum_characters": chapter["minimum_characters"], "actual_characters": record["chars"] if record else 0,
              "required_topics": [t["term"] for t in chapter["required_topics"]],
              "required_sections": [s["id"] or s["title"] for s in chapter["required_sections"]],
              "assigned_sources": chapter["primary_sources"] + chapter["supporting_sources"],
              "required_references": chapter["required_references"], "required_assets": chapter["expected_assets"]}
    paragraph_max = scale.get("paragraph_chars_max")
    if paragraph_max:
        status["paragraph_stats"] = paragraph_statistics(record, paragraph_max)
    if not record:
        reasons.append({"type": "missing_file", "detail": f"{chapter['file']} does not exist"})
    else:
        if record["id"] != chapter["id"] or record["h1_count"] != 1 or not record["starts_with_h1"]:
            reasons.append({"type": "structure", "detail": f"Chapter must start with exactly one level-one heading {{#{chapter['id']}}}"})
        deficit = chapter["minimum_characters"] - record["chars"]
        if deficit > 0: reasons.append({"type": "length", "detail": f"{record['chars']} of minimum {chapter['minimum_characters']} characters (target {chapter['target_characters']})", "deficit": chapter["target_characters"] - record["chars"]})
        lowered = record["prose"].lower()
        missing = [t["term"] for t in chapter["required_topics"] if not any(a.lower() in lowered for a in t["alternatives"])]
        if missing: reasons.append({"type": "topics", "detail": "Missing required topics: " + ", ".join(missing), "missing": missing})
        heading_ids = {h["id"] for h in record["headings"]}; heading_titles = {h["title"] for h in record["headings"]}
        absent = [s["id"] or s["title"] for s in chapter["required_sections"] if not ((s["id"] and s["id"] in heading_ids) or (not s["id"] and any(s["title"] in t for t in heading_titles)))]
        if absent: reasons.append({"type": "sections", "detail": "Missing required sections: " + ", ".join(absent), "missing": absent})
        cited = {c["key"] for c in record["cites"]}
        uncited = [x for x in chapter["required_references"] if x not in cited]
        if uncited: reasons.append({"type": "references", "detail": "Required references not cited: " + ", ".join(uncited), "missing": uncited})
        if record["placeholders"]: reasons.append({"type": "placeholders", "detail": "Placeholder/unfinished text remains"})
        import editorial_plan
        reasons += editorial_plan.contract_reasons(chapter["id"], record)
        status["cited_sources"] = sorted(cited)
        status["unused_assigned_sources"] = [x for x in status["assigned_sources"] if x not in cited]
    summary_errors = check_summary(chapter["id"])
    if summary_errors: reasons.append({"type": "summary", "detail": "; ".join(summary_errors)})
    status["status"] = "complete" if not reasons else "incomplete"
    status["reasons"] = reasons
    status["deficit"] = max(0, chapter["target_characters"] - status["actual_characters"])
    return status


def write_contracts(chapters, records, scale):
    from manuscript import by_chapter
    mapped = by_chapter(records, chapters)
    results = [evaluate_contract(chapter, mapped.get(chapter["id"]), scale) for chapter in chapters]
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    for result in results: write_json(STATUS_DIR / f"{result['id']}.json", result)
    for stale in STATUS_DIR.glob("*.json"):
        if stale.stem not in {r["id"] for r in results}: stale.unlink()
    total = sum(r["actual_characters"] for r in results)
    paragraph_values = [r["paragraph_stats"] for r in results if "paragraph_stats" in r]
    paragraph_count = sum(r["paragraph_count"] for r in paragraph_values)
    paragraph_violations = sum(r["violation_count"] for r in paragraph_values)
    aggregate = {"total_target": sum(r["target_characters"] for r in results), "total_actual": total,
                 "book_minimum": scale["minimum_characters"], "book_target": scale["target_characters"],
                 "book_deficit": max(0, scale["minimum_characters"] - total),
                 "complete": sum(1 for r in results if r["status"] == "complete"),
                 "paragraph_stats": {"paragraph_chars_max": scale.get("paragraph_chars_max"),
                     "max_paragraph_chars": max((p["max_paragraph_chars"] for p in paragraph_values), default=0),
                     "median_paragraph_chars": statistics.median([x for r in results for x in paragraph_lengths(mapped.get(r["id"]))]) if paragraph_count else 0,
                     "p90_paragraph_chars": sorted([x for r in results for x in paragraph_lengths(mapped.get(r["id"]))])[max(0, math.ceil(paragraph_count * 0.9) - 1)] if paragraph_count else 0,
                     "violation_count": paragraph_violations, "paragraph_count": paragraph_count,
                     "violation_ratio": paragraph_violations / paragraph_count if paragraph_count else 0}, "chapters": [
                     {"id": r["id"], "status": r["status"], "target": r["target_characters"], "minimum": r["minimum_characters"],
                      "actual": r["actual_characters"], "deficit": r["deficit"], "reasons": [x["type"] for x in r["reasons"]]} for r in results]}
    write_json(ROOT / "reports/chapter-status.json", aggregate)
    return results, aggregate


def packet(chapter, chapters, scale):
    """Bounded research packet: the chapter job reads this instead of the whole raw corpus."""
    index = registry.load_index(); known = registry.by_id(index); notes = research.load_notes()
    concepts = {}
    concept_map = research.load_optional(research.synthesis_path("concept-map")) or {}
    wanted = set(chapter["introduces"] + chapter["develops"] + chapter["assumes"])
    for concept in as_list(concept_map.get("concepts")):
        if isinstance(concept, dict) and (concept.get("id") in wanted or concept.get("term") in wanted):
            concepts[concept.get("id")] = {"id": concept.get("id"), "term": concept.get("term"), "definition": concept.get("definition"),
                                          "role": "introduce" if concept.get("id") in chapter["introduces"] else "develop" if concept.get("id") in chapter["develops"] else "assume"}
    def describe(identifier):
        source = known.get(identifier, {})
        note = notes.get(identifier, {})
        return {"id": identifier, "title": source.get("title"), "content": source.get("content_path"), "chars": source.get("chars"),
                "relevance": note.get("relevance"), "summary": note.get("summary")}
    claim_list = []
    for identifier in chapter["primary_sources"] + chapter["supporting_sources"]:
        if identifier in notes: claim_list += research.claims(identifier, notes[identifier])
    position = [c["id"] for c in chapters].index(chapter["id"])
    previous = chapters[position - 1]["id"] if position else None
    related = list(dict.fromkeys(chapter["prerequisites"] + ([previous] if previous else [])))
    summaries = []
    for identifier in related:
        path = summary_path(identifier)
        if path.is_file():
            data = yaml_data(path)
            summaries.append({"chapter": identifier, "summary": data.get("summary"), "introduced_concepts": as_list(data.get("introduced_concepts")),
                              "key_terms": as_list(data.get("key_terms")), "handoff": data.get("handoff")})
    others = [{"id": c["id"], "title": c["title"], "introduces": c["introduces"]} for c in chapters if c["id"] != chapter["id"]]
    import editorial_plan
    plan = editorial_plan.load_plan(chapter["id"])
    import user_intent
    data = {
        # The user's own words come first: they govern voice, density, scope and structure (docs/user-intent.md).
        **({"user_intent": user_intent.packet_entry()} if user_intent.present() else {}),
        "chapter": chapter["id"], "title": chapter["title"], "file": chapter["file"], "purpose": chapter["purpose"],
        "target_characters": chapter["target_characters"], "minimum_characters": chapter["minimum_characters"],
        "required_sections": chapter["required_sections"], "required_topics": [t["term"] for t in chapter["required_topics"]],
        "must_not_repeat": chapter["must_not_repeat"], "hands_off_to": chapter["hands_off_to"],
        "shared_state": {"book_bible": "plan/book-bible.yaml", "glossary": "source/metadata/glossary.yaml",
                         "concept_map": "plan/concept-map.yaml", "outline": "source/metadata/outline.yaml",
                         "reference_registry": "source/references/references.json"},
        "prerequisite_summaries": summaries,
        "primary_sources": [describe(x) for x in chapter["primary_sources"]],
        "supporting_sources": [describe(x) for x in chapter["supporting_sources"]],
        "required_references": chapter["required_references"],
        "claims": claim_list, "concepts": list(concepts.values()), "other_chapters": others,
        "expected_assets": chapter["expected_assets"],
        "editorial_plan": ({"file": f"plan/editorial/{chapter['id']}.yaml", "reader_before": plan.get("reader_before"), "reader_after": plan.get("reader_after"),
                            "sections": [{"id": s.get("id"), "heading": s.get("heading"), "rhetorical_role": s.get("rhetorical_role"),
                                          "expected_density": s.get("expected_density"), "target_chars": s.get("target_chars"),
                                          "slots": [editorial_plan.slot_markdown(d) for d in s["devices"] if editorial_plan.live(d)]} for s in plan["sections"]],
                            "chapter_end": [editorial_plan.slot_markdown(e, e.get("type")) for e in plan["chapter_end"]]} if plan else None),
        "syntax": {"citation": "[cite:src-0001] or [cite:src-0001,src-0002]", "cross_reference": "@ch:id @sec:id @fig:id @tbl:id @eq:id",
                   "slot": "::: {.slot #device-id kind=type} one line: what the device will show :::",
                   "chapter_heading": f"# {chapter['title']} {{#{chapter['id']}}}"}}
    PACKETS.mkdir(parents=True, exist_ok=True)
    write_yaml(PACKETS / f"{chapter['id']}.yaml", data, "Generated chapter research packet. Regenerated before each chapter task.")
    return data

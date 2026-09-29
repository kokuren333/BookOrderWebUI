"""Supplementary research log, corpus analysis notes, global synthesis, research freeze and coverage."""
import json
from pathlib import Path
import re

from common import ROOT, read_project, yaml_data, write_json, write_yaml, as_list, walk
import sources as registry

NOTES = ROOT / "research/notes"
PLAN = ROOT / "plan"
SEARCH_LOG = ROOT / "research/search-log.jsonl"
LOCK = ROOT / "research/research-lock.json"
PLAN_FILE = ROOT / "research/research-plan.yaml"
RELEVANCE = ("core", "supporting", "background", "irrelevant", "duplicate")
RELIABILITY = ("primary", "secondary", "tertiary", "unknown")
SYNTHESIS_FILES = ("book-context", "concept-map", "argument-map", "timeline", "source-clusters", "topic-synthesis")


def nonempty(value, minimum=1):
    return isinstance(value, str) and len(re.sub(r"\s+", "", value)) >= minimum


def load_optional(path):
    return yaml_data(path) if Path(path).is_file() else None


# ---------------------------------------------------------------- search log

def search_entries():
    if not SEARCH_LOG.is_file(): return []
    return [json.loads(line) for line in SEARCH_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]


def log_search(query, gap=None, tool_name=None, candidates=None, selected=None, rejected=None, note=None):
    if not query or not query.strip(): raise ValueError("--query is required")
    entries = search_entries()
    entry = {"id": f"q-{len(entries) + 1:04d}", "at": registry.now(), "query": query.strip(), "gap": gap, "tool": tool_name,
             "candidates": candidates or [], "selected": selected or [], "rejected": rejected or [], "note": note}
    SEARCH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SEARCH_LOG.open("a", encoding="utf-8") as stream: stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


# ---------------------------------------------------------------- research plan

def check_research_plan(project=None):
    """Supplementary research is complete when every identified gap is resolved or explained, discovered
    sources are persisted, and nothing is still pending."""
    project = project or read_project(); errors = []
    allowed = bool(project["research"].get("allow_web_research"))
    index = registry.load_index()
    plan = load_optional(PLAN_FILE)
    if plan is None: return [f"Missing {PLAN_FILE.relative_to(ROOT).as_posix()}"]
    mode = str(plan.get("web_research", ""))
    if mode not in ("performed", "disabled", "not_needed"): errors.append("research-plan.yaml web_research must be performed, disabled or not_needed")
    if not allowed and mode == "performed": errors.append("Web research is disabled in project.json; web_research must be 'disabled'")
    gaps = as_list(plan.get("gaps"))
    if not gaps and not (mode == "not_needed" and nonempty(plan.get("rationale"), 40)):
        errors.append("List the research gaps you checked (gaps), or set web_research: not_needed with a rationale of 40+ characters")
    queries = {entry["id"]: entry for entry in search_entries()}
    known = registry.by_id(index)
    for gap in gaps:
        if not isinstance(gap, dict) or not gap.get("id") or not nonempty(gap.get("description"), 5):
            errors.append("Each gap needs id and description"); continue
        status = gap.get("status")
        if status not in ("resolved", "unresolvable", "not_needed"):
            errors.append(f"{gap['id']}: status must be resolved, unresolvable or not_needed"); continue
        ids = as_list(gap.get("sources"))
        if status == "resolved":
            if not ids: errors.append(f"{gap['id']}: a resolved gap must list the source IDs that resolve it")
            for identifier in ids:
                if identifier not in known: errors.append(f"{gap['id']}: unknown source {identifier}")
                elif known[identifier]["ingest_status"] not in registry.USABLE: errors.append(f"{gap['id']}: {identifier} is not ingested")
        if status == "unresolvable":
            if allowed and mode == "performed" and not [q for q in as_list(gap.get("queries")) if q in queries]:
                errors.append(f"{gap['id']}: record the searches attempted (bookorder research log) and list their IDs in queries")
            if not nonempty(gap.get("note"), 10): errors.append(f"{gap['id']}: explain the remaining limitation in note")
    discovered = [s for s in index["sources"] if s["origin"] == "discovered" and not s.get("post_draft")]
    if not allowed and discovered: errors.append("Web research is disabled but discovered sources were added")
    selected = {item for entry in queries.values() for item in as_list(entry.get("selected"))}
    for source in discovered:
        if source["ingest_status"] in registry.PENDING: errors.append(f"Discovered source {source['id']} is still {source['ingest_status']}")
        provenance = source.get("discovery") or {}
        if source["id"] not in selected and source.get("url") not in selected and not provenance.get("query"):
            errors.append(f"Discovered source {source['id']} has no search provenance (use --query on source add or research log --selected)")
    return errors


# ---------------------------------------------------------------- notes (per-source analysis)

def note_path(identifier):
    return NOTES / f"{identifier}.yaml"


def load_notes():
    notes = {}
    if NOTES.is_dir():
        for path in sorted(NOTES.glob("src-*.yaml")):
            notes[path.stem] = yaml_data(path)
    return notes


def check_note(identifier, note, known):
    errors = []
    if str(note.get("source")) != identifier: errors.append(f"{identifier}: note.source must be {identifier}")
    relevance = note.get("relevance")
    if relevance not in RELEVANCE: errors.append(f"{identifier}: relevance must be one of {', '.join(RELEVANCE)}")
    if relevance == "duplicate" and note.get("duplicate_of") not in known: errors.append(f"{identifier}: duplicate_of must name an existing source")
    if note.get("reliability", "unknown") not in RELIABILITY: errors.append(f"{identifier}: reliability must be one of {', '.join(RELIABILITY)}")
    if not nonempty(note.get("summary"), 60): errors.append(f"{identifier}: summary must describe the whole source (60+ characters)")
    import source_roles
    errors += source_roles.check_note_fields(identifier, note)
    claims = as_list(note.get("key_claims"))
    if relevance in ("core", "supporting") and not claims: errors.append(f"{identifier}: core/supporting sources need key_claims")
    for claim in claims:
        text = claim.get("text") if isinstance(claim, dict) else claim
        if not nonempty(text, 8): errors.append(f"{identifier}: every key claim needs text")
    return errors


def claims(identifier, note):
    result = []
    for number, claim in enumerate(as_list(note.get("key_claims")), 1):
        item = claim if isinstance(claim, dict) else {"text": claim}
        result.append({"id": item.get("id") or f"claim-{identifier}-{number:02d}", "source": identifier, "text": item.get("text"),
                       "locator": item.get("locator")})
    return result


def usable_sources(index=None):
    index = index or registry.load_index()
    return [s for s in index["sources"] if s["ingest_status"] in registry.USABLE]


def missing_notes(index=None):
    notes_dir = NOTES
    return [s["id"] for s in usable_sources(index) if not (notes_dir / f"{s['id']}.yaml").is_file()]


def check_notes(index=None):
    index = index or registry.load_index(); known = registry.by_id(index); errors = []
    notes = load_notes()
    for source in usable_sources(index):
        if source["id"] not in notes: errors.append(f"Missing research/notes/{source['id']}.yaml"); continue
        errors += check_note(source["id"], notes[source["id"]], known)
    return errors


# ---------------------------------------------------------------- global synthesis

def synthesis_path(name):
    return PLAN / f"{name}.yaml"


def check_synthesis(index=None):
    index = index or registry.load_index(); errors = []
    known = registry.by_id(index); notes = load_notes()
    data = {}
    for name in SYNTHESIS_FILES:
        value = load_optional(synthesis_path(name))
        if value is None: errors.append(f"Missing plan/{name}.yaml"); continue
        data[name] = value
    def sources_ok(where, ids, required=True):
        ids = as_list(ids)
        if required and not ids: errors.append(f"{where}: list supporting source IDs")
        for identifier in ids:
            if identifier not in known: errors.append(f"{where}: unknown source {identifier}")
    if "book-context" in data:
        context = data["book-context"]
        if not nonempty(context.get("summary"), 150): errors.append("book-context.yaml: summary must synthesize the whole corpus (150+ characters)")
        if len(as_list(context.get("key_questions"))) < 3: errors.append("book-context.yaml: list at least 3 key_questions")
    if "concept-map" in data:
        concepts = as_list(data["concept-map"].get("concepts"))
        if len(concepts) < 3: errors.append("concept-map.yaml: at least 3 concepts are required")
        ids = [c.get("id") for c in concepts if isinstance(c, dict)]
        if len(ids) != len(set(ids)) or not all(ids): errors.append("concept-map.yaml: concept IDs must be present and unique")
        for concept in concepts:
            if not isinstance(concept, dict): continue
            if not nonempty(concept.get("term")) or not nonempty(concept.get("definition"), 10): errors.append(f"concept {concept.get('id')}: term and definition are required")
            sources_ok(f"concept {concept.get('id')}", concept.get("sources"), required=concept.get("origin") != "author")
    if "argument-map" in data:
        argument = data["argument-map"]
        if not nonempty(argument.get("central_thesis"), 20): errors.append("argument-map.yaml: central_thesis is required")
        arguments = as_list(argument.get("arguments"))
        if len(arguments) < 2: errors.append("argument-map.yaml: at least 2 arguments are required")
        for item in arguments:
            if isinstance(item, dict): sources_ok(f"argument {item.get('id')}", item.get("support"))
    if "timeline" in data:
        timeline = data["timeline"]
        if not as_list(timeline.get("events")) and not nonempty(timeline.get("not_applicable"), 10):
            errors.append("timeline.yaml: add events or explain not_applicable")
    if "source-clusters" in data:
        clusters = as_list(data["source-clusters"].get("clusters"))
        if not clusters: errors.append("source-clusters.yaml: at least one cluster is required")
        clustered = {identifier for cluster in clusters if isinstance(cluster, dict) for identifier in as_list(cluster.get("sources"))}
        for identifier, note in notes.items():
            if note.get("relevance") in ("core", "supporting", "background") and identifier not in clustered:
                errors.append(f"source-clusters.yaml: relevant source {identifier} is not assigned to a cluster")
    if "topic-synthesis" in data:
        topics = as_list(data["topic-synthesis"].get("topics"))
        if len(topics) < 2: errors.append("topic-synthesis.yaml: at least 2 topics are required")
        for topic in topics:
            if isinstance(topic, dict):
                if not nonempty(topic.get("synthesis"), 60): errors.append(f"topic {topic.get('id')}: synthesis must combine sources (60+ characters)")
                sources_ok(f"topic {topic.get('id')}", topic.get("sources"))
        if "contradictions" not in data["topic-synthesis"]: errors.append("topic-synthesis.yaml: record contradictions (an empty list is allowed)")
        for item in as_list(data["topic-synthesis"].get("contradictions")):
            if isinstance(item, dict):
                if len(as_list(item.get("sources"))) < 2 or not nonempty(item.get("resolution"), 10):
                    errors.append(f"contradiction {item.get('id')}: needs 2+ sources and a resolution/handling note")
    glossary = ROOT / "source/metadata/glossary.yaml"
    terms = as_list(yaml_data(glossary).get("terms")) if glossary.is_file() else []
    if len(terms) < 3: errors.append("source/metadata/glossary.yaml: define at least 3 terms (term, definition, aliases, forbidden)")
    for term in terms:
        if isinstance(term, dict) and not (nonempty(term.get("term") or term.get("preferred")) and nonempty(term.get("definition"), 5)):
            errors.append("glossary: every term needs term and definition")
    return errors


def corpus_summary(index=None):
    """Deterministic corpus overview, rebuilt from the registry and notes."""
    index = index or registry.load_index(); notes = load_notes()
    clusters = load_optional(synthesis_path("source-clusters")) or {}
    membership = {}
    for cluster in as_list(clusters.get("clusters")):
        if isinstance(cluster, dict):
            for identifier in as_list(cluster.get("sources")): membership.setdefault(identifier, []).append(cluster.get("id"))
    relevance = {}
    for note in notes.values(): relevance[note.get("relevance", "unknown")] = relevance.get(note.get("relevance", "unknown"), 0) + 1
    summary = {"supplied": registry.counts(index, "supplied"), "discovered": registry.counts(index, "discovered"),
               "total_characters": sum(s.get("chars", 0) for s in index["sources"] if s["ingest_status"] in registry.USABLE),
               "analyzed": len(notes), "by_relevance": relevance,
               "clusters": [{"id": c.get("id"), "label": c.get("label"), "sources": len(as_list(c.get("sources")))} for c in as_list(clusters.get("clusters")) if isinstance(c, dict)],
               "sources": [{"id": s["id"], "origin": s["origin"], "status": s["ingest_status"], "title": s.get("title"), "chars": s.get("chars", 0),
                            "relevance": notes.get(s["id"], {}).get("relevance"), "clusters": membership.get(s["id"], [])} for s in index["sources"]]}
    write_yaml(ROOT / "research/corpus-summary.yaml", summary, "Generated by BookOrder from research/index.json and research/notes/. Do not edit.")
    return summary


# ---------------------------------------------------------------- freeze

def load_lock():
    return json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.is_file() else None


def freeze():
    index = registry.load_index()
    existing = load_lock()
    if existing: return existing
    lock = {"version": 1, "frozen_at": registry.now(), "sources": [s["id"] for s in index["sources"]],
            "hashes": {s["id"]: s.get("sha256") for s in index["sources"]}, "post_draft_additions": []}
    write_json(LOCK, lock)
    return lock


def record_post_draft(identifier, reason, issue=None):
    lock = load_lock()
    if not lock: raise ValueError("Research is not frozen yet; add sources during supplementary research instead")
    lock["post_draft_additions"].append({"id": identifier, "reason": reason, "issue": issue, "at": registry.now()})
    lock["version"] += 1
    write_json(LOCK, lock)


def check_lock():
    lock = load_lock(); errors = []
    if not lock: return ["research-lock.json is missing"]
    index = registry.load_index(); known = registry.by_id(index)
    for identifier in lock["sources"]:
        if identifier not in known: errors.append(f"Locked source {identifier} disappeared from the registry"); continue
        if lock["hashes"].get(identifier) and known[identifier].get("sha256") != lock["hashes"][identifier]:
            errors.append(f"Locked source {identifier} content changed after the research freeze")
    later = [s["id"] for s in index["sources"] if s["id"] not in lock["sources"]]
    recorded = {item["id"] for item in lock.get("post_draft_additions", [])}
    for identifier in later:
        if identifier not in recorded: errors.append(f"{identifier} was added after the freeze without being recorded as post-draft research")
    return errors


# ---------------------------------------------------------------- coverage

def coverage(usage, project=None, index=None):
    """source-coverage.json: how each source is reflected. usage = {src: [{chapter, section}]}"""
    project = project or read_project(); index = index or registry.load_index(); notes = load_notes()
    report = {}; orphans = []
    import source_roles
    roles = source_roles.table(index, notes, write=False)
    outline = ROOT / "source/metadata/outline.yaml"
    assigned = set()
    if outline.is_file():
        for chapter in as_list(yaml_data(outline).get("chapters")):
            if isinstance(chapter, dict):
                srcs = chapter.get("sources") or {}
                assigned |= {str(x) for x in (as_list(srcs.get("primary")) + as_list(srcs.get("supporting")) if isinstance(srcs, dict) else as_list(srcs))}
    for source in index["sources"]:
        identifier = source["id"]; note = notes.get(identifier, {}); relevance = note.get("relevance")
        state = source["ingest_status"]
        if identifier in usage: status = "used"
        elif state == "duplicate" or relevance == "duplicate": status = "duplicate"
        elif state == "unavailable": status = "unavailable"
        elif state in registry.PENDING: status = "pending"
        elif relevance == "irrelevant": status = "irrelevant"
        elif relevance == "background": status = "background_only"
        elif not roles.get(identifier, {}).get("citation_allowed", True) and identifier in assigned:
            status = "consulted"  # background / structure reference: informs a chapter, listed in the background bibliography
        elif note: status = "analyzed"
        else: status = "ingested"
        entry = {"status": status, "origin": source["origin"], "relevance": relevance, "role": roles.get(identifier, {}).get("role"), "used_in": usage.get(identifier, [])}
        if status in ("analyzed", "ingested") and source["origin"] == "supplied": orphans.append(identifier)
        report[identifier] = entry
    required = bool(project["research"].get("require_supplied_coverage", True))
    result = {"required": required, "orphan_supplied_sources": orphans, "sources": report}
    write_json(ROOT / "reports/source-coverage.json", result)
    return result

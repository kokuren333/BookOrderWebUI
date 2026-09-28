"""Root publication orchestrator for `/goal`.

The agent runtime supplies the model; this module owns the publication lifecycle. It persists the phase state
machine, runs every deterministic step itself, hands the agent exactly the authoring/review tasks that remain,
verifies the agent's work against machine-checkable gates and is the only component allowed to declare the
publication complete. Nothing here trusts a task's own claim of success: `done` only asks for re-verification.
"""
from datetime import datetime, timezone
import json
import os
import time
import traceback

from common import ROOT, read_project, write_json, as_list, yaml_data, fingerprint as build_fingerprint, editorial_plan_fingerprint

# outline (architecture) -> EditorialPlan -> section drafting -> VisualPlan / assets -> integration -> layout.
PHASES = ["source_ingestion", "supplementary_research", "corpus_analysis", "research_frozen", "architecture",
          "reference_assignment", "editorial_planning", "drafting", "chapter_review", "asset_planning", "asset_generation",
          "integration", "audit", "rewrite", "prose_audit", "prose_editing", "final_audit", "design", "layout", "build", "validation", "package", "complete"]
# EditorialPlan is an explicit semantic input to each downstream publication artifact.
EDITORIAL_PLAN_DOWNSTREAM = ["drafting", "chapter_review", "asset_planning", "asset_generation", "integration",
                            "audit", "rewrite", "prose_audit", "prose_editing", "final_audit", "design", "layout", "build", "validation", "package", "complete"]
STATES = ("pending", "running", "complete", "blocked", "failed")
STATE_FILE = ROOT / "project-state.json"
EVENTS = ROOT / "run-events.jsonl"
SUMMARY = ROOT / "execution-summary.json"
SKILL_IDS = {"source_ingestion": ("source-ingestion",), "supplementary_research": ("research",),
             "corpus_analysis": ("research",), "architecture": ("book-authoring",),
             "editorial_planning": ("editorial-planning",), "drafting": ("book-authoring", "editorial-planning"),
             "chapter_review": ("book-authoring",), "integration": ("editing",),
             "asset_planning": ("figures",), "asset_generation": ("figures",), "audit": ("audit",),
             "prose_audit": ("prose-audit", "whole-book-review"),
             "rewrite": ("editing", "audit"), "prose_editing": ("developmental-editing", "cadence-editing"),
             "final_audit": ("audit",), "design": ("editorial-design",),
             "layout": ("editorial-design", "publication-qa"), "build": ("publication-qa",)}
MAX_REVIEW_ROUNDS = 6
MAX_REWRITE_PASSES = 6
INGEST_TIME_BUDGET = float(os.environ.get("BOOKORDER_INGEST_SECONDS", "150"))


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- persistence / observability

def log_event(stage, event, **fields):
    record = {"at": now(), "stage": stage, "event": event, **{k: v for k, v in fields.items() if v is not None}}
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS.open("a", encoding="utf-8") as stream: stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def events():
    if not EVENTS.is_file(): return []
    return [json.loads(line) for line in EVENTS.read_text(encoding="utf-8").splitlines() if line.strip()]


def new_state(project):
    from planning import compute_scale
    from design import load_design
    try: design = load_design()
    except Exception: design = {}
    return {"format": "bookorder-project-state", "version": 1, "status": "running", "phase": PHASES[0],
            "phases": {name: "pending" for name in PHASES}, "phase_times": {}, "scale": compute_scale(project, design),
            "accepted": {}, "counters": {}, "blockers": [], "reviewed_hashes": {}, "created_at": now(), "updated_at": now(),
            # Jobs started with this flag verify user-intent compliance (docs/user-intent.md); older states are not re-gated.
            "user_intent_protocol": 1,
            "project": {"title": project["book"]["title"], "requested_pages": project["book"].get("target_pages"),
                        "language": project["book"].get("language"), "citation_style": project["citations"]["style"]}}


def load_state():
    project = read_project()
    # Resolve the planning input before any freshness comparison. A first build must not create
    # a new semantic fingerprint midway through an otherwise complete orchestration run.
    from design import load_design
    from layout_spec import load_or_create
    design_spec = load_design()
    load_or_create(project=project, design=design_spec)
    from style_bible import load_or_resolve
    load_or_resolve(project=project, design=design_spec)
    if STATE_FILE.is_file():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if "editorial_planning" not in state["phases"] and state["phases"].get("drafting") == "complete":
            # Drafted before EditorialPlan existed: the manuscript is not re-planned; gates 18/19 check plans only if written.
            state["phases"]["editorial_planning"] = "complete"; state.setdefault("notes", {})["editorial_planning"] = "legacy: drafted before EditorialPlan"
        for name in PHASES: state["phases"].setdefault(name, "pending")
        return project, state
    state = new_state(project)
    log_event("goal", "init", requested_pages=state["scale"]["requested_pages"], target_characters=state["scale"]["target_characters"],
              minimum_characters=state["scale"]["minimum_characters"])
    save_state(state)
    return project, state


def save_state(state):
    state["updated_at"] = now()
    write_json(STATE_FILE, state)


def set_phase(state, phase, value, reason=None):
    previous = state["phases"].get(phase)
    if previous == value: return
    state["phases"][phase] = value
    times = state["phase_times"].setdefault(phase, {})
    if value == "running": times.setdefault("started", now())
    if value == "complete": times["completed"] = now()
    log_event(phase, {"running": "start", "complete": "complete", "pending": "reopen", "blocked": "blocked", "failed": "failed"}[value], reason=reason)


def reopen(state, phase, reason):
    """Invalidate a phase and everything after it. Later phases never keep 'complete' over a stale prerequisite."""
    start = PHASES.index(phase)
    key = "reopen:" + phase
    state["counters"][key] = state["counters"].get(key, 0) + 1
    for name in PHASES[start:]:
        if state["phases"][name] != "pending": set_phase(state, name, "pending", reason if name == phase else f"after {phase} reopened")
    state["status"] = "running"


def refresh_editorial_plan_dependency(state):
    """Reopen dependent phases when semantic EditorialPlan source files change."""
    if state.get("phases", {}).get("editorial_planning") != "complete": return False
    current = editorial_plan_fingerprint()
    snapshots = state.setdefault("artifact_fingerprints", {})
    previous = snapshots.get("editorial_plan")
    if previous is None:
        # Adopt pre-existing jobs once; legacy state predates this dependency record.
        snapshots["editorial_plan"] = current
        return False
    if current == previous: return False
    snapshots["editorial_plan"] = current
    reopen(state, "drafting", "EditorialPlan semantic inputs changed; dependent manuscript and publication artifacts are stale")
    return True


# ---------------------------------------------------------------- context (lazy computed views)

class Context:
    def __init__(self, project, state):
        self.project = project; self.state = state; self._cache = {}
    def get(self, key, producer):
        if key not in self._cache: self._cache[key] = producer()
        return self._cache[key]
    def invalidate(self, *keys):
        for key in keys or list(self._cache): self._cache.pop(key, None)
    @property
    def scale(self): return self.state["scale"]
    def outline(self):
        from planning import load_outline
        return self.get("outline", lambda: load_outline(self.scale))
    def records(self):
        from manuscript import analyze_all
        return self.get("records", analyze_all)
    def by_chapter(self):
        from manuscript import by_chapter
        return self.get("by_chapter", lambda: by_chapter(self.records(), self.outline()))
    def contracts(self):
        from planning import write_contracts
        return self.get("contracts", lambda: write_contracts(self.outline(), self.records(), self.scale))
    def usage(self):
        from manuscript import usage
        return self.get("usage", lambda: usage(self.records()))
    def coverage(self):
        from research import coverage
        return self.get("coverage", lambda: coverage(self.usage(), self.project))
    def manuscript_fingerprint(self):
        from manuscript import fingerprint
        return self.get("mfp", fingerprint)


def task(identifier, phase, title, instructions, outputs=(), inputs=(), group=None, checks=None, kind="agent"):
    from skills import resolve
    import user_intent
    item = {"id": identifier, "phase": phase, "kind": kind, "title": title, "skills": resolve(*SKILL_IDS.get(phase, ())),
            "inputs": list(inputs), "outputs": list(outputs), "instructions": instructions if isinstance(instructions, list) else [instructions],
            "parallel_group": group, "failing_checks": checks or [], "done": f"bookorder done {identifier}"}
    # The user's verbatim instructions travel with every agent task: a sub-agent that only sees this task still has them.
    block = user_intent.task_block(phase) if kind == "agent" else None
    if block: item["user_intent"] = block
    return item


def intent_active(ctx):
    """User-intent compliance checks apply when the user wrote instructions and the job started under this protocol."""
    import user_intent
    return user_intent.present(ctx.project) and bool(ctx.state.get("user_intent_protocol"))


def intent_check_errors(ctx, path, label=None):
    """A content-changing task records a short intent_check in the file it already writes."""
    import user_intent
    if not intent_active(ctx) or not path.is_file(): return []
    try: data = yaml_data(path)
    except ValueError: return []
    if user_intent.noted(data.get("intent_check")): return []
    return [f"{label or path.relative_to(ROOT).as_posix()}: intent_check is required — how this work follows the user's instructions "
            "(or which conflict you recorded in plan/user-intent.yaml)"]


class Result:
    def __init__(self, done=False, tasks=None, blockers=None, info=None):
        self.done = done; self.tasks = tasks or []; self.blockers = blockers or []; self.info = info


def accepted(state, identifier):
    return state["accepted"].get(identifier)


def accept(state, identifier, **fields):
    state["accepted"][identifier] = {"at": now(), **fields}
    log_event("goal", "accepted", task=identifier)


def agent_reported(state, identifier):
    return identifier in state.setdefault("reported", {})


def bump(state, key):
    state["counters"][key] = state["counters"].get(key, 0) + 1
    return state["counters"][key]


# ---------------------------------------------------------------- phase handlers

def h_source_ingestion(ctx):
    import sources as registry
    index = registry.reset_interrupted(registry.init_supplied())
    started = time.monotonic()
    while any(s["ingest_status"] == "pending" and s["origin"] == "supplied" for s in index["sources"]):
        if time.monotonic() - started > INGEST_TIME_BUDGET: break
        log_event("source_ingestion", "invoke", tool="fetch-sources")
        attempted = registry.ingest(limit=24, index=index)
        log_event("source_ingestion", "complete", tool="fetch-sources", attempted=len(attempted))
        index = registry.load_index()
    supplied = [s for s in index["sources"] if s["origin"] == "supplied"]
    remaining = [s for s in supplied if s["ingest_status"] == "pending"]
    if remaining:
        return Result(tasks=[task("ingest:continue", "source_ingestion", f"Continue automatic fetching ({len(remaining)} supplied sources remain)",
                                  "Run `bookorder goal` again; fetching is split into short batches so every command stays short.", kind="tool")])
    tasks = []
    for source in supplied:
        state = source["ingest_status"]
        if state in ("needs_agent_fetch", "needs_agent_extraction"):
            location = source.get("url") or source.get("path")
            how = ("Open it with your own browsing/fetch tool" if state == "needs_agent_fetch" else
                   f"Read the saved original ({source.get('raw_path') or source.get('path')}) with your PDF/document tools")
            tasks.append(task(f"ingest:{source['id']}", "source_ingestion", f"Ingest {source['id']}: {location}", [
                f"{how} and extract the COMPLETE readable text (not only the title or first paragraphs) to a temporary Markdown file.",
                f"Then run: bookorder source submit {source['id']} --file <file.md> --status fully_ingested|partially_ingested --method <how> [--title ... --author ... --published YYYY-MM-DD]",
                f"If it truly cannot be read: bookorder source unavailable {source['id']} --attempt \"what you tried\" --reason \"why it is unavailable\"",
                "Limitations so far: " + "; ".join(source.get("limitations", []))], outputs=[f"research/supplied/{source['id']}/source.md"], group="ingest"))
        elif state == "partially_ingested" and not any(a.get("method") == "agent-review" or a.get("result") == "submitted" for a in source["attempts"]):
            tasks.append(task(f"verify:{source['id']}", "source_ingestion", f"Verify partial extraction of {source['id']}", [
                f"Automatic extraction looks partial: {'; '.join(source.get('limitations', []))}. Compare {source.get('content_path')} with the original.",
                f"If it is the complete work: bookorder source confirm {source['id']} --note \"why it is complete\"",
                f"If more text exists: fetch it with your tools and `bookorder source submit {source['id']} --file <full.md>`",
                f"If only partial access is possible: bookorder source accept-partial {source['id']} --note \"what is missing and why\""], group="ingest"))
    if tasks: return Result(tasks=tasks)
    counts = registry.counts(index, "supplied")
    if counts["pending_total"] or counts["attempted"] < counts["total"]:
        return Result(blockers=[{"category": "source retrieval", "detail": f"{counts['pending_total']} supplied sources pending"}])
    log_event("source_ingestion", "summary", **{k: counts[k] for k in ("total", "fully_ingested", "partially_ingested", "unavailable", "duplicate", "pending_total")})
    return Result(done=True)


def h_supplementary_research(ctx):
    import sources as registry
    import research
    index = registry.reset_interrupted(registry.load_index())
    if any(s["ingest_status"] == "pending" for s in index["sources"]):
        log_event("supplementary_research", "invoke", tool="fetch-sources")
        registry.ingest(limit=24); index = registry.load_index()
        log_event("supplementary_research", "complete", tool="fetch-sources")
    tasks = []
    for source in index["sources"]:
        if source["origin"] == "discovered" and source["ingest_status"] in ("needs_agent_fetch", "needs_agent_extraction"):
            tasks.append(task(f"ingest:{source['id']}", "supplementary_research", f"Ingest discovered source {source['id']}", [
                f"Automatic retrieval failed ({'; '.join(source.get('limitations', []))}). Fetch {source.get('url')} with your tools and submit it:",
                f"bookorder source submit {source['id']} --file <file.md> --status fully_ingested|partially_ingested, or bookorder source unavailable {source['id']} --attempt ... --reason ..."], group="ingest"))
    errors = research.check_research_plan(ctx.project)
    if errors or tasks:
        allowed = ctx.project["research"].get("allow_web_research")
        if errors:
            tasks.append(task("research:supplementary", "supplementary_research", "Identify research gaps and perform supplementary research", [
                "Read research/source-status.json and skim every ingested source to find gaps: missing definitions, primary references, official documentation, standards, statistics, newer developments, contradictory evidence, terminology.",
                ("For each gap search the web. Log EVERY search: bookorder research log --query \"...\" --gap gap-01 --tool <search tool> --candidates <json/yaml file> --selected <url or src id>. "
                 "Add each selected source: bookorder source add --url <url> --query \"...\" --gap gap-01 --reason \"why\" (it is fetched and persisted automatically)."
                 if allowed else "Web research is DISABLED for this job: do not discover sources. Record gaps as limitations (status: unresolvable) using only supplied material."),
                "Write research/research-plan.yaml: web_research (performed|disabled|not_needed), gaps: [{id, description, priority, status: resolved|unresolvable|not_needed, sources: [src-...], queries: [q-...], note}].",
                "Important findings must be persisted as sources (source add) — never rely on conversation memory."],
                outputs=["research/research-plan.yaml", "research/search-log.jsonl"], checks=errors))
        return Result(tasks=tasks)
    return Result(done=True)


def h_corpus_analysis(ctx):
    import sources as registry
    import research
    index = registry.load_index()
    research.corpus_summary(index)
    tasks = []
    note_errors = research.check_notes(index)
    missing = research.missing_notes(index)
    batches = [missing[i:i + 8] for i in range(0, len(missing), 8)]
    for number, batch in enumerate(batches, 1):
        tasks.append(task(f"analyze:{batch[0]}", "corpus_analysis", f"Analyze sources {batch[0]}…{batch[-1]} ({len(batch)})", [
            "Read each source's COMPLETE persisted text (research/<origin>/<id>/source.md) — not only its opening.",
            "For each, write research/notes/<id>.yaml: source, relevance (core|supporting|background|irrelevant|duplicate), duplicate_of?, reliability (primary|secondary|tertiary|unknown), summary (whole-source synthesis), key_claims: [{text, locator}], concepts: [terms], limitations, bibliographic: {title, authors, published, container, publisher, type}.",
            "Sources: " + ", ".join(batch)], outputs=[f"research/notes/{x}.yaml" for x in batch], group="analyze"))
    invalid = [e for e in note_errors if not e.startswith("Missing")]
    if invalid:
        tasks.append(task("analyze:fix", "corpus_analysis", "Fix invalid source notes", ["Correct these note problems:"] + invalid, checks=invalid))
    if tasks: return Result(tasks=tasks)
    errors = research.check_synthesis(index)
    if errors:
        return Result(tasks=[task("synthesize", "corpus_analysis", "Global research synthesis across the WHOLE corpus", [
            "Read all research/notes/*.yaml (and source texts where needed) before writing. The book structure must come from the whole corpus, not source order.",
            "Write plan/book-context.yaml (summary, key_questions, reader_needs), plan/concept-map.yaml (concepts: id, term, aliases, definition, sources, related), plan/argument-map.yaml (central_thesis, arguments: id, claim, support, counter), plan/timeline.yaml (events or not_applicable), plan/source-clusters.yaml (clusters: id, label, sources — every relevant source), plan/topic-synthesis.yaml (topics: id, title, synthesis, sources, disputes, candidate_chapter; contradictions: id, description, sources, resolution).",
            "Write source/metadata/glossary.yaml (terms: term, definition, aliases, forbidden variants).",
            "Identify recurring concepts, aliases, chronology, disputes, causal links, primary vs secondary evidence, duplicates and contradictions."],
            outputs=[f"plan/{n}.yaml" for n in research.SYNTHESIS_FILES] + ["source/metadata/glossary.yaml"], checks=errors)])
    research.corpus_summary(index)
    return Result(done=True)


def h_research_frozen(ctx):
    import research
    import sources as registry
    index = registry.load_index()
    if any(s["ingest_status"] in registry.PENDING for s in index["sources"]):
        return Result(blockers=[{"category": "source retrieval", "detail": "Sources still pending at research freeze"}])
    lock = research.freeze()
    log_event("research_frozen", "summary", sources=len(lock["sources"]))
    return Result(done=True)


def h_architecture(ctx):
    from planning import check_bible, check_outline, dependency_graph
    errors = check_bible()
    outline_errors, chapters = check_outline(ctx.scale, ctx.project)
    errors += outline_errors
    intent_outputs = []
    if intent_active(ctx):
        errors += architecture_intent_errors(ctx)
        intent_outputs = ["plan/user-intent.yaml"]
    if errors:
        scale = ctx.scale
        return Result(tasks=[task("architecture", "architecture", "Book Bible and whole-book architecture", [
            f"Scale: {scale['target_characters']:,} body characters (minimum {scale['minimum_characters']:,}) ≈ {scale['requested_pages']} pages. Budgets are binding.",
            *profile_lines(),
            "Write plan/book-bible.yaml: title, subtitle, purpose, audience, tone, central_thesis, scope{included, excluded}, terminology{preferred_terms, definitions, aliases}, editorial_rules{voice, formality, tense, punctuation, citation_style, repetition_policy}, global_narrative{opening, development, turning_points, conclusion}, recurring_concepts, recurring_examples, cross_references, chapter_dependencies, design_intent{theme, typography, figure_style, callout_policy}.",
            "Write source/metadata/outline.yaml: chapters: [{id: ch-<slug>, title, file: source/manuscript/NN-<slug>.md, part?, purpose, prerequisites, introduces, develops, assumes, hands_off_to, target_characters, required_sections: [{id: sec-..., title}], required_topics, sources: {primary, supporting}, required_references, expected_assets, must_not_repeat, handoff}].",
            "Design chapters as a dependency graph grounded in plan/topic-synthesis.yaml and plan/source-clusters.yaml; allocate the character budget intentionally; assign every relevant supplied source."],
            outputs=["plan/book-bible.yaml", "source/metadata/outline.yaml"] + intent_outputs, checks=errors)])
    graph = dependency_graph(chapters)
    log_event("architecture", "summary", chapters=len(chapters), waves=len(graph["parallel_waves"]), planned_characters=sum(c["target_characters"] for c in chapters))
    return Result(done=True)


def architecture_intent_errors(ctx):
    """plan/user-intent.yaml is valid and the Book Bible says which choices come from the user and which are defaults."""
    import user_intent
    from planning import BIBLE
    user_intent.seed(ctx.project)
    errors = user_intent.check(ctx.project)
    bible = yaml_data(BIBLE) if BIBLE.is_file() else {}
    section = bible.get("user_intent") if isinstance(bible.get("user_intent"), dict) else {}
    if not as_list(section.get("governs")):
        errors.append("book-bible.yaml: user_intent.governs is required (each user choice and how this book follows it)")
    if "defaults_used" not in section:
        errors.append("book-bible.yaml: user_intent.defaults_used is required (BookOrder defaults used where the user said nothing; [] if none)")
    return errors


def profile_lines():
    """The resolved PublicationProfile as planning instructions (empty for states that predate profiles)."""
    import publication_profile
    profile = publication_profile.load_resolved()
    return publication_profile.summary_lines(profile) if profile else []


def h_reference_assignment(ctx):
    import citations
    from planning import packet
    log_event("reference_assignment", "invoke", tool="reference-registry")
    entries = citations.generate()
    chapters = ctx.outline()
    for chapter in chapters: packet(chapter, chapters, ctx.scale)
    ctx.contracts()
    log_event("reference_assignment", "complete", tool="reference-registry", references=len(entries), packets=len(chapters))
    return Result(done=True)


def h_editorial_planning(ctx):
    """Before drafting: every chapter's EditorialPlan, checked against the profile (reports/editorial-plan.yaml)."""
    import editorial_plan as ep
    from planning import packet
    chapters = ctx.outline()
    result = ep.run(chapters, project=ctx.project)
    stopping = ep.blocking(ep.all_findings(result))
    if stopping:
        by_chapter = {}
        for f in stopping: by_chapter.setdefault(f.get("chapter") or "book", []).append(f)
        limits = result["limits"]
        tasks = []
        for chapter in chapters:
            problems = by_chapter.get(chapter["id"])
            if not problems: continue
            tasks.append(task(f"editorial:{chapter['id']}", "editorial_planning", f"Editorial plan for {chapter['id']} — {chapter['title']}", [
                f"Plan the chapter before drafting it: read plan/chapter-packets/{chapter['id']}.yaml, plan/book-bible.yaml and the outline entry, then write plan/editorial/{chapter['id']}.yaml (skills/editorial/editorial-planning.md).",
                "Fields: chapter_id, chapter_title, chapter_role (" + "|".join(ep.CHAPTER_ROLES) + "), reader_before, reader_after, target_chars "
                f"({chapter['target_characters']:,} in the outline), lead, density_profile, sections, chapter_end, waivers.",
                "Each section: id, heading, purpose, rhetorical_role (" + "|".join(ep.RHETORICAL_ROLES) + "), intended_reader_effect, expected_density (light|medium|heavy), "
                "target_chars, summary_points, devices, example_needs, case_study_needs, citation_needs, cross_refs, visual_opportunities, new_terms, counterarguments.",
                "Each device: id (becomes the slot id; fig-/tbl- for figures, charts, timelines and tables so it is also the asset id), type (" + ", ".join(ep.CATALOG) + "), "
                "why, placement {intent, position: section_start|early|middle|late|section_end}, source_ids (required for pull_quote, real case_study, timeline, "
                "external counterpoint, chart and factual figure/table); visuals also information_shape and basis. Intents only: rows, nodes and captions are decided in plan/assets-plan.yaml.",
                f"Pauses: at most {limits['pause_every_chars']['max']:,} characters without a device (target {limits['pause_every_chars']['target']:,}); about "
                f"{limits['chars_per_text_page']} characters fill a text page and the proof allows {limits['max_text_only_pages']} text-only pages in a row. "
                "Vary section density; never add a device only to meet a count — split or restructure sections, or waive a medium finding with a reason."] +
                profile_lines() + ["Problems to fix:"] + [f"- [{f['severity']}] {f['rule']} {f.get('section') or ''} {f.get('device') or ''}: {f['detail']}"
                                                          + (f" (try: {f['suggestion']})" if f.get("suggestion") else "") for f in problems[:40]],
                inputs=[f"plan/chapter-packets/{chapter['id']}.yaml"], outputs=[f"plan/editorial/{chapter['id']}.yaml"], group="editorial",
                checks=[f"{f['rule']}: {f['detail']}" for f in problems[:20]]))
        if by_chapter.get("book") and not tasks:
            tasks.append(task("editorial:book", "editorial_planning", "Book-level editorial plan findings", [
                "Revise the chapter plans, or record a reasoned waiver in plan/editorial/book.yaml (waivers: [{rule, reason}]):"] +
                [f"- [{f['severity']}] {f['rule']}: {f['detail']}" for f in by_chapter["book"]], outputs=["plan/editorial/book.yaml"],
                checks=[f["rule"] for f in by_chapter["book"]]))
        return Result(tasks=tasks)
    for chapter in chapters: packet(chapter, chapters, ctx.scale)
    log_event("editorial_planning", "summary", **{k: v for k, v in result["summary"].items() if isinstance(v, (int, float))})
    return Result(done=True)


def drafted(chapter, record, ctx=None):
    from planning import check_summary, summary_path
    return (bool(record) and record["id"] == chapter["id"] and record["chars"] >= 0.5 * chapter["minimum_characters"] and not check_summary(chapter["id"])
            and not (ctx and intent_check_errors(ctx, summary_path(chapter["id"]))))


def h_drafting(ctx):
    from planning import packet
    import citations
    citations.generate()
    chapters = ctx.outline(); mapped = ctx.by_chapter()
    done = {c["id"] for c in chapters if drafted(c, mapped.get(c["id"]), ctx)}
    tasks = []; waiting = []
    waves = {}
    for chapter in chapters:
        level = 1 + max([waves.get(p, 0) for p in chapter["prerequisites"]], default=0); waves[chapter["id"]] = level
        if chapter["id"] in done: continue
        if not all(p in done for p in chapter["prerequisites"]): waiting.append(chapter["id"]); continue
        packet(chapter, chapters, ctx.scale)
        record = mapped.get(chapter["id"])
        current = record["chars"] if record else 0
        from planning import check_summary
        problems = ([] if record else [f"{chapter['file']} missing"]) + (["chapter heading ID must be " + chapter["id"]] if record and record["id"] != chapter["id"] else [])
        problems += ([f"only {current} characters; a first full draft needs at least {int(0.5 * chapter['minimum_characters'])}"] if record and current < 0.5 * chapter["minimum_characters"] else []) + check_summary(chapter["id"])
        from planning import summary_path
        problems += intent_check_errors(ctx, summary_path(chapter["id"]))
        tasks.append(task(f"draft:{chapter['id']}", "drafting", f"Draft {chapter['id']} — {chapter['title']} ({chapter['target_characters']:,} characters)", [
            f"Read plan/chapter-packets/{chapter['id']}.yaml first, then plan/book-bible.yaml, source/metadata/glossary.yaml and the packet's source texts. Do not redefine terminology, tone or thesis.",
            f"Write {chapter['file']} section by section: skeleton → each required section → source enrichment → examples → citations → transitions. Target {chapter['target_characters']:,} characters (minimum {chapter['minimum_characters']:,}); currently {current:,}.",
            "Cite with [cite:src-XXXX] only; cross-reference with @ch:/@sec:/@fig:/@tbl:/@eq:. Never type visible citation numbers.",
            *editorial_lines(chapter),
            f"Then write plan/summaries/{chapter['id']}.yaml: summary (60+ chars), introduced_concepts, key_terms, examples_used, handoff (what the next chapters can assume)"
            + (", intent_check (one or two sentences: how this chapter follows the user's instructions, or the conflict you recorded)." if intent_active(ctx) else ".")],
            inputs=[f"plan/chapter-packets/{chapter['id']}.yaml"], outputs=[chapter["file"], f"plan/summaries/{chapter['id']}.yaml"], group=f"wave-{level}", checks=problems))
    if tasks or waiting:
        return Result(tasks=tasks, info=(f"Waiting on prerequisites: {', '.join(waiting)}" if waiting else None))
    return Result(done=True)


def editorial_lines(chapter):
    """Drafting instructions from the chapter's EditorialPlan (none for legacy jobs without plans)."""
    import editorial_plan
    plan = editorial_plan.load_plan(chapter["id"])
    if not plan: return []
    return editorial_plan.summary_lines(plan) + [
        "Write the sections in this order with their purpose, role and size. Reserve every device as a slot at its placement, e.g. "
        + (editorial_plan.slot_markdown(next((d for _, d in editorial_plan.devices(plan) if editorial_plan.live(d)), {"id": "tbl-example", "type": "table", "placement": "…"})).replace("\n", " ")) + ".",
        "Do not explain in the prose what a slot will show (no paraphrase of the table or quote around it): lead into it and move on. "
        "Component devices (key_point, definition, warning, counterpoint, case_study, pull_quote, column, checklist) and the chapter-end items may be written "
        "directly instead of a slot, with the same id: ::: {.key-point #id} ... ::: (case_study -> .case-study, column -> .sidebar, pull_quote -> .pull-quote, "
        "key_points/summary -> .summary, open_question -> .note, check_questions -> .exercise, further_reading -> .sidebar, bridge_to_next -> ::: {#id} ... :::).",
        "Figures, charts, timelines and tables stay slots until the asset phase produces them."]


def expansion_task(contract, chapter, phase="chapter_review"):
    from planning import packet
    kinds = [r["type"] for r in contract["reasons"]]
    lines = [f"Contract status: {contract['actual_characters']:,}/{contract['target_characters']:,} characters (minimum {contract['minimum_characters']:,})."]
    lines += ["Problem: " + r["detail"] for r in contract["reasons"]]
    if "length" in kinds:
        lines.append(f"Expand by about {contract['deficit']:,} characters with substance: unused assigned sources {', '.join(contract.get('unused_assigned_sources', [])) or '(none)'}, missing concepts, worked examples, historical context, technical explanation, comparisons, counterexamples, limitations. No padding or repetition.")
    lines.append(f"Use plan/chapter-packets/{contract['id']}.yaml (regenerated). Keep the Book Bible, glossary and must_not_repeat. Update plan/summaries/{contract['id']}.yaml if the content changed (keep any intent_check current).")
    return task(("expand:" if kinds == ["length"] else "review:") + contract["id"], phase,
                ("Expand " if kinds == ["length"] else "Complete contract for ") + contract["id"], lines,
                outputs=[chapter["file"]], group="chapters", checks=[r["detail"] for r in contract["reasons"]])


def h_chapter_review(ctx):
    from planning import packet
    chapters = ctx.outline(); results, aggregate = ctx.contracts()
    tasks = []; blockers = []
    by_id = {c["id"]: c for c in chapters}
    for contract in results:
        if contract["status"] == "complete": continue
        key = f"review:{contract['id']}"
        rounds = ctx.state["counters"].get(key, 0)
        if rounds >= MAX_REVIEW_ROUNDS:
            blockers.append({"category": "chapter length deficit" if any(r["type"] == "length" for r in contract["reasons"]) else "chapter contract",
                             "detail": f"{contract['id']} still fails its contract after {rounds} review rounds: " + "; ".join(r["detail"] for r in contract["reasons"])})
            continue
        packet(by_id[contract["id"]], chapters, ctx.scale)
        log_event("chapter_review", "contract_failed", chapter=contract["id"], actual=contract["actual_characters"],
                  minimum=contract["minimum_characters"], deficit=contract["deficit"], reasons=[r["type"] for r in contract["reasons"]])
        tasks.append(expansion_task(contract, by_id[contract["id"]]))
    if blockers: return Result(blockers=blockers, tasks=tasks)
    if tasks: return Result(tasks=tasks)
    if aggregate["book_deficit"] > 0:
        # Every chapter meets its own minimum but the book is still short: expand the chapters furthest below target.
        short = sorted(results, key=lambda r: r["actual_characters"] / max(r["target_characters"], 1))[:max(1, len(results) // 3)]
        return Result(tasks=[task(f"expand:{r['id']}", "chapter_review", f"Expand {r['id']} (book is {aggregate['book_deficit']:,} characters short)", [
            f"The manuscript totals {aggregate['total_actual']:,} characters; the book (≈{ctx.scale['requested_pages']} pages) needs at least {aggregate['book_minimum']:,}.",
            f"Grow {r['id']} toward its {r['target_characters']:,}-character target with substantive material from its packet (unused sources, examples, comparisons, limitations)."],
            outputs=[by_id[r["id"]]["file"]], group="chapters") for r in short])
    return Result(done=True)


def run_integration_checks(ctx, scope):
    import audit
    results, _ = ctx.contracts()
    records = {cid: rec for cid, rec in ctx.by_chapter().items()}
    if scope == "integration": found = audit.integration_checks(records, ctx.outline(), results)
    else: found = audit.audit_checks(records, ctx.outline(), results, ctx.coverage(), ctx.project, ctx.scale)
    log_event(scope, "invoke", tool="deterministic-" + scope, detected=len(found))
    return audit.update_ledger(found, scope, ctx.manuscript_fingerprint())


def h_integration(ctx):
    import audit
    ledger = run_integration_checks(ctx, "integration")
    high = [e for e in audit.open_issues(ledger, ("high",)) if e.get("scope") == "integration"]
    ids = [c["id"] for c in ctx.outline()]
    review_errors = audit.check_review_file(ROOT / "plan/integration-review.yaml", ids) + intent_check_errors(ctx, ROOT / "plan/integration-review.yaml")
    if high or review_errors or not agent_reported(ctx.state, "integrate"):
        lines = ["Read the whole manuscript in order as ONE book. Fix: repeated explanations, terminology drift, inconsistent definitions, contradictions, concepts used before introduction, missing callbacks/hand-offs, broken cross references, duplicated examples, abrupt transitions, inconsistent voice, disproportionate chapter sizes.",
                 "Deterministic findings to fix (see reports/audit-report.yaml):"]
        lines += [f"- {e['id']} [{e['severity']}] {e['chapter']}/{e.get('section') or ''}: {e['detail']}" for e in audit.open_issues(ledger, ("high", "medium")) if e.get("scope") == "integration"][:60]
        lines.append("Then write plan/integration-review.yaml: reviewed_chapters: [all chapter IDs], changes: [{chapter, description}], remaining_issues: [...]. Keep chapter contracts satisfied.")
        return Result(tasks=[task("integrate", "integration", "Whole-book integration pass", lines, outputs=["plan/integration-review.yaml"],
                                  checks=review_errors + [e["detail"] for e in high])])
    results, _ = ctx.contracts()
    if any(r["status"] != "complete" for r in results): return Result(tasks=[expansion_task(r, next(c for c in ctx.outline() if c["id"] == r["id"]), "integration") for r in results if r["status"] != "complete"])
    accept(ctx.state, "integrate", fingerprint=ctx.manuscript_fingerprint())
    return Result(done=True)


def h_asset_planning(ctx):
    import assets
    errors = assets.check_plan(ctx.outline(), ctx.project)
    if errors:
        policy = ctx.project.get("figures", {})
        return Result(tasks=[task("plan-assets", "asset_planning", "Plan figures, tables, equations and images", [
            "Now that substantive text exists, read each chapter and decide where a non-prose representation materially improves understanding. Do not add decorative visuals.",
            f"Figure policy: {json.dumps(policy)}. Route comparisons to tables, quantities to charts, structure to diagrams, and formulas to equations. Consider generated images only for accepted abstract/pictorial concepts or chapter openers; never for factual data or density targets.",
            "Write plan/assets-plan.yaml: assets: [{id (fig-/tbl-/eq- prefix), chapter, section, placement, purpose, type (diagram|chart|table|equation|image|screenshot|cover), source (diagram: source/assets/diagrams/<name>.yaml) or data/prompt, path (chart/image), caption, provenance, style}], or none_needed with a reason.",
            "Each visual is a candidate BookOrder judges (skills/design/figures.md, reports/visual-review.yaml): give information_shape {kind: comparison|quantity|chronology|hierarchy|process|causal|relation|formula|abstract|sequence|source_image, plus counts}, improvement_claim {kinds: [reduce_working_memory|reveal_structure|show_quantity_shape|anchor_abstraction|orient_reader], statement: what the reader gains over prose, in one sentence}, factual_basis (data|source|derived_from_text|illustrative) and source_ids. For images add role, factuality, provider-neutral subject, PNG path and print geometry; keep all lettering in the renderer.",
            "Profile visual density is a health check, not a quota: never add a figure to reach it. Keep rejected ideas in the plan with decision: rejected and decision_reason.",
            "Every figure, chart, timeline and table intent in plan/editorial/*.yaml becomes a candidate here with the same id and device: <device id>; "
            "decide rows/columns, nodes, renderer, geometry and caption from its information_shape. Do not invent visuals outside the editorial plan without adding them there.",
            "Include every expected_assets entry from outline.yaml."], outputs=["plan/assets-plan.yaml"], checks=errors)])
    import visual_review
    review = visual_review.run(ctx.outline())
    log_event("asset_planning", "visual_review", **review["summary"])
    fallback = editorial_fallback_task(ctx, review)
    if fallback: return Result(tasks=[fallback])
    assets.sync_figure_registry()
    return Result(done=True)


def editorial_fallback_task(ctx, review):
    """A rejected visual goes back to the EditorialPlan: table, prose, case study or summary (never a replacement figure by default)."""
    import editorial_plan as ep
    rejected = ep.rejected_devices(ctx.outline(), review)
    if not rejected:
        if not ep.exists(): return None
        # A fallback already applied must itself leave a valid plan (pauses, counts, a table's 3×3 shape).
        stopping = ep.blocking(ep.all_findings(ep.run(ctx.outline(), project=ctx.project)))
        if not stopping: return None
        return task("editorial:recheck", "asset_planning", "Repair the editorial plan after the visual fallbacks", [
            "The editorial plan no longer passes its checks (reports/editorial-plan.yaml). Fix the plans, restructuring sections rather than adding devices to meet counts:"] +
            [f"- [{f['severity']}] {f.get('chapter') or 'book'} {f.get('section') or ''} {f.get('device') or ''} {f['rule']}: {f['detail']}" for f in stopping[:40]],
            outputs=sorted({f"plan/editorial/{f['chapter']}.yaml" for f in stopping if f.get("chapter")}), checks=[f["rule"] for f in stopping[:20]])
    lines = ["The visual review (reports/visual-review.yaml) rejected these planned visuals. Return each to the editorial plan with a fallback:",
             *[f"- {r['chapter']} {r['device']} ({', '.join(r['codes'])}): bookorder editorial fallback {r['device']} --to {r['options'][0]} --reason \"...\""
               + (f"   (other options: {', '.join(r['options'][1:])})" if len(r["options"]) > 1 else "") for r in rejected],
             "prose drops the device (remove its slot and say it in the text); table / case_study / summary add a device in its place that must pass the plan checks "
             "(a table needs a 3×3 comparison, a real case study needs sources). Then remove the rejected candidate from plan/assets-plan.yaml or mark it decision: rejected.",
             "If the fallback leaves a text wall or a visual shortage, restructure the sections (split, reorder, move a comparison into a table) — do not add a figure to reach the number."]
    return task("editorial-fallback", "asset_planning", f"Fall back {len(rejected)} rejected visuals in the editorial plan", lines,
                outputs=[f"plan/editorial/{r['chapter']}.yaml" for r in rejected], checks=[f"{r['device']}: {', '.join(r['codes'])}" for r in rejected])


def h_asset_generation(ctx):
    import assets
    from design import load_design, normalize
    from diagrams import generate
    assets.sync_figure_registry()
    try:
        design_spec = load_design()
        tokens = normalize(design_spec, require_pdf=False)
        import image_assets, layout_spec, style_bible, visual_review
        layout = layout_spec.load_or_create(project=ctx.project, design=design_spec)
        style = style_bible.load_or_resolve(project=ctx.project, design=design_spec)
        image_decisions = visual_review.decisions() or {}
        image_assets.prepare(assets.assets(), image_decisions, style, layout, ctx.project)
        image_check = image_assets.check(assets.assets(), image_decisions)
    except Exception as exc:
        return Result(tasks=[task("assets:images", "asset_generation", "Fix image request or provider",
                                  [f"Image asset preparation failed: {exc}", "Review plan/assets-plan.yaml, resolved StyleBible and project.image_generation.provider."],
                                  checks=[str(exc)])])
    try:
        rendered = generate(tokens, raster=False)
        log_event("asset_generation", "complete", tool="diagram-ir-svg", diagrams=len(rendered))
    except Exception as exc:
        return Result(tasks=[task("assets:diagrams", "asset_generation", "Fix Diagram IR", [f"Diagram rendering failed: {exc}", "Fix the Diagram IR files under source/assets/diagrams/."], checks=[str(exc)])])
    ctx.invalidate()
    errors = assets.check_generation(ctx.outline(), ctx.records())
    errors += [f"{item['asset_id']}: {item['detail']}" for item in image_check['checks'] if item['severity'] == 'high']
    if errors:
        grouped = {}
        for error in errors: grouped.setdefault(error.split(":")[0], []).append(error)
        return Result(tasks=[task(f"asset:{identifier}", "asset_generation", f"Create and place {identifier}", problems + [
            "Diagrams: write Diagram IR YAML (type, title, nodes, edges) and place ![caption](source/assets/figures/<name>.svg){#fig-id} in the planned section — the SVG is rendered by BookOrder.",
            "Tables: pipe table followed by `Table: Caption {#tbl-id}`. Equations: ::: {.equation #eq-id} with $$LaTeX$$ :::. Refer to them with @fig:/@tbl:/@eq:.",
            "Generated images: only accepted abstract/image candidates enter the ImageGenerationRequest pipeline. Configure project.image_generation.provider: fake for offline fixtures; without a provider, required images remain pending_provider and block completion. Review source/assets/generated/<id>.request.json and <id>.json.",
            "A rejected or pending visual must not appear in the text: follow its suggestion in reports/visual-review.yaml (prose, list, table or another type)."],
            group="assets", checks=problems) for identifier, problems in grouped.items()])
    results, _ = ctx.contracts()
    if any(r["status"] != "complete" for r in results):
        return Result(tasks=[expansion_task(r, next(c for c in ctx.outline() if c["id"] == r["id"]), "asset_generation") for r in results if r["status"] != "complete"])
    filling = slot_tasks(ctx)
    if filling: return Result(tasks=filling)
    return Result(done=True)


def open_slots(ctx):
    """Chapter id -> slot ids still in the text (every device must be produced before integration)."""
    return {cid: [s["id"] for s in rec.get("slots", [])] for cid, rec in ctx.by_chapter().items() if rec and rec.get("slots")}


def slot_tasks(ctx):
    import editorial_plan as ep
    tasks = []
    by_id = {c["id"]: c for c in ctx.outline()}
    for chapter, slots in open_slots(ctx).items():
        plan = ep.load_plan(chapter) or ep.normalize({"chapter_id": chapter})
        planned = {d.get("id"): d for _, d in ep.devices(plan, include_end=True)}
        lines = [f"Replace each open slot in {by_id[chapter]['file']} with the device it reserves, keeping the id (skills/editorial/editorial-planning.md):"]
        for ident in slots:
            d = planned.get(ident, {})
            lines.append(f"- {ident} ({d.get('type', 'unplanned')}): {ep.placement(d)['intent'] if d else 'not in the plan: remove it or add it to plan/editorial/' + chapter + '.yaml'}"
                         + (f" [sources: {', '.join(d.get('source_ids', []))}]" if d.get("source_ids") else ""))
        lines.append("Figures/tables come from plan/assets-plan.yaml (same id). Write components as ::: {.key-point #id} ... ::: etc. A device that cannot be produced "
                     "honestly falls back: bookorder editorial fallback <id> --to prose|table|case_study|summary --reason ...")
        tasks.append(task(f"slots:{chapter}", "asset_generation", f"Fill {len(slots)} open slots in {chapter}", lines, outputs=[by_id[chapter]["file"]], group="slots",
                          checks=[f"open slot {i}" for i in slots]))
    return tasks


def chapter_hashes(ctx):
    return {cid: (rec["sha256"] if rec else None) for cid, rec in ctx.by_chapter().items()}


def h_audit(ctx):
    import audit
    import citations
    citations.generate()
    ledger = run_integration_checks(ctx, "audit")
    ids = [c["id"] for c in ctx.outline()]
    tasks = []
    for chapter in ctx.outline():
        path = ROOT / f"plan/audit/{chapter['id']}.yaml"
        errors = audit.check_review_file(path, [chapter["id"]])
        if errors or not agent_reported(ctx.state, f"audit:{chapter['id']}"):
            tasks.append(task(f"audit:{chapter['id']}", "audit", f"Audit {chapter['id']}", [
                f"Audit {chapter['file']} against its sources (packet + research/notes) and the Book Bible: factual consistency, unsupported claims, citation/source mismatch, contradictions, terminology drift, inconsistent definitions, repeated explanations, duplicated examples, dependency errors, transitions, figure/table/equation consistency, notation.",
                f"Write plan/audit/{chapter['id']}.yaml: chapter: {chapter['id']}, reviewed: true, checks: [what you verified], issues: [{{severity: high|medium|low, section, type, description, action}}]. Report real problems only; do not fix yet."],
                outputs=[f"plan/audit/{chapter['id']}.yaml"], group="audit", checks=errors))
    book_errors = audit.check_review_file(ROOT / "plan/audit/book.yaml", ids) + intent_check_errors(ctx, ROOT / "plan/audit/book.yaml")
    if book_errors or not agent_reported(ctx.state, "audit:book"):
        tasks.append(task("audit:book", "audit", "Whole-book audit (cross-chapter)", [
            "Audit across chapters: contradictory statements between chapters, narrative progression, chapter balance, repeated explanations, supplied-source coverage (reports/source-coverage.json), bibliography consistency, figure/table/equation consistency and design consistency.",
            "Deterministic findings are already in reports/audit-report.yaml.",
            "Write plan/audit/book.yaml: reviewed_chapters: [all chapter IDs], issues: [{severity, chapter, section, type, description, action}]."],
            outputs=["plan/audit/book.yaml"], checks=book_errors))
    if tasks: return Result(tasks=tasks)
    found = audit.agent_issues(ROOT / "plan/audit/book.yaml", "book")
    for chapter in ctx.outline(): found += audit.agent_issues(ROOT / f"plan/audit/{chapter['id']}.yaml", chapter["id"])
    ledger = audit.load_ledger()
    known = {audit.issue_key(e) for e in ledger["issues"].values()}
    new = [f for f in found if audit.issue_key(f) not in known]
    if new: audit.update_ledger(new, "agent", ctx.manuscript_fingerprint())
    ctx.state["reviewed_hashes"] = chapter_hashes(ctx)
    accept(ctx.state, "audit", fingerprint=ctx.manuscript_fingerprint(), agent_issues=len(found))
    return Result(done=True)


def h_prose_audit(ctx):
    import audit, prose_signals
    import publication_profile
    profile = publication_profile.load_resolved() or {}
    signals = prose_signals.run(ctx.outline(), profile.get("genre", "general"))
    ids = [c["id"] for c in ctx.outline()]
    path = ROOT / "plan/prose-audit.yaml"
    errors = audit.check_review_file(path, ids) + intent_check_errors(ctx, path)
    if path.is_file():
        report = yaml_data(path)
        for field in ("candidates", "lexical_comparison", "role_comparison", "protected_passages"):
            if field not in report: errors.append(f"plan/prose-audit.yaml: missing {field}")
    if errors or not agent_reported(ctx.state, "prose:audit"):
        return Result(tasks=[task("prose:audit", "prose_audit", "Review prose across the complete manuscript", [
            "Read every chapter in order, then compare chapter and section openings/endings and recurring rhetorical roles across chapters.",
            "Use reports/prose-signals.json as descriptive evidence. Inspect meta discourse, repeated contrasts, paragraph mini-summaries, scaffolding, duplicated argument and uniform structure in context; a frequency alone never warrants an edit.",
            f"Genre context: {signals['genre_context']}. Preserve necessary medical/scientific qualifications, definitions and citations.",
            "Classify rhetorical roles from context: orientation, recap, preview, claim, qualification, counterargument, definition, summary and exercise. Compare role sequences and chapter-opening recap/preview rates, summary endings and qualification density across chapters. Keep lexical repetition separate from rhetorical repetition.",
            "Write plan/prose-audit.yaml with reviewed_chapters: [all IDs], candidates: [{chapter, section, category, evidence, reader_work, proposed_action}], lexical_comparison: [...], role_comparison: [...], and protected_passages: [{chapter, reason}]. Use [] for no findings. No manuscript edits in this task."],
            outputs=["plan/prose-audit.yaml"], checks=errors)])
    accept(ctx.state, "prose_audit", fingerprint=ctx.manuscript_fingerprint())
    return Result(done=True)


def requires_rewrite(issue):
    """Warnings remain visible in reports, but only high paragraph/pacing findings block the workflow."""
    if issue.get("severity") not in ("high", "medium"): return False
    if issue.get("severity") == "medium" and issue.get("type") in ("paragraph-length", "layout-pacing"): return False
    return True


def rewrite_tasks(ctx, ledger):
    import audit
    open_items = [e for e in audit.open_issues(ledger, ("high", "medium")) if requires_rewrite(e)]
    grouped = {}
    for item in open_items: grouped.setdefault(item.get("chapter") or "book", []).append(item)
    tasks = []
    for chapter, items in grouped.items():
        lines = ["Targeted rewrite: change only the affected sections unless a structural fix is required. Afterwards update citations, cross references, the chapter summary, glossary, figures/tables and source coverage as needed."]
        lines += [f"- {e['id']} [{e['severity']}] {e['type']} {e.get('section') or ''}: {e['detail']}" + (f" (evidence: {e['evidence']})" if e.get("evidence") else "") for e in items[:50]]
        lines += ["Agent-reported issues: after fixing run `bookorder audit resolve <id> --note \"what changed\"`. Deterministic issues close automatically when no longer detected. Medium issues that should stay: `bookorder audit resolve <id> --wontfix --note \"reason\"` (never for high).",
                  "Missing evidence? Post-draft research is allowed but tracked: bookorder source add --url ... --post-draft --reason ... --issue <audit-id>, then write its research note before citing it."]
        tasks.append(task(f"rewrite:{chapter}", "rewrite", f"Targeted rewrite of {chapter} ({len(items)} issues)", lines, group="rewrite",
                          checks=[e["id"] for e in items]))
    return tasks


def h_rewrite(ctx):
    import audit
    import citations
    import sources as registry
    index = registry.load_index()
    pending = [s for s in index["sources"] if s["ingest_status"] in registry.PENDING]
    if pending:
        registry.ingest(ids={s["id"] for s in pending if s["ingest_status"] == "pending"})
    citations.generate()
    ledger = run_integration_checks(ctx, "audit")
    tasks = rewrite_tasks(ctx, ledger)
    results, _ = ctx.contracts()
    tasks += [expansion_task(r, next(c for c in ctx.outline() if c["id"] == r["id"]), "rewrite") for r in results if r["status"] != "complete"]
    import research
    missing_notes = [s for s in research.missing_notes()]
    if missing_notes:
        tasks.append(task("analyze:post-draft", "rewrite", "Analyze post-draft sources", [f"Write research/notes/<id>.yaml for: {', '.join(missing_notes)}"]))
    if tasks:
        passes = ctx.state["counters"].get("rewrite_passes", 0)
        if passes >= MAX_REWRITE_PASSES:
            return Result(blockers=[{"category": "editorial inconsistency", "detail": f"{len(tasks)} rewrite targets remain after {passes} passes"}], tasks=tasks)
        return Result(tasks=tasks)
    return Result(done=True)


def h_prose_editing(ctx):
    import audit
    path = ROOT / "plan/prose-editing.yaml"
    errors = audit.check_review_file(path, [c["id"] for c in ctx.outline()]) + intent_check_errors(ctx, path)
    if path.is_file():
        report = yaml_data(path)
        for field in ("edits", "preserved", "citation_reaudit"):
            if field not in report: errors.append(f"plan/prose-editing.yaml: missing {field}")
        rechecked = {(entry.get("chapter"), entry.get("section")) for entry in as_list(report.get("citation_reaudit")) if isinstance(entry, dict) and entry.get("result") == "supported" and entry.get("source_ids")}
        for edit in as_list(report.get("edits")):
            if not isinstance(edit, dict) or edit.get("citation_impact") not in ("unchanged", "changed", "uncertain"):
                errors.append("plan/prose-editing.yaml: each edit needs citation_impact: unchanged|changed|uncertain")
            elif edit["citation_impact"] in ("changed", "uncertain") and (edit.get("chapter"), edit.get("section")) not in rechecked:
                errors.append(f"plan/prose-editing.yaml: {edit.get('chapter')}/{edit.get('section')} changed a cited claim without a supported source recheck")
    if errors or not agent_reported(ctx.state, "prose:edit"):
        return Result(tasks=[task("prose:edit", "prose_editing", "Developmental and cadence edit", [
            "Read plan/prose-audit.yaml, reports/prose-signals.json, the complete manuscript, the Book Bible and the resolved publication profile.",
            "For each candidate ask what new work it does for the reader. Delete redundancy, merge duplication, move misplaced argument, consolidate important repetition, and keep useful or genre-required passages. Make the minimum effective edit; do not rewrite the whole book.",
            "Then review recurring openings, transitions, contrasts and paragraph endings for cadence. Do not randomize sentence lengths, swap synonyms mechanically, or make technical writing colloquial.",
            "Preserve source claims, citation anchors, figures, IDs and authorial voice. If an edit changes the meaning of a cited claim, reopen fact/citation review for that passage and record it in the report.",
            "Write plan/prose-editing.yaml: reviewed_chapters: [all IDs], edits: [{chapter, section, action, reason, citation_impact: unchanged|changed|uncertain}], preserved: [...], citation_reaudit: [{chapter, section, claim, source_ids, result: supported}]. Recheck changed or uncertain cited claims against their sources before marking supported. Use [] when no entries."],
            outputs=["plan/prose-editing.yaml"], checks=errors)])
    accept(ctx.state, "prose_editing", fingerprint=ctx.manuscript_fingerprint())
    return Result(done=True)


def h_final_audit(ctx):
    import audit
    import citations
    import research
    citations.generate()
    ledger = run_integration_checks(ctx, "audit")
    reviewed = ctx.state.get("reviewed_hashes", {})
    current = chapter_hashes(ctx)
    changed = [cid for cid, value in current.items() if reviewed.get(cid) != value]
    tasks = []
    for chapter in changed:
        path = ROOT / f"plan/audit/final-{chapter}.yaml"
        if agent_reported(ctx.state, f"reaudit:{chapter}") and not audit.check_review_file(path, [chapter]) and ctx.state["reported"][f"reaudit:{chapter}"].get("hash") == value_of(current, chapter):
            continue
        tasks.append(task(f"reaudit:{chapter}", "final_audit", f"Re-audit rewritten {chapter}", [
            f"{chapter} changed after the audit. Re-read it completely and check that the rewrites fixed the issues without new errors (facts vs sources, citations, terminology, transitions, cross references).",
            f"Write plan/audit/final-{chapter}.yaml: chapter: {chapter}, reviewed: true, new_issues: [{{severity, section, type, description, action}}] (empty if clean)."],
            outputs=[f"plan/audit/final-{chapter}.yaml"], group="reaudit"))
    if tasks: return Result(tasks=tasks)
    new = []
    for chapter in changed:
        new += audit.agent_issues(ROOT / f"plan/audit/final-{chapter}.yaml", "final-" + chapter)
    known = {audit.issue_key(e) for e in audit.load_ledger()["issues"].values()}
    new = [f for f in new if audit.issue_key(f) not in known]
    if new: ledger = audit.update_ledger(new, "agent", ctx.manuscript_fingerprint())
    for chapter in changed: ctx.state["reviewed_hashes"][chapter] = current[chapter]
    problems = [e for e in audit.open_issues(ledger, ("high", "medium")) if requires_rewrite(e)]
    results, _ = ctx.contracts()
    lock_errors = research.check_lock()
    if problems or any(r["status"] != "complete" for r in results) or lock_errors:
        bump(ctx.state, "rewrite_passes")
        reopen(ctx.state, "rewrite", f"final audit found {len(problems)} open issues" + (f"; lock: {lock_errors[0]}" if lock_errors else ""))
        return Result(info="reopened rewrite")
    accept(ctx.state, "final_audit", fingerprint=ctx.manuscript_fingerprint())
    return Result(done=True)


def value_of(mapping, key):
    return mapping.get(key)


def h_design(ctx):
    from design import load_design, normalize
    errors = []
    try:
        spec = load_design(); normalize(spec, require_pdf=bool(ctx.project["outputs"].get("pdf")))
    except Exception as exc: errors.append(f"Design Spec: {exc}")
    decisions = ROOT / "plan/design-decisions.yaml"
    errors += intent_check_errors(ctx, decisions)
    if errors or not decisions.is_file() or not agent_reported(ctx.state, "design"):
        art = ""
        try: art = load_design().get("art_direction", "")
        except Exception: pass
        return Result(tasks=[task("design", "design", "Apply the design direction", [
            "Read docs/design-system.md, book.design.yaml and plan/book-bible.yaml design_intent. Art direction from the user: " + (art or "(none)"),
            "Translate the direction into book.design.yaml (theme, page, typography roles, colors, layout density, component variants, figure style). Use custom.css / custom.typ only for what the Design Spec cannot express.",
            "Run `bookorder fonts` if you change fonts; unavailable fonts fall back (reports/design-report.json).",
            "Write plan/design-decisions.yaml: theme, decisions: [{direction, spec_change}], overrides: [...], notes."],
            outputs=["book.design.yaml", "plan/design-decisions.yaml"], checks=errors)])
    return Result(done=True)


def build_fresh():
    report = ROOT / "reports/build-report.json"
    if not report.is_file(): return False
    data = json.loads(report.read_text(encoding="utf-8"))
    return data.get("ok") and data.get("fingerprint") == build_fingerprint()


def run_build(ctx, stage):
    import build as builder
    log_event(stage, "invoke", tool="build")
    try:
        builder.build()
        log_event(stage, "complete", tool="build")
        return None
    except Exception as exc:
        from common import report
        report("build-report.json", {"ok": False, "fingerprint": build_fingerprint(), "error": str(exc)})
        log_event(stage, "failed", tool="build", error=str(exc)[:500])
        return str(exc)


def h_layout(ctx):
    import audit
    if not build_fresh():
        error = run_build(ctx, "layout")
        if error:
            return Result(tasks=[task("fix-build", "layout", "Fix the proof build", ["The proof build failed:", error[:3000], "Fix canonical source/design (not generated files) and run bookorder goal."], checks=[error[:300]])])
    built = (ROOT / "reports/build-report.json").stat().st_mtime
    walls = layout_pacing(ctx)
    if walls: return walls
    review = ROOT / "reports/layout-review.md"
    pacing = audit.pacing_issues({cid: rec for cid, rec in ctx.by_chapter().items()})
    fresh_review = review.is_file() and review.stat().st_mtime >= built and len(review.read_text(encoding="utf-8").strip()) > 200
    intent_missing = intent_active(ctx) and review.is_file() and not layout_review_has_intent(review)
    if not fresh_review or intent_missing or not agent_reported(ctx.state, "layout-review"):
        lines = ["Open the proof outputs: publish/book.pdf (several representative pages at real size incl. chapter openers, dense tables, figures, equations, bibliography), publish/site/ (navigation, search, mobile width), interchange/book.docx styles, EPUB if requested.",
                 "Check awkward page breaks, orphan headings, figures separated from their explanation, overflowing tables/code, missing glyphs, long uninterrupted prose runs, callout density and chapter density differences.",
                 "Fix problems in canonical source or Design Spec, rebuild with `bookorder goal`, then record ACTUAL checks and findings in reports/layout-review.md (never invent checks)."]
        lines += [f"- pacing: {p['chapter']}/{p.get('section') or ''}: {p['detail']}" for p in pacing[:20]]
        return Result(tasks=[task("layout-review", "layout", "Visual layout and pacing review of the proof build", lines, outputs=["reports/layout-review.md"],
                                  checks=(["reports/layout-review.md: add a '## User intent' section (what you checked against the user's instructions)"] if intent_missing else None))])
    return Result(done=True)


def layout_review_has_intent(path):
    import re
    return bool(re.search(r"^#{1,4}\s*User intent\b", path.read_text(encoding="utf-8"), re.IGNORECASE | re.MULTILINE))


def layout_pacing(ctx):
    """Text walls measured on the proof pages (scripts/pacing.py) enter the ledger; high ones become revision tasks."""
    import audit, pacing
    result = pacing.check(ctx.project)
    audit.update_ledger(pacing.ledger_issues(result), "layout", ctx.manuscript_fingerprint())
    log_event("layout", "pacing", verdict=result["verdict"], high=result["summary"].get("high", 0))
    if result["verdict"] == "pass": return None
    high = [f for f in result["findings"] if f["severity"] == "high"]
    if any(f["rule"] == "layout_unmeasured" for f in high):
        return Result(tasks=[task("fix-layout-metrics", "layout", "Make the layout measurable", [high[0]["detail"]], checks=[high[0]["detail"][:300]])])
    by_id = {c["id"]: c for c in ctx.outline()}
    limit = result["limits"]
    tasks = []
    for chapter in sorted({f["chapter"] for f in high if f.get("chapter") in by_id}):
        lines = [f"The typeset proof shows text walls in {chapter}: more than {limit['max_text_only_pages']} consecutive pages with no figure, table, callout, "
                 f"pull quote, case study or summary ({limit['tier']} limit, from {limit['source']}). Headings, lists and code blocks do not break a wall.",
                 "Revise the chapter source so that every stretch stays within the limit. Prefer converting existing text (comparison -> table, "
                 "process -> diagram, digression -> column/counterpoint) over adding material; never add decorative assets. Candidates (reports/pacing-report.json):"]
        lines += pacing.task_lines(result, chapter)
        tasks.append(task(f"pacing:{chapter}", "layout", f"Break the text walls in {chapter}", lines, outputs=[by_id[chapter]["file"]], group="pacing"))
    book = [f for f in high if not f.get("chapter") or f["chapter"] not in by_id]
    if book and not tasks:
        tasks.append(task("pacing:book", "layout", "Break the text walls across the book", [f"- {f['detail']}" for f in book]))
    return Result(tasks=tasks)


def h_build(ctx):
    if build_fresh(): return Result(done=True)
    error = run_build(ctx, "build")
    if error:
        return Result(tasks=[task("fix-build", "build", "Fix the build", ["Build failed:", error[:3000]], checks=[error[:300]])])
    return Result(done=True)


def h_validation(ctx):
    from validate import validate
    log_event("validation", "invoke", tool="validate")
    result = validate()
    log_event("validation", "complete" if result["ok"] else "failed", tool="validate", errors=len(result["errors"]))
    if not result["ok"]:
        if any("rebuild" in e.lower() or "changed since" in e.lower() for e in result["errors"]):
            reopen(ctx.state, "build", "validation found a stale build"); return Result(info="rebuilding")
        return Result(tasks=[task("fix-validation", "validation", "Fix structural validation errors", result["errors"][:80], checks=result["errors"][:80])])
    gates = completion_gates(ctx, include_package=False)
    failing = [g for g in gates if not g["passed"]]
    if failing: return handle_failed_gates(ctx, failing)
    return Result(done=True)


def write_editorial_review(ctx):
    import audit
    ledger = audit.load_ledger()
    lines = ["# Editorial review (generated from the audit ledger)", "",
             f"Integration accepted: {accepted(ctx.state, 'integrate') and accepted(ctx.state, 'integrate')['at']}",
             f"Whole-book prose audit accepted: {accepted(ctx.state, 'prose_audit') and accepted(ctx.state, 'prose_audit')['at']}",
             f"Prose edit accepted: {accepted(ctx.state, 'prose_editing') and accepted(ctx.state, 'prose_editing')['at']}",
             f"Final audit accepted: {accepted(ctx.state, 'final_audit') and accepted(ctx.state, 'final_audit')['at']}", "",
             "| ID | Severity | Status | Chapter | Type | Detail |", "|---|---|---|---|---|---|"]
    for entry in sorted(ledger["issues"].values(), key=lambda e: e["id"]):
        lines.append(f"| {entry['id']} | {entry['severity']} | {entry['status']} | {entry.get('chapter') or ''} | {entry['type']} | {str(entry['detail']).replace('|', '/')[:160]} |")
    integration = ROOT / "plan/integration-review.yaml"
    if integration.is_file(): lines += ["", "## Integration review", "", "See plan/integration-review.yaml."]
    if (ROOT / "plan/prose-audit.yaml").is_file():
        lines += ["", "## Whole-book prose review", "", "See plan/prose-audit.yaml, plan/prose-editing.yaml and reports/prose-signals.json. Signals are descriptive; editorial decisions are recorded in the plan files."]
    import user_intent
    lines += user_intent.report_lines(ctx.project)
    (ROOT / "reports/editorial-review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def h_package(ctx):
    import package
    write_editorial_review(ctx)
    if not build_fresh():
        reopen(ctx.state, "build", "package found a stale build"); return Result(info="rebuilding")
    log_event("package", "invoke", tool="package")
    try: package.package()
    except Exception as exc:
        log_event("package", "failed", tool="package", error=str(exc)[:500])
        return Result(tasks=[task("fix-package", "package", "Packaging failed", [str(exc)[:3000]], checks=[str(exc)[:300]])])
    log_event("package", "complete", tool="package")
    return Result(done=True)


def h_complete(ctx):
    gates = completion_gates(ctx, include_package=True)
    failing = [g for g in gates if not g["passed"]]
    if failing: return handle_failed_gates(ctx, failing)
    ctx.state["status"] = "complete"
    log_event("complete", "publication_complete", gates=len(gates))
    return Result(done=True)


HANDLERS = {"source_ingestion": h_source_ingestion, "supplementary_research": h_supplementary_research, "corpus_analysis": h_corpus_analysis,
            "research_frozen": h_research_frozen, "architecture": h_architecture, "reference_assignment": h_reference_assignment,
            "editorial_planning": h_editorial_planning,
            "drafting": h_drafting, "chapter_review": h_chapter_review, "integration": h_integration, "asset_planning": h_asset_planning,
            "asset_generation": h_asset_generation, "audit": h_audit, "prose_audit": h_prose_audit,
            "rewrite": h_rewrite, "prose_editing": h_prose_editing, "final_audit": h_final_audit, "design": h_design,
            "layout": h_layout, "build": h_build, "validation": h_validation, "package": h_package, "complete": h_complete}


# ---------------------------------------------------------------- completion gates

def art_direction_gate(project, root=None, current_fingerprint=None):
    root = root or ROOT
    path = root / "reports/art-direction-check.yaml"
    report = yaml_data(path) if path.is_file() else {}
    pdf = root / "publish/book.pdf"
    pdf_fresh = (not project.get("outputs", {}).get("pdf") or
                 (pdf.is_file() and report.get("pdf_sha256") == __import__("hashlib").sha256(pdf.read_bytes()).hexdigest()))
    fresh = report.get("build_fingerprint") == (current_fingerprint or build_fingerprint()) and pdf_fresh
    summary = report.get("summary") or {}
    high, medium = int(summary.get("high", 0)), int(summary.get("medium", 0))
    return {"passed": bool(fresh and high == 0), "fresh": bool(fresh),
            "high": high, "medium": medium, "report": report}


def image_asset_gate(plan_assets=None, decisions=None, root=None):
    import assets, image_assets, visual_review
    checked = image_assets.check(plan_assets if plan_assets is not None else assets.assets(),
                                 decisions if decisions is not None else visual_review.decisions() or {},
                                 root=root, write=False)
    return {"passed": checked["summary"]["high"] == 0, "summary": checked["summary"], "checks": checked["checks"]}

def completion_gates(ctx, include_package=True):
    """Publication-level criteria. PDF built != complete; all files exist != complete; exit code 0 != complete."""
    import research
    import sources as registry
    import audit
    from planning import check_bible, check_outline
    gates = []
    def gate(identifier, name, passed, detail, phase, category):
        gates.append({"id": identifier, "name": name, "passed": bool(passed), "detail": detail, "phase": phase, "category": category})
    index = registry.load_index(); supplied = registry.counts(index, "supplied")
    gate(1, "All supplied sources attempted", supplied["attempted"] == supplied["total"], f"{supplied['attempted']}/{supplied['total']} attempted", "source_ingestion", "source retrieval")
    gate(2, "Zero pending supplied sources", supplied["pending_total"] == 0, f"{supplied['pending_total']} pending", "source_ingestion", "source retrieval")
    try: cov = ctx.coverage()
    except Exception as exc: cov = {"required": True, "orphan_supplied_sources": [f"coverage error: {exc}"]}
    orphans = cov["orphan_supplied_sources"]
    gate(3, "Required source coverage", not cov["required"] or not orphans, ("orphans: " + ", ".join(orphans[:20])) if orphans else "ok", "rewrite", "source coverage")
    synthesis = research.check_notes(index) + research.check_synthesis(index)
    gate(4, "Research synthesis complete", not synthesis and research.load_lock() is not None, "; ".join(synthesis[:5]) or "ok", "corpus_analysis", "research gap")
    bible = check_bible()
    gate(5, "Book Bible complete", not bible, "; ".join(bible[:5]) or "ok", "architecture", "chapter dependency")
    outline_errors, chapters = check_outline(ctx.scale, ctx.project)
    gate(6, "Book architecture complete", not outline_errors, "; ".join(outline_errors[:5]) or "ok", "architecture", "chapter dependency")
    results, aggregate = ctx.contracts() if chapters else ([], {"total_actual": 0, "book_minimum": ctx.scale["minimum_characters"]})
    failing = [r["id"] for r in results if r["status"] != "complete"]
    gate(7, "Chapter contracts satisfied", chapters and not failing, ("failing: " + ", ".join(failing)) if failing else f"{len(results)} chapters", "chapter_review", "chapter length deficit")
    total = aggregate["total_actual"]
    gate(8, "Manuscript length above minimum", total >= ctx.scale["minimum_characters"],
         f"{total:,} of minimum {ctx.scale['minimum_characters']:,} characters ({(ctx.scale.get('profile') or {}).get('id', 'page target')} profile, ≈{ctx.scale['requested_pages']} pages)", "chapter_review", "chapter length deficit")
    gate(9, "Cross-chapter integration passed", accepted(ctx.state, "integrate") is not None, "accepted" if accepted(ctx.state, "integrate") else "not run", "integration", "editorial inconsistency")
    import assets as asset_module
    asset_errors = (asset_module.check_plan(chapters, ctx.project) if chapters else ["no chapters"]) or asset_module.check_generation(chapters, ctx.records())
    gate(10, "Required figures/tables/equations complete", not asset_errors, "; ".join(asset_errors[:5]) or "ok", "asset_generation", "asset generation")
    ledger = run_integration_checks(ctx, "audit") if chapters else audit.load_ledger()
    citation_open = [e for e in audit.open_issues(ledger, ("high",)) if e["type"] in ("source-mismatch", "bibliography", "cross-reference")]
    gate(11, "Citation/reference validation passed", not citation_open, "; ".join(e["detail"] for e in citation_open[:5]) or "ok", "rewrite", "citation errors")
    final = accepted(ctx.state, "final_audit")
    fresh = final is not None and final.get("fingerprint") == ctx.manuscript_fingerprint()
    gate(12, "Whole-book audit passed on the final manuscript", fresh and accepted(ctx.state, "audit") is not None,
         "fresh" if fresh else ("manuscript changed after the final audit" if final else "not run"), "final_audit", "editorial inconsistency")
    # Layout pacing is judged on the current pages by gate 17, not by what the ledger remembers.
    high = [e for e in audit.open_issues(ledger, ("high",)) if e["type"] != "layout-pacing"]
    # Paragraph-length medium findings are warnings; only high-tier paragraph violations gate completion.
    medium = [e for e in audit.open_issues(ledger, ("medium",)) if e["type"] not in ("layout-pacing", "paragraph-length")]
    gate(13, "High-severity audit issues resolved", not high and not medium, f"{len(high)} high, {len(medium)} medium open", "rewrite", "editorial inconsistency")
    design_problems = audit.design_issues()
    gate(14, "Design validation passed", not design_problems, "; ".join(i["detail"] for i in design_problems) or "ok", "design", "design")
    gate(15, "Build passed and is current", build_fresh(), "fresh" if build_fresh() else "missing, failed or stale", "build", "build")
    import pacing
    walls = pacing.check(ctx.project)
    detail = f"{walls['summary'].get('high', 0)} high, {walls['summary'].get('medium', 0)} medium; max text-only run " \
             f"{walls['summary'].get('max_text_only_run', '?')} (limit {walls['limits']['max_text_only_pages']}, {walls['limits']['tier']})"
    if walls["verdict"] == "fail": detail += ": " + "; ".join(f["detail"] for f in walls["findings"] if f["severity"] == "high")[:400]
    gate(17, "Layout pacing within profile", walls["verdict"] == "pass", detail, "layout", "layout pacing")
    import editorial_plan as ep
    legacy = (ctx.state.get("notes") or {}).get("editorial_planning")
    if chapters and (ep.exists() or not legacy):
        plan = ep.run(chapters, project=ctx.project)
        stopping = ep.blocking(ep.all_findings(plan))
        gate(18, "Editorial plan valid for the profile", not stopping, "; ".join(f"{f['chapter'] or 'book'}: {f['rule']}" for f in stopping[:6])
             or f"{plan['summary']['planned']} chapters planned, {plan['summary']['waived']} waived", "editorial_planning", "editorial plan")
    else: gate(18, "Editorial plan valid for the profile", True, legacy or "no chapters", "editorial_planning", "editorial plan")
    slots = open_slots(ctx) if chapters else {}
    gate(19, "No unresolved slots", not slots, "; ".join(f"{c}: {', '.join(v[:5])}" for c, v in slots.items())[:400] or "all devices placed",
         "asset_generation", "asset generation")
    art = art_direction_gate(ctx.project)
    gate(20, "Art direction consistency", art["passed"],
         f"{art['high']} high, {art['medium']} medium; " + ("fresh" if art["fresh"] else "missing or stale"),
         "validation", "visual consistency")
    image_check = image_asset_gate()
    gate(21, "Generated images resolved and print-safe", image_check['passed'],
         f"{image_check['summary']['high']} high, {image_check['summary']['medium']} medium",
         "validation", "image asset")
    intent = user_intent_gate(ctx)
    gate(22, "User intent governed the book", intent["passed"], intent["detail"], intent["phase"], "user intent")
    if include_package:
        from common import output_paths
        target = ROOT / "publish/result.zip"
        outputs_ok = all(p.is_file() and p.stat().st_size for p in output_paths(ctx.project))
        packaged = target.is_file() and (ROOT / "reports/build-report.json").is_file() and target.stat().st_mtime >= (ROOT / "reports/build-report.json").stat().st_mtime
        gate(16, "Requested output package generated", outputs_ok and packaged, "publish/result.zip" if packaged else "missing or older than build", "package", "build")
    write_json(ROOT / "reports/completion-gates.json", {"checked_at": now(), "passed": all(g["passed"] for g in gates), "gates": gates})
    return gates


def user_intent_gate(ctx):
    """Gate 22: with user instructions, the interpretation is valid and every content/review stage recorded its intent check.
    Conflicts are allowed (they are reported); silence is not."""
    import user_intent
    if not user_intent.present(ctx.project): return {"passed": True, "detail": "no user instructions", "phase": "architecture"}
    if not ctx.state.get("user_intent_protocol"): return {"passed": True, "detail": "legacy job (started before user-intent checks)", "phase": "architecture"}
    from planning import summary_path
    stages = [("architecture", architecture_intent_errors(ctx))]
    stages.append(("drafting", [e for c in ctx.outline() for e in intent_check_errors(ctx, summary_path(c["id"]))]))
    for phase, name in (("integration", "plan/integration-review.yaml"), ("audit", "plan/audit/book.yaml"), ("prose_audit", "plan/prose-audit.yaml"),
                        ("prose_editing", "plan/prose-editing.yaml"), ("design", "plan/design-decisions.yaml")):
        path = ROOT / name
        stages.append((phase, [f"Missing {name}"] if not path.is_file() else intent_check_errors(ctx, path)))
    review = ROOT / "reports/layout-review.md"
    stages.append(("layout", [] if review.is_file() and layout_review_has_intent(review) else ["reports/layout-review.md: no '## User intent' section"]))
    failing = [(phase, errors) for phase, errors in stages if errors]
    if failing:
        return {"passed": False, "phase": failing[0][0], "detail": "; ".join(e for _, errors in failing for e in errors)[:400]}
    found = user_intent.conflicts(ctx.project); overridden = user_intent.overrides(ctx.project)
    return {"passed": True, "phase": "architecture", "detail": f"{len(found)} conflicts reported, {len(overridden)} defaults switched off"
            + (f" ({', '.join(sorted(overridden))})" if overridden else "")}


def handle_failed_gates(ctx, failing):
    earliest = min(failing, key=lambda g: PHASES.index(g["phase"]))
    log_event("goal", "gates_failed", gates=[g["id"] for g in failing])
    if earliest["id"] == 20:
        path = ROOT / "reports/art-direction-check.yaml"
        report = yaml_data(path) if path.is_file() else {}
        if "missing or stale" in earliest["detail"]:
            reopen(ctx.state, "build", "art direction report missing or stale")
            return Result(info="Rebuilding art direction measurements")
        high = [item for item in report.get("checks", []) if item.get("severity") == "high"]
        return Result(tasks=[task("fix-art-direction", "validation", "Resolve art direction drift",
                                  [f"{item['category']} p.{item.get('page') or '?'}: {item['detail']} — {item['suggested_fix']}" for item in high[:20]],
                                  checks=[item["detail"] for item in high[:10]])])
    if earliest["id"] == 21:
        import assets, image_assets, visual_review
        check = image_assets.check(assets.assets(), visual_review.decisions() or {})
        problems = [f"{item['asset_id']}: {item['detail']}" for item in check['checks'] if item['severity'] == 'high']
        return Result(tasks=[task("resolve-image-assets", "validation", "Resolve required generated images",
                                  problems + ["Configure a provider, repair the requested image, or change the editorial/visual plan and rebuild."],
                                  checks=problems[:10])])
    reopen(ctx.state, earliest["phase"], f"gate {earliest['id']} failed: {earliest['name']} ({earliest['detail']})")
    return Result(info=f"Reopened {earliest['phase']}: {earliest['name']}")


# ---------------------------------------------------------------- driver

def advance(max_steps=80):
    project, state = load_state()
    ctx = Context(project, state)
    tasks = []; info = []
    refresh_editorial_plan_dependency(state)
    if state["blockers"] and state["status"] == "blocked":
        return state, [], ["BLOCKED — see blockers; after resolving run `bookorder unblock`"]
    for _ in range(max_steps):
        # A completed publication is re-verified on every call: persisted "complete" flags are never trusted alone.
        current = next((p for p in PHASES if state["phases"][p] != "complete"), "complete")
        if current == "complete" and state["phases"]["complete"] == "complete":
            gates = completion_gates(ctx, include_package=True)
            failing = [g for g in gates if not g["passed"]]
            if not failing: state["status"] = "complete"; break
            state["status"] = "running"; handle_failed_gates(ctx, failing); ctx.invalidate(); continue
        state["phase"] = current
        if state["phases"][current] in ("pending", "failed"): set_phase(state, current, "running")
        try:
            result = HANDLERS[current](ctx)
        except Exception as exc:
            set_phase(state, current, "failed", str(exc)[:300])
            state["status"] = "incomplete"
            log_event(current, "error", error=str(exc)[:1000], trace=traceback.format_exc()[-2000:])
            tasks = [task(f"fix:{current}", current, f"Internal step failed in {current}", [str(exc)[:3000],
                           "Fix the underlying file problem (see run-events.jsonl) and run `bookorder goal` again."], checks=[str(exc)[:300]])]
            break
        ctx.invalidate()
        if result.info: info.append(result.info)
        if result.blockers:
            state["blockers"] = result.blockers; state["status"] = "blocked"
            set_phase(state, current, "blocked", result.blockers[0]["detail"][:300])
            tasks = result.tasks; break
        if result.done:
            if current == "editorial_planning":
                state.setdefault("artifact_fingerprints", {})["editorial_plan"] = editorial_plan_fingerprint()
            set_phase(state, current, "complete")
            if current == "complete": state["status"] = "complete"; break
            continue
        if result.tasks:
            state["status"] = "running"; tasks = result.tasks
            for item in tasks:
                if item["kind"] == "agent":
                    for skill in item["skills"] or [None]:
                        log_event(current, "invoke", task=item["id"], skill=skill)
            break
        # No tasks, not done (e.g. a reopen happened): loop to re-evaluate from the earliest open phase.
    else:
        info.append("Step limit reached; run bookorder goal again")
    save_state(state)
    write_summary(ctx)
    return state, tasks, info


def report_done(identifier, note=None):
    project, state = load_state()
    ctx = Context(project, state)
    record = {"at": now(), "note": note}
    if identifier.startswith("reaudit:"):
        record["hash"] = chapter_hashes(ctx).get(identifier.split(":", 1)[1])
    state.setdefault("reported", {})[identifier] = record
    for prefix, counter in (("review:", "review:"), ("expand:", "review:")):
        if identifier.startswith(prefix): bump(state, counter + identifier.split(":", 1)[1])
    if identifier.startswith("rewrite:"): state["counters"]["rewrite_round_reports"] = state["counters"].get("rewrite_round_reports", 0) + 1
    log_event(state["phase"], "agent_done", task=identifier, note=note)
    save_state(state)


def block(identifier, category, reason):
    project, state = load_state()
    state["blockers"].append({"category": category, "detail": reason, "task": identifier, "at": now()})
    state["status"] = "blocked"; set_phase(state, state["phase"], "blocked", reason)
    log_event(state["phase"], "blocked", task=identifier, category=category, reason=reason)
    save_state(state)


def unblock(note):
    project, state = load_state()
    state["blockers"] = []; state["status"] = "running"
    if state["phases"][state["phase"]] == "blocked": set_phase(state, state["phase"], "running", note)
    log_event(state["phase"], "unblocked", note=note)
    save_state(state)


def write_summary(ctx):
    import sources as registry
    state = ctx.state
    stream = events()
    skills = {}; tools = {}
    for event in stream:
        if event.get("skill") and event["event"] == "invoke": skills[event["skill"]] = skills.get(event["skill"], 0) + 1
        if event.get("tool") and event["event"] == "invoke": tools[event["tool"]] = tools.get(event["tool"], 0) + 1
    index = registry.load_index()
    chapters = {}
    status_path = ROOT / "reports/chapter-status.json"
    if status_path.is_file(): chapters = json.loads(status_path.read_text(encoding="utf-8"))
    gates_path = ROOT / "reports/completion-gates.json"
    gates = json.loads(gates_path.read_text(encoding="utf-8")) if gates_path.is_file() else None
    build_path = ROOT / "reports/build-report.json"
    build = json.loads(build_path.read_text(encoding="utf-8")) if build_path.is_file() else None
    validation_path = ROOT / "reports/validation-report.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8")) if validation_path.is_file() else None
    diagnosis = [{"category": b["category"], "detail": b["detail"]} for b in state.get("blockers", [])]
    if gates:
        diagnosis += [{"category": g["category"], "detail": f"gate {g['id']} {g['name']}: {g['detail']}"} for g in gates["gates"] if not g["passed"]]
    summary = {
        "generated_at": now(), "publication_status": state["status"], "current_phase": state["phase"],
        "complete": state["status"] == "complete",
        "phases": [{"phase": p, "state": state["phases"][p], **state["phase_times"].get(p, {})} for p in PHASES],
        "scale": state["scale"],
        "sources": {"supplied": registry.counts(index, "supplied"), "discovered": registry.counts(index, "discovered"),
                    "post_draft": sum(1 for s in index["sources"] if s.get("post_draft"))},
        "searches_logged": len(__import__("research").search_entries()),
        "chapters": {"planned": len(chapters.get("chapters", [])), "complete": chapters.get("complete", 0),
                     "total_characters": chapters.get("total_actual", 0), "minimum_characters": state["scale"]["minimum_characters"]},
        "skills_invoked": skills, "tools_invoked": tools,
        "tasks_reported_done": len(state.get("reported", {})), "accepted_reviews": sorted(state["accepted"]),
        "rewrite_passes": state["counters"].get("rewrite_passes", 0), "reopened": {k: v for k, v in state["counters"].items() if k.startswith("reopen:")},
        "design_theme": build.get("theme") if build else None,
        "renderer_outputs": build.get("outputs") if build and build.get("ok") else [],
        "validation": {"ok": validation.get("ok"), "errors": len(validation.get("errors", []))} if validation else None,
        "completion_gates": gates, "diagnosis": diagnosis, "user_intent": __import__("user_intent").summary(ctx.project),
        "files": {"state": "project-state.json", "events": "run-events.jsonl", "source_status": "research/source-status.json",
                  "source_index": "research/index.json", "search_log": "research/search-log.jsonl", "research_lock": "research/research-lock.json",
                  "corpus_summary": "research/corpus-summary.yaml", "book_bible": "plan/book-bible.yaml", "outline": "source/metadata/outline.yaml",
                  "chapter_status": "reports/chapter-status.json", "source_coverage": "reports/source-coverage.json",
                  "assets_plan": "plan/assets-plan.yaml", "editorial_plan": "reports/editorial-plan.yaml", "audit_report": "reports/audit-report.yaml",
                  "validation_report": "reports/validation-report.json", "completion_gates": "reports/completion-gates.json"}}
    write_json(SUMMARY, summary)
    return summary


def status_text(state, tasks, info):
    lines = []
    status = state["status"].upper()
    lines.append(f"STATUS: {status}   phase: {state['phase']}")
    done = [p for p in PHASES if state["phases"][p] == "complete"]
    lines.append(f"phases complete: {len(done)}/{len(PHASES)}  (" + ", ".join(f"{p}={state['phases'][p]}" for p in PHASES if state['phases'][p] != 'pending') + ")")
    for item in info: lines.append("note: " + item)
    for blocker in state.get("blockers", []): lines.append(f"BLOCKER [{blocker['category']}]: {blocker['detail']}")
    if state["status"] == "complete":
        lines.append("Publication COMPLETE. Deliverables: publish/, interchange/, publish/result.zip. See execution-summary.json.")
        import user_intent
        if user_intent.present():
            lines.append(f"User intent: {len(user_intent.conflicts())} conflicts recorded — include every one (instruction, stage, resolution, reason) "
                         "in your final report to the user; see reports/editorial-review.md '## User intent'.")
        return "\n".join(lines)
    if tasks:
        agent = [t for t in tasks if t["kind"] == "agent"]
        lines.append(f"\nNEXT TASKS ({len(tasks)}){' — independent tasks in the same parallel_group may run in parallel' if len(agent) > 1 else ''}:")
        for item in tasks:
            lines.append(f"\n## {item['id']} — {item['title']}" + (f"  [group: {item['parallel_group']}]" if item["parallel_group"] else ""))
            if item["skills"]: lines.append("Read: " + ", ".join(item["skills"]))
            if item.get("user_intent"):
                import user_intent
                lines += user_intent.render(item["user_intent"])
                lines.append("Task:")
            for line in item["instructions"]: lines.append("  " + line)
            if item["inputs"]: lines.append("Inputs: " + ", ".join(item["inputs"]))
            if item["outputs"]: lines.append("Outputs: " + ", ".join(item["outputs"][:12]))
            if item["failing_checks"]: lines.append("Currently failing: " + " | ".join(str(c) for c in item["failing_checks"][:12]))
            lines.append(f"When finished: {item['done']}" if item["kind"] == "agent" else "Then run: bookorder goal")
    lines.append("\nDo not stop: after each task run `bookorder done <id>` (or `bookorder goal`) until STATUS: COMPLETE.")
    return "\n".join(lines)

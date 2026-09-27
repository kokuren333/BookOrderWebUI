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

from common import ROOT, read_project, write_json, as_list, fingerprint as build_fingerprint

PHASES = ["source_ingestion", "supplementary_research", "corpus_analysis", "research_frozen", "architecture",
          "reference_assignment", "drafting", "chapter_review", "integration", "asset_planning", "asset_generation",
          "audit", "rewrite", "final_audit", "design", "layout", "build", "validation", "package", "complete"]
STATES = ("pending", "running", "complete", "blocked", "failed")
STATE_FILE = ROOT / "project-state.json"
EVENTS = ROOT / "run-events.jsonl"
SUMMARY = ROOT / "execution-summary.json"
SKILLS = {"source_ingestion": ["skills/source-ingestion.md"], "supplementary_research": ["skills/research.md"],
          "corpus_analysis": ["skills/research.md"], "architecture": ["skills/book-authoring.md"],
          "drafting": ["skills/book-authoring.md"], "chapter_review": ["skills/book-authoring.md"], "integration": ["skills/editing.md"],
          "asset_planning": ["skills/figures.md"], "asset_generation": ["skills/figures.md"], "audit": ["skills/audit.md"],
          "rewrite": ["skills/editing.md", "skills/audit.md"], "final_audit": ["skills/audit.md"], "design": ["skills/editorial-design.md"],
          "layout": ["skills/editorial-design.md", "skills/publication-qa.md"], "build": ["skills/publication-qa.md"]}
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
            "project": {"title": project["book"]["title"], "requested_pages": project["book"].get("target_pages"),
                        "language": project["book"].get("language"), "citation_style": project["citations"]["style"]}}


def load_state():
    project = read_project()
    if STATE_FILE.is_file():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
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
    return {"id": identifier, "phase": phase, "kind": kind, "title": title, "skills": SKILLS.get(phase, []),
            "inputs": list(inputs), "outputs": list(outputs), "instructions": instructions if isinstance(instructions, list) else [instructions],
            "parallel_group": group, "failing_checks": checks or [], "done": f"bookorder done {identifier}"}


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
    if errors:
        scale = ctx.scale
        return Result(tasks=[task("architecture", "architecture", "Book Bible and whole-book architecture", [
            f"Scale: {scale['requested_pages']} pages ≈ {scale['target_characters']:,} characters (minimum {scale['minimum_characters']:,}; ~{scale['characters_per_page']}/page). Budgets are binding.",
            "Write plan/book-bible.yaml: title, subtitle, purpose, audience, tone, central_thesis, scope{included, excluded}, terminology{preferred_terms, definitions, aliases}, editorial_rules{voice, formality, tense, punctuation, citation_style, repetition_policy}, global_narrative{opening, development, turning_points, conclusion}, recurring_concepts, recurring_examples, cross_references, chapter_dependencies, design_intent{theme, typography, figure_style, callout_policy}.",
            "Write source/metadata/outline.yaml: chapters: [{id: ch-<slug>, title, file: source/manuscript/NN-<slug>.md, part?, purpose, prerequisites, introduces, develops, assumes, hands_off_to, target_characters, required_sections: [{id: sec-..., title}], required_topics, sources: {primary, supporting}, required_references, expected_assets, must_not_repeat, handoff}].",
            "Design chapters as a dependency graph grounded in plan/topic-synthesis.yaml and plan/source-clusters.yaml; allocate the character budget intentionally; assign every relevant supplied source."],
            outputs=["plan/book-bible.yaml", "source/metadata/outline.yaml"], checks=errors)])
    graph = dependency_graph(chapters)
    log_event("architecture", "summary", chapters=len(chapters), waves=len(graph["parallel_waves"]), planned_characters=sum(c["target_characters"] for c in chapters))
    return Result(done=True)


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


def drafted(chapter, record):
    from planning import check_summary
    return bool(record) and record["id"] == chapter["id"] and record["chars"] >= 0.5 * chapter["minimum_characters"] and not check_summary(chapter["id"])


def h_drafting(ctx):
    from planning import packet
    import citations
    citations.generate()
    chapters = ctx.outline(); mapped = ctx.by_chapter()
    done = {c["id"] for c in chapters if drafted(c, mapped.get(c["id"]))}
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
        tasks.append(task(f"draft:{chapter['id']}", "drafting", f"Draft {chapter['id']} — {chapter['title']} ({chapter['target_characters']:,} characters)", [
            f"Read plan/chapter-packets/{chapter['id']}.yaml first, then plan/book-bible.yaml, source/metadata/glossary.yaml and the packet's source texts. Do not redefine terminology, tone or thesis.",
            f"Write {chapter['file']} section by section: skeleton → each required section → source enrichment → examples → citations → transitions. Target {chapter['target_characters']:,} characters (minimum {chapter['minimum_characters']:,}); currently {current:,}.",
            "Cite with [cite:src-XXXX] only; cross-reference with @ch:/@sec:/@fig:/@tbl:/@eq:. Never type visible citation numbers.",
            f"Then write plan/summaries/{chapter['id']}.yaml: summary (60+ chars), introduced_concepts, key_terms, examples_used, handoff (what the next chapters can assume)."],
            inputs=[f"plan/chapter-packets/{chapter['id']}.yaml"], outputs=[chapter["file"], f"plan/summaries/{chapter['id']}.yaml"], group=f"wave-{level}", checks=problems))
    if tasks or waiting:
        return Result(tasks=tasks, info=(f"Waiting on prerequisites: {', '.join(waiting)}" if waiting else None))
    return Result(done=True)


def expansion_task(contract, chapter, phase="chapter_review"):
    from planning import packet
    kinds = [r["type"] for r in contract["reasons"]]
    lines = [f"Contract status: {contract['actual_characters']:,}/{contract['target_characters']:,} characters (minimum {contract['minimum_characters']:,})."]
    lines += ["Problem: " + r["detail"] for r in contract["reasons"]]
    if "length" in kinds:
        lines.append(f"Expand by about {contract['deficit']:,} characters with substance: unused assigned sources {', '.join(contract.get('unused_assigned_sources', [])) or '(none)'}, missing concepts, worked examples, historical context, technical explanation, comparisons, counterexamples, limitations. No padding or repetition.")
    lines.append(f"Use plan/chapter-packets/{contract['id']}.yaml (regenerated). Keep the Book Bible, glossary and must_not_repeat. Update plan/summaries/{contract['id']}.yaml if the content changed.")
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
            f"The manuscript totals {aggregate['total_actual']:,} characters; the {ctx.scale['requested_pages']}-page book needs at least {aggregate['book_minimum']:,}.",
            f"Grow {r['id']} toward its {r['target_characters']:,}-character target with substantive material from its packet (unused sources, examples, comparisons, limitations)."],
            outputs=[by_id[r["id"]]["file"]], group="chapters") for r in short])
    return Result(done=True)


def run_integration_checks(ctx, scope):
    import audit
    results, _ = ctx.contracts()
    records = {cid: rec for cid, rec in ctx.by_chapter().items()}
    if scope == "integration": found = audit.integration_checks(records, ctx.outline(), results)
    else: found = audit.audit_checks(records, ctx.outline(), results, ctx.coverage(), ctx.project)
    log_event(scope, "invoke", tool="deterministic-" + scope, detected=len(found))
    return audit.update_ledger(found, scope, ctx.manuscript_fingerprint())


def h_integration(ctx):
    import audit
    ledger = run_integration_checks(ctx, "integration")
    high = [e for e in audit.open_issues(ledger, ("high",)) if e.get("scope") == "integration"]
    ids = [c["id"] for c in ctx.outline()]
    review_errors = audit.check_review_file(ROOT / "plan/integration-review.yaml", ids)
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
            f"Figure policy: {json.dumps(policy)}. Prefer Diagram IR (flow, concept-map, hierarchy, timeline, comparison, cycle, process, network, matrix), tables and equations over generated images.",
            "Write plan/assets-plan.yaml: assets: [{id (fig-/tbl-/eq- prefix), chapter, section, placement, purpose, type (diagram|chart|table|equation|image|screenshot|cover), source (diagram: source/assets/diagrams/<name>.yaml) or data/prompt, path (chart/image), caption, provenance, style}], or none_needed with a reason.",
            "Include every expected_assets entry from outline.yaml."], outputs=["plan/assets-plan.yaml"], checks=errors)])
    assets.sync_figure_registry()
    return Result(done=True)


def h_asset_generation(ctx):
    import assets
    from design import load_design, normalize
    from diagrams import generate
    assets.sync_figure_registry()
    try:
        tokens = normalize(load_design(), require_pdf=False)
        rendered = generate(tokens, raster=False)
        log_event("asset_generation", "complete", tool="diagram-ir-svg", diagrams=len(rendered))
    except Exception as exc:
        return Result(tasks=[task("assets:diagrams", "asset_generation", "Fix Diagram IR", [f"Diagram rendering failed: {exc}", "Fix the Diagram IR files under source/assets/diagrams/."], checks=[str(exc)])])
    ctx.invalidate()
    errors = assets.check_generation(ctx.outline(), ctx.records())
    if errors:
        grouped = {}
        for error in errors: grouped.setdefault(error.split(":")[0], []).append(error)
        return Result(tasks=[task(f"asset:{identifier}", "asset_generation", f"Create and place {identifier}", problems + [
            "Diagrams: write Diagram IR YAML (type, title, nodes, edges) and place ![caption](source/assets/figures/<name>.svg){#fig-id} in the planned section — the SVG is rendered by BookOrder.",
            "Tables: pipe table followed by `Table: Caption {#tbl-id}`. Equations: ::: {.equation #eq-id} with $$LaTeX$$ :::. Refer to them with @fig:/@tbl:/@eq:.",
            "Generated images: save under source/assets/images/ and record source/assets/generated/<id>.json {prompt, generator, created_at, purpose}. If no image tool is available, change the plan to a diagram instead."],
            group="assets", checks=problems) for identifier, problems in grouped.items()])
    results, _ = ctx.contracts()
    if any(r["status"] != "complete" for r in results):
        return Result(tasks=[expansion_task(r, next(c for c in ctx.outline() if c["id"] == r["id"]), "asset_generation") for r in results if r["status"] != "complete"])
    return Result(done=True)


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
    book_errors = audit.check_review_file(ROOT / "plan/audit/book.yaml", ids)
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


def rewrite_tasks(ctx, ledger):
    import audit
    open_items = audit.open_issues(ledger, ("high", "medium"))
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
    problems = audit.open_issues(ledger, ("high", "medium"))
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
    review = ROOT / "reports/layout-review.md"
    pacing = audit.pacing_issues({cid: rec for cid, rec in ctx.by_chapter().items()})
    fresh_review = review.is_file() and review.stat().st_mtime >= built and len(review.read_text(encoding="utf-8").strip()) > 200
    if not fresh_review or not agent_reported(ctx.state, "layout-review"):
        lines = ["Open the proof outputs: publish/book.pdf (several representative pages at real size incl. chapter openers, dense tables, figures, equations, bibliography), publish/site/ (navigation, search, mobile width), interchange/book.docx styles, EPUB if requested.",
                 "Check awkward page breaks, orphan headings, figures separated from their explanation, overflowing tables/code, missing glyphs, long uninterrupted prose runs, callout density and chapter density differences.",
                 "Fix problems in canonical source or Design Spec, rebuild with `bookorder goal`, then record ACTUAL checks and findings in reports/layout-review.md (never invent checks)."]
        lines += [f"- pacing: {p['chapter']}/{p.get('section') or ''}: {p['detail']}" for p in pacing[:20]]
        return Result(tasks=[task("layout-review", "layout", "Visual layout and pacing review of the proof build", lines, outputs=["reports/layout-review.md"])])
    return Result(done=True)


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
             f"Final audit accepted: {accepted(ctx.state, 'final_audit') and accepted(ctx.state, 'final_audit')['at']}", "",
             "| ID | Severity | Status | Chapter | Type | Detail |", "|---|---|---|---|---|---|"]
    for entry in sorted(ledger["issues"].values(), key=lambda e: e["id"]):
        lines.append(f"| {entry['id']} | {entry['severity']} | {entry['status']} | {entry.get('chapter') or ''} | {entry['type']} | {str(entry['detail']).replace('|', '/')[:160]} |")
    integration = ROOT / "plan/integration-review.yaml"
    if integration.is_file(): lines += ["", "## Integration review", "", "See plan/integration-review.yaml."]
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
            "drafting": h_drafting, "chapter_review": h_chapter_review, "integration": h_integration, "asset_planning": h_asset_planning,
            "asset_generation": h_asset_generation, "audit": h_audit, "rewrite": h_rewrite, "final_audit": h_final_audit, "design": h_design,
            "layout": h_layout, "build": h_build, "validation": h_validation, "package": h_package, "complete": h_complete}


# ---------------------------------------------------------------- completion gates

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
         f"{total:,} of minimum {ctx.scale['minimum_characters']:,} characters ({ctx.scale['requested_pages']} pages requested)", "chapter_review", "chapter length deficit")
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
    high = audit.open_issues(ledger, ("high",)); medium = audit.open_issues(ledger, ("medium",))
    gate(13, "High-severity audit issues resolved", not high and not medium, f"{len(high)} high, {len(medium)} medium open", "rewrite", "editorial inconsistency")
    design_problems = audit.design_issues()
    gate(14, "Design validation passed", not design_problems, "; ".join(i["detail"] for i in design_problems) or "ok", "design", "design")
    gate(15, "Build passed and is current", build_fresh(), "fresh" if build_fresh() else "missing, failed or stale", "build", "build")
    if include_package:
        from common import output_paths
        target = ROOT / "publish/result.zip"
        outputs_ok = all(p.is_file() and p.stat().st_size for p in output_paths(ctx.project))
        packaged = target.is_file() and (ROOT / "reports/build-report.json").is_file() and target.stat().st_mtime >= (ROOT / "reports/build-report.json").stat().st_mtime
        gate(16, "Requested output package generated", outputs_ok and packaged, "publish/result.zip" if packaged else "missing or older than build", "package", "build")
    write_json(ROOT / "reports/completion-gates.json", {"checked_at": now(), "passed": all(g["passed"] for g in gates), "gates": gates})
    return gates


def handle_failed_gates(ctx, failing):
    earliest = min(failing, key=lambda g: PHASES.index(g["phase"]))
    log_event("goal", "gates_failed", gates=[g["id"] for g in failing])
    reopen(ctx.state, earliest["phase"], f"gate {earliest['id']} failed: {earliest['name']} ({earliest['detail']})")
    return Result(info=f"Reopened {earliest['phase']}: {earliest['name']}")


# ---------------------------------------------------------------- driver

def advance(max_steps=80):
    project, state = load_state()
    ctx = Context(project, state)
    tasks = []; info = []
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
        "completion_gates": gates, "diagnosis": diagnosis,
        "files": {"state": "project-state.json", "events": "run-events.jsonl", "source_status": "research/source-status.json",
                  "source_index": "research/index.json", "search_log": "research/search-log.jsonl", "research_lock": "research/research-lock.json",
                  "corpus_summary": "research/corpus-summary.yaml", "book_bible": "plan/book-bible.yaml", "outline": "source/metadata/outline.yaml",
                  "chapter_status": "reports/chapter-status.json", "source_coverage": "reports/source-coverage.json",
                  "assets_plan": "plan/assets-plan.yaml", "audit_report": "reports/audit-report.yaml",
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
        return "\n".join(lines)
    if tasks:
        agent = [t for t in tasks if t["kind"] == "agent"]
        lines.append(f"\nNEXT TASKS ({len(tasks)}){' — independent tasks in the same parallel_group may run in parallel' if len(agent) > 1 else ''}:")
        for item in tasks:
            lines.append(f"\n## {item['id']} — {item['title']}" + (f"  [group: {item['parallel_group']}]" if item["parallel_group"] else ""))
            if item["skills"]: lines.append("Read: " + ", ".join(item["skills"]))
            for line in item["instructions"]: lines.append("  " + line)
            if item["inputs"]: lines.append("Inputs: " + ", ".join(item["inputs"]))
            if item["outputs"]: lines.append("Outputs: " + ", ".join(item["outputs"][:12]))
            if item["failing_checks"]: lines.append("Currently failing: " + " | ".join(str(c) for c in item["failing_checks"][:12]))
            lines.append(f"When finished: {item['done']}" if item["kind"] == "agent" else "Then run: bookorder goal")
    lines.append("\nDo not stop: after each task run `bookorder done <id>` (or `bookorder goal`) until STATUS: COMPLETE.")
    return "\n".join(lines)

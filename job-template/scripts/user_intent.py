"""Book-specific user intent: the WebUI's free-text instructions as a governing input to every phase.

The verbatim text lives in project.json `user_instructions` (and TASK.md). It is never summarised away: every
agent task that BookOrder prints carries it verbatim (orchestrator.task), and chapter packets carry it too.

Precedence (docs/user-intent.md):

1. Invariants: factual and citation integrity, source provenance, safety, build validity, the requested outputs,
   and the physical publication settings explicitly selected in the WebUI.
2. Explicit user selections: structured settings for the fields they represent, and the verbatim free-text intent
   for the editorial choices it states (voice, density, scope, structure, examples, apparatus...).
3. Derived decisions: resolved profile, Book Bible, outline, editorial plans.
4. BookOrder defaults and Skill heuristics, which only fill what the user left unspecified.

plan/user-intent.yaml is the agent's interpretation (directives with verbatim `source_quote`s, the pipeline
defaults they switch off, and conflicts). It never outranks the verbatim text. An override is honoured only when
its quote really occurs in the user's text and the rule it switches off is a pipeline default (OVERRIDABLE);
invariant checks cannot be switched off this way.
"""
import re
import unicodedata

from common import ROOT, as_list, read_project, write_yaml, yaml_data

PATH = ROOT / "plan/user-intent.yaml"
DOC = "docs/user-intent.md"

# Pipeline defaults (profile heuristics) that explicit user intent may switch off, by checker rule id.
OVERRIDABLE = {
    # editorial_plan.py
    "chapter_end_missing": "profile chapter-end apparatus (key points / summary, questions, exercises, bridge, checklist)",
    "further_reading_missing": "profile further-reading list per chapter",
    "chapter_lead_missing": "profile chapter lead",
    "key_point_needed": "key-point box for long sections",
    "definition_needed": "definition device for new terms",
    "device_count_under": "profile minimum of tables / callouts / case studies / columns / pull quotes per chapter",
    "device_count_over": "profile maximum of tables / callouts / case studies / columns / pull quotes per chapter",
    "density_monotonous": "varied light / medium / heavy section density",
    "abstract_run": "concrete example after a run of abstraction",
    "section_too_long": "profile section length range",
    "section_too_short": "profile section length range",
    "pause_interval_exceeded": "profile pause rhythm (a device every N characters)",
    "pause_interval_long": "profile pause rhythm (a device every N characters)",
    "text_wall_risk": "planned text-only pages",
    "visual_shortage": "profile visual density (figures/tables per 10,000 characters)",
    "visual_overload": "profile visual density (figures/tables per 10,000 characters)",
    "nonprose_share_low": "profile non-prose share",
    "visual_opportunity_unused": "turning comparisons / chronologies into visuals",
    # pacing.py (gate 17, measured on the typeset proof)
    "layout_pacing": "measured text-only page runs (gate 17)",
}
# Measured pacing findings that the `layout_pacing` override covers.
PACING_RULES = ("run_over_limit", "repeated_walls_in_chapter", "run_crosses_chapters")
CONFLICT_CATEGORIES = ("invariant", "structured_setting", "source_evidence", "technical")

# Phases whose tasks change the book (text, structure, visuals, design) and therefore re-check the intent before done.
CONTENT_PHASES = ("architecture", "editorial_planning", "drafting", "chapter_review", "integration", "asset_planning",
                  "asset_generation", "rewrite", "prose_editing", "design", "layout", "validation")
# Phases that judge or research: they read the intent, and never report a requested choice as a defect.
REVIEW_PHASES = ("supplementary_research", "corpus_analysis", "audit", "prose_audit", "final_audit", "build")

PHASE_NOTES = {
    "supplementary_research": "Research scope follows it: topics it excludes are not gaps to fill, cases and sources it names come first, "
                              "depth it limits stays limited. Do not widen the scope for completeness. Factual accuracy, provenance and "
                              "citation integrity still apply to everything the book does cover.",
    "corpus_analysis": "Judge relevance and synthesise with it in mind (emphasis, exclusions, named cases); do not drop a supplied source "
                       "silently: mark it background/irrelevant with the reason.",
    "architecture": "Shape the Book Bible and outline by it. In plan/book-bible.yaml write user_intent: {governs: [each user choice and how "
                    "the book follows it], defaults_used: [BookOrder defaults adopted only where the user said nothing]}. In "
                    "plan/user-intent.yaml write directives: [{id, source_quote (exact words from the text), interpretation, applies_to: "
                    "[phases], overrides: [pipeline default rule ids it switches off]}] and conflicts. Overridable defaults: "
                    + ", ".join(sorted(OVERRIDABLE)) + ".",
    "editorial_planning": "Chapter roles, section devices and chapter-end items follow it. A profile default it rejects (for example a "
                          "chapter summary the user does not want) is not planned: list it under the directive's overrides in "
                          "plan/user-intent.yaml instead.",
    "drafting": "Voice, distance to the reader, density, stance, examples and exclusions follow it, not a generic textbook style. "
                "Record a one-line intent_check in plan/summaries/<chapter>.yaml (how this chapter follows it, or the conflict).",
    "chapter_review": "Add length only with material it allows (do not add history, counterarguments or scaffolding it excludes).",
    "integration": "Consistency fixes must not normalise the voice or structure the user chose. Write intent_check in "
                   "plan/integration-review.yaml.",
    "asset_planning": "Visual choices follow it (what the user wants shown as a figure or table, and what not to illustrate).",
    "asset_generation": "Visual choices follow it (what the user wants shown as a figure or table, and what not to illustrate).",
    "audit": "Do not report as a defect what the user explicitly asked for (for example no chapter summaries, a one-sided or rough voice, "
             "an omitted topic). Report departures from it as issues with type: user-intent. Factual and citation errors are always "
             "issues. Write intent_check in plan/audit/book.yaml (how the whole book matches it).",
    "rewrite": "Fix the issue without restoring anything it excludes and without normalising the requested voice.",
    "prose_audit": "Patterns the user asked for are protected (list them in protected_passages); only repetition the intent does not call "
                   "for is a candidate. Write intent_check in plan/prose-audit.yaml.",
    "prose_editing": "Keep the voice the user asked for and remove only mechanical repetition and over-explanation. Do not humanise, "
                     "normalise or balance toward a generic style; do not restore counterarguments, summaries or scaffolding it "
                     "excludes. Write intent_check in plan/prose-editing.yaml.",
    "final_audit": "Check that rewrites did not undo it; departures are issues with type: user-intent.",
    "design": "Visual direction follows it within the structured format settings (page size, layout, outputs chosen in the WebUI stay). "
              "Write intent_check in plan/design-decisions.yaml.",
    "layout": "Resolve pacing by restructuring what the user allows; do not insert summaries, counterpoints or pull quotes it excludes. "
              "The layout review (publication QA) adds a '## User intent' section to reports/layout-review.md: what you checked in the "
              "rendered outputs against it.",
    "validation": "Fixes stay within it.",
    "build": "Fixes stay within it.",
}


# ---------------------------------------------------------------- the verbatim text

def verbatim(project=None):
    """The exact user text (project.json user_instructions). Never an interpretation."""
    if project is None:
        try: project = read_project()
        except Exception: return ""
    value = project.get("user_instructions")
    return value if isinstance(value, str) else ""


def present(project=None):
    return bool(verbatim(project).strip())


def _norm(text):
    """Comparison form for quotes: YAML is read through Pandoc, which drops Markdown markup and folds whitespace."""
    text = unicodedata.normalize("NFKC", str(text or ""))
    return re.sub(r"[\s*_`>#~\\]+", "", text)


def quoted(quote, project=None, text=None):
    """True when `quote` really occurs in the user's text (markup and whitespace ignored)."""
    needle = _norm(quote)
    return len(needle) >= 2 and needle in _norm(verbatim(project) if text is None else text)


# ---------------------------------------------------------------- plan/user-intent.yaml

def seed(project=None):
    """Create plan/user-intent.yaml (interpretation skeleton) when the user wrote instructions. Never overwrites."""
    if not present(project) or PATH.is_file(): return False
    write_yaml(PATH, {"verbatim_source": "project.json user_instructions (also TASK.md); authoritative over everything below",
                      "verbatim": verbatim(project), "directives": [], "conflicts": []},
               "Interpretation of the user's instructions. The verbatim text wins over this file. See " + DOC + ".")
    return True


def load():
    if not PATH.is_file(): return {}
    try: return yaml_data(PATH)
    except ValueError: return {}


def check(project=None):
    """Problems in plan/user-intent.yaml (empty when there is no user text)."""
    if not present(project): return []
    if not PATH.is_file(): return ["Missing plan/user-intent.yaml (interpret the user's instructions as directives)"]
    try: data = yaml_data(PATH)
    except ValueError as exc: return [f"plan/user-intent.yaml: {exc}"]
    errors = []
    directives = [d for d in as_list(data.get("directives")) if isinstance(d, dict)]
    if not directives: errors.append("plan/user-intent.yaml: directives are required (one per distinct user choice, each with a verbatim source_quote)")
    ids = set()
    for d in directives:
        ident = str(d.get("id") or "").strip() or "?"
        if ident in ids: errors.append(f"plan/user-intent.yaml: directive id {ident} is used twice")
        ids.add(ident)
        if not quoted(d.get("source_quote"), project):
            errors.append(f"plan/user-intent.yaml: {ident} source_quote must be copied exactly from the user's instructions")
        if len(str(d.get("interpretation") or "").strip()) < 5: errors.append(f"plan/user-intent.yaml: {ident} interpretation is required")
        if not as_list(d.get("applies_to")): errors.append(f"plan/user-intent.yaml: {ident} applies_to is required")
        for rule in as_list(d.get("overrides")):
            if str(rule) not in OVERRIDABLE:
                errors.append(f"plan/user-intent.yaml: {ident} cannot override {rule}: only pipeline defaults ({', '.join(sorted(OVERRIDABLE))}) "
                              "can be switched off; invariants and structured settings are recorded as conflicts instead")
    for c in as_list(data.get("conflicts")):
        if not isinstance(c, dict): errors.append("plan/user-intent.yaml: each conflict is a mapping"); continue
        if not quoted(c.get("instruction"), project): errors.append("plan/user-intent.yaml: conflict instruction must quote the user's words")
        if c.get("category") not in CONFLICT_CATEGORIES:
            errors.append(f"plan/user-intent.yaml: conflict category must be one of {', '.join(CONFLICT_CATEGORIES)}")
        for key in ("stage", "resolution", "reason"):
            if len(str(c.get(key) or "").strip()) < 2: errors.append(f"plan/user-intent.yaml: conflict {key} is required")
    return errors


def overrides(project=None):
    """Pipeline-default rule id -> {quote, directive, interpretation} for every valid override (empty without user text)."""
    if not present(project): return {}
    out = {}
    for d in as_list(load().get("directives")):
        if not isinstance(d, dict) or not quoted(d.get("source_quote"), project): continue
        for rule in as_list(d.get("overrides")):
            if str(rule) in OVERRIDABLE:
                out.setdefault(str(rule), {"quote": str(d.get("source_quote")), "directive": str(d.get("id") or ""),
                                           "interpretation": str(d.get("interpretation") or "")})
    return out


def apply_overrides(findings, intent):
    """Mark findings of switched-off pipeline defaults as waived by user intent (they stop blocking)."""
    for f in findings:
        entry = (intent or {}).get(f.get("rule"))
        if entry:
            f["waived"] = f"user intent {entry['directive']}: \"{entry['quote']}\""
            f["user_intent"] = entry["directive"] or True
    return findings


def conflicts(project=None):
    if not present(project): return []
    return [c for c in as_list(load().get("conflicts")) if isinstance(c, dict)]


def noted(value):
    """An intent_check entry: a sentence, or a mapping/list with content."""
    if isinstance(value, (list, dict)): return bool(value)
    return len(str(value or "").strip()) >= 10


# ---------------------------------------------------------------- task injection

def task_block(phase, project=None):
    """The user-intent block for an agent task in `phase` (None when the user wrote nothing or the phase is mechanical)."""
    text = verbatim(project)
    if not text.strip() or (phase not in CONTENT_PHASES and phase not in REVIEW_PHASES): return None
    rules = ["Read this before performing the task. It is the book-specific instruction from the user and governs this task: it "
             "outranks BookOrder defaults, profile heuristics and Skill preferences (" + DOC + ").",
             "Preserve it unless it conflicts with an invariant (facts, citations, provenance, safety, build validity, requested "
             "outputs) or with a setting explicitly selected in the WebUI (page size, layout, outputs, scale). Do not silently "
             "normalise it toward the default BookOrder style or a generically 'better' book.",
             "If you cannot follow part of it, do not ignore it: add {instruction (the user's words), stage, category: "
             + "|".join(CONFLICT_CATEGORIES) + ", resolution, reason} to conflicts in plan/user-intent.yaml.",
             "plan/user-intent.yaml is only an interpretation; where it differs from the verbatim text, the verbatim text wins."]
    if phase in PHASE_NOTES: rules.append(PHASE_NOTES[phase])
    done = (["Before `bookorder done`: reread the relevant user instructions, verify that what you produced does not contradict "
             "them, and record any intentional divergence (with the exact conflict and reason) in plan/user-intent.yaml."]
            if phase in CONTENT_PHASES else [])
    return {"verbatim": text, "source": "project.json user_instructions / TASK.md", "interpretation": "plan/user-intent.yaml",
            "rules": rules, "before_done": done}


def render(block):
    """Printed form of a task's user-intent block."""
    lines = ["User intent (verbatim from project.json user_instructions / TASK.md):", "  <<<"]
    lines += ["  " + line for line in block["verbatim"].rstrip("\n").split("\n")]
    lines += ["  >>>"] + ["  - " + rule for rule in block["rules"] + block["before_done"]]
    return lines


def packet_entry(project=None):
    text = verbatim(project)
    if not text.strip(): return None
    return {"verbatim": text, "interpretation": "plan/user-intent.yaml", "precedence": "governs voice, density, scope, structure and "
            "apparatus over BookOrder defaults; structured WebUI settings and factual/citation integrity stay binding (" + DOC + ")"}


# ---------------------------------------------------------------- reporting

def report_lines(project=None):
    """Markdown section for reports/editorial-review.md (the job's final editorial report)."""
    if not present(project): return []
    data = load()
    lines = ["", "## User intent", "", "Verbatim instructions: project.json `user_instructions` / TASK.md. Interpretation: plan/user-intent.yaml.", ""]
    directives = [d for d in as_list(data.get("directives")) if isinstance(d, dict)]
    if directives:
        lines += ["| Directive | User's words | Interpretation | Defaults switched off |", "|---|---|---|---|"]
        for d in directives:
            cell = lambda v: str(v or "").replace("|", "/").replace("\n", " ")
            lines.append(f"| {cell(d.get('id'))} | {cell(d.get('source_quote'))} | {cell(d.get('interpretation'))} | {cell(', '.join(map(str, as_list(d.get('overrides')))))} |")
    else: lines.append("No directives recorded.")
    found = conflicts(project)
    lines += ["", "### Conflicts", ""]
    if found:
        lines += ["| User instruction | Stage | Category | Resolution | Reason |", "|---|---|---|---|---|"]
        for c in found:
            cell = lambda v: str(v or "").replace("|", "/").replace("\n", " ")
            lines.append(f"| {cell(c.get('instruction'))} | {cell(c.get('stage'))} | {cell(c.get('category'))} | {cell(c.get('resolution'))} | {cell(c.get('reason'))} |")
    else: lines.append("None recorded.")
    return lines


def summary(project=None):
    if not present(project): return {"present": False}
    data = load()
    return {"present": True, "interpretation": "plan/user-intent.yaml",
            "directives": len([d for d in as_list(data.get("directives")) if isinstance(d, dict)]),
            "overrides": sorted(overrides(project)), "conflicts": conflicts(project)}

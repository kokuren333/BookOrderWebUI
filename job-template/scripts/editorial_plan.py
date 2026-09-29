"""EditorialPlan: what each section does for the reader, where it pauses and which devices carry what, decided
before drafting (plan/editorial/<chapter-id>.yaml, checked into reports/editorial-plan.yaml).

A chapter plan states its role, the reader before and after, its size and its sections. A section states its
purpose, rhetorical role, intended effect, density (light | medium | heavy), size, points, needs and the devices
it carries. Devices come from a closed catalogue and every one says why it is there and where it goes; devices
that assert facts cite sources that exist in the research registry.

The plan is checked against the resolved PublicationProfile before a word is written: device counts per chapter,
the pause interval in characters (the preventive half of pacing; the typeset pages are judged later by
scripts/pacing.py), the density rhythm, section sizes, chapter-end apparatus and the visual rate. Visual devices
are intents only (a comparison here, a chronology there); rows, nodes, renderer, geometry and caption are decided
in plan/assets-plan.yaml and judged by scripts/visual_review.py. A visual the review rejects comes back here and
falls back to a table, prose, a case study or a summary.

Drafting reserves each device as a slot in the chapter text:

    ::: {.slot #tbl-eval-axes kind=table}
    推薦・総合・実力の評価軸を比較
    :::

The slot is replaced by the device itself (same id) when it is produced. Proof builds show open slots as
placeholders; the final validation fails while any slot is unresolved.
"""
import math
import re

from common import ROOT, as_list, write_yaml, yaml_data
from user_intent import apply_overrides

SCHEMA = "bookorder/editorial-plan@1"
DIR = ROOT / "plan/editorial"
BOOK = DIR / "book.yaml"
REPORT = ROOT / "reports/editorial-plan.yaml"

CHAPTER_ROLES = ("introduction", "problem_setting", "development", "counterargument", "synthesis", "practice")
RHETORICAL_ROLES = ("thesis", "evidence", "example", "contrast", "concession", "synthesis", "transition", "application")
DENSITIES = ("light", "medium", "heavy")
POSITIONS = {"section_start": 0.0, "early": 0.25, "middle": 0.5, "late": 0.75, "section_end": 1.0}
STATUSES = ("planned", "realized", "dropped", "replaced")
BASES = ("data", "source", "derived_from_text", "illustrative")
CHAPTER_END = ("key_points", "open_question", "bridge_to_next", "further_reading", "check_questions", "exercises", "checklist", "summary")

# The closed device catalogue. component: the manuscript class that realises it; count: the profile budget it
# spends (devices.<count>); visual: an intent that becomes a plan/assets-plan.yaml candidate.
CATALOG = {
    "figure": {"visual": True, "count": "visuals"},
    "chart": {"visual": True, "count": "visuals"},
    "table": {"visual": True, "count": "tables"},
    "timeline": {"visual": True, "count": "visuals"},
    "key_point": {"component": "key-point", "count": "callouts"},
    "definition": {"component": "definition", "count": "callouts"},
    "glossary": {"component": "glossary-term", "count": None},
    "warning": {"component": "warning", "count": "callouts"},
    "counterpoint": {"component": "counterpoint", "count": "callouts"},
    "checklist": {"component": "checklist", "count": "callouts"},
    "pull_quote": {"component": "pull-quote", "count": "pull_quotes"},
    "case_study": {"component": "case-study", "count": "case_studies"},
    "column": {"component": "sidebar", "count": "columns"},
    "chapter_summary": {"component": "summary", "count": None},
}
ALIASES = {"sidebar": "column", "summary": "key_point", "key-point": "key_point", "pull-quote": "pull_quote", "case-study": "case_study"}
# The publication block library (schemas/publication-architecture.json) extends the catalogue: exercises with answer
# keys, pitfalls, next actions, templates/forms, dialogue examples, clinical cases, algorithm cards … Visual blocks
# (workflow_diagram, decision_table, comparison_table, infographic …) are figure/table intents with a visual_type.
import json as _json
VOCAB = _json.loads((ROOT / "schemas/publication-architecture.json").read_text(encoding="utf-8"))
NEW_COUNTS = {"pitfalls": "callouts", "callout": "callouts", "clinical_case": "case_studies"}
for _block, _spec in VOCAB["blocks"].items():
    _device = _spec.get("device")
    if _spec.get("visual") or _device in CATALOG or _device in ("summary", "further_reading", "open_question", "bridge_to_next", "references"): continue
    CATALOG[_device] = {"component": _spec.get("component"), "marker": _spec.get("marker_class"), "count": NEW_COUNTS.get(_device), "block": _block}
BLOCK_TO_DEVICE = {b: spec["device"] for b, spec in VOCAB["blocks"].items() if spec.get("visual") or spec["device"] in ("warning",)}
CHAPTER_END_ANY = tuple(dict.fromkeys(CHAPTER_END + tuple(b for b, spec in VOCAB["blocks"].items() if "chapter_end" in spec.get("positions", []))))
# Chapter-end items and the component that realises each (bridge_to_next is a plain paragraph block).
END_COMPONENT = {"key_points": "summary", "summary": "summary", "open_question": "note", "bridge_to_next": None,
                 "further_reading": "sidebar", "check_questions": "exercise", "exercises": "exercise", "checklist": "checklist"}
for _block, _spec in VOCAB["blocks"].items():
    if "chapter_end" in _spec.get("positions", []): END_COMPONENT.setdefault(_block, _spec.get("component"))
# A glossary entry is an inline term, not a pause; everything else interrupts running prose on the page.
PAUSES = set(CATALOG) - {"glossary"}
COUNTS = {"tables": "tables_per_chapter", "callouts": "callouts_per_chapter", "case_studies": "case_studies_per_chapter",
          "columns": "columns_per_chapter", "pull_quotes": "pull_quotes_per_chapter"}
# Roles that argue from a source; a pull quote belongs where the argument starts from someone's words.
QUOTE_ROLES = {"thesis", "evidence", "contrast", "concession"}
CONCRETE_ROLES = {"example", "application"}
# Page area of a device as a share of a text page (preventive estimate of the non-prose share).
AREA = {"exercises": 0.2, "answer_key": 0.15, "pitfalls": 0.12, "next_actions": 0.12, "case_reflection": 0.1, "clinical_case": 0.0,
        "template_forms": 0.2, "dialogue_examples": 0.15, "algorithm_card": 0.2, "callout": 0.1, "figure": 0.4, "chart": 0.4, "table": 0.35, "timeline": 0.35, "key_point": 0.12, "definition": 0.12, "warning": 0.12,
        "counterpoint": 0.15, "checklist": 0.15, "pull_quote": 0.12, "case_study": 0.0, "column": 0.0, "chapter_summary": 0.2}
SEVERITIES = ("error", "medium", "low")
DEVICE_ID = re.compile(r"[a-z][a-z0-9-]*")


# ---------------------------------------------------------------- data

def _coerce(value):
    """Pandoc's YAML reader returns numbers as strings."""
    if isinstance(value, dict): return {k: _coerce(v) for k, v in value.items()}
    if isinstance(value, list): return [_coerce(v) for v in value]
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"-?\d+", text): return int(text)
        if re.fullmatch(r"-?\d*\.\d+", text): return float(text)
        if text in ("true", "false"): return text == "true"
    return value


def plan_path(chapter_id):
    return DIR / f"{chapter_id}.yaml"


def load_plan(chapter_id):
    path = plan_path(chapter_id)
    return normalize(_coerce(yaml_data(path))) if path.is_file() else None


def load_plans(chapters):
    return {c["id"]: load_plan(c["id"]) for c in chapters}


def load_book():
    return _coerce(yaml_data(BOOK)) if BOOK.is_file() else {}


def exists():
    return DIR.is_dir() and any(p.name != "book.yaml" for p in DIR.glob("ch-*.yaml"))


def device_type(value):
    value = str(value or "").strip()
    return ALIASES.get(value, value)


def placement(device):
    raw = device.get("placement")
    if isinstance(raw, dict): return {"intent": str(raw.get("intent") or "").strip(), "position": raw.get("position")}
    return {"intent": str(raw or "").strip(), "position": None}


def normalize(plan):
    """Plan with defaults filled in (the file stays as the author wrote it)."""
    plan = dict(plan or {})
    sections = []
    for raw in as_list(plan.get("sections")):
        if not isinstance(raw, dict): continue
        section = dict(raw)
        section["devices"] = []
        for d in as_list(raw.get("devices")):
            if not isinstance(d, dict): continue
            device = dict(d); device["type"] = device_type(d.get("type")); device["status"] = d.get("status") or "planned"
            if device["type"] in BLOCK_TO_DEVICE and device["type"] not in CATALOG:
                block = device["type"]; device["block"] = block; device["type"] = BLOCK_TO_DEVICE[block]
                if VOCAB["blocks"][block].get("visual_type"): device.setdefault("visual_type", VOCAB["blocks"][block]["visual_type"])
            device["source_ids"] = [str(s) for s in as_list(d.get("source_ids"))]
            section["devices"].append(device)
        for key in ("summary_points", "example_needs", "case_study_needs", "citation_needs", "cross_refs", "visual_opportunities",
                    "new_terms", "counterarguments"):
            section[key] = as_list(raw.get(key))
        sections.append(section)
    plan["sections"] = sections
    end = []
    for item in as_list(plan.get("chapter_end")):
        entry = dict(item) if isinstance(item, dict) else {"type": str(item)}
        entry["source_ids"] = [str(s) for s in as_list(entry.get("source_ids"))]
        entry.setdefault("id", end_id(plan.get("chapter_id"), entry.get("type")))
        end.append(entry)
    plan["chapter_end"] = end
    plan["waivers"] = [w for w in as_list(plan.get("waivers")) if isinstance(w, dict)]
    return plan


def end_id(chapter_id, kind):
    return f"{chapter_id}-{str(kind or '').replace('_', '-')}"


def live(device):
    return device.get("status", "planned") in ("planned", "realized")


def devices(plan, include_end=False):
    """(section, device) pairs in reading order."""
    pairs = [(s, d) for s in plan["sections"] for d in s["devices"]]
    if include_end: pairs += [(None, {**e, "type": "chapter_end:" + str(e.get("type"))}) for e in plan["chapter_end"]]
    return pairs


# ---------------------------------------------------------------- findings

def finding(rule, severity, detail, chapter=None, section=None, device=None, suggestion=None):
    return {"rule": rule, "severity": severity, "chapter": chapter, "section": section, "device": device, "detail": detail,
            **({"suggestion": suggestion} if suggestion else {})}


def _waive(findings, waivers):
    for f in findings:
        if f["severity"] == "error": continue
        for w in waivers:
            if w.get("rule") == f["rule"] and all(w.get(k) in (None, "", f.get(k)) for k in ("section", "device")) and str(w.get("reason") or "").strip():
                f["waived"] = str(w["reason"]).strip(); break
    return findings


def blocking(findings):
    """Errors and unwaived medium findings stop the plan; low findings are advice. A pipeline default the user's
    explicit intent switched off (plan/user-intent.yaml overrides, scripts/user_intent.py) never blocks."""
    return [f for f in findings if not f.get("user_intent") and (f["severity"] == "error" or (f["severity"] == "medium" and not f.get("waived")))]


# ---------------------------------------------------------------- device conditions

def shape_admits(kind, shape):
    """Whether a visual intent's information shape can be accepted by the visual review (scripts/visual_review.py)."""
    import visual_review
    options = visual_review.route(shape) if shape.get("kind") in visual_review.SHAPES else []
    wanted = {"table": lambda o: o == "table", "chart": lambda o: o == "chart", "timeline": lambda o: o == "diagram.timeline",
              "figure": lambda o: o.startswith("diagram") or o.startswith("image") or o == "screenshot"}[kind]
    return any(wanted(o) for o in options), options


def fallback_for(options):
    """The device (or prose) an inadmissible visual intent should become."""
    first = (options or ["prose"])[0]
    if first in ("list", "prose"): return "prose"
    if first == "table": return "table"
    if first == "chart": return "chart"
    if first == "diagram.timeline": return "timeline"
    return "figure"


def check_device(chapter, section, device, known_sources, first_terms, chapter_role=None):
    out = []; kind = device["type"]; ident = device.get("id"); sid = section.get("id")
    add = lambda rule, severity, detail, suggestion=None: out.append(finding(rule, severity, detail, chapter, sid, ident, suggestion))
    if kind not in CATALOG:
        add("device_unknown_type", "error", f"device type {device.get('type')!r} is not in the catalogue ({', '.join(CATALOG)})"); return out
    if not ident or not DEVICE_ID.fullmatch(str(ident)): add("device_id_invalid", "error", "device id must match [a-z][a-z0-9-]* (it becomes the slot id)")
    if device["status"] not in STATUSES: add("device_status_invalid", "error", f"status must be one of {', '.join(STATUSES)}")
    if not live(device):
        if not str((device.get("fallback") or {}).get("reason") or device.get("reason") or "").strip():
            add("device_withdrawn_without_reason", "error", f"{device['status']} device needs fallback.reason")
        return out
    if not str(device.get("why") or "").strip(): add("device_missing_why", "error", "every device says why the reader needs it here")
    where = placement(device)
    if not where["intent"]: add("device_missing_placement", "error", "placement intent is required (where in the section, after which point)")
    if where["position"] and where["position"] not in POSITIONS: add("device_placement_invalid", "error", f"placement.position must be one of {', '.join(POSITIONS)}")
    if kind == "chapter_summary": add("chapter_summary_in_section", "error", "a chapter summary belongs in chapter_end (key_points or summary)")
    sources = device["source_ids"]; basis = device.get("basis")
    for s in sources:
        if known_sources is not None and s not in known_sources: add("source_unknown", "error", f"source {s} does not exist in the research registry")
        elif known_sources is not None and known_sources[s] not in ("fully_ingested", "partially_ingested"):
            add("source_unusable", "error", f"source {s} is {known_sources[s]} and cannot support a device")
    needs = None
    if kind == "pull_quote": needs = "a pull quote reproduces someone's words"
    elif kind == "case_study" and device.get("basis", "real") != "hypothetical": needs = "a real case study reports what happened"
    elif kind == "timeline": needs = "a timeline states dated facts"
    elif kind == "counterpoint" and device.get("origin", "external") != "author": needs = "an external counter-argument is someone else's claim"
    elif kind == "chart": needs = "a chart plots data"
    elif kind in ("figure", "table") and basis in ("source", "data"): needs = f"a {kind} with basis {basis} asserts facts"
    if needs and not sources: add("source_required", "error", f"{needs}: source_ids are required", "cite the source, or keep it as the book's own prose")
    allowed = ("real", "hypothetical") if kind == "case_study" else BASES
    if basis and basis not in allowed: add("basis_invalid", "error", f"basis must be one of {', '.join(allowed)}")
    points = [p for p in section["summary_points"] if str(p).strip()]
    if kind == "key_point" and not (int(section.get("target_chars") or 0) > 1500 and len(points) >= 3):
        add("key_point_unwarranted", "low", "key points are for sections over 1,500 characters with 3+ points", "a clear closing sentence may be enough")
    if kind in ("definition", "glossary"):
        terms = [str(t) for t in as_list(device.get("terms"))]
        if not terms: add("definition_terms_missing", "error", f"a {kind} names the terms it defines (terms: [...])")
        for term in terms:
            if term not in [str(t) for t in section["new_terms"]]:
                add("definition_not_new", "medium", f"{term} is not listed in this section's new_terms: define terms where they first appear")
            elif first_terms.get(term, (chapter, sid)) != (chapter, sid):
                add("definition_not_first_use", "medium", f"{term} first appears in {first_terms[term][0]}/{first_terms[term][1]}; define it there")
    if kind == "pull_quote":
        if not (device.get("quote") or device.get("locator")): add("pull_quote_unlocated", "medium", "give the quote text or its locator in the source (no paraphrase in quotation marks)")
        if section.get("rhetorical_role") not in QUOTE_ROLES: add("pull_quote_unwarranted", "low", "a pull quote belongs where the argument starts from a source's words")
    if kind == "counterpoint" and not section["counterarguments"] and section.get("rhetorical_role") not in ("concession", "contrast"):
        add("counterpoint_unwarranted", "low", "no counter-argument or alternative reading is listed for this section")
    if kind == "checklist" and section.get("rhetorical_role") != "application" and chapter_role != "practice":
        add("checklist_unwarranted", "low", "checklists belong to application sections or practice chapters")
    if CATALOG[kind].get("visual"):
        shape = device.get("information_shape") if isinstance(device.get("information_shape"), dict) else {}
        if not shape.get("kind"): add("visual_shape_missing", "error", f"a {kind} intent names its information_shape (kind and counts)")
        else:
            ok, options = shape_admits(kind, shape)
            if kind == "timeline" and int(shape.get("events") or 0) < 3:
                add("timeline_too_few_events", "error", f"{shape.get('events') or 0} dated events: a timeline needs 3 or more", "prose")
            elif kind == "table" and shape.get("kind") == "comparison" and not (int(shape.get("items") or 0) >= 3 and int(shape.get("attributes") or 0) >= 3):
                add("table_too_small", "error", f"{shape.get('items') or 0} items × {shape.get('attributes') or 0} attributes: a table needs 3×3 or more", "prose")
            elif not ok:
                add("visual_not_admissible", "error", f"a {shape.get('kind')} shape would be rejected as a {kind} (fits {', '.join(options) or 'prose'})",
                    fallback_for(options))
            if shape.get("kind") == "causal" and not sources: add("causal_without_sources", "error", "causal structure needs studies or data behind it", "prose")
        if kind in ("figure", "chart") and basis == "illustrative" and shape.get("kind") != "abstract":
            add("visual_illustrative", "error", "an illustrative arrangement presented as structure is rejected by the visual review", "case_study")
        if kind in ("figure", "chart", "table") and not basis: add("visual_basis_missing", "error", "basis is required (data, source, derived_from_text)")
    return out


# ---------------------------------------------------------------- pacing (characters, before typesetting)

def pause_points(plan):
    """Offsets (characters from the chapter start) where running prose is interrupted, with what interrupts it."""
    points = [(0, "chapter opener", None)]; offset = 0
    for section in plan["sections"]:
        size = int(section.get("target_chars") or 0)
        pauses = [d for d in section["devices"] if live(d) and d["type"] in PAUSES]
        unplaced = [d for d in pauses if placement(d)["position"] not in POSITIONS]
        for i, device in enumerate(pauses):
            position = placement(device)["position"]
            fraction = POSITIONS[position] if position in POSITIONS else (unplaced.index(device) + 1) / (len(unplaced) + 1)
            points.append((offset + round(fraction * size), device["type"], device.get("id")))
        offset += size
    if plan["chapter_end"]: points.append((offset, "chapter end", None))
    points.append((offset, "chapter boundary", None))
    return sorted(points, key=lambda p: p[0]), offset


def pacing(plan, profile, chapter):
    rhythm = profile["rhythm"]; per_page = profile["scale"]["chars_per_text_page"]
    points, total = pause_points(plan)
    gaps = []; findings = []
    starts = []; offset = 0
    for s in plan["sections"]:
        starts.append((offset, s.get("id"))); offset += int(s.get("target_chars") or 0)
    for (a, what_a, _), (b, what_b, ident) in zip(points, points[1:]):
        gap = b - a
        if gap <= 0: continue
        spanned = [sid for (start, sid), (end, _) in zip(starts, starts[1:] + [(total, None)]) if start < b and end > a]
        pages = gap / per_page
        entry = {"from": a, "to": b, "chars": gap, "pages_est": round(pages, 1), "after": what_a, "until": what_b, "sections": spanned}
        gaps.append(entry)
        where = f"{', '.join(spanned) or 'chapter'} ({a:,}–{b:,})"
        if gap > rhythm["pause_every_chars"]["max"]:
            findings.append(finding("pause_interval_exceeded", "error", f"{gap:,} characters without a pause in {where}; the profile allows "
                                    f"{rhythm['pause_every_chars']['max']:,}", chapter, spanned[0] if spanned else None, None,
                                    "split the section or place a device the content supports (table, case study, counterpoint, key point)"))
        elif gap > rhythm["pause_every_chars"]["target"]:
            findings.append(finding("pause_interval_long", "low", f"{gap:,} characters without a pause in {where} (target {rhythm['pause_every_chars']['target']:,})",
                                    chapter, spanned[0] if spanned else None))
        if pages > rhythm["max_text_only_pages"]:
            findings.append(finding("text_wall_risk", "medium", f"about {pages:.1f} text-only pages in {where}; the typeset limit is "
                                    f"{rhythm['max_text_only_pages']} (checked on the proof by the pacing gate)", chapter, spanned[0] if spanned else None))
    return gaps, findings


# ---------------------------------------------------------------- one chapter

REQUIRED_CHAPTER = ("chapter_title", "chapter_role", "reader_before", "reader_after", "target_chars", "sections", "chapter_end")
REQUIRED_SECTION = ("id", "heading", "purpose", "rhetorical_role", "intended_reader_effect", "expected_density", "target_chars")


DEVICE_BLOCK = {"warning": "warning_box", "chapter_summary": "summary"}


def block_of(device):
    """The block-library id a device realises (policy checks use it)."""
    import publication_architecture as pa
    return pa.canonical(device.get("block") or DEVICE_BLOCK.get(device.get("type"), device.get("type")))


def adaptive(arch):
    """AUTO / GUIDED: the block policy decides; FIXED (or no architecture, the legacy default): the profile template."""
    return bool(arch) and not arch.get("legacy") and arch.get("mode") in ("auto", "guided")


def check_chapter(chapter, plan, profile, known_sources=None, first_terms=None, last=False, intent=None, arch=None):
    cid = chapter["id"]; findings = []; intent = intent or {}
    flexible = adaptive(arch)
    add = lambda rule, severity, detail, section=None, device=None, suggestion=None: findings.append(finding(rule, severity, detail, cid, section, device, suggestion))
    if plan is None:
        add("plan_missing", "error", f"write plan/editorial/{cid}.yaml before drafting"); return {"id": cid, "findings": findings}
    first_terms = first_terms if first_terms is not None else {}
    plan = normalize(plan)
    if plan.get("chapter_id") != cid: add("chapter_id_mismatch", "error", f"chapter_id must be {cid}")
    for key in REQUIRED_CHAPTER:
        value = plan.get(key)
        optional_end = key == "chapter_end" and (flexible or not profile["structure"]["chapter_end"] or "chapter_end_missing" in intent)
        if value in (None, "", []) and not optional_end: add("missing_field", "error", f"{key} is required")
    if plan.get("chapter_role") and plan["chapter_role"] not in CHAPTER_ROLES: add("chapter_role_invalid", "error", f"chapter_role must be one of {', '.join(CHAPTER_ROLES)}")
    target = int(plan.get("target_chars") or 0); outline_target = int(chapter.get("target_characters") or 0)
    if target and outline_target and abs(target - outline_target) > 0.1 * outline_target:
        add("target_mismatch_outline", "error", f"target_chars {target:,} differs from the outline budget {outline_target:,} by more than 10%")
    sections = plan["sections"]
    ids = [s.get("id") for s in sections]
    for sid in {i for i in ids if ids.count(i) > 1}: add("section_duplicate_id", "error", f"section id {sid} is used twice", sid)
    covered = set(ids) | {s.get("parent") for s in sections}  # a required section may be planned as several parts (parent: <id>)
    for required in chapter.get("required_sections", []):
        if required.get("id") and required["id"] not in covered: add("required_section_missing", "error", f"outline section {required['id']} is not planned", required["id"])
    total = sum(int(s.get("target_chars") or 0) for s in sections)
    if target and sections:
        drift = abs(total - target) / target
        if drift > 0.15: add("section_sum_mismatch", "error", f"sections total {total:,} characters against a chapter target of {target:,}")
        elif drift > 0.05: add("section_sum_mismatch", "medium", f"sections total {total:,} characters against a chapter target of {target:,}")
    size = profile["structure"]["section_chars"]
    for s in sections:
        sid = s.get("id")
        for key in REQUIRED_SECTION:
            if s.get(key) in (None, ""): add("section_missing_field", "error", f"section {sid or '?'}: {key} is required", sid)
        if s.get("rhetorical_role") and s["rhetorical_role"] not in RHETORICAL_ROLES: add("rhetorical_role_invalid", "error", f"rhetorical_role must be one of {', '.join(RHETORICAL_ROLES)}", sid)
        if s.get("expected_density") and s["expected_density"] not in DENSITIES: add("density_invalid", "error", "expected_density must be light, medium or heavy", sid)
        chars = int(s.get("target_chars") or 0)
        if chars > size["max"]: add("section_too_long", "medium", f"{chars:,} characters; the profile's sections run {size['min']:,}–{size['max']:,}", sid,
                                    suggestion="split it at a change of purpose or rhetorical role")
        elif chars and chars < size["min"]: add("section_too_short", "low", f"{chars:,} characters; the profile's sections run {size['min']:,}–{size['max']:,}", sid)
        for term in s["new_terms"]: first_terms.setdefault(str(term), (cid, sid))
    # Density rhythm.
    rhythm = [s.get("expected_density") for s in sections]
    declared = [str(x) for x in as_list(plan.get("density_profile"))]
    if declared and declared != rhythm: add("density_profile_mismatch", "error", f"density_profile {declared} does not match the sections' expected_density {rhythm}")
    if len(sections) >= 3 and len(set(rhythm)) == 1:
        add("density_monotonous", "medium", f"every section is {rhythm[0]}: vary light, medium and heavy sections so the chapter breathes")
    run = 0
    for s, density in zip(sections, rhythm):
        run = run + 1 if density == "heavy" else 0
        if run == 3: add("density_heavy_run", "low", "three heavy sections in a row", s.get("id"))
    # Devices.
    seen = {}
    for s in sections:
        sid = s.get("id")
        for device in s["devices"]:
            findings += check_device(cid, s, device, known_sources, first_terms, plan.get("chapter_role"))
        chars = int(s.get("target_chars") or 0)
        kinds = {d["type"] for d in s["devices"] if live(d)}
        points = [p for p in s["summary_points"] if str(p).strip()]
        if chars > 1500 and len(points) >= 3 and "key_point" not in kinds:
            add("key_point_needed", "low" if flexible else "medium", f"{chars:,} characters with {len(points)} points: plan a key_point", sid, suggestion="key_point")
        defined = {str(t) for d in s["devices"] if live(d) and d["type"] in ("definition", "glossary") for t in as_list(d.get("terms"))}
        undefined = [str(t) for t in s["new_terms"] if str(t) not in defined and first_terms.get(str(t)) == (cid, sid)]
        if undefined: add("definition_needed", "low", f"new terms without a definition device: {', '.join(undefined)} (a clear definition in prose is fine)", sid)
        for opportunity in s["visual_opportunities"]:
            if not isinstance(opportunity, dict) or opportunity.get("declined"): continue
            shape = opportunity.get("information_shape") or opportunity
            used = any(isinstance(d.get("information_shape"), dict) and d["information_shape"].get("kind") == shape.get("kind") for d in s["devices"] if live(d))
            admissible = [k for k in ("table", "chart", "timeline", "figure") if shape.get("kind") and shape_admits(k, shape)[0]]
            if admissible and not used:
                add("visual_opportunity_unused", "low", f"{shape.get('kind')} ({opportunity.get('note') or opportunity.get('description') or ''}) could be a {admissible[0]}; "
                    "plan it or mark it declined with a reason", sid, suggestion=admissible[0])
    for s, d in devices(plan):
        if d.get("id"):
            if d["id"] in seen: add("device_duplicate_id", "error", f"device id {d['id']} is used twice", s.get("id"), d["id"])
            seen[d["id"]] = s.get("id")
    # Concrete material after a stretch of abstraction.
    limit = 2 * profile["rhythm"]["abstract_run_chars_max"]; stretch = 0; begun = None
    for s in sections:
        concrete = s.get("rhetorical_role") in CONCRETE_ROLES or s["example_needs"] or any(d["type"] == "case_study" and live(d) for d in s["devices"])
        if concrete: stretch = 0; begun = None; continue
        stretch += int(s.get("target_chars") or 0); begun = begun or s.get("id")
        if stretch > limit:
            add("abstract_run", "medium", f"{stretch:,} characters of abstraction from {begun} without an example or case", s.get("id"),
                suggestion="example_needs or a sourced case_study"); stretch = 0; begun = None
    # Counts per chapter against the profile.
    counts = {key: 0 for key in COUNTS}; visuals = 0
    for _, d in devices(plan):
        if not live(d) or d["type"] not in CATALOG: continue
        spend = CATALOG[d["type"]]["count"]
        if spend in counts: counts[spend] += 1
        if CATALOG[d["type"]].get("visual") and spend != "tables": visuals += 1
    for key, setting in COUNTS.items():
        bounds = profile["devices"][setting]
        # Profile ranges are per-chapter averages (0.8 callouts); a chapter holds whole devices.
        low, high = int(bounds["min"] + 0.5), int(bounds["max"] + 0.5)
        if counts[key] > high: add("device_count_over", "medium" if flexible else "error", f"{counts[key]} {key.replace('_', ' ')}; the profile allows at most {bounds['max']} per chapter")
        elif counts[key] < low:
            add("device_count_under", "low" if flexible else "medium", f"{counts[key]} {key.replace('_', ' ')}; the profile expects at least {bounds['min']} per chapter. Look for material the "
                "sections already contain; do not add devices to reach the number (waive with a reason if the chapter has none)", suggestion=key)
    # Chapter end. FIXED: the profile's apparatus in every chapter (legacy). AUTO/GUIDED: only what the architecture
    # explicitly requires; every item is chosen for this chapter's content and says why.
    if flexible: required = [k for k in arch["block_policy"].get("required_chapter_end") or [] if not (k == "bridge_to_next" and last)]
    else: required = [k for k in profile["structure"]["chapter_end"] if not (k == "bridge_to_next" and last)]
    present = [str(e.get("type")) for e in plan["chapter_end"]]
    import publication_architecture as pa
    for item in present:
        if item not in CHAPTER_END_ANY: add("chapter_end_unknown", "error", f"chapter_end {item} is not one of {', '.join(CHAPTER_END_ANY)}")
    for item in required:
        if item not in present and pa.canonical(item) not in {pa.canonical(x) for x in present}:
            add("chapter_end_missing", "error", f"the {'architecture' if flexible else 'profile'} requires {item} at the end of every chapter")
    if flexible:
        findings += block_policy_findings(cid, chapter, plan, arch)
    reading = profile["citations"]["further_reading_per_chapter"]
    for e in plan["chapter_end"]:
        if e.get("type") == "further_reading":
            if len(e["source_ids"]) < int(reading["min"] + 0.5): add("further_reading_sources", "error", f"further reading lists {len(e['source_ids'])} sources; the profile expects {reading['min']}+")
            for s in e["source_ids"]:
                if known_sources is not None and s not in known_sources: add("source_unknown", "error", f"source {s} does not exist in the research registry", device=e["id"])
                elif known_sources is not None and known_sources[s] not in ("fully_ingested", "partially_ingested"):
                    add("source_unusable", "error", f"source {s} is {known_sources[s]} and cannot support further reading", device=e["id"])
    if int(reading["min"] + 0.5) > 0 and "further_reading" not in present: add("further_reading_missing", "low" if flexible else "medium", f"the profile expects {reading['min']}+ further-reading sources per chapter")
    if profile["structure"]["chapter_lead"] == "required" and not str(plan.get("lead") or "").strip():
        add("chapter_lead_missing", "medium", "the profile requires a chapter lead: state what it tells the reader (lead: ...)")
    gaps, pace = pacing(plan, profile, cid)
    findings += pace
    _waive(findings, plan["waivers"])
    apply_overrides(findings, intent)
    return {"id": cid, "role": plan.get("chapter_role"), "target_chars": target, "planned_chars": total, "density_profile": rhythm,
            "counts": {**counts, "visuals": visuals + counts["tables"]}, "pauses": gaps,
            "max_gap_chars": max([g["chars"] for g in gaps], default=0), "findings": findings}


def block_policy_findings(cid, chapter, plan, arch):
    """AUTO / GUIDED: every device and chapter-end item is a block the chapter's policy allows, exercises come with
    answers, the chapter's planned blocks (outline) are realised, uploaded assets meant for it are planned."""
    import publication_architecture as pa
    import source_roles
    out = []
    add = lambda rule, severity, detail, section=None, device=None, suggestion=None: out.append(finding(rule, severity, detail, cid, section, device, suggestion))
    policy = pa.chapter_policy(arch, chapter)
    used = []
    items = [(s, d, block_of(d)) for s, d in devices(plan) if live(d)] + [(None, e, pa.canonical(e.get("type"))) for e in plan["chapter_end"]]
    for section, d, block in items:
        used.append(block)
        where = section.get("id") if section else None
        state = pa.status(policy, block)
        why = pa.reason(arch, block)
        if state == "forbidden":
            add("block_forbidden", "error", f"{block} is forbidden for this book{(' (' + why + ')') if why else ''}; remove it", where, d.get("id"))
        elif state == "discouraged":
            add("block_discouraged", "medium", f"{block} is discouraged for a {arch['archetype']['primary']}{(' (' + why + ')') if why else ''}: drop it, or keep it "
                "with a waiver that says why this chapter needs it", where, d.get("id"))
        if section is None and not str(d.get("why") or "").strip():
            add("chapter_end_missing_why", "error", f"chapter_end {d.get('type')} needs why: what this chapter's reader gains from it here", None, d.get("id"))
    exercises = [(s, d) for s, d, b in items if b == "exercises"]
    answers = [d for s, d, b in items if b == "answer_key"]
    for section, d in exercises:
        if not answers and not str((d.get("answers") or {}).get("location") if isinstance(d.get("answers"), dict) else d.get("answers") or "").strip():
            add("exercise_without_answers", "error", "exercises need answers or explanations the reader can recover: plan an answer_key, or answers: {location: <section id | appendix>}",
                section.get("id") if section else None, d.get("id"), "answer_key")
    for block in policy["planned"]:
        if block not in used and pa.status(policy, block) != "forbidden":
            add("chapter_block_unplanned", "medium", f"the outline plans a {block} for this chapter (source/metadata/outline.yaml blocks) but the editorial plan does not; plan it or update the outline")
    referenced = {str(d.get("asset_ref")) for _, d in devices(plan) if d.get("asset_ref")}
    declined = {str(x.get("asset")) for x in as_list(plan.get("declined_assets")) if isinstance(x, dict) and str(x.get("reason") or "").strip()}
    try: uploads = source_roles.for_chapter(cid)
    except Exception: uploads = []
    for asset in uploads:
        if asset["requires_decision"] and asset["id"] not in referenced | declined:
            add("uploaded_asset_unplanned", "medium", f"the user uploaded {asset['id']} ({asset['label']}, {asset['asset_role']}) for this chapter"
                + (f": \"{asset['instruction']}\"" if asset.get("instruction") else "") + "; plan a device with asset_ref: " + asset["id"]
                + " or list it under declined_assets with the reason")
    return out


def uniformity_findings(chapters, plans, arch):
    """Book level (AUTO/GUIDED): the same chapter-end apparatus in every chapter is a template, not a decision."""
    import publication_architecture as pa
    out = []
    planned = [plans[c["id"]] for c in chapters if plans.get(c["id"])]
    if len(planned) < 3: return out
    ends = [tuple(sorted(pa.canonical(e.get("type")) for e in p["chapter_end"] if e.get("type") != "bridge_to_next")) for p in planned]
    reason = str((arch.get("chapter_strategy") or {}).get("uniform_structure_reason") or "").strip()
    practice = arch.get("exercise_policy") in ("every_chapter", "exam_focused")
    if ends[0] and len(set(ends)) == 1 and not reason and not (practice and set(ends[0]) <= {"exercises", "answer_key"}):
        out.append(finding("chapter_end_uniform", "medium", f"every chapter ends with the same apparatus ({', '.join(ends[0])}); choose chapter-end blocks per chapter "
                           "from its content, or state chapter_strategy.uniform_structure_reason in plan/publication-architecture.yaml"))
    shapes = [tuple(sorted({block_of(d) for _, d in devices(p) if live(d)})) for p in planned]
    if shapes[0] and len(set(shapes)) == 1 and not reason:
        out.append(finding("structure_uniform", "low", f"every chapter uses the same set of blocks ({', '.join(shapes[0])})"))
    return out


# ---------------------------------------------------------------- the book

def check(chapters, plans, profile, known_sources=None, book=None, intent=None, arch=None):
    """The editorial plan of the whole book against the profile (a report dict). `intent`: pipeline-default rule ids
    switched off by explicit user intent (user_intent.overrides). `arch`: the publication architecture (None = the
    legacy FIXED behaviour)."""
    book = book or {}; first_terms = {}; intent = intent or {}
    if adaptive(arch):
        # The architecture's visual density (「図表を多く」, a visual guide …) scales the profile's visual-rate health check.
        import publication_architecture as pa
        profile = pa.scaled_profile(profile, arch)
    results = [check_chapter(c, plans.get(c["id"]), profile, known_sources, first_terms, last=i == len(chapters) - 1, intent=intent, arch=arch) for i, c in enumerate(chapters)]
    findings = []
    if adaptive(arch): findings += uniformity_findings(chapters, {k: normalize(v) for k, v in plans.items() if v}, arch)
    ids = {}
    for c in chapters:
        plan = plans.get(c["id"])
        if not plan: continue
        for s, d in devices(plan, include_end=True):
            if d.get("id") in ids and ids[d["id"]] != c["id"]:
                findings.append(finding("device_duplicate_id", "error", f"device id {d['id']} is also used in {ids[d['id']]}", c["id"], None, d["id"]))
            ids.setdefault(d.get("id"), c["id"])
    chars = sum(r.get("planned_chars") or 0 for r in results) or sum(int(c.get("target_characters") or 0) for c in chapters)
    visuals = sum((r.get("counts") or {}).get("visuals", 0) for r in results)
    rate = visuals * 10000 / chars if chars else 0
    rng = profile["devices"]["visuals_per_10k"]
    unused = [f for r in results for f in r["findings"] if f["rule"] == "visual_opportunity_unused"]
    if chars and rate < rng["min"]:
        findings.append(finding("visual_shortage", "medium", f"{visuals} visual intents = {rate:.2f} per 10,000 characters, below the profile minimum {rng['min']}. "
                                "Revisit sections for comparisons, chronologies, processes with branches and quantities the text already holds"
                                + (f" (unused: {', '.join(str(f['section']) for f in unused[:8])})" if unused else "")
                                + "; never add a figure to reach the number. If the book has none, waive it in plan/editorial/book.yaml with the reason."))
    elif chars and rate > rng["max"]:
        findings.append(finding("visual_overload", "medium", f"{rate:.2f} visual intents per 10,000 characters, above the profile maximum {rng['max']}"))
    area = sum(AREA.get(d["type"], 0) for c in chapters if plans.get(c["id"]) for _, d in devices(plans[c["id"]]) if live(d))
    area += 0.2 * sum(len(plans[c["id"]]["chapter_end"]) for c in chapters if plans.get(c["id"]))
    pages = chars / profile["scale"]["chars_per_text_page"] if chars else 0
    share = area / (pages + area) if pages else 0
    if chars and share < 0.5 * profile["scale"]["nonprose_share_target"]:
        findings.append(finding("nonprose_share_low", "low", f"planned devices fill about {share:.0%} of the pages; the profile targets {profile['scale']['nonprose_share_target']:.0%} "
                                "(an estimate before typesetting)"))
    _waive(findings, [w for w in as_list(book.get("waivers")) if isinstance(w, dict)])
    apply_overrides(findings, intent)
    every = findings + [f for r in results for f in r["findings"]]
    summary = {"chapters": len(chapters), "planned": sum(1 for c in chapters if plans.get(c["id"])), "errors": sum(f["severity"] == "error" and not f.get("user_intent") for f in every),
               "medium": sum(f["severity"] == "medium" and not f.get("waived") for f in every), "low": sum(f["severity"] == "low" for f in every),
               "waived": sum(bool(f.get("waived")) for f in every), "user_intent_overrides": sorted(intent), "planned_chars": chars, "visual_intents": visuals,
               "visuals_per_10k": round(rate, 2), "nonprose_share_est": round(share, 3)}
    summary["structure_mode"] = (arch or {}).get("mode", "fixed")
    return {"schema": SCHEMA, "profile": profile.get("id"), "ok": not blocking(every), "summary": summary,
            "limits": {"pause_every_chars": profile["rhythm"]["pause_every_chars"], "max_text_only_pages": profile["rhythm"]["max_text_only_pages"],
                       "chars_per_text_page": profile["scale"]["chars_per_text_page"], "nonprose_share_target": profile["scale"]["nonprose_share_target"],
                       "visuals_per_10k": rng, "note": "character-based prevention before drafting; the typeset proof is judged by the pacing gate (gate 17)"},
            "chapters": results, "findings": findings}


def all_findings(result):
    return result["findings"] + [f for r in result["chapters"] for f in r["findings"]]


# ---------------------------------------------------------------- job integration

def known_sources():
    import sources as registry
    return {s["id"]: s["ingest_status"] for s in registry.load_index()["sources"]}


def profile_for(project=None):
    import publication_profile
    profile = publication_profile.load_resolved()
    if profile: return profile
    from common import read_project
    try:
        from design import load_design
        design = load_design()
    except Exception: design = {}
    return publication_profile.resolve(project or read_project(), design)


def run(chapters, write=True, project=None):
    import user_intent
    import publication_architecture as pa
    try: arch = pa.load(project)
    except Exception: arch = None
    result = check(chapters, load_plans(chapters), profile_for(project), known_sources(), load_book(), intent=user_intent.overrides(project), arch=arch)
    if write:
        REPORT.parent.mkdir(exist_ok=True)
        write_yaml(REPORT, result, "Generated by BookOrder from plan/editorial/*.yaml and the resolved profile. Change the plans, not this file.")
    return result


def summary_lines(plan):
    """The chapter's plan as drafting instructions (sections in order with their devices and slots)."""
    lines = [f"Editorial plan plan/editorial/{plan['chapter_id']}.yaml ({plan.get('chapter_role')}): the reader starts at "
             f"\"{plan.get('reader_before')}\" and ends at \"{plan.get('reader_after')}\"."]
    for s in plan["sections"]:
        lines.append(f"- {s.get('id')} {s.get('heading')} [{s.get('rhetorical_role')}, {s.get('expected_density')}, {int(s.get('target_chars') or 0):,} chars]: "
                     f"{s.get('purpose')} → {s.get('intended_reader_effect')}")
        for d in s["devices"]:
            if live(d): lines.append(f"    slot {d['id']} ({d['type']}, {placement(d)['position'] or 'middle'}): {placement(d)['intent']}")
    if plan["chapter_end"]: lines.append("- chapter end: " + ", ".join(f"{e['type']} (slot {e['id']})" for e in plan["chapter_end"]))
    return lines


def slot_markdown(device, kind=None):
    intent = placement(device)["intent"] or str(device.get("why") or "")
    return f"::: {{.slot #{device['id']} kind={kind or device['type']}}}\n{intent}\n:::"


# ---------------------------------------------------------------- slots in the manuscript

def expected(plan):
    """Device id -> (kind, component class or None) for every live device and chapter-end item."""
    out = {}
    for _, d in devices(plan):
        if live(d) and d["type"] in CATALOG: out[d["id"]] = (d["type"], CATALOG[d["type"]].get("component"))
    for e in plan["chapter_end"]: out[e["id"]] = ("chapter_end:" + str(e.get("type")), END_COMPONENT.get(str(e.get("type"))))
    return out


def withdrawn(plan):
    return {d["id"] for _, d in devices(plan) if not live(d) and d.get("id")}


def slot_status(plan, record, placed_assets=None):
    """How the chapter text stands against its plan: realized, open (slot present), missing, stale, unknown."""
    placed_assets = placed_assets or {}
    want = expected(plan)
    slots = {s["id"]: s for s in (record or {}).get("slots", [])}
    anchors = set((record or {}).get("anchors", [])) - set(slots)
    elements = anchors | set((record or {}).get("figures", [])) | {t for t in (record or {}).get("tables", []) if t}
    status = {"realized": [], "open": [], "missing": [], "stale": [], "unknown": [], "kind_mismatch": []}
    for ident, (kind, _) in want.items():
        done = ident in elements or any(a in elements for a in placed_assets.get(ident, []))
        if done and ident in slots: status["stale"].append(ident)
        elif done: status["realized"].append(ident)
        elif ident in slots:
            status["open"].append(ident)
            if slots[ident].get("kind") and slots[ident]["kind"] != kind.split(":")[-1]: status["kind_mismatch"].append(ident)
        else: status["missing"].append(ident)
    gone = withdrawn(plan)
    status["stale"] += [i for i in slots if i in gone]
    status["unknown"] = [i for i in slots if i not in want and i not in gone]
    return status


def contract_reasons(chapter_id, record):
    """Chapter contract problems from the plan: every planned device has a slot or is already in the text."""
    plan = load_plan(chapter_id)
    if plan is None or record is None: return []
    status = slot_status(plan, record, placed_by_device())
    reasons = []
    if status["missing"]: reasons.append({"type": "slots", "detail": "Planned devices with neither a slot nor the device in the text: " + ", ".join(status["missing"])
                                          + " (insert ::: {.slot #id kind=type} ... ::: at the planned placement)", "missing": status["missing"]})
    if status["unknown"]: reasons.append({"type": "slots", "detail": "Slots that are not in the editorial plan: " + ", ".join(status["unknown"])})
    if status["stale"]: reasons.append({"type": "slots", "detail": "Slots left behind (device already placed, dropped or replaced): " + ", ".join(status["stale"])})
    return reasons


def placed_by_device():
    """Editorial device id -> asset ids planned for it (plan/assets-plan.yaml `device:`)."""
    try:
        import assets
        out = {}
        for a in assets.assets():
            if a.get("device"): out.setdefault(str(a["device"]), []).append(str(a.get("id")))
        return out
    except Exception: return {}


def visual_devices(chapters):
    """(chapter id, device) for every live visual intent in the plans."""
    out = []
    for c in chapters:
        plan = load_plan(c["id"])
        if plan: out += [(c["id"], d) for _, d in devices(plan) if live(d) and CATALOG.get(d["type"], {}).get("visual")]
    return out


# ---------------------------------------------------------------- rejected visuals come back to the plan

FALLBACKS = ("table", "prose", "case_study", "summary")
REASON_FALLBACK = {"linear_sequence": ["prose"], "list_sufficient": ["prose"], "binary_comparison": ["prose"], "too_few_nodes": ["prose"],
                   "density_only": ["prose", "summary"], "no_reader_gain": ["prose", "summary"], "orient_only": ["prose"],
                   "disclaimer_caption": ["prose", "case_study"], "illustrative_structure": ["case_study", "prose"],
                   "causal_without_evidence": ["prose", "case_study"], "missing_sources": ["prose", "case_study"],
                   "concept_map_few_edges": ["table", "prose"], "concept_map_edge_semantics": ["table", "prose"],
                   "concept_map_no_structure": ["table", "prose"], "concept_map_claim": ["table", "prose"],
                   "duplicate_in_chapter": ["prose", "summary"], "repeated_composition": ["prose", "table"]}


def suggest(reasons):
    """Fallback options for a rejected visual, most specific first."""
    options = []
    for reason in reasons:
        code = reason.get("code") if isinstance(reason, dict) else str(reason)
        if code == "shape_routes_elsewhere":
            text = str(reason.get("suggestion") or "") if isinstance(reason, dict) else ""
            options.append("table" if "table" in text else "prose")
        options += REASON_FALLBACK.get(code, [])
    options = [o for o in dict.fromkeys(options + ["prose"]) if o in FALLBACKS]
    return options


def rejected_devices(chapters, review):
    """Live visual devices whose candidate the visual review rejected: they must fall back in the plan."""
    by_id = {cid_d[1]["id"]: cid_d for cid_d in visual_devices(chapters)}
    out = []
    for c in review.get("candidates", []):
        ident = c.get("device") or c.get("id")
        if c.get("decision") == "rejected" and ident in by_id:
            chapter, device = by_id[ident]
            out.append({"chapter": chapter, "device": ident, "candidate": c["id"], "codes": [r["code"] for r in c.get("rejection_reasons", [])],
                        "options": suggest(c.get("rejection_reasons", []))})
    return out


def fallback(plan, device_id, to, reason, codes=None):
    """Replace a device in a plan dict: `prose` drops it; table / case_study / summary put a new device in its place.
    Returns the new device id (None for prose). The new device keeps the placement and sources; its own checks
    (a table needs a 3×3 comparison, a real case study needs sources) apply as for any device."""
    if to not in FALLBACKS: raise ValueError(f"fallback must be one of {', '.join(FALLBACKS)}")
    if not str(reason or "").strip(): raise ValueError("a fallback needs a reason")
    for section in plan["sections"]:
        for i, device in enumerate(section["devices"]):
            if device.get("id") != device_id: continue
            if not live(device): raise ValueError(f"{device_id} is already {device['status']}")
            record = {"to": to, "reason": reason, **({"review": list(codes)} if codes else {})}
            if to == "prose":
                device.update(status="dropped", fallback=record); return None
            kind = {"summary": "key_point"}.get(to, to)
            new_id = f"{device_id}-{kind.replace('_', '-')}"
            new = {"id": new_id, "type": kind, "why": reason, "placement": device.get("placement"), "source_ids": list(device.get("source_ids", [])),
                   "status": "planned", "replaces": device_id}
            if kind == "table":
                new["basis"] = device.get("basis") or "derived_from_text"
                shape = device.get("information_shape") if isinstance(device.get("information_shape"), dict) else {}
                new["information_shape"] = shape if shape.get("kind") == "comparison" else {"kind": "comparison", "items": 0, "attributes": 0}
            if kind == "case_study": new["basis"] = "real"
            device.update(status="replaced", replaced_by=new_id, fallback=record)
            section["devices"].insert(i + 1, new)
            return new_id
    raise ValueError(f"device {device_id} is not in the plan")


def apply_fallback(chapter_id, device_id, to, reason, codes=None):
    """`bookorder editorial fallback`: rewrite plan/editorial/<chapter>.yaml with the fallback applied."""
    path = plan_path(chapter_id)
    raw = _coerce(yaml_data(path))
    plan = normalize(raw)
    new_id = fallback(plan, device_id, to, reason, codes)
    # Write back the author's structure with the device list changed (normalised defaults are not written).
    by_section = {s.get("id"): s["devices"] for s in plan["sections"]}
    for section in as_list(raw.get("sections")):
        if isinstance(section, dict) and section.get("id") in by_section:
            section["devices"] = by_section[section["id"]]
    write_yaml(path, raw, f"Editorial plan for {chapter_id} (fallback {device_id} -> {to} applied by BookOrder)")
    return new_id


def find_chapter(device_id, chapters):
    for c in chapters:
        plan = load_plan(c["id"])
        if plan and any(d.get("id") == device_id for _, d in devices(plan)): return c["id"]
    return None

"""Intent-driven publication architecture: Intent Interpreter + Publication Architect.

    user intent (verbatim text, description, readers) + structured WebUI request (project.json publication_architecture)
      → PublicationIntent            plan/publication-intent.yaml
      → PublicationArchitecture      plan/publication-architecture.yaml
          archetype (primary + secondary) → block policy → visual policy → exercise policy
          → chapter strategy (per-chapter architecture lives in the outline) → citation / source / layout strategy

The vocabulary (archetypes, block library, visual taxonomy, signals) is schemas/publication-architecture.json, shared
with the WebUI. A template is a *block library* the planner combines, never a fixed book grammar.

Modes (project.json publication_architecture.mode):
    auto    BookOrder infers archetype and policies from the intent; chapters may differ in structure.
    guided  the user's structured choices (archetype, block lists, exercise / visual policy) are binding constraints.
    fixed   legacy template behaviour: the profile's chapter-end apparatus is required in every chapter.
            Projects without `publication_architecture` (all jobs made before this change) are FIXED.

Authority: explicit user words and structured settings > the agent's interpretation > archetype defaults. A block
the user excluded (「章末問題はいらない」) is enforced as forbidden on every load: the agent's architecture file
cannot relax it, and no later phase may plan it.
"""
import json
import re
import unicodedata

from common import ROOT, as_list, read_project, write_yaml, yaml_data

SCHEMA_INTENT = "bookorder/publication-intent@1"
SCHEMA_ARCH = "bookorder/publication-architecture@1"
VOCAB = json.loads((ROOT / "schemas/publication-architecture.json").read_text(encoding="utf-8"))
MODES = tuple(VOCAB["structure_modes"])
ARCHETYPES = tuple(VOCAB["archetypes"])
BLOCKS = VOCAB["blocks"]
VISUAL_TYPES = VOCAB["visual_types"]
EXERCISE_POLICIES = tuple(VOCAB["exercise_policies"])
DENSITIES = tuple(VOCAB["visual_densities"])
INTENT = ROOT / "plan/publication-intent.yaml"
ARCH = ROOT / "plan/publication-architecture.yaml"
LAYOUT_REFERENCES = ROOT / "plan/layout-references.yaml"
EXERCISE_BLOCKS = tuple(b for b, spec in BLOCKS.items() if spec.get("exercise"))
POLICY_KEYS = ("preferred", "allowed", "discouraged", "forbidden")
# Signals whose effect is a hint (inferred from context), not a user directive.
HINT_EFFECTS = ("archetype", "evidence_priority", "preferred_authority")


def canonical(block):
    """Block id with aliases resolved (check_questions -> exercises, key_points -> summary)."""
    block = str(block or "").strip()
    return BLOCKS.get(block, {}).get("alias_of") or block


# ---------------------------------------------------------------- request

def request(project=None):
    """The structured request, normalised. `legacy: True` when project.json predates the architecture (FIXED)."""
    project = project if project is not None else read_project()
    raw = project.get("publication_architecture")
    if isinstance(raw, str) and raw.strip(): raw = {"mode": raw.strip()}   # "auto" shorthand is not a legacy job
    if not isinstance(raw, dict):
        return {"mode": VOCAB["legacy_mode"], "legacy": True, "archetype": "auto", "secondary_archetype": None, "block_policy": {},
                "exercise_policy": "auto", "visual_policy": {}, "notes": {}}
    mode = str(raw.get("mode") or VOCAB["default_mode"]).lower()
    blocks = raw.get("block_policy") if isinstance(raw.get("block_policy"), dict) else {}
    visual = raw.get("visual_policy") if isinstance(raw.get("visual_policy"), dict) else {}
    notes = {k: str(raw.get(k) or "") for k in ("archetype_note", "chapter_architecture", "layout_strategy", "tone", "reading_mode", "use_context", "reader_level")
             if str(raw.get(k) or "").strip()}
    evidence = raw.get("evidence_policy") if isinstance(raw.get("evidence_policy"), dict) else {}
    return {"mode": mode, "legacy": False, "archetype": str(raw.get("archetype") or "auto"), "secondary_archetype": raw.get("secondary_archetype") or None,
            "block_policy": {k: [canonical(b) for b in as_list(blocks.get(k))] for k in ("preferred", "discouraged", "forbidden")},
            "exercise_policy": str(raw.get("exercise_policy") or "auto"), "visual_policy": {
                "density": str(visual.get("density") or "auto"), "preferred_types": [str(t) for t in as_list(visual.get("preferred_types"))],
                "avoid_types": [str(t) for t in as_list(visual.get("avoid_types"))]},
            "evidence_policy": {"priority": str(evidence.get("priority") or "auto"), "preferred_authority": [str(a) for a in as_list(evidence.get("preferred_authority"))],
                                "note": str(evidence.get("note") or "")},
            "notes": notes}


def mode(project=None):
    return request(project)["mode"]


def validate_request(req):
    errors = []
    if req["mode"] not in MODES: errors.append(f"publication_architecture.mode must be one of {', '.join(MODES)}")
    for key in ("archetype", "secondary_archetype"):
        value = req.get(key)
        if value and value != "auto" and value not in ARCHETYPES: errors.append(f"publication_architecture.{key} {value!r} is not one of {', '.join(ARCHETYPES)}")
    for key, blocks in req["block_policy"].items():
        for b in blocks:
            if b not in BLOCKS: errors.append(f"publication_architecture.block_policy.{key}: unknown block {b!r}")
    if req["exercise_policy"] not in EXERCISE_POLICIES + ("auto",): errors.append(f"exercise_policy must be one of {', '.join(EXERCISE_POLICIES)}")
    density = req["visual_policy"].get("density", "auto")
    if density not in DENSITIES + ("auto",): errors.append(f"visual_policy.density must be one of {', '.join(DENSITIES)}")
    for t in req["visual_policy"].get("preferred_types", []) + req["visual_policy"].get("avoid_types", []):
        if t not in VISUAL_TYPES: errors.append(f"visual_policy: unknown visual type {t!r}")
    return errors


# ---------------------------------------------------------------- Intent Interpreter (deterministic part)

def _nfkc(text):
    return unicodedata.normalize("NFKC", str(text or ""))


def signals(text, where="user_instructions"):
    """Explicit signals in the user's own words: [{id, quote, where, effect}]. Patterns: schemas/publication-architecture.json."""
    found = []
    text = _nfkc(text)
    for signal in VOCAB["intent_signals"]:
        for pattern in signal["patterns"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                found.append({"id": signal["id"], "quote": match.group(0), "where": where, "effect": signal["effect"]}); break
    return found


def user_signals(project):
    import user_intent
    book = project.get("book") or {}
    return signals(user_intent.verbatim(project)) + signals(book.get("description"), "book.description")


def reader_level(readers):
    text = _nfkc(readers)
    if re.search(r"新人|新任|初学者|入門|学生|初心者|未経験|beginner|novice|student", text, re.I): return "novice"
    if re.search(r"専門医|専門家|上級|研究者|指導者|expert|advanced|specialist", text, re.I): return "advanced"
    if re.search(r"中堅|実務者|経験者|intermediate|practitioner", text, re.I): return "intermediate"
    return "unspecified"


def infer_archetype(project, found):
    """(primary, secondary, reason) from explicit hints in the user's text; falls back to the profile genre."""
    hints = [s for s in found if s["effect"].get("archetype")]
    primary = hints[0]["effect"]["archetype"] if hints else None
    secondary = next((s["effect"]["archetype"] for s in hints[1:] if s["effect"]["archetype"] != primary), None)
    reason = f"user text: 「{hints[0]['quote']}」" if hints else None
    if not primary:
        genre = ((project.get("profile") or {}).get("genre") if isinstance(project.get("profile"), dict) else None) or project.get("genre")
        primary = {"practical": "practical_guide", "technical": "technical_manual", "medical_science": "textbook", "criticism": "academic_monograph",
                   "essay": "essay_like_book"}.get(genre, "practical_guide" if re.search(r"実務|現場|ガイド|手引|マニュアル|how-to|guide", _nfkc(project["book"].get("description")), re.I) else "textbook")
        reason = f"profile genre {genre}" if genre else "book description (no explicit publication type)"
    return primary, secondary, reason


def interpret(project=None):
    """PublicationIntent seed: every field with its value and provenance (user_setting | user_text | inferred | default)."""
    project = project if project is not None else read_project()
    req = request(project); book = project.get("book") or {}
    found = user_signals(project)
    fields = {}
    def put(name, value, origin, evidence=None):
        fields[name] = {"value": value, "origin": origin, **({"evidence": evidence} if evidence else {})}
    put("publication_goal", book.get("description"), "user_setting", "book.description")
    put("audience", book.get("target_readers"), "user_setting", "book.target_readers")
    put("reader_level", req["notes"].get("reader_level") or reader_level(book.get("target_readers")), "user_setting" if req["notes"].get("reader_level") else "inferred")
    if req["archetype"] not in ("auto", "", None) and req["archetype"] in ARCHETYPES:
        primary, origin, why = req["archetype"], "user_setting", "project.json publication_architecture.archetype"
        secondary = req.get("secondary_archetype")
    else:
        primary, secondary, why = infer_archetype(project, found)
        origin = "user_text" if why.startswith("user text") else "inferred"
        secondary = req.get("secondary_archetype") or secondary
    spec = VOCAB["archetypes"][primary]
    put("publication_archetype", primary, origin, why)
    put("secondary_archetype", secondary, "user_setting" if req.get("secondary_archetype") else ("user_text" if secondary else "default"))
    put("reading_mode", req["notes"].get("reading_mode") or spec["reading_mode"], "user_setting" if req["notes"].get("reading_mode") else "default")
    put("use_context", req["notes"].get("use_context") or book.get("description"), "user_setting" if req["notes"].get("use_context") else "inferred")
    tone = next((s for s in found if s["effect"].get("tone")), None)
    put("tone", req["notes"].get("tone") or (tone["effect"]["tone"] if tone else spec["tone"]),
        "user_setting" if req["notes"].get("tone") else "user_text" if tone else "default", f"「{tone['quote']}」" if tone else None)
    evidence = next((s for s in found if s["effect"].get("evidence_priority")), None)
    priority = req.get("evidence_policy", {}).get("priority", "auto")
    put("evidence_priority", priority if priority not in ("auto", "") else (evidence["effect"]["evidence_priority"] if evidence else spec["evidence_priority"]),
        "user_setting" if priority not in ("auto", "") else "inferred" if evidence else "default", f"「{evidence['quote']}」" if evidence else None)
    density_signal = next((s for s in found if s["effect"].get("visual_density")), None)
    density = req["visual_policy"].get("density", "auto")
    put("visual_density", density if density != "auto" else (density_signal["effect"]["visual_density"] if density_signal else spec["visual_density"]),
        "user_setting" if density != "auto" else "user_text" if density_signal else "default", f"「{density_signal['quote']}」" if density_signal else None)
    put("visual_need", "high" if fields["visual_density"]["value"] in ("high", "very_high") else "low" if fields["visual_density"]["value"] in ("minimal", "low") else "medium",
        fields["visual_density"]["origin"])
    exercise_signal = next((s for s in found if s["effect"].get("exercise_policy")), None)
    exercise = req["exercise_policy"]
    put("interactivity_need", exercise if exercise != "auto" else (exercise_signal["effect"]["exercise_policy"] if exercise_signal else spec["exercise_policy"]),
        "user_setting" if exercise != "auto" else "user_text" if exercise_signal else "default", f"「{exercise_signal['quote']}」" if exercise_signal else None)
    pages = int(float(book.get("target_pages") or 0))
    put("page_budget", pages, "user_setting", "book.target_pages")
    put("expected_reading_time", f"about {max(1, round(pages * 2 / 60))} h" if pages else "unspecified", "inferred")
    put("chapter_strategy", req["notes"].get("chapter_architecture") or spec["chapter_strategy"], "user_setting" if req["notes"].get("chapter_architecture") else "default")
    import bibliography
    put("citation_policy", bibliography.policy(project)["summary"], "user_setting" if isinstance(project.get("citations"), dict) and len(project["citations"]) > 1 else "default")
    put("source_policy", "roles from the WebUI per file; unspecified sources are classified in corpus analysis (plan/source-roles.yaml)", "default")
    put("layout_strategy", req["notes"].get("layout_strategy") or ("follow uploaded layout references" if _layout_refs(project) else "theme and layout preset"),
        "user_setting" if req["notes"].get("layout_strategy") else "inferred")
    directives = [{"id": s["id"], "quote": s["quote"], "where": s["where"], "effect": s["effect"]} for s in found
                  if any(k not in HINT_EFFECTS for k in s["effect"])]
    return {"schema": SCHEMA_INTENT, "mode": req["mode"], "fields": fields, "explicit_signals": directives,
            "verbatim_source": "project.json user_instructions and book.description (authoritative over this file)"}


def _layout_refs(project):
    import source_roles
    return [a for a in source_roles.uploaded_assets(project) if a["role"] == "layout_reference"]


# ---------------------------------------------------------------- Publication Architect

def enforced(project):
    """Block constraints that no interpretation can relax: structured GUIDED/AUTO choices and explicit user words.
    Returns {forbidden: {block: reason}, preferred: {...}, discouraged: {...}, exercise_policy, visual_density}."""
    req = request(project)
    out = {"forbidden": {}, "preferred": {}, "discouraged": {}, "exercise_policy": None, "visual_density": None}
    if req["legacy"]: return out
    for key in ("forbidden", "preferred", "discouraged"):
        for block in req["block_policy"].get(key, []): out[key][block] = "WebUI block policy"
    if req["exercise_policy"] not in ("auto", ""): out["exercise_policy"] = (req["exercise_policy"], "WebUI exercise policy")
    if req["visual_policy"].get("density", "auto") != "auto": out["visual_density"] = (req["visual_policy"]["density"], "WebUI visual density")
    for s in user_signals(project):
        reason = f"user: 「{s['quote']}」"
        for block in s["effect"].get("forbid", []): out["forbidden"].setdefault(canonical(block), reason)
        for block in s["effect"].get("prefer", []): out["preferred"].setdefault(canonical(block), reason)
        for block in s["effect"].get("discourage", []): out["discouraged"].setdefault(canonical(block), reason)
        if s["effect"].get("exercise_policy") and not out["exercise_policy"]:
            # A prohibition is stronger than a wish when both occur.
            out["exercise_policy"] = (s["effect"]["exercise_policy"], reason)
        if s["effect"].get("visual_density") and not out["visual_density"]: out["visual_density"] = (s["effect"]["visual_density"], reason)
    if any(canonical(b) in EXERCISE_BLOCKS for b in out["forbidden"]):
        out["exercise_policy"] = ("none", out["forbidden"].get("exercises") or next(iter(out["forbidden"].values())))
        for b in EXERCISE_BLOCKS: out["preferred"].pop(b, None)
    for b in out["forbidden"]: out["preferred"].pop(b, None); out["discouraged"].pop(b, None)
    return out


def derive(project=None, intent=None):
    """PublicationArchitecture from the intent (deterministic default the agent refines)."""
    project = project if project is not None else read_project()
    intent = intent or interpret(project); req = request(project)
    fields = intent["fields"]; primary = fields["publication_archetype"]["value"]; secondary = fields["secondary_archetype"]["value"]
    spec = VOCAB["archetypes"][primary]; second = VOCAB["archetypes"].get(secondary) or {}
    if req["legacy"] or req["mode"] == "fixed":
        import publication_profile
        profile = publication_profile.load_resolved() or {}
        end = [canonical(b) for b in (profile.get("structure") or {}).get("chapter_end", [])]
        policy = {"preferred": [], "allowed": sorted(BLOCKS), "discouraged": [], "forbidden": [], "requirements": ["fixed_template_chapter_end"],
                  "required_chapter_end": end, "origin": {}}
        exercise = "every_chapter" if any(b in EXERCISE_BLOCKS for b in end) else "none"
    else:
        preferred = list(dict.fromkeys(spec["preferred_blocks"] + [b for b in second.get("preferred_blocks", []) if b not in spec["discouraged_blocks"]]))
        discouraged = [b for b in spec["discouraged_blocks"] if b not in second.get("preferred_blocks", [])]
        policy = {"preferred": preferred, "allowed": [], "discouraged": discouraged, "forbidden": list(spec["forbidden_blocks"]),
                  "requirements": list(dict.fromkeys(spec["requirements"] + second.get("requirements", []))), "required_chapter_end": [], "origin": {}}
        for b in preferred: policy["origin"][b] = f"archetype {primary}" + (f"+{secondary}" if b in second.get("preferred_blocks", []) else "")
        for b in discouraged: policy["origin"][b] = f"archetype {primary}"
        exercise = fields["interactivity_need"]["value"]
        if fields["interactivity_need"]["origin"] == "default" and fields["publication_archetype"]["origin"] not in ("user_setting", "user_text") \
                and exercise in ("where_useful", "every_chapter", "exam_focused"):
            # The archetype was only guessed (no user choice, no explicit wish): do not make exercises a preferred
            # block of an unknown book — the architect adds them only if the content and the user call for them.
            exercise = "optional"
            for b in ("exercises", "answer_key"):
                if b in policy["preferred"]: policy["preferred"].remove(b); policy["origin"].pop(b, None)
        if exercise in ("where_useful", "every_chapter", "exam_focused"):
            for b in ("exercises", "answer_key"):
                if b not in policy["preferred"]: policy["preferred"].append(b)
                if b in policy["discouraged"]: policy["discouraged"].remove(b)
            if "exercises_have_answers_or_explanations" not in policy["requirements"]: policy["requirements"].append("exercises_have_answers_or_explanations")
        elif exercise == "none":
            for b in ("exercises", "check_questions", "answer_key"):
                if b not in policy["discouraged"]: policy["discouraged"].append(b)
                if b in policy["preferred"]: policy["preferred"].remove(b)
    policy = apply_enforced(policy, enforced(project))
    if "exercises" in policy["forbidden"]: exercise = "none"
    policy["allowed"] = sorted(b for b in BLOCKS if b not in policy["forbidden"] and not BLOCKS[b].get("alias_of"))
    density = fields["visual_density"]["value"]
    visual = {"density": density, "density_factor": VOCAB["visual_densities"].get(density, 1.0),
              "preferred_types": list(dict.fromkeys(req["visual_policy"].get("preferred_types", []) + spec["visual_preferred"] + second.get("visual_preferred", []))),
              "avoid_types": req["visual_policy"].get("avoid_types", []), "min_distinct_types": 3 if density not in ("minimal", "low") else 1,
              "max_share_per_type": 0.5, "rule": "Plan what must be seen, not how many figures: every visual states its purpose and why it beats prose."}
    return {"schema": SCHEMA_ARCH, "mode": req["mode"], "legacy": req["legacy"],
            "archetype": {"primary": primary, "secondary": secondary, "note": req["notes"].get("archetype_note", ""), "reason": fields["publication_archetype"].get("evidence")},
            "block_policy": policy, "exercise_policy": exercise, "visual_policy": visual,
            "chapter_strategy": {"strategy": fields["chapter_strategy"]["value"], "vary_structure": req["mode"] != "fixed",
                                 "uniform_structure_reason": None,
                                 "note": "Per-chapter architecture is in source/metadata/outline.yaml: content_intent, blocks, visuals, block_overrides."},
            "citation_policy": fields["citation_policy"]["value"], "source_policy": fields["source_policy"]["value"],
            "evidence_policy": evidence_policy(project, fields), "layout_strategy": fields["layout_strategy"]["value"],
            "tone": fields["tone"]["value"], "reading_mode": fields["reading_mode"]["value"],
            "intent_trace": [{"quote": s["quote"], "effect": s["effect"]} for s in intent["explicit_signals"]]}


def evidence_policy(project, fields=None):
    req = request(project); fields = fields or interpret(project)["fields"]
    priority = fields["evidence_priority"]["value"]
    preferred = req.get("evidence_policy", {}).get("preferred_authority") or next(
        (s["effect"]["preferred_authority"] for s in user_signals(project) if s["effect"].get("preferred_authority")), [])
    minimum = VOCAB["evidence_priorities"].get(priority, 2)
    return {"priority": priority, "preferred_authority": preferred, "minimum_rank_for_factual_claims": minimum,
            "note": req.get("evidence_policy", {}).get("note", ""),
            "rule": "Factual claims, numbers and recommendations cite evidence sources; background and experience sources may inform the "
                    "text but are not the sole support of a factual claim."}


def apply_enforced(policy, forced):
    policy = {**policy, "origin": dict(policy.get("origin") or {})}
    for key in ("preferred", "discouraged", "forbidden"): policy[key] = list(policy.get(key) or [])
    for block, reason in forced["forbidden"].items():
        if block not in policy["forbidden"]: policy["forbidden"].append(block)
        for key in ("preferred", "discouraged"):
            if block in policy[key]: policy[key].remove(block)
        policy["origin"][block] = reason
        policy["required_chapter_end"] = [b for b in policy.get("required_chapter_end", []) if b != block]
    for block, reason in forced["preferred"].items():
        if block in policy["forbidden"]: continue
        if block not in policy["preferred"]: policy["preferred"].append(block)
        if block in policy["discouraged"]: policy["discouraged"].remove(block)
        policy["origin"][block] = reason
    for block, reason in forced["discouraged"].items():
        if block in policy["forbidden"] or forced["preferred"].get(block): continue
        if block not in policy["discouraged"]: policy["discouraged"].append(block)
        if block in policy["preferred"]: policy["preferred"].remove(block)
        policy["origin"][block] = reason
    if "exercises" in policy["forbidden"]:
        policy["requirements"] = [r for r in policy.get("requirements") or [] if r != "exercises_have_answers_or_explanations"]
    policy["forbidden_reasons"] = {b: policy["origin"].get(b, "") for b in policy["forbidden"]}
    return policy


# ---------------------------------------------------------------- files

def seed(project=None):
    """Write plan/publication-intent.yaml and plan/publication-architecture.yaml when missing (never overwrites)."""
    project = project if project is not None else read_project()
    wrote = False
    if not INTENT.is_file():
        write_yaml(INTENT, interpret(project), "PublicationIntent seeded by BookOrder (deterministic interpretation). Refine the values; "
                   "keep explicit_signals. The user's verbatim text in project.json wins over this file."); wrote = True
    if not ARCH.is_file():
        write_yaml(ARCH, derive(project), "PublicationArchitecture seeded by BookOrder from the intent. Refine it for this book; blocks the user "
                   "excluded stay forbidden (BookOrder re-applies them on every load)."); wrote = True
    return wrote


def _coerce(value):
    if isinstance(value, dict): return {k: _coerce(v) for k, v in value.items()}
    if isinstance(value, list): return [_coerce(v) for v in value]
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()): return int(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d*\.\d+", value.strip()): return float(value)
    return value


def load(project=None):
    """The effective architecture: the agent-refined file when present, else the derived default. User-enforced
    constraints are re-applied, so a forbidden block can never come back through an edit."""
    project = project if project is not None else read_project()
    data = None
    if ARCH.is_file():
        try: data = _coerce(yaml_data(ARCH))
        except ValueError: data = None
    if not isinstance(data, dict) or not isinstance(data.get("block_policy"), dict): data = derive(project)
    req = request(project)
    data["mode"] = req["mode"]; data["legacy"] = req["legacy"]
    policy = data["block_policy"]
    for key in ("preferred", "discouraged", "forbidden", "requirements", "required_chapter_end"): policy[key] = [canonical(b) if key != "requirements" else str(b) for b in as_list(policy.get(key))]
    data["block_policy"] = apply_enforced(policy, enforced(project))
    if "exercises" in data["block_policy"]["forbidden"]: data["exercise_policy"] = "none"
    forced = enforced(project)
    if forced["exercise_policy"] and forced["exercise_policy"][0] == "none": data["exercise_policy"] = "none"
    data.setdefault("visual_policy", derive(project)["visual_policy"])
    return data


def is_fixed(project=None):
    return request(project)["mode"] == "fixed"


def check(project=None):
    """Problems in the publication-planning files (empty list = accepted)."""
    project = project if project is not None else read_project()
    req = request(project); errors = validate_request(req)
    if req["legacy"] or req["mode"] == "fixed": return errors   # FIXED: the template decides; nothing for the agent to design
    for path, label in ((INTENT, "plan/publication-intent.yaml"), (ARCH, "plan/publication-architecture.yaml")):
        if not path.is_file(): errors.append(f"Missing {label}")
    if errors: return errors
    try: intent = _coerce(yaml_data(INTENT)); arch = _coerce(yaml_data(ARCH))
    except ValueError as exc: return [str(exc)]
    fields = intent.get("fields") if isinstance(intent.get("fields"), dict) else {}
    for name in VOCAB["intent_fields"]:
        value = fields.get(name)
        if not isinstance(value, dict) or value.get("value") in (None, ""):
            if name != "secondary_archetype": errors.append(f"plan/publication-intent.yaml: fields.{name}.value is required")
    if not intent.get("reviewed_by_agent"):
        errors.append("plan/publication-intent.yaml: set reviewed_by_agent: true after checking every field against the user's words and the corpus")
    archetype = arch.get("archetype") if isinstance(arch.get("archetype"), dict) else {}
    if archetype.get("primary") not in ARCHETYPES: errors.append(f"plan/publication-architecture.yaml: archetype.primary must be one of {', '.join(ARCHETYPES)}")
    if archetype.get("secondary") not in (None, "", "null") and archetype.get("secondary") not in ARCHETYPES:
        errors.append("plan/publication-architecture.yaml: archetype.secondary must be an archetype or null")
    if req["mode"] == "guided" and req["archetype"] not in ("auto", "") and archetype.get("primary") != req["archetype"]:
        errors.append(f"GUIDED mode: archetype.primary must stay {req['archetype']} (selected in the WebUI)")
    policy = arch.get("block_policy") if isinstance(arch.get("block_policy"), dict) else {}
    for key in ("preferred", "discouraged", "forbidden"):
        for b in as_list(policy.get(key)):
            if canonical(b) not in BLOCKS: errors.append(f"block_policy.{key}: unknown block {b} (library: schemas/publication-architecture.json)")
    forbidden = {canonical(b) for b in as_list(policy.get("forbidden"))}
    preferred = {canonical(b) for b in as_list(policy.get("preferred"))}
    for b in sorted(forbidden & preferred): errors.append(f"block_policy: {b} is both preferred and forbidden")
    forced = enforced(project)
    for block, reason in forced["forbidden"].items():
        if block not in forbidden: errors.append(f"block_policy.forbidden must include {block} ({reason})")
        if block in preferred: errors.append(f"block_policy.preferred must not include {block} ({reason})")
    if req["mode"] == "guided":
        for block, reason in forced["preferred"].items():
            if block not in preferred and block not in forbidden: errors.append(f"GUIDED mode: block_policy.preferred must include {block} ({reason})")
    if arch.get("exercise_policy") not in EXERCISE_POLICIES: errors.append(f"exercise_policy must be one of {', '.join(EXERCISE_POLICIES)}")
    elif forced["exercise_policy"] and forced["exercise_policy"][0] == "none" and arch["exercise_policy"] != "none":
        errors.append(f"exercise_policy must be none ({forced['exercise_policy'][1]})")
    elif req["mode"] == "guided" and forced["exercise_policy"] and arch["exercise_policy"] != forced["exercise_policy"][0]:
        errors.append(f"GUIDED mode: exercise_policy must be {forced['exercise_policy'][0]} ({forced['exercise_policy'][1]})")
    visual = arch.get("visual_policy") if isinstance(arch.get("visual_policy"), dict) else {}
    if visual.get("density") not in DENSITIES: errors.append(f"visual_policy.density must be one of {', '.join(DENSITIES)}")
    elif forced["visual_density"] and req["mode"] == "guided" and visual["density"] != forced["visual_density"][0]:
        errors.append(f"GUIDED mode: visual_policy.density must be {forced['visual_density'][0]}")
    for t in as_list(visual.get("preferred_types")) + as_list(visual.get("avoid_types")):
        if t not in VISUAL_TYPES: errors.append(f"visual_policy: unknown visual type {t}")
    trace = as_list(arch.get("intent_trace"))
    import user_intent
    for s in forced_quotes(project):
        if not any(isinstance(t, dict) and user_intent._norm(s) in user_intent._norm(t.get("quote")) for t in trace):
            errors.append(f"intent_trace must record how 「{s}」 shapes the architecture")
    strategy = arch.get("chapter_strategy") if isinstance(arch.get("chapter_strategy"), dict) else {}
    if not str(strategy.get("strategy") or "").strip(): errors.append("chapter_strategy.strategy is required")
    errors += layout_reference_errors(project)
    return errors


def forced_quotes(project):
    return [s["quote"] for s in user_signals(project) if any(k not in HINT_EFFECTS for k in s["effect"])]


def layout_reference_errors(project):
    """Every uploaded layout reference is analysed for composition only (plan/layout-references.yaml)."""
    refs = _layout_refs(project)
    if not refs: return []
    if not LAYOUT_REFERENCES.is_file(): return ["Missing plan/layout-references.yaml (composition analysis of " + ", ".join(r["id"] for r in refs) + ")"]
    try: data = yaml_data(LAYOUT_REFERENCES)
    except ValueError as exc: return [str(exc)]
    errors = []; entries = {str(e.get("asset")): e for e in as_list(data.get("references")) if isinstance(e, dict)}
    for ref in refs:
        entry = entries.get(ref["id"])
        if not entry: errors.append(f"plan/layout-references.yaml: no entry for {ref['id']} ({ref['label']})"); continue
        features = entry.get("features") if isinstance(entry.get("features"), dict) else {}
        known = [k for k in VOCAB["layout_reference_fields"] if str(features.get(k) or "").strip()]
        if len(known) < 8: errors.append(f"plan/layout-references.yaml {ref['id']}: describe at least 8 of {', '.join(VOCAB['layout_reference_fields'])}")
        if entry.get("content_used") not in (False, "false"): errors.append(f"plan/layout-references.yaml {ref['id']}: content_used must be false (composition only)")
        if not as_list(entry.get("apply")): errors.append(f"plan/layout-references.yaml {ref['id']}: apply lists what the design adopts")
    return errors


# ---------------------------------------------------------------- effective per-chapter policy

def chapter_policy(arch, chapter=None):
    """Book policy with the outline chapter's block_overrides merged (forbidden stays forbidden)."""
    policy = {k: list(as_list(arch["block_policy"].get(k))) for k in ("preferred", "discouraged", "forbidden", "required_chapter_end")}
    over = (chapter or {}).get("block_overrides") if isinstance((chapter or {}).get("block_overrides"), dict) else {}
    for key in ("preferred", "discouraged"):
        for b in as_list(over.get(key)):
            b = canonical(b)
            if b in policy["forbidden"]: continue
            other = "discouraged" if key == "preferred" else "preferred"
            if b in policy[other]: policy[other].remove(b)
            if b not in policy[key]: policy[key].append(b)
    for b in as_list(over.get("forbidden")):
        b = canonical(b)
        if b not in policy["forbidden"]: policy["forbidden"].append(b)
    policy["planned"] = [canonical(b) for b in as_list((chapter or {}).get("blocks"))]
    return policy


def status(policy, block):
    block = canonical(block)
    for key in ("forbidden", "discouraged", "preferred"):
        if block in policy.get(key, []): return key
    return "allowed" if block in BLOCKS else "unknown"


def reason(arch, block):
    return (arch["block_policy"].get("origin") or {}).get(canonical(block)) or (arch["block_policy"].get("forbidden_reasons") or {}).get(canonical(block)) or ""


# ---------------------------------------------------------------- prompts

def summary_lines(arch=None, chapter=None, project=None):
    """The architecture as task instructions (Writer / Editor / Designer / QA)."""
    arch = arch or load(project)
    if arch.get("legacy") or arch["mode"] == "fixed":
        return [f"Publication architecture: FIXED mode (legacy template). Chapter-end apparatus required in every chapter: "
                f"{', '.join(arch['block_policy'].get('required_chapter_end') or []) or 'none'}."
                + (f" Forbidden by the user: {', '.join(arch['block_policy']['forbidden'])}." if arch["block_policy"].get("forbidden") else "")]
    a = arch["archetype"]; p = chapter_policy(arch, chapter); v = arch["visual_policy"]
    lines = [f"Publication architecture ({arch['mode'].upper()}, plan/publication-architecture.yaml): {a['primary']}"
             + (f" + {a['secondary']}" if a.get("secondary") else "") + f"; tone: {arch.get('tone')}; reading mode: {arch.get('reading_mode')}.",
             "Blocks are a library to combine per chapter, not a template: use a block only where this chapter's content needs it. "
             "No block is required in every chapter unless the architecture's requirements say so.",
             f"- preferred: {', '.join(p['preferred']) or '-'}; discouraged (needs a reason): {', '.join(p['discouraged']) or '-'}; "
             f"FORBIDDEN: {', '.join(f'{b} ({reason(arch, b)})' for b in p['forbidden']) or '-'}.",
             f"- exercise policy: {arch.get('exercise_policy')}" + ("; every exercise has an answer or explanation (answer_key)" if arch.get("exercise_policy") not in ("none",) else "; plan no exercises, quizzes or review questions") + ".",
             f"- requirements: {', '.join(arch['block_policy'].get('requirements') or []) or '-'}.",
             f"- visual policy: density {v.get('density')}; prefer {', '.join(v.get('preferred_types') or []) or '-'}; avoid {', '.join(v.get('avoid_types') or []) or '-'}; "
             f"at least {v.get('min_distinct_types', 1)} distinct visual types across the book, no type over {int(float(v.get('max_share_per_type', 0.5)) * 100)}% of visuals.",
             f"- evidence: {arch.get('evidence_policy', {}).get('rule', '')} Preferred authority: {', '.join(arch.get('evidence_policy', {}).get('preferred_authority') or []) or '-'}."]
    if chapter:
        lines.append(f"- this chapter ({chapter.get('id')}): content intent: {chapter.get('content_intent') or '(see outline)'}; planned blocks: {', '.join(p['planned']) or '-'}; "
                     f"visuals: {', '.join(map(str, as_list(chapter.get('visuals')))) or '-'}.")
    return lines


# ---------------------------------------------------------------- chapter architecture (outline)

def check_outline(chapters, arch=None, project=None):
    """AUTO / GUIDED: each outline chapter states its content intent and the blocks and visuals it needs; chapters
    are not clones of one template; uploaded assets point at real chapters."""
    arch = arch or load(project)
    if arch.get("legacy") or arch["mode"] == "fixed" or not chapters: return []
    errors = []
    ids = {c["id"] for c in chapters}
    for c in chapters:
        name = c["id"]
        if len(str(c.get("content_intent") or "").strip()) < 10: errors.append(f"{name}: content_intent is required (what this chapter must do for its reader)")
        if c.get("blocks_declared") is False: errors.append(f"{name}: blocks is required (the block-library items this chapter's content needs; [] for plain prose)")
        policy = chapter_policy(arch, c)
        for b in c.get("blocks") or []:
            if canonical(b) not in BLOCKS: errors.append(f"{name}: unknown block {b} (library: schemas/publication-architecture.json)")
            elif status(policy, b) == "forbidden": errors.append(f"{name}: block {b} is forbidden ({reason(arch, b) or 'block policy'})")
        for v in c.get("visuals") or []:
            if v not in VISUAL_TYPES: errors.append(f"{name}: unknown visual type {v} (taxonomy: {', '.join(VISUAL_TYPES)})")
        over = c.get("block_overrides") or {}
        for key in ("preferred", "discouraged"):
            for b in as_list(over.get(key)):
                if canonical(b) in arch["block_policy"]["forbidden"]: errors.append(f"{name}: block_overrides.{key} cannot re-allow forbidden {b}")
    if arch.get("exercise_policy") == "none":
        for c in chapters:
            for b in c.get("blocks") or []:
                if canonical(b) in EXERCISE_BLOCKS: errors.append(f"{c['id']}: exercise_policy is none; remove {b}")
    reason_text = str((arch.get("chapter_strategy") or {}).get("uniform_structure_reason") or "").strip()
    signatures = [tuple(sorted(canonical(b) for b in c.get("blocks") or [])) for c in chapters]
    if len(chapters) >= 4 and len(set(signatures)) == 1 and not reason_text:
        errors.append("every chapter plans the same blocks (" + ", ".join(signatures[0]) + "): design each chapter from its content "
                      "(the same unified voice does not need the same structure), or give chapter_strategy.uniform_structure_reason")
    import source_roles
    for asset in source_roles.uploaded_assets(project):
        if asset.get("intended_chapter") and source_roles.chapter_ref(asset["intended_chapter"], chapters) not in ids:
            errors.append(f"uploaded {asset['id']} ({asset['label']}) is meant for chapter {asset['intended_chapter']!r}, which is not in the outline: "
                          "use that id for the chapter it describes, or record why in plan/publication-architecture.yaml asset_notes")
    return errors


def scaled_profile(profile, arch=None):
    """The profile with its visual-rate health check scaled by the architecture's visual density (AUTO / GUIDED only):
    「図表を多く」 or a visual guide raises the range, an essay-like book lowers it."""
    if not profile: return profile
    try: arch = arch or load()
    except Exception: return profile
    if arch.get("legacy") or arch.get("mode") not in ("auto", "guided"): return profile
    policy = arch.get("visual_policy") or {}
    factor = float(policy.get("density_factor") or VOCAB["visual_densities"].get(policy.get("density"), 1.0))
    if factor == 1.0: return profile
    return {**profile, "devices": {**profile["devices"], "visuals_per_10k": {k: round(float(v) * factor, 2) for k, v in profile["devices"]["visuals_per_10k"].items()}}}

"""PublicationProfile: the editorial shape of the book, resolved before planning (plan/profile.resolved.yaml).

A profile says how much body text the book carries and how that text is organised and interrupted: chapter
structure, paragraph and section length, figure/table/callout/case-study density, chapter-end apparatus, the
text-wall limit, non-prose share, citation habits and the weight of the art direction.

Resolution order (later wins):
    profiles/tiers/<tier>.yaml  →  profiles/genres/<genre>.yaml  →  project.json overrides
Recommended input: `"profile": "long"` or `"profile": {"tier": "long", "genre": "criticism", "overrides": {...}}`.
Compatibility: a project with only `book.target_pages` gets the tier its size implies (<=80 short, <=200 standard,
<=450 long, else monograph) and a body size derived from that page count; the page count itself is never the
profile. Pages are an estimate derived from body characters, characters per text page, the non-prose share and
front/back matter. The same inputs always resolve to the same profile (inputs_fingerprint).
"""
import copy
import hashlib
import json
import math
import re

from common import ROOT, write_yaml, yaml_data

SCHEMA = "bookorder/publication-profile@1"
PROFILES = ROOT / "profiles"
RESOLVED = ROOT / "plan/profile.resolved.yaml"
TIERS = ("short", "standard", "long", "monograph")
GENRES = ("technical", "medical_science", "practical", "criticism", "essay")
GENRE_ALIASES = {"medical": "medical_science", "science": "medical_science", "medical-science": "medical_science",
                 "humanities": "criticism", "general": None, "": None}
PAGE_TIERS = ((80, "short"), (200, "standard"), (450, "long"))

# Characters of running text on a full text-only page, A5 at standard density (measured: a 10pt Japanese A5
# page holds about 780 non-space characters). Page size and density scale it.
TEXT_PAGE_CHARS = {"ja": 780, "zh": 800, "ko": 700, "default": 2200}
PAGE_AREA = {"A5": 1.0, "B5": 1.42, "A4": 2.0, "Letter": 1.95, "B6": 0.71}
A5_AREA_MM2 = 148.0 * 210.0
DENSITY = {"compact": 1.15, "standard": 1.0, "spacious": 0.85}

CHAPTER_END = ("key_points", "open_question", "bridge_to_next", "further_reading", "check_questions", "exercises", "checklist", "summary")
IMAGE_ROLES = ("chapter_opener", "part_opener", "editorial_illustration")

# Validation spec: (kind, bounds or choices). "range" = {min, target, max} with min <= target <= max.
SPEC = {
    "scale": {"target_body_chars": ("int", 1000, 3000000), "target_pages": ("int", 1, 5000), "chars_per_text_page": ("number", 100, 6000),
              "nonprose_share_target": ("number", 0, 0.9), "minimum_ratio": ("number", 0.3, 1), "chapter_minimum_ratio": ("number", 0.3, 1),
              "front_matter_pages": ("int", 0, 60), "back_matter_share": ("number", 0, 0.5), "back_matter_pages": ("int", 0, 1000),
              "language": ("str",), "page_size": ("str",), "density": ("str",)},
    "structure": {"parts": ("range", 0, 20), "chapters": ("range", 1, 100), "heading_depth_max": ("int", 1, 4),
                  "section_chars": ("range", 100, 12000), "paragraph_chars_max": ("int", 150, 2000),
                  "chapter_lead": ("enum", ("none", "optional", "required")), "chapter_end": ("list", CHAPTER_END)},
    "devices": {"visuals_per_10k": ("range", 0, 12), "tables_per_chapter": ("range", 0, 20), "callouts_per_chapter": ("range", 0, 20),
                "case_studies_per_chapter": ("range", 0, 10), "columns_per_chapter": ("range", 0, 10), "pull_quotes_per_chapter": ("range", 0, 10)},
    "rhythm": {"max_text_only_pages": ("int", 1, 20), "pause_every_chars": ("pair", 300, 20000), "abstract_run_chars_max": ("int", 300, 10000)},
    "citations": {"style": ("enum", ("numeric", "author_date", "endnotes_per_chapter", "minimal")), "inline_markers_per_page_max": ("number", 0, 10),
                  "further_reading_per_chapter": ("range", 0, 20)},
    "art_direction": {"weight": ("enum", ("light", "standard", "strong")), "ornament_level": ("enum", ("none", "low", "medium", "high")),
                      "generative_images": ("images",)},
}
INTEGER_RANGES = {"structure.parts", "structure.chapters", "structure.section_chars"}


# ---------------------------------------------------------------- data

def _coerce(value):
    """Pandoc's YAML reader yields strings for numbers; restore numbers recursively."""
    if isinstance(value, dict): return {k: _coerce(v) for k, v in value.items()}
    if isinstance(value, list): return [_coerce(v) for v in value]
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()): return int(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?", value.strip()): return float(value)
    return value


def load_data(kind, name):
    path = PROFILES / kind / f"{name}.yaml"
    if not path.is_file(): raise ValueError(f"Unknown {kind[:-1]} {name!r}; choose one of {', '.join(TIERS if kind == 'tiers' else GENRES)}")
    return _coerce(yaml_data(path))


def _get(tree, path):
    for key in path.split("."): tree = tree[key]
    return tree


def _set(tree, path, value):
    keys = path.split(".")
    for key in keys[:-1]: tree = tree.setdefault(key, {})
    tree[keys[-1]] = value


def _flatten(tree, prefix=""):
    """Nested override mapping -> dotted paths (dotted keys are accepted as they are)."""
    out = {}
    for key, value in (tree or {}).items():
        path = f"{prefix}{key}"
        if isinstance(value, dict) and path.count(".") < 1 and key in SPEC: out.update(_flatten(value, path + "."))
        else: out[path] = value
    return out


def _scaled(value, factor, integer=False):
    if isinstance(value, dict): return {k: _scaled(v, factor, integer) for k, v in value.items()}
    if isinstance(value, (int, float)):
        result = value * factor
        return int(round(result)) if integer else round(result, 3)
    return value


# ---------------------------------------------------------------- request

def request(project):
    """What the project asks for, normalised: tier, genre, user overrides and the compatibility inputs."""
    raw = project.get("profile")
    spec = {"tier": raw} if isinstance(raw, str) else dict(raw or {})
    book = project.get("book") or {}; pacing = project.get("pacing") or {}; legacy = project.get("scale") or {}
    pages = int(float(book.get("target_pages") or 0))
    overrides = _flatten(spec.get("overrides"))
    notes = []
    tier = spec.get("tier") or pacing.get("tier")
    if tier: notes.append(f"tier {tier} from project.json " + ("profile" if spec.get("tier") else "pacing.tier"))
    else:
        tier = next((name for bound, name in PAGE_TIERS if pages <= bound), "monograph") if pages else "standard"
        notes.append(f"tier {tier} chosen from book.target_pages={pages} (compatibility)" if pages else "tier standard (no profile or page target)")
    genre = spec.get("genre", project.get("genre"))
    genre = GENRE_ALIASES.get(genre, genre)
    # Settings that predate profiles are honoured as user overrides.
    if str(pacing.get("max_text_only_pages", "")).isdigit(): overrides.setdefault("rhythm.max_text_only_pages", int(pacing["max_text_only_pages"]))
    if legacy.get("target_characters"): overrides.setdefault("scale.target_body_chars", int(float(legacy["target_characters"])))
    for key in ("minimum_ratio", "chapter_minimum_ratio"):
        if legacy.get(key) is not None: overrides.setdefault(f"scale.{key}", float(legacy[key]))
    compatibility = {"target_pages": pages or None, "characters_per_page": legacy.get("characters_per_page")}
    return {"tier": tier, "genre": genre, "overrides": overrides, "compatibility": compatibility, "notes": notes}


# ---------------------------------------------------------------- resolution

def page_estimate(body_chars, chars_per_text_page, nonprose, front, back_share):
    main = body_chars / (chars_per_text_page * (1 - nonprose))
    back = math.ceil(main * back_share)
    return math.ceil(main + front + back), back


def body_for_pages(pages, chars_per_text_page, nonprose, front, back_share):
    front = min(front, int(pages * 0.1))
    main = max(1.0, (pages - front) / (1 + back_share))
    return int(round(main * chars_per_text_page * (1 - nonprose))), front


def page_basis(project, design):
    """(page size name, area relative to A5) for the characters-per-page model. A layout requested in project.json
    (layout_preset / layout_spec, e.g. from the WebUI) wins over the Design Spec page, so B6 and custom sizes count."""
    size = (design.get("page") or {}).get("size", "A5")
    chosen = {}
    if project.get("layout_preset") or project.get("layout_spec"):
        try:
            import layout_spec
            chosen = layout_spec.request(project)
        except Exception: chosen = {}
    size = chosen.get("page_size") or size
    if size in PAGE_AREA and size != "custom": return size, PAGE_AREA[size]
    page = chosen.get("page") or {}
    try:
        import layout_spec
        width, height = (float(page["width_mm"]), float(page["height_mm"])) if size == "custom" else layout_spec.page_dimensions(size)
    except Exception: return size, 1.0
    return size, round(width * height / A5_AREA_MM2, 3)


def resolve(project, design=None):
    """The resolved profile (a dict). Deterministic: no clock, no environment beyond the arguments and data files."""
    design = design or {}
    ask = request(project)
    if ask["tier"] not in TIERS: raise ValueError(f"profile tier must be one of {', '.join(TIERS)} (got {ask['tier']!r})")
    if ask["genre"] is not None and ask["genre"] not in GENRES: raise ValueError(f"profile genre must be one of {', '.join(GENRES)} (got {ask['genre']!r})")
    tier = load_data("tiers", ask["tier"])
    genre = load_data("genres", ask["genre"]) if ask["genre"] else {}
    profile = {key: copy.deepcopy(tier[key]) for key in SPEC}
    resolved_from = [f"profiles/tiers/{ask['tier']}.yaml"] + ([f"profiles/genres/{ask['genre']}.yaml"] if genre else [])

    for path, factor in (genre.get("multiply") or {}).items():
        _set(profile, path, _scaled(_get(profile, path), float(factor), integer=path in INTEGER_RANGES or path == "structure.paragraph_chars_max"))
    for path, delta in (genre.get("add") or {}).items(): _set(profile, path, _get(profile, path) + delta)
    for path, value in (genre.get("set") or {}).items(): _set(profile, path, copy.deepcopy(value))

    # Body size and page model. Characters per text page come from the design; body chars from an explicit
    # override, else from a compatibility page target, else from the tier.
    scale = profile["scale"]
    language = str((project.get("book") or {}).get("language", "en")).split("-")[0].lower()
    size, area = page_basis(project, design); density = (design.get("layout") or {}).get("density", "standard")
    overrides = dict(ask["overrides"])
    for path in [p for p in overrides if p.startswith("scale.")]:
        if path != "scale.target_body_chars": _set(profile, path, overrides.pop(path))
    per_page = overrides.pop("scale.chars_per_text_page", None) or TEXT_PAGE_CHARS.get(language, TEXT_PAGE_CHARS["default"]) * area * DENSITY.get(density, 1.0)
    if ask["compatibility"]["characters_per_page"]:  # legacy: effective characters per page, devices included
        per_page = float(ask["compatibility"]["characters_per_page"]) / (1 - scale["nonprose_share_target"])
    per_page = round(float(per_page))
    front = scale["front_matter_pages"]
    if "scale.target_body_chars" in overrides: body = int(overrides.pop("scale.target_body_chars")); origin = "override"
    elif ask["compatibility"]["target_pages"]:
        body, front = body_for_pages(ask["compatibility"]["target_pages"], per_page, scale["nonprose_share_target"], front, scale["back_matter_share"])
        origin = f"book.target_pages={ask['compatibility']['target_pages']}"
    else: body = int(scale["target_body_chars"]); origin = "tier"
    pages, back = page_estimate(body, per_page, scale["nonprose_share_target"], front, scale["back_matter_share"])
    scale.update(target_body_chars=body, chars_per_text_page=per_page, target_pages=pages, front_matter_pages=front,
                 back_matter_pages=back, language=language, page_size=size, density=density)
    scale.setdefault("chapter_minimum_ratio", 0.75)

    for path, value in overrides.items():
        section = path.split(".")[0]
        if section not in SPEC: raise ValueError(f"profile override {path}: unknown section {section}")
        _set(profile, path, value)
    if overrides: resolved_from.append("project.json overrides")
    if origin.startswith("book.target_pages"): resolved_from.append(f"project.json {origin} (compatibility: body size)")

    inputs = {"tier": tier, "genre": genre, "request": {k: ask[k] for k in ("tier", "genre", "overrides", "compatibility")},
              "language": language, "page_size": size, "density": density}
    if size not in PAGE_AREA: inputs["page_area"] = area
    fingerprint = "sha256:" + hashlib.sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
    result = {"schema": SCHEMA, "id": f"{ask['tier']}.{ask['genre'] or 'general'}", "tier": ask["tier"], "genre": ask["genre"] or "general",
              "resolved_from": resolved_from,
              "source": {"tier": ask["tier"], "genre": ask["genre"] or "general", "user_overrides": ask["overrides"], "body_chars_from": origin,
                         "compatibility": {k: v for k, v in ask["compatibility"].items() if v}, "notes": ask["notes"]},
              "inputs_fingerprint": fingerprint, **profile}
    result = ordered(result)
    errors = validate(result)
    if errors: raise ValueError("Invalid publication profile: " + "; ".join(errors))
    return result


# ---------------------------------------------------------------- validation

def _check(path, value, rule, errors):
    kind = rule[0]
    number = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if kind in ("int", "number"):
        if not number(value) or (kind == "int" and int(value) != value): errors.append(f"{path}: expected {'an integer' if kind == 'int' else 'a number'}"); return
        if not rule[1] <= value <= rule[2]: errors.append(f"{path}: {value} outside {rule[1]}..{rule[2]}")
    elif kind == "str":
        if not isinstance(value, str): errors.append(f"{path}: expected text")
    elif kind == "enum":
        if value not in rule[1]: errors.append(f"{path}: {value!r} is not one of {', '.join(rule[1])}")
    elif kind == "list":
        if not isinstance(value, list) or any(v not in rule[1] for v in value): errors.append(f"{path}: items must be among {', '.join(rule[1])}")
    elif kind in ("range", "pair"):
        keys = ("min", "target", "max") if kind == "range" else ("target", "max")
        if not isinstance(value, dict) or set(value) != set(keys) or not all(number(value[k]) for k in keys):
            errors.append(f"{path}: expected numbers {{{', '.join(keys)}}}"); return
        ordered = [value[k] for k in keys]
        if ordered != sorted(ordered): errors.append(f"{path}: needs {' <= '.join(keys)} (got {', '.join(str(v) for v in ordered)})")
        if not all(rule[1] <= v <= rule[2] for v in ordered): errors.append(f"{path}: values outside {rule[1]}..{rule[2]}")
    elif kind == "images":
        if not isinstance(value, dict) or set(value) != {"allowed", "max_total"}: errors.append(f"{path}: expected {{allowed, max_total}}"); return
        if not isinstance(value["allowed"], list) or any(v not in IMAGE_ROLES for v in value["allowed"]): errors.append(f"{path}.allowed: roles among {', '.join(IMAGE_ROLES)}")
        if not number(value["max_total"]) or not 0 <= value["max_total"] <= 200: errors.append(f"{path}.max_total: 0..200")
        if value.get("max_total") and not value.get("allowed"): errors.append(f"{path}: max_total without allowed roles")


def validate(profile):
    """Schema and consistency errors (empty list = valid)."""
    errors = []
    if profile.get("schema") != SCHEMA: errors.append(f"schema must be {SCHEMA}")
    for section, rules in SPEC.items():
        block = profile.get(section)
        if not isinstance(block, dict): errors.append(f"{section}: missing"); continue
        for key in set(block) - set(rules): errors.append(f"{section}.{key}: unknown setting")
        for key, rule in rules.items():
            if key not in block: errors.append(f"{section}.{key}: missing"); continue
            _check(f"{section}.{key}", block[key], rule, errors)
    if errors: return errors
    s, r = profile["structure"], profile["rhythm"]
    if s["section_chars"]["max"] < s["paragraph_chars_max"]: errors.append("structure.section_chars.max must be at least paragraph_chars_max")
    if r["pause_every_chars"]["max"] < s["paragraph_chars_max"]: errors.append("rhythm.pause_every_chars.max must be at least paragraph_chars_max")
    if profile["devices"]["visuals_per_10k"]["max"] <= 0 and profile["tier"] != "monograph" and profile["genre"] != "essay":
        errors.append("devices.visuals_per_10k.max must allow some visuals")
    return errors


# ---------------------------------------------------------------- files and consumers

def ordered(profile):
    """Readable, stable key order: header fields, then sections and settings in SPEC order."""
    head = {k: profile[k] for k in ("schema", "id", "tier", "genre", "resolved_from", "source", "inputs_fingerprint") if k in profile}
    body = {section: {key: profile[section][key] for key in rules if key in profile[section]} for section, rules in SPEC.items()}
    for section, block in body.items():
        for key, value in block.items():
            if isinstance(value, dict) and set(value) <= {"min", "target", "max"}: block[key] = {k: value[k] for k in ("min", "target", "max") if k in value}
    return {**head, **body}


def write(profile):
    """plan/profile.resolved.yaml (generated; the inputs live in project.json and profiles/)."""
    RESOLVED.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(RESOLVED, ordered(profile), "Generated by BookOrder from profiles/ and project.json. Edit project.json `profile`, not this file.")
    return RESOLVED


def load_resolved():
    """The resolved profile of this job, or None when it has not been resolved (or is invalid)."""
    if not RESOLVED.is_file(): return None
    try: profile = _coerce(yaml_data(RESOLVED))
    except Exception: return None
    return profile if not validate(profile) else None


def scale(profile):
    """The orchestrator's `scale` (chapter budgets, length gates), derived from the profile."""
    s = profile["scale"]
    effective = round(s["chars_per_text_page"] * (1 - s["nonprose_share_target"]))
    return {"requested_pages": s["target_pages"], "language": s["language"], "page_size": s["page_size"], "density": s["density"],
            "characters_per_page": effective, "target_characters": s["target_body_chars"],
            "minimum_characters": math.ceil(s["target_body_chars"] * s["minimum_ratio"]), "minimum_ratio": s["minimum_ratio"],
            "chapter_minimum_ratio": s["chapter_minimum_ratio"], "minimum_chapters": profile["structure"]["chapters"]["min"],
            "maximum_chapters": profile["structure"]["chapters"]["max"],
            "paragraph_chars_max": profile["structure"]["paragraph_chars_max"],
            "nonprose_share_target": s["nonprose_share_target"],
            "profile": {"id": profile["id"], "tier": profile["tier"], "genre": profile["genre"], "inputs_fingerprint": profile["inputs_fingerprint"],
                        "file": "plan/profile.resolved.yaml"},
            "estimate_note": (f"{s['target_body_chars']:,} body characters ≈ {s['target_pages']} pages at {s['chars_per_text_page']} characters per "
                              f"text page with {s['nonprose_share_target']:.0%} non-prose area and {s['front_matter_pages']}+{s['back_matter_pages']} "
                              "front/back pages. Pages are an estimate; the character minimum is enforced.")}


def summary_lines(profile):
    """Planning instructions that state the profile to the author."""
    s, st, d, r = profile["scale"], profile["structure"], profile["devices"], profile["rhythm"]
    rng = lambda x: f"{x['min']}–{x['max']} (target {x['target']})"
    return [f"Publication profile {profile['id']} (plan/profile.resolved.yaml) is binding for the plan:",
            f"- {s['target_body_chars']:,} body characters, about {s['target_pages']} pages; {rng(st['chapters'])} chapters"
            + (f", {rng(st['parts'])} parts" if st["parts"]["max"] else "") + f"; headings to level {st['heading_depth_max']}.",
            f"- Sections {rng(st['section_chars'])} characters; paragraphs at most {st['paragraph_chars_max']} characters; "
            f"chapter lead {st['chapter_lead']}; chapter end: {', '.join(st['chapter_end']) or 'none'}.",
            f"- Per 10,000 characters {rng(d['visuals_per_10k'])} figures/tables; per chapter {rng(d['tables_per_chapter'])} tables, "
            f"{rng(d['callouts_per_chapter'])} callouts, {rng(d['case_studies_per_chapter'])} case studies, {rng(d['pull_quotes_per_chapter'])} pull quotes.",
            f"- At most {r['max_text_only_pages']} consecutive text-only pages (gate 17); a pause about every {r['pause_every_chars']['target']:,} "
            f"characters (never more than {r['pause_every_chars']['max']:,}); concrete example after at most {r['abstract_run_chars_max']:,} characters of abstraction.",
            f"- Citations {profile['citations']['style']}, at most {profile['citations']['inline_markers_per_page_max']} markers per page; "
            f"art direction {profile['art_direction']['weight']}, ornament {profile['art_direction']['ornament_level']}."]

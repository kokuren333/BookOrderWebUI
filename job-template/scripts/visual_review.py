"""Visual candidate review: which planned visuals earn their place (reports/visual-review.yaml).

Every figure, chart, table and generated image in plan/assets-plan.yaml is a *candidate*. BookOrder decides
accepted / rejected / pending from what the candidate claims and what it actually is:

- an improvement claim (reduce_working_memory, reveal_structure, show_quantity_shape, anchor_abstraction,
  orient_reader) plus one sentence on what the reader gains over prose;
- the information shape (comparison, quantity, chronology, hierarchy, process, causal, relation, formula,
  abstract, sequence, source_image), which routes to the representation that fits it;
- the drawn structure itself once its Diagram IR exists (nodes, edges, labels, branching, cycles);
- evidence for what it asserts (factual_basis, source_ids), and no disclaimer in the caption.

Visual density from the PublicationProfile is a health check of the plan, never a quota: a shortfall becomes
an issue asking to revisit the editorial plan, not an instruction to add figures. Rejected candidates stay in
the plan with their reasons so they can go back to prose, become a table or change type. Only accepted
candidates are generated (diagrams.generate, check_generation).
"""
from pathlib import Path
import re

from common import ROOT, as_list, write_yaml

SCHEMA = "bookorder/visual-review@1"
REPORT = ROOT / "reports/visual-review.yaml"
CLAIMS = ("reduce_working_memory", "reveal_structure", "show_quantity_shape", "anchor_abstraction", "orient_reader")
SHAPES = ("comparison", "quantity", "chronology", "hierarchy", "process", "causal", "relation", "formula", "abstract",
          "sequence", "source_image")
BASES = ("data", "source", "derived_from_text", "illustrative", "none")
VISUAL_TYPES = ("diagram", "chart", "table", "image", "screenshot", "equation")
DECISIONS = ("accepted", "rejected", "pending")
# Rejections that stand even for a figure the user uploaded and placed (integrity, not usefulness).
USER_UPLOAD_BLOCKING = ("missing_sources", "causal_without_evidence", "disclaimer_caption", "withdrawn")
RING = {"cycle", "network", "concept-map"}
TREE = {"hierarchy"}
IMAGE_ROLES = ("chapter_opener", "part_opener", "editorial_illustration")
# Captions that apologise for the figure: its claim exceeds its basis.
DISCLAIMER = re.compile(r"実証的な?(因果)?モデルではない|実証的(な)?(根拠|モデル)ではない|編集部が(整理|作成)した(概念|図)|概念図(であり|で)|"
                        r"模式図にすぎない|not an? (empirical|causal) model|for illustration only|schematic only|editorial arrangement", re.I)
# Purposes that exist to fill the page rather than to explain.
PADDING = re.compile(r"密度|ノルマ|埋め|文章壁|視覚的(な)?(変化|休止|アクセント)|単調さを避け|ページを(埋|区切)|visual (break|variety|interest)|"
                     r"break up (the )?text|fill|density|quota|pacing|add a visual", re.I)
CAUSAL_WORDS = re.compile(r"原因|要因|影響|もたらす|引き起こ|因果|効果|交絡|cause|effect|confound|leads to|drives", re.I)
DEFAULT_RENDERERS = {"table": ("native-table", "list"), "chart": ("python-chart", "native-table"), "diagram": ("diagram-ir-svg", "graphviz"),
                     "image": ("imagegen", "svg-abstract"), "screenshot": ("source-image", None), "equation": ("typst-math", None)}


# ---------------------------------------------------------------- structure of a diagram

def diagram_structure(spec):
    """Counts and topology of a Diagram IR spec, with the implicit edges the renderer draws."""
    nodes = [n["id"] for n in spec.get("nodes", [])]; kind = spec.get("type")
    edges = [dict(e) for e in spec.get("edges", [])]
    if not edges and kind in ("flow", "process", "timeline", "cycle") and len(nodes) > 1:
        edges = [{"from": nodes[i], "to": nodes[(i + 1) % len(nodes)]} for i in range(len(nodes) if kind == "cycle" else len(nodes) - 1)]
    if not edges and kind == "concept-map": edges = [{"from": nodes[0], "to": n} for n in nodes[1:]]
    out = {n: 0 for n in nodes}; into = {n: 0 for n in nodes}; graph = {n: [] for n in nodes}
    for e in edges:
        out[e["from"]] = out.get(e["from"], 0) + 1; into[e["to"]] = into.get(e["to"], 0) + 1
        graph.setdefault(e["from"], []).append(e["to"])
    state, cycle = {}, False

    def visit(n):
        nonlocal cycle
        state[n] = 1
        for m in graph.get(n, []):
            if state.get(m) == 1: cycle = True
            elif not state.get(m): visit(m)
        state[n] = 2
    for n in nodes:
        if not state.get(n): visit(n)
    depth = {}
    def level(n, seen=()):
        if n in seen: return 0
        parents = [e["from"] for e in edges if e["to"] == n]
        return 0 if not parents else 1 + max(level(p, seen + (n,)) for p in parents)
    if not cycle: depth = {n: level(n) for n in nodes}
    labelled = sum(1 for e in edges if str(e.get("label") or "").strip())
    branching = any(v >= 2 for v in out.values()); merging = any(v >= 2 for v in into.values())
    return {"type": kind, "nodes": len(nodes), "edges": len(edges), "explicit_edges": len(spec.get("edges", [])), "labelled_edges": labelled,
            "branching": branching, "merging": merging, "cycle": cycle, "levels": (max(depth.values()) + 1) if depth else None,
            "linear": not (branching or merging or cycle), "layout": "ring" if kind in RING else "tree" if kind in TREE else "grid",
            "edge_labels": [str(e.get("label") or "") for e in edges]}


def _load_diagram(asset):
    source = asset.get("source")
    if not source: return None
    path = ROOT / str(source)
    if not path.is_file(): return None
    import json
    from common import yaml_data
    from schema import validate_schema
    schema = json.loads((ROOT / "schemas/diagram.schema.json").read_text(encoding="utf-8"))
    return validate_schema(yaml_data(path), schema, str(source), coerce=True)


# ---------------------------------------------------------------- candidate

def _number(value):
    try: return float(value)
    except (TypeError, ValueError): return None


def visual_type(asset, structure=None):
    kind = asset.get("type")
    if kind == "diagram": return "diagram." + str((structure or {}).get("type") or (asset.get("information_shape") or {}).get("diagram") or asset.get("diagram_type") or "unknown")
    if kind == "chart": return "chart." + str(asset.get("chart_type") or (asset.get("information_shape") or {}).get("chart") or "unspecified")
    if kind == "image": return "image." + str(asset.get("role") or "illustration")
    return str(kind)


def _scalar(value):
    # Pandoc hands YAML numbers and booleans back as strings.
    if isinstance(value, str):
        if re.fullmatch(r"-?\d+", value.strip()): return int(value)
        if value.strip() in ("true", "false"): return value.strip() == "true"
    return value


def candidate(asset, chapter_index=None):
    """Normalised candidate fields from an asset-plan entry (and its Diagram IR once it exists)."""
    shape = dict(asset.get("information_shape") or {}) if isinstance(asset.get("information_shape"), dict) else {"kind": asset.get("information_shape")}
    shape = {k: _scalar(v) for k, v in shape.items()}
    claim = asset.get("improvement_claim") or {}
    if isinstance(claim, (str, list)): claim = {"kinds": as_list(claim)}
    statement = str(claim.get("statement") or asset.get("purpose") or "").strip()
    structure = None
    if asset.get("type") == "diagram":
        try: spec = _load_diagram(asset)
        except Exception: spec = None
        if spec:
            structure = diagram_structure(spec)
        elif shape.get("nodes") is not None:
            n = int(_number(shape.get("nodes")) or 0); e = int(_number(shape.get("edges")) or 0)
            structure = {"type": shape.get("diagram"), "nodes": n, "edges": e, "explicit_edges": e,
                         "labelled_edges": int(_number(shape.get("labelled_edges")) or 0), "branching": bool(shape.get("branching")),
                         "merging": bool(shape.get("merging")), "cycle": bool(shape.get("cycle")), "levels": _number(shape.get("levels")),
                         "linear": not (shape.get("branching") or shape.get("merging") or shape.get("cycle")),
                         "layout": "ring" if shape.get("diagram") in RING else "tree" if shape.get("diagram") in TREE else "grid", "edge_labels": [],
                         "declared": True}
    renderers = DEFAULT_RENDERERS.get(asset.get("type"), (None, None))
    return {"id": str(asset.get("id")), "device": str(asset.get("device") or "") or None, "chapter": asset.get("chapter"), "chapter_index": chapter_index, "section": asset.get("section"),
            "type": asset.get("type"), "visual_type": visual_type(asset, structure), "information_shape": shape,
            "improvement_claim": {"kinds": [str(k) for k in as_list(claim.get("kinds"))], "statement": statement},
            "preferred_renderer": asset.get("preferred_renderer") or renderers[0], "fallback_renderer": asset.get("fallback_renderer") or renderers[1],
            "factual_basis": asset.get("factual_basis"), "source_ids": [str(s) for s in as_list(asset.get("source_ids"))],
            "factuality": asset.get("factuality") or ("illustrative" if asset.get("factual_basis") == "illustrative" else
                                                  "conceptual" if shape.get("kind") == "abstract" else "factual"),
            "duplicate_group": asset.get("duplicate_group"), "caption": str(asset.get("caption") or ""), "purpose": str(asset.get("purpose") or ""),
            "role": asset.get("role"), "requested": asset.get("decision"), "request_reason": asset.get("decision_reason"),
            "uploaded_asset": asset.get("uploaded_asset"),
            "structure": structure}


def signature(c):
    """Composition fingerprint: two candidates with the same one look alike on the page."""
    s = c.get("structure")
    if s: return f"{c['type']}:{s['layout']}:{s['nodes']}n"
    return f"{c['visual_type']}:{c['information_shape'].get('kind')}"


# ---------------------------------------------------------------- routing

def route(shape):
    """Representations that fit an information shape (first = preferred); None means prose or a list."""
    kind = shape.get("kind"); n = lambda key: _number(shape.get(key)) or 0
    if kind == "comparison":
        if n("items") >= 3 and n("attributes") >= 3: return ["table"]
        return ["table", "list"]
    if kind == "quantity": return ["chart"] if n("values") >= 5 else ["table", "prose"]
    if kind == "chronology": return ["diagram.timeline", "chart", "table"] if n("events") >= 3 else ["prose"]
    if kind == "hierarchy": return ["diagram.hierarchy", "table"] if n("levels") >= 2 else ["list"]
    if kind == "process":
        if shape.get("branching") or shape.get("merging") or shape.get("cycle"): return ["diagram.flow", "diagram.process", "diagram.cycle", "diagram.network"]
        return ["list"]
    if kind == "sequence": return ["list"]
    if kind == "causal": return ["diagram.network", "diagram.flow", "diagram.hierarchy"]
    if kind == "relation": return ["diagram.concept-map", "diagram.network", "diagram.matrix", "table"]
    if kind == "formula": return ["equation"]
    if kind == "abstract": return ["image.chapter_opener", "image.part_opener", "image.editorial_illustration"]
    if kind == "source_image": return ["screenshot"]
    return []


def _fits(visual, options):
    # A diagram whose Diagram IR is not written yet is judged on its shape; its drawn type is checked once it exists.
    if visual == "diagram.unknown" and any(o.startswith("diagram") for o in options): return True
    return any(visual == o or visual.startswith(o + ".") or (o in ("chart", "table", "equation", "screenshot", "image") and visual.split(".")[0] == o) for o in options)


# ---------------------------------------------------------------- rules

def _reason(code, detail, suggestion=None):
    return {"code": code, "detail": detail, **({"suggestion": suggestion} if suggestion else {})}


def rules(c, profile=None):
    """Hard rejection reasons for one candidate (empty = acceptable on its own)."""
    reasons = []; kind = c["type"]; shape = c["information_shape"]; claim = c["improvement_claim"]; s = c.get("structure")
    if kind in ("equation", "cover"): return []  # defined by the text; not a visual choice
    kinds = claim["kinds"]
    if not kinds: reasons.append(_reason("missing_improvement_claim", "no improvement_claim.kinds", f"state one of {', '.join(CLAIMS)} or keep it as prose"))
    unknown = [k for k in kinds if k not in CLAIMS]
    if unknown: reasons.append(_reason("unknown_improvement_claim", f"unknown claim {', '.join(unknown)}"))
    if len(re.sub(r"\s", "", claim["statement"])) < 12:
        reasons.append(_reason("no_reader_gain", "no one-sentence statement of what the reader gains over prose", "if it cannot be said, keep the prose"))
    if PADDING.search(claim["statement"] + " " + c["purpose"]):
        reasons.append(_reason("density_only", "the stated purpose is to fill, pace or decorate the page", "visual density is a check, not a quota: keep the prose"))
    if kinds == ["orient_reader"] and not (kind == "image" and c.get("role") in IMAGE_ROLES):
        reasons.append(_reason("orient_only", "orient_reader alone justifies only chapter/part openers or editorial illustrations"))
    if DISCLAIMER.search(c["caption"]):
        reasons.append(_reason("disclaimer_caption", "the caption has to disclaim the figure (not a model / arranged by the editors)",
                               "draw only what the sources support, or return to prose"))
    if shape.get("kind") and shape["kind"] not in SHAPES: reasons.append(_reason("unknown_shape", f"unknown information_shape {shape['kind']}"))
    options = route(shape) if shape.get("kind") in SHAPES else []
    if shape.get("kind") in SHAPES and options and not _fits(c["visual_type"], options):
        target = options[0]
        code = "list_sufficient" if target in ("list", "prose") else "shape_routes_elsewhere"
        reasons.append(_reason(code, f"a {shape['kind']} shape ({', '.join(f'{k}={v}' for k, v in shape.items() if k != 'kind')}) is shown better as {target}",
                               f"use {' or '.join(options)}"))
    if not shape.get("kind") and kind in ("diagram", "chart", "table"):
        reasons.append(_reason("missing_information_shape", "no information_shape: the representation cannot be justified"))
    # Evidence.
    basis = c["factual_basis"]
    needs_sources = kind in ("chart", "diagram", "table") and "orient_reader" not in kinds
    if basis and basis not in BASES: reasons.append(_reason("unknown_factual_basis", f"factual_basis must be one of {', '.join(BASES)}"))
    if needs_sources and basis in (None, "", "none"):
        reasons.append(_reason("missing_factual_basis", "no factual_basis for a figure that asserts facts or relations"))
    if basis in ("data", "source") and not c["source_ids"]:
        reasons.append(_reason("missing_sources", f"factual_basis {basis} without source_ids"))
    causal = shape.get("kind") == "causal" or (s and s["type"] in ("network", "flow", "concept-map") and any(CAUSAL_WORDS.search(l) for l in s.get("edge_labels", [])))
    if causal and (basis not in ("data", "source") or not c["source_ids"]):
        reasons.append(_reason("causal_without_evidence", "draws causal links without data or sources behind them", "cite the studies, or describe the association in prose"))
    if basis == "illustrative" and kind in ("diagram", "chart") and set(kinds) & {"reveal_structure", "show_quantity_shape"}:
        reasons.append(_reason("illustrative_structure", "an illustrative arrangement is presented as the structure or quantities of the subject"))
    # Drawn structure.
    if s:
        if s["nodes"] <= 2: reasons.append(_reason("too_few_nodes", f"{s['nodes']} nodes: a sentence says it", "prose"))
        if s["linear"] and s["type"] not in ("timeline", "hierarchy") and s["nodes"] >= 2:
            reasons.append(_reason("linear_sequence", f"a straight chain of {s['nodes']} steps (A→B→C) with no branch, merge or loop", "numbered list"))
        if s["type"] == "comparison" and s["nodes"] <= 2: reasons.append(_reason("binary_comparison", "two items compared", "table or list"))
        if s["type"] == "concept-map": reasons += concept_map_rules(c, s)
    if kind == "image":
        if c.get("factuality") == "factual" or shape.get("kind") == "source_image":
            reasons.append(_reason("factual_image_not_generative", "factual information needs a source-grounded table, chart, diagram or screenshot"))
        allowed = ((profile or {}).get("art_direction") or {}).get("generative_images") or {}
        if profile and c.get("role") not in as_list(allowed.get("allowed")):
            reasons.append(_reason("image_role_not_allowed", f"the profile allows generated images only as {', '.join(as_list(allowed.get('allowed'))) or 'nothing'}"))
    return reasons


def concept_map_rules(c, s):
    """Concept maps are held to a stricter standard: they must show structure that prose cannot."""
    reasons = []
    if s["nodes"] < 3: pass  # already too_few_nodes
    if s["edges"] < 3: reasons.append(_reason("concept_map_few_edges", f"{s['edges']} edges; a concept map needs at least 3 relations"))
    labelled_all = s["labelled_edges"] == s["edges"] and s["edges"] > 0
    if not labelled_all and not str(c["information_shape"].get("edge_semantics") or "").strip():
        reasons.append(_reason("concept_map_edge_semantics", f"{s['edges'] - s['labelled_edges']} of {s['edges']} relations are unnamed and no edge_semantics is given",
                               "name every relation, or use a list"))
    if not (s["branching"] or s["merging"] or s["cycle"] or (s.get("levels") or 0) >= 3):
        reasons.append(_reason("concept_map_no_structure", "no branch, merge, cycle or hierarchy: the map is a sentence drawn as boxes"))
    if "reveal_structure" not in c["improvement_claim"]["kinds"]:
        reasons.append(_reason("concept_map_claim", "a concept map must claim reveal_structure"))
    return reasons


# ---------------------------------------------------------------- the whole plan

def review(assets, chapters, profile=None, planned_chars=None, genre=None):
    """Decisions for every candidate plus book-level findings."""
    order = {c["id"]: i for i, c in enumerate(chapters)}
    cands = [candidate(a, order.get(a.get("chapter"))) for a in assets if a.get("type") in VISUAL_TYPES]
    genre = genre or (profile or {}).get("genre")
    for c in cands:
        c["rejection_reasons"] = rules(c, profile)
    # Duplicates within a chapter: same visual type and same claim.
    seen = {}
    for c in sorted(cands, key=lambda c: (c["chapter_index"] or 0, c["id"])):
        if c["type"] == "equation": continue
        key = (c["chapter"], c["visual_type"], tuple(sorted(c["improvement_claim"]["kinds"])))
        if key in seen: c["rejection_reasons"].append(_reason("duplicate_in_chapter", f"same type and claim as {seen[key]} in {c['chapter']}", "merge them or change one"))
        else: seen[key] = c["id"]
    # The same diagram composition repeated across the book.
    first = {}
    for c in sorted(cands, key=lambda c: (c["chapter_index"] or 0, c["id"])):
        if c["type"] != "diagram": continue  # charts differ by their data; their sameness is a monotony finding
        key = c.get("duplicate_group") or signature(c)
        if key in first: c["rejection_reasons"].append(_reason("repeated_composition", f"looks like {first[key]} (template {key})", "vary the representation or drop one"))
        else: first[key] = c["id"]
    for c in cands:
        if c["type"] in ("equation", "cover"): c["decision"] = "accepted"
        elif c["requested"] == "rejected":
            c["decision"] = "rejected"; c["rejection_reasons"].insert(0, _reason("withdrawn", str(c["request_reason"] or "withdrawn in the plan")))
        elif c["rejection_reasons"] and c.get("uploaded_asset") and not any(r["code"] in USER_UPLOAD_BLOCKING for r in c["rejection_reasons"]):
            # The user uploaded this figure and said where it belongs: usefulness heuristics yield to the user's
            # explicit choice (docs/user-intent.md); evidence problems still reject it.
            c["decision"] = "accepted"; c["user_directed"] = True
            c["waived_reasons"] = c["rejection_reasons"]; c["rejection_reasons"] = []
        elif c["rejection_reasons"]: c["decision"] = "rejected"
        elif c["requested"] == "pending": c["decision"] = "pending"
        else: c["decision"] = "accepted"
        c["generate"] = c["decision"] == "accepted"
    findings = monotony(cands, chapters, genre) + density(cands, chapters, profile, planned_chars)
    summary = {k: sum(c["decision"] == k for c in cands) for k in DECISIONS}
    return {"schema": SCHEMA, "profile": (profile or {}).get("id"), "genre": genre, "summary": summary,
            "plan_as_written": monotony(cands, chapters, genre, severity=False),
            "candidates": [{k: v for k, v in c.items() if k not in ("chapter_index", "requested", "request_reason", "purpose")} for c in cands],
            "findings": findings}


def monotony(cands, chapters, genre, severity=True):
    """Book-level sameness, reported even when every figure is acceptable on its own. Judged on the visuals that
    will be printed (accepted and pending); `severity=False` describes the plan as written, for information."""
    findings = []; data_ok = genre in ("technical", "medical_science")
    live = [c for c in cands if c["type"] in ("diagram", "chart", "image", "table") and (not severity or c["decision"] != "rejected")]
    level = lambda wanted: wanted if severity else "info"
    index = {ch["id"]: i for i, ch in enumerate(chapters)}
    by_type = {}
    for c in live:
        if c["type"] != "table" and c["chapter"] in index: by_type.setdefault(c["visual_type"], set()).add(index[c["chapter"]])
    for kind, where in sorted(by_type.items()):
        run = best = 0
        for i in range(len(chapters)):
            run = run + 1 if i in where else 0; best = max(best, run)
        if best >= 4:
            charts = kind.startswith("chart") and data_ok
            findings.append({"severity": level("low" if charts else "medium"), "rule": "same_type_consecutive_chapters",
                             "detail": f"{kind} in {best} consecutive chapters" + (" (data charts: expected in this genre)" if charts else "")})
    templates = {}
    for c in live:
        if c["type"] in ("diagram", "chart"): templates.setdefault(c.get("duplicate_group") or signature(c), []).append(c)
    for key, members in templates.items():
        if len(members) >= 3:
            charts = members[0]["type"] == "chart" and data_ok
            findings.append({"severity": level("low" if charts else "high" if members[0]["type"] == "diagram" else "medium"), "rule": "template_repeated",
                             "detail": f"template {key} used {len(members)} times: " + ", ".join(m["id"] for m in members)})
    visuals = [c for c in live if c["type"] != "table"]
    counts = [sum(1 for c in visuals if c["chapter"] == ch["id"]) for ch in chapters]
    types = {c["visual_type"].split(".")[0] + ":" + (c.get("structure") or {}).get("layout", "") for c in visuals}
    if len(chapters) >= 4 and sum(counts) >= 4 and all(n <= 1 for n in counts) and sum(counts) >= len(chapters) - 1 and len(types) == 1:
        findings.append({"severity": level("high"), "rule": "one_identical_visual_per_chapter",
                         "detail": f"every chapter carries at most one visual, all {next(iter(types))}: a quota, not an editorial choice"})
    return findings


def density(cands, chapters, profile, planned_chars):
    """Accepted visuals against the profile's visuals_per_10k (a health check of the plan, never a quota)."""
    if not profile: return []
    rng = profile["devices"]["visuals_per_10k"]
    chars = planned_chars or sum(int(c.get("target_characters") or 0) for c in chapters)
    if not chars: return []
    accepted = sum(1 for c in cands if c["decision"] == "accepted" and c["type"] in ("diagram", "chart", "table", "image", "screenshot"))
    rate = accepted * 10000 / chars
    rejected = sum(1 for c in cands if c["decision"] == "rejected")
    if rate < rng["min"]:
        return [{"severity": "medium", "rule": "visual_opportunities_insufficient",
                 "detail": f"{accepted} accepted visuals = {rate:.2f} per 10,000 characters, below the profile minimum {rng['min']} ({rejected} rejected). "
                           "Revisit the editorial plan and section structure for comparisons, processes, quantities and chronologies the text "
                           "already contains; do not add figures to reach the number. If the book genuinely has none, waive this with a reason.",
                 "accepted_per_10k": round(rate, 2), "profile_min": rng["min"]}]
    if rate > rng["max"]:
        return [{"severity": "medium", "rule": "visual_overload", "detail": f"{rate:.2f} visuals per 10,000 characters, above the profile maximum {rng['max']}",
                 "accepted_per_10k": round(rate, 2), "profile_max": rng["max"]}]
    return [{"severity": "info", "rule": "visual_density_ok", "detail": f"{rate:.2f} accepted visuals per 10,000 characters (profile {rng['min']}–{rng['max']})"}]


# ---------------------------------------------------------------- job integration

def run(outline=None, write=True):
    """Review plan/assets-plan.yaml for this job and write reports/visual-review.yaml."""
    import assets as asset_module
    from planning import load_outline
    import publication_profile
    chapters = outline if outline is not None else load_outline()
    profile = publication_profile.load_resolved()
    try:
        import publication_architecture
        profile = publication_architecture.scaled_profile(profile)
    except Exception: pass
    result = review(asset_module.assets(), chapters, profile)
    if write:
        REPORT.parent.mkdir(exist_ok=True)
        write_yaml(REPORT, result, "Generated by BookOrder: decisions on plan/assets-plan.yaml candidates. Change the plan, not this file.")
    return result


def completeness(asset):
    """Fields a visual candidate must carry before it can be judged (plan errors, not rejections)."""
    if asset.get("type") not in VISUAL_TYPES or asset.get("type") == "equation" or asset.get("decision") == "rejected": return []
    missing = []
    claim = asset.get("improvement_claim")
    if not isinstance(claim, dict) or not as_list(claim.get("kinds")): missing.append("improvement_claim.kinds")
    if not (isinstance(claim, dict) and claim.get("statement")) and not asset.get("purpose"): missing.append("improvement_claim.statement")
    shape = asset.get("information_shape")
    if not (isinstance(shape, dict) and shape.get("kind")) and asset.get("type") != "screenshot": missing.append("information_shape.kind")
    if asset.get("type") in ("diagram", "chart", "table") and not asset.get("factual_basis"): missing.append("factual_basis")
    if asset.get("decision") not in (None, "", "pending"): missing.append("decision may only be pending or rejected (BookOrder decides acceptance)")
    return missing


def decisions(result=None):
    """Asset id -> accepted | rejected | pending (None when no plan exists yet)."""
    try: result = result or run(write=False)
    except Exception: return None
    return {c["id"]: c["decision"] for c in result["candidates"]}

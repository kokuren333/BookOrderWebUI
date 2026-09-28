"""Whole-book integration checks, audit ledger, targeted rewrite tracking and visual pacing."""
import hashlib
import json
import re
import unicodedata

from common import ROOT, read_project, yaml_data, write_json, write_yaml, as_list, walk, plain, bibliography_keys
import research
import sources as registry

LEDGER = ROOT / "reports/audit-ledger.json"
REPORT = ROOT / "reports/audit-report.yaml"
AUDIT_DIR = ROOT / "plan/audit"
SEVERITIES = ("high", "medium", "low")
AGENT_TYPES = ("factual-inconsistency", "unsupported-claim", "source-mismatch", "contradiction", "terminology-drift",
               "inconsistent-definition", "repetition", "duplicated-example", "dependency-error", "missing-transition",
               "narrative", "chapter-balance", "figure", "table", "equation", "cross-reference", "bibliography", "design", "layout-pacing", "visual-plan", "other")
CALLOUTS = {"note", "tip", "warning", "definition", "key-point", "example", "exercise", "summary", "checklist", "sidebar", "pull-quote"}
HARD_CITATION = re.compile(r"(?<![\w\]])\[(?:\d{1,3})(?:\s*[,–-]\s*\d{1,3})*\](?!\()")
NUMERIC_FACT = re.compile(r"\d[\d,.]*\s*(?:%|％|percent|倍|億|万|million|billion)|(?:19|20)\d{2}\s*年")


def normalize(text):
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[\s\W_]+", "", text)


def iter_blocks(record):
    """Top-level blocks with their chapter and nearest section."""
    section = record["id"]
    for block in record["ast"]["blocks"]:
        if block["t"] == "Header": section = block["c"][1][0] or section
        yield section, block


def issue(kind, severity, chapter, detail, section=None, action="rewrite", source="deterministic", evidence=None):
    return {"type": kind, "severity": severity, "chapter": chapter, "section": section, "detail": detail, "action": action,
            "source": source, "evidence": evidence}


# ---------------------------------------------------------------- deterministic checks

def terminology_issues(records, chapters):
    issues = []
    glossary_path = ROOT / "source/metadata/glossary.yaml"
    terms = as_list(yaml_data(glossary_path).get("terms")) if glossary_path.is_file() else []
    bible = yaml_data(ROOT / "plan/book-bible.yaml") if (ROOT / "plan/book-bible.yaml").is_file() else {}
    for item in as_list((bible.get("terminology") or {}).get("preferred_terms")):
        if isinstance(item, dict): terms.append(item)
    for term in terms:
        if not isinstance(term, dict): continue
        preferred = term.get("term") or term.get("preferred")
        for variant in as_list(term.get("forbidden")) + as_list(term.get("avoid")):
            variant = str(variant)
            if len(variant) < 2: continue
            for chapter in chapters:
                record = records.get(chapter["id"])
                if record and variant.lower() in record["prose"].lower():
                    issues.append(issue("terminology-drift", "medium", chapter["id"], f"Use '{preferred}' instead of '{variant}'", evidence=variant))
    return issues


def concept_order_issues(records, chapters):
    issues = []
    concept_map = research.load_optional(research.synthesis_path("concept-map")) or {}
    concepts = {c.get("id"): c for c in as_list(concept_map.get("concepts")) if isinstance(c, dict)}
    order = [c["id"] for c in chapters]
    for position, chapter in enumerate(chapters):
        for concept_id in chapter["introduces"]:
            concept = concepts.get(concept_id)
            if not concept: continue
            names = [str(concept.get("term") or "")] + [str(x) for x in as_list(concept.get("aliases"))]
            names = [n for n in names if len(n) >= 3]
            for earlier in order[:position]:
                record = records.get(earlier)
                later_chapter = next(c for c in chapters if c["id"] == earlier)
                if concept_id in later_chapter["assumes"] or concept_id in later_chapter["develops"]: continue
                if record and any(n.lower() in record["prose"].lower() for n in names):
                    issues.append(issue("dependency-error", "medium", earlier,
                                        f"Concept '{names[0]}' is used before {chapter['id']} introduces it; add a forward reference or move the definition",
                                        action="rewrite", evidence=concept_id))
    return issues


def duplicate_issues(records):
    issues = []; paragraphs = {}; sentences = {}
    for record in records.values():
        if not record: continue
        for section, block in iter_blocks(record):
            if block["t"] != "Para": continue
            text = plain(block["c"]); key = normalize(text)
            if len(key) >= 80: paragraphs.setdefault(key, []).append((record["id"], section, text[:80]))
            for sentence in re.split(r"(?<=[。．.!?！？])\s*", text):
                skey = normalize(sentence)
                if len(skey) >= 40: sentences.setdefault(skey, []).append((record["id"], section, sentence[:80]))
    reported = set()
    for key, places in paragraphs.items():
        if len(places) > 1:
            for chapter, section, excerpt in places[1:]:
                issues.append(issue("repetition", "high", chapter, f"Paragraph duplicates {places[0][0]}/{places[0][1]}", section, evidence=excerpt))
                reported.add((chapter, section))
    for key, places in sentences.items():
        chapters_seen = {p[0] for p in places}
        if len(chapters_seen) > 1:
            for chapter, section, excerpt in places[1:]:
                if (chapter, section) not in reported and chapter != places[0][0]:
                    issues.append(issue("repetition", "medium", chapter, f"Sentence repeated from {places[0][0]}", section, evidence=excerpt))
    return issues


def reference_issues(records, chapters):
    issues = []
    anchors = {a for r in records.values() if r for a in r["anchors"]}
    anchors |= {c["id"] for c in chapters}
    for record in records.values():
        if not record: continue
        for ref in record["refs"]:
            if ref["target"] not in anchors:
                issues.append(issue("cross-reference", "high", record["id"], f"Broken cross-reference {ref['key']}", ref["section"], evidence=ref["key"]))
    for chapter in chapters:
        record = records.get(chapter["id"])
        if not record: continue
        targets = {r["target"] for r in record["refs"]}
        for later in chapter["hands_off_to"]:
            later_record = records.get(later)
            later_anchors = set(later_record["anchors"]) if later_record else {later}
            if not targets & (later_anchors | {later}):
                issues.append(issue("missing-transition", "low", chapter["id"], f"No explicit hand-off reference to {later} (@ch:{later[3:]})", action="rewrite"))
    return issues


def balance_issues(contracts):
    issues = []
    for contract in contracts:
        if contract["status"] != "complete":
            for reason in contract["reasons"]:
                issues.append(issue("chapter-balance" if reason["type"] == "length" else "contract", "high", contract["id"], reason["detail"], action="expand" if reason["type"] == "length" else "rewrite"))
        elif contract["target_characters"] and contract["actual_characters"] > 1.8 * contract["target_characters"]:
            issues.append(issue("chapter-balance", "medium", contract["id"], f"{contract['actual_characters']} characters is far above the {contract['target_characters']} budget; tighten or rebalance"))
    return issues


def citation_issues(records, project):
    issues = []
    index = registry.load_index(); known = registry.by_id(index)
    try: keys = set(bibliography_keys())
    except Exception as exc: keys = set(); issues.append(issue("bibliography", "high", None, f"Bibliography cannot be read: {exc}"))
    for record in records.values():
        if not record: continue
        for cite in record["cites"]:
            key = cite["key"]
            if key not in keys and key not in known:
                issues.append(issue("source-mismatch", "high", record["id"], f"Unknown citation key {key}", cite["section"], evidence=key))
            elif key in known and known[key]["ingest_status"] not in registry.USABLE:
                issues.append(issue("source-mismatch", "high", record["id"], f"{key} is {known[key]['ingest_status']}; it cannot support a claim", cite["section"], evidence=key))
            elif key in known and key not in keys:
                issues.append(issue("bibliography", "high", record["id"], f"{key} is missing from the generated bibliography; rerun reference assignment", cite["section"]))
        for section, block in iter_blocks(record):
            if block["t"] in ("Para", "Plain"):
                text = plain(block["c"])
                if HARD_CITATION.search(text):
                    issues.append(issue("bibliography", "high", record["id"], "Hard-coded visible citation number; use [cite:src-XXXX]", section, evidence=HARD_CITATION.search(text).group(0)))
                has_cite = any(n["t"] == "Cite" for n in walk(block["c"]))
                if len(NUMERIC_FACT.findall(text)) >= 2 and not has_cite:
                    issues.append(issue("unsupported-claim", "low", record["id"], "Paragraph states several figures/dates without a citation; verify support", section, action="verify", evidence=text[:80]))
    return issues


def asset_issues(records, chapters):
    import assets as asset_module
    issues = []
    if asset_module.load_plan() is not None:
        for error in asset_module.check_generation(chapters, {r["path"]: r for r in records.values() if r}):
            issues.append(issue("figure", "high", None, error, action="generate"))
    for chapter, identifier in asset_module.unplanned({r["path"]: r for r in records.values() if r}):
        issues.append(issue("figure", "medium", chapter, f"{identifier} is not in plan/assets-plan.yaml; plan or remove it", action="plan"))
    diagrams = {}
    for path in sorted((ROOT / "source/assets/diagrams").glob("*.yaml")):
        diagrams.setdefault(hashlib.sha256(normalize(path.read_text(encoding="utf-8").split("title", 1)[-1]).encode()).hexdigest(), []).append(path.name)
    for names in diagrams.values():
        if len(names) > 1: issues.append(issue("figure", "medium", None, "Near-identical diagrams: " + ", ".join(names), action="rewrite"))
    issues += legibility_issues(records) + visual_plan_issues()
    for record in records.values():
        if not record: continue
        equations = [e for e in record["equations"] if e]
        referenced = {r["target"] for r in record["refs"]}
        for identifier in record["equations"]:
            if not identifier: issues.append(issue("equation", "medium", record["id"], "Equation without a stable #eq- ID"))
        for node in walk(record["ast"]["blocks"]):
            if node["t"] == "Figure" and not plain(node["c"][1][1]).strip():
                issues.append(issue("figure", "medium", record["id"], f"Figure {node['c'][0][0] or '(no id)'} has no caption"))
            if node["t"] == "Table":
                import crossref
                if not crossref._table_id(node): issues.append(issue("table", "low", record["id"], "Table without caption ID {#tbl-...}; it cannot be cross-referenced"))
    return issues


def visual_plan_issues():
    """Book-level findings of the visual review (reports/visual-review.yaml): monotony and density health."""
    import assets as asset_module
    if asset_module.load_plan() is None: return []
    try:
        import visual_review
        result = visual_review.run()
    except Exception as exc:
        return [issue("figure", "low", None, f"Visual review could not run: {exc}", action="verify")]
    return [issue("visual-plan", f["severity"], None, f["detail"], action="plan", evidence=f["rule"])
            for f in result["findings"] if f["severity"] in SEVERITIES]


def legibility_issues(records):
    """Figure text measured at its printed size (scripts/figure_check.py, reports/figure-check.json)."""
    try:
        from design import load_design
        import figure_check
        report = figure_check.check(load_design(), [r for r in records.values() if r])
    except Exception as exc:
        return [issue("figure", "low", None, f"Figure legibility could not be checked: {exc}", action="verify")]
    issues, minimum = [], report["tokens"]["min_label_pt"]
    for figure in report["figures"]:
        if figure["status"] == "fail":
            smallest = ", ".join(f"{b['text']!r} {b['pt']}pt" for b in figure["below_min"][:3])
            issues.append(issue("figure", "high", figure["chapter"], f"{figure['id']} prints text below {minimum}pt at its placed width "
                                f"{figure['placed_width_mm']} mm ({smallest}); redraw it at its printed size (skills/design/figures.md)", action="generate"))
        elif figure["status"] == "unverified" and figure.get("type") == "chart":
            issues.append(issue("figure", "medium", figure["chapter"], f"{figure['id']}: printed text size cannot be verified; "
                                "render the chart with scripts/chartkit.py (SVG, or PNG with its render record)", action="generate"))
    return issues


def pacing_issues(records):
    """Manuscript-based pacing hints (low). The authority is the page-based check in scripts/pacing.py."""
    issues = []
    for record in records.values():
        if not record: continue
        run = 0; tables = 0; components = 0; section = record["id"]
        for block in record["ast"]["blocks"]:
            kind = block["t"]
            if kind == "Header": section = block["c"][1][0]; run = 0
            if kind in ("Para", "Plain", "BlockQuote"):
                run += len(re.sub(r"\s+", "", plain(block["c"])))
                if run > 9000:
                    issues.append(issue("pacing", "low", record["id"], "Manuscript estimate: very long uninterrupted prose; see reports/pacing-report.json for the measured pages", section, action="layout")); run = 0
            elif kind in ("Figure", "Div", "Table", "CodeBlock", "BulletList", "OrderedList"): run = 0
            tables = tables + 1 if kind == "Table" else 0
            if tables == 3: issues.append(issue("pacing", "low", record["id"], "Three consecutive tables; add explanation between them", section, action="layout"))
            if kind == "Div" and set(block["c"][0][1]) & CALLOUTS: components += 1
        if components >= 3 and record["chars"] / components < 600:
            issues.append(issue("pacing", "low", record["id"], f"{components} callouts for {record['chars']} characters; keep ordinary prose dominant", action="layout"))
    return issues


def placeholder_issues(records):
    return [issue("other", "high", r["id"], "Placeholder/unfinished text remains") for r in records.values() if r and r["placeholders"]]


def design_issues():
    try:
        from design import load_design
        load_design(); return []
    except Exception as exc:
        return [issue("design", "high", None, f"Design Spec invalid: {exc}", action="design")]


def coverage_issues(cov):
    if not cov["required"]: return []
    return [issue("coverage", "high", None, f"Relevant supplied source {identifier} is not reflected in the manuscript; cite it where it supports the text or re-classify it in its note with a reason", action="rewrite", evidence=identifier)
            for identifier in cov["orphan_supplied_sources"]]


def integration_checks(records, chapters, contracts):
    return (terminology_issues(records, chapters) + concept_order_issues(records, chapters) + duplicate_issues(records)
            + reference_issues(records, chapters) + balance_issues(contracts) + placeholder_issues(records))


def paragraph_length_issues(records, chapters, scale):
    maximum = scale.get("paragraph_chars_max")
    if not maximum: return []
    from planning import paragraph_statistics
    found = []
    for chapter in chapters:
        record = records.get(chapter["id"])
        if not record: continue
        stats = paragraph_statistics(record, maximum)
        if stats["high"]:
            severity = "high"
        elif stats["medium"]:
            severity = "medium"
        else:
            continue
        found.append(issue("paragraph-length", severity, chapter["id"],
            f"paragraphs over {maximum} chars: max {stats['max_paragraph_chars']}, median {stats['median_paragraph_chars']}, "
            f"p90 {stats['p90_paragraph_chars']}; {stats['violation_count']}/{stats['paragraph_count']} "
            f"({stats['violation_ratio']:.1%}) exceed the profile limit", evidence=stats))
    return found


def audit_checks(records, chapters, contracts, cov, project=None, scale=None):
    project = project or read_project()
    return (integration_checks(records, chapters, contracts) + citation_issues(records, project) + asset_issues(records, chapters)
            + coverage_issues(cov) + design_issues() + pacing_issues(records)
            + paragraph_length_issues(records, chapters, scale or {}))


# ---------------------------------------------------------------- agent reviews

def agent_issues(path, label):
    if not path.is_file(): return []
    data = yaml_data(path); found = []
    for number, item in enumerate(as_list(data.get("issues")) + as_list(data.get("new_issues")), 1):
        if not isinstance(item, dict): continue
        severity = item.get("severity") if item.get("severity") in SEVERITIES else "medium"
        found.append(issue(item.get("type") if item.get("type") in AGENT_TYPES else "other", severity, item.get("chapter") or data.get("chapter"),
                           str(item.get("description") or item.get("detail") or ""), item.get("section"), item.get("action") or "rewrite",
                           source=f"agent:{label}", evidence=item.get("evidence")))
    return found


def check_review_file(path, required_chapters, key="reviewed_chapters"):
    if not path.is_file(): return [f"Missing {path.relative_to(ROOT).as_posix()}"]
    data = yaml_data(path); reviewed = set(as_list(data.get(key)))
    if data.get("chapter") and data.get("reviewed") in (True, "true"): reviewed.add(data.get("chapter"))
    missing = [c for c in required_chapters if c not in reviewed]
    errors = [f"{path.relative_to(ROOT).as_posix()}: not reviewed: {', '.join(missing)}"] if missing else []
    for item in as_list(data.get("issues")) + as_list(data.get("new_issues")):
        if not isinstance(item, dict) or not research.nonempty(str(item.get("description") or item.get("detail") or ""), 10):
            errors.append(f"{path.relative_to(ROOT).as_posix()}: every issue needs a description")
    return errors


# ---------------------------------------------------------------- ledger

def issue_key(item):
    basis = "|".join(str(item.get(k) or "") for k in ("source", "type", "chapter", "section", "detail", "evidence"))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def load_ledger():
    if LEDGER.is_file(): return json.loads(LEDGER.read_text(encoding="utf-8"))
    return {"next": 1, "issues": {}, "runs": []}


def update_ledger(found, scope, fingerprint):
    """Merge a run into the ledger. Deterministic issues auto-resolve when no longer detected; agent issues stay
    open until resolved with a note. IDs are stable per issue key."""
    ledger = load_ledger(); now = registry.now(); seen = set()
    for item in found:
        key = issue_key(item); seen.add(key)
        entry = ledger["issues"].get(key)
        if not entry:
            entry = dict(item, id=f"audit-{ledger['next']:03d}", status="open", first_seen=now, history=[],
                         scope=scope if item["source"] == "deterministic" else "agent")
            ledger["next"] += 1; ledger["issues"][key] = entry
        elif entry["status"] == "resolved" and item["source"] == "deterministic":
            entry["status"] = "open"; entry["history"].append({"at": now, "event": "reopened (detected again)"})
        entry["last_seen"] = now
    for key, entry in ledger["issues"].items():
        # Layout findings come from the typeset pages; only a layout run can resolve them.
        covered = entry.get("scope") == scope or (scope == "audit" and entry.get("scope") != "layout")
        if entry["source"] == "deterministic" and entry["status"] == "open" and key not in seen and covered:
            entry["status"] = "resolved"; entry["history"].append({"at": now, "event": "no longer detected"})
    ledger["runs"].append({"at": now, "scope": scope, "fingerprint": fingerprint, "detected": len(found)})
    write_json(LEDGER, ledger); render_report(ledger)
    return ledger


def resolve(identifier, note, wontfix=False):
    ledger = load_ledger()
    entry = next((e for e in ledger["issues"].values() if e["id"] == identifier), None)
    if not entry: raise ValueError(f"Unknown audit issue {identifier}")
    if not note or len(note.strip()) < 10: raise ValueError("Describe the fix (or the wontfix reason) in --note")
    if wontfix and entry["severity"] == "high": raise ValueError("High-severity issues must be fixed, not waived")
    if entry["source"] == "deterministic" and not wontfix:
        raise ValueError("Deterministic issues resolve automatically when the re-audit no longer detects them; fix the text and run bookorder goal")
    entry["status"] = "wontfix" if wontfix else "resolved"
    entry["history"].append({"at": registry.now(), "event": entry["status"], "note": note})
    write_json(LEDGER, ledger); render_report(ledger)
    return entry


def open_issues(ledger=None, severities=("high", "medium")):
    ledger = ledger or load_ledger()
    return [e for e in ledger["issues"].values() if e["status"] == "open" and e["severity"] in severities]


def render_report(ledger=None):
    ledger = ledger or load_ledger()
    ordered = sorted(ledger["issues"].values(), key=lambda e: (e["status"] != "open", SEVERITIES.index(e["severity"]), e["id"]))
    summary = {"open": {s: sum(1 for e in ordered if e["status"] == "open" and e["severity"] == s) for s in SEVERITIES},
               "resolved": sum(1 for e in ordered if e["status"] == "resolved"), "wontfix": sum(1 for e in ordered if e["status"] == "wontfix"),
               "runs": len(ledger["runs"]), "last_run": ledger["runs"][-1] if ledger["runs"] else None}
    issues = [{k: e.get(k) for k in ("id", "severity", "status", "type", "chapter", "section", "detail", "action", "source", "evidence")} for e in ordered]
    write_yaml(REPORT, {"summary": summary, "issues": issues}, "Generated audit report. Resolve agent issues with `bookorder audit resolve <id> --note`.")
    return summary

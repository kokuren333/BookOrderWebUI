"""Citation Manager + Bibliography Builder: how the text cites is separate from how the back matter lists.

project.json `citations` (all optional; the WebUI writes them for new jobs):

    in_text_citation_style   numeric | author-year | note          (legacy key: style)
    footnote_style           full | short | numbered_reference     (note only: what a footnote contains)
    bibliography_style       standard | author_date                (how one entry is formatted)
    bibliography_numbering   numbered | unnumbered                  ([1] … in the back matter)
    numbering_scope          per_group | continuous
    bibliography_sort        citation_order | author | title
    bibliography_grouping    {cited, background, visual, design: bool}   separate lists, each can be switched off
    citation_source_roles    roles whose sources may be cited in the text (default: evidence, redraw_source)
    reference_source_roles   roles listed under 参考資料 when consulted but not cited (default: background, evidence,
                             structure_reference)

Groups: 引用文献 (sources cited in the text), 参考資料 (consulted, not cited: background reading, experience articles),
図表・画像出典 (sources of figures, redraw sources, uploaded images), デザイン参考資料 (layout/style/visual references;
off by default). A source appears in one group only.

A project without any of the new keys keeps the legacy behaviour exactly (one CSL for text and list, citeproc's own
bibliography). Otherwise citeproc renders only the in-text form (suppress-bibliography) and this module builds the
lists: entries are formatted by a bibliography-only CSL, numbered and grouped here, and written as `#refs` with one
sub-heading per group. With numeric in-text citations the cited list is always in citation order and numbered, so
the numbers in the text and in the list agree. reports/bibliography.json records what was built.
"""
import copy
import json

from common import ROOT, as_list, bibliography_files, run, tool, walk, yaml_data

VOCAB = json.loads((ROOT / "schemas/publication-architecture.json").read_text(encoding="utf-8"))
C = VOCAB["citations"]
NEW_KEYS = ("in_text_citation_style", "footnote_style", "bibliography_style", "bibliography_numbering", "numbering_scope",
            "bibliography_sort", "bibliography_grouping", "citation_source_roles", "reference_source_roles")
IN_TEXT_CSL = {"numeric": "templates/csl/numeric.csl", "author-year": None, "note": "templates/csl/note.csl"}
FOOTNOTE_CSL = {"full": "templates/csl/note.csl", "short": "templates/csl/note-short.csl", "numbered_reference": "templates/csl/numeric.csl"}
GROUPS = tuple(C["groups"])
REPORT = ROOT / "reports/bibliography.json"


def policy(project):
    """Resolved citation/bibliography policy (a dict). `builder`: legacy (single CSL, old output) or grouped."""
    c = project.get("citations") if isinstance(project.get("citations"), dict) else {}
    legacy = not any(k in c for k in NEW_KEYS)
    in_text = str(c.get("in_text_citation_style") or c.get("style") or "numeric")
    if in_text not in C["in_text_styles"]: in_text = "numeric"
    footnote = str(c.get("footnote_style") or "full")
    if footnote not in C["footnote_styles"]: footnote = "full"
    style = str(c.get("bibliography_style") or ("author_date" if in_text == "author-year" else "standard"))
    if style not in C["bibliography_styles"]: style = "standard"
    numbering = str(c.get("bibliography_numbering") or "numbered")
    scope = str(c.get("numbering_scope") or "per_group")
    sort = str(c.get("bibliography_sort") or ("author" if in_text == "author-year" or (in_text == "note" and footnote != "numbered_reference") else "citation_order"))
    raw_groups = c.get("bibliography_grouping") if isinstance(c.get("bibliography_grouping"), dict) else {}
    groups = {g: bool(raw_groups[g]) if isinstance(raw_groups.get(g), bool) else str(raw_groups.get(g, "")).lower() == "true" if g in raw_groups else C["groups"][g]["default"] for g in GROUPS}
    adjustments = []
    cited_numbering = numbering
    if in_text == "numeric" or (in_text == "note" and footnote == "numbered_reference"):
        if sort != "citation_order": adjustments.append("cited list kept in citation order so the numbers in the text match the list")
        if numbering != "numbered": adjustments.append("cited list numbered because the text cites by number"); cited_numbering = "numbered"
        # The text shows bare numbers: a second list restarting at [1] would make 「[1]」 ambiguous. Numbers run on.
        if scope == "per_group" and numbering == "numbered" and any(groups.get(g) for g in ("background", "visual", "design")):
            scope = "continuous"; adjustments.append("numbering continues across lists so no other list reuses a number the text cites")
    if not groups["cited"] and in_text != "note":
        groups["cited"] = True; adjustments.append("引用文献 kept: the text cites sources, so the cited list cannot be switched off")
    csl = FOOTNOTE_CSL[footnote] if in_text == "note" else IN_TEXT_CSL[in_text]
    result = {"builder": "legacy" if legacy else "grouped", "in_text_citation_style": in_text, "footnote_style": footnote if in_text == "note" else None,
              "in_text_csl": csl, "bibliography_style": style, "bibliography_csl": C["bibliography_styles"][style],
              "bibliography_numbering": numbering, "cited_numbering": cited_numbering, "numbering_scope": scope, "bibliography_sort": sort,
              "bibliography_grouping": groups,
              "citation_source_roles": [str(r) for r in as_list(c.get("citation_source_roles"))] or list(VOCAB["citable_roles"]),
              "reference_source_roles": [str(r) for r in as_list(c.get("reference_source_roles"))] or ["background", "evidence", "structure_reference"],
              "adjustments": adjustments}
    in_label = {"numeric": "numeric [n]", "author-year": "author-year (Author, Year)", "note": f"footnotes ({footnote})"}[in_text]
    result["summary"] = ("legacy: one CSL style for text and bibliography" if legacy else
                         f"in text: {in_label}; bibliography: {style} entries, {numbering} ({scope}), sorted by {sort}; groups: "
                         + ", ".join(g for g, on in groups.items() if on))
    return result


# ---------------------------------------------------------------- building

def cited_order(doc):
    order = []
    for node in walk(doc["blocks"]):
        if node["t"] == "Cite":
            for citation in node["c"][0]:
                if citation["citationId"] not in order: order.append(citation["citationId"])
    return order


def format_entries(ids, style_csl, language=None):
    """id -> list of Pandoc blocks (the formatted entry). citeproc does all entry formatting with the bibliography-only
    CSL in the book's locale; one call per list, so year suffixes (Kaplan 2020a/b) are assigned among the same works
    as in the text."""
    files = bibliography_files()
    if not ids or not files: return {}
    source = "---\nnocite: |\n  " + ", ".join("@" + i for i in ids) + "\n---\n"
    args = [tool("pandoc"), "-f", "markdown", "-t", "json", "--citeproc", "--csl", str(ROOT / style_csl)] + (["-M", f"lang={language}"] if language else [])
    for path in files: args += ["--bibliography", str(path)]
    out = json.loads(run(args, source))
    entries = {}
    for node in walk(out["blocks"]):
        if node["t"] == "Div" and node["c"][0][0].startswith("ref-"):
            entries[node["c"][0][0][4:]] = node["c"][1]
    return entries


def _text(value):
    return {"t": "Str", "c": value}


def _plain_entry(text):
    return [{"t": "Para", "c": [_text(text)]}]


def _sort_key(sort, entry):
    record = entry.get("record") or {}
    if sort == "title": return str(record.get("title") or entry["id"]).lower()
    names = record.get("author") or []
    first = names[0] if names else {}
    return (str(first.get("family") or first.get("literal") or record.get("publisher") or record.get("title") or entry["id"])).lower()


def collect(project, cited, pol):
    """{group: [entry]} — each entry {id, kind: source|asset, record?, text?}. Pure: reads registry, notes, plans."""
    import research, source_roles, sources as registry
    index = registry.load_index(); notes = research.load_notes(); roles = source_roles.table(index, notes, write=False)
    records = {e["id"]: e for e in _references()}
    groups = {g: [] for g in GROUPS}; placed = set()
    for sid in cited:
        groups["cited"].append({"id": sid, "kind": "source", "record": records.get(sid)}); placed.add(sid)
    visual_ids = []
    plan_path = ROOT / "plan/assets-plan.yaml"
    plan = yaml_data(plan_path) if plan_path.is_file() else {}
    for asset in as_list(plan.get("assets")):
        if isinstance(asset, dict) and asset.get("decision", "accepted") != "rejected":
            visual_ids += [str(s) for s in as_list(asset.get("source_ids")) + as_list(asset.get("sources"))]
    for sid, entry in roles.items():
        if entry["role"] == "redraw_source" and entry["status"] in registry.USABLE: visual_ids.append(sid)
    for sid in dict.fromkeys(visual_ids):
        if sid in records and sid not in placed:
            groups["visual"].append({"id": sid, "kind": "source", "record": records.get(sid)}); placed.add(sid)
    decisions = {str(d.get("asset")): d for d in as_list(plan.get("uploaded_assets")) if isinstance(d, dict)}
    for asset in source_roles.uploaded_assets(project):
        decision = decisions.get(asset["id"], {})
        if asset["role"] in ("asset", "redraw_source") and decision.get("decision") in ("placed", "redrawn"):
            label = asset.get("label") or asset.get("original_name")
            credit = decision.get("credit") or asset.get("caption") or ""
            groups["visual"].append({"id": asset["id"], "kind": "asset", "text": f"{label}" + (f" — {credit}" if credit and credit != label else "") + "（提供資料）"})
        elif asset["role"] in ("layout_reference", "style_reference", "visual_reference"):
            groups["design"].append({"id": asset["id"], "kind": "asset", "text": f"{asset.get('label') or asset.get('original_name')}（{source_roles.ROLES[asset['role']]['label']}）"})
    assigned = _assigned_sources()
    for s in index["sources"]:
        sid = s["id"]
        if sid in placed or s["ingest_status"] not in registry.USABLE or sid not in records: continue
        note = notes.get(sid, {}); entry = roles.get(sid, {})
        if note.get("relevance") in ("irrelevant", "duplicate"): continue
        if entry.get("role") not in pol["reference_source_roles"]: continue
        if entry.get("role") == "background" or sid in assigned:
            groups["background"].append({"id": sid, "kind": "source", "record": records.get(sid)}); placed.add(sid)
    return groups


def _references():
    path = ROOT / "source/references/references.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


def _assigned_sources():
    outline = ROOT / "source/metadata/outline.yaml"
    found = set()
    if outline.is_file():
        for chapter in as_list(yaml_data(outline).get("chapters")):
            if isinstance(chapter, dict):
                srcs = chapter.get("sources") or {}
                found |= {str(x) for x in (as_list(srcs.get("primary")) + as_list(srcs.get("supporting")) if isinstance(srcs, dict) else as_list(srcs))}
    return found


def build(doc, project, language="ja"):
    """Replace citeproc's list with the grouped, numbered back matter. `doc` is the citeproc output (suppress-bibliography)."""
    pol = policy(project)
    cited = cited_order(doc)
    groups = collect(project, cited, pol)
    formatted = {}
    for entries in groups.values():
        formatted.update(format_entries([e["id"] for e in entries if e["kind"] == "source"], pol["bibliography_csl"], language))
    japanese = str(language).lower().startswith("ja")
    blocks = []; report = {"policy": {k: v for k, v in pol.items() if k != "summary"}, "summary": pol["summary"], "cited_in_text": cited, "groups": []}
    number = 0
    for group in GROUPS:
        entries = groups[group]
        if not pol["bibliography_grouping"][group] or not entries: continue
        numbered = (pol["cited_numbering"] if group == "cited" else pol["bibliography_numbering"]) == "numbered"
        if group != "cited" or pol["bibliography_sort"] != "citation_order" and not (pol["in_text_citation_style"] == "numeric" or pol["footnote_style"] == "numbered_reference"):
            if pol["bibliography_sort"] != "citation_order": entries = sorted(entries, key=lambda e: _sort_key(pol["bibliography_sort"], e))
        if pol["numbering_scope"] == "per_group": number = 0
        title = C["groups"][group]["ja" if japanese else "en"]
        blocks.append({"t": "Header", "c": [3, [f"sec-references-{group}", ["unnumbered"], []], [_text(title)]]})
        listed = []
        for entry in entries:
            content = copy.deepcopy(formatted.get(entry["id"])) if entry["kind"] == "source" else _plain_entry(entry["text"])
            if not content: content = _plain_entry((entry.get("record") or {}).get("title") or entry["id"])
            if numbered:
                number += 1
                first = content[0]
                if first["t"] in ("Para", "Plain"): first["c"] = [_text(f"[{number}]"), {"t": "Space"}] + first["c"]
            anchor = f"ref-{entry['id']}"
            blocks.append({"t": "Div", "c": [[anchor, ["csl-entry", f"bib-{group}"], []], content]})
            listed.append({"id": entry["id"], "number": number if numbered else None, "kind": entry["kind"]})
        report["groups"].append({"group": group, "title": title, "numbered": numbered, "entries": listed})
    _write_report(report)
    if not blocks: return doc
    heading = "参考文献" if japanese else "References"
    doc["blocks"] = [b for b in doc["blocks"] if not (b["t"] == "Div" and b["c"][0][0] == "refs")]
    if not any(b["t"] == "Header" and b["c"][1][0] == "sec-references" for b in doc["blocks"]):
        doc["blocks"].append({"t": "Header", "c": [2, ["sec-references", ["unnumbered"], []], [_text(heading)]]})
    doc["blocks"].append({"t": "Div", "c": [["refs", ["references", "bookorder-bibliography"], []], blocks]})
    return doc


def wrap_numbered_footnotes(doc):
    """footnote_style numbered_reference: citeproc rendered [n]; put each citation into a footnote."""
    def visit(value):
        if isinstance(value, list):
            out = []
            for item in value:
                if isinstance(item, dict) and item.get("t") == "Cite":
                    out.append({"t": "Note", "c": [{"t": "Para", "c": [item]}]})
                else:
                    visit(item); out.append(item)
            value[:] = out
        elif isinstance(value, dict):
            if value.get("t") == "Note": return
            for child in value.values():
                if isinstance(child, (list, dict)): visit(child)
    visit(doc["blocks"])
    return doc


def _write_report(report):
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_report():
    return json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.is_file() else None


def check_report(project, report=None):
    """QA: the built back matter matches the policy (used by the publication architecture QA)."""
    pol = policy(project); report = report if report is not None else load_report()
    if pol["builder"] == "legacy": return []
    if report is None: return [{"rule": "bibliography_not_built", "severity": "medium", "detail": "reports/bibliography.json missing: build the book"}]
    problems = []
    seen = {}
    for group in report["groups"]:
        if not pol["bibliography_grouping"].get(group["group"]): problems.append({"rule": "bibliography_group_disabled", "severity": "high", "detail": f"{group['group']} list was built although switched off"})
        want = (pol["cited_numbering"] if group["group"] == "cited" else pol["bibliography_numbering"]) == "numbered"
        if group["numbered"] != want: problems.append({"rule": "bibliography_numbering", "severity": "high", "detail": f"{group['title']}: numbering differs from the policy"})
        for e in group["entries"]:
            if e["id"] in seen: problems.append({"rule": "bibliography_duplicate", "severity": "high", "detail": f"{e['id']} is listed in {seen[e['id']]} and {group['group']}"})
            seen[e["id"]] = group["group"]
    cited = [e["id"] for g in report["groups"] if g["group"] == "cited" for e in g["entries"]]
    if pol["bibliography_grouping"]["cited"] and set(cited) != set(report["cited_in_text"]):
        problems.append({"rule": "bibliography_cited_mismatch", "severity": "high", "detail": "引用文献 differs from the sources cited in the text"})
    if pol["in_text_citation_style"] == "numeric" and cited != report["cited_in_text"]:
        problems.append({"rule": "bibliography_order", "severity": "high", "detail": "numeric citations: 引用文献 must follow citation order"})
    import source_roles
    roles = source_roles.table(write=False)
    for g in report["groups"]:
        if g["group"] == "background":
            for e in g["entries"]:
                if e["id"] in report["cited_in_text"]: problems.append({"rule": "background_contains_cited", "severity": "high", "detail": f"{e['id']} is cited but listed as 参考資料"})
    for sid in report["cited_in_text"]:
        entry = roles.get(sid)
        if entry and entry["role"] not in pol["citation_source_roles"] and not (entry["citation_allowed"] and entry["citation_allowed_origin"] == "user"):
            problems.append({"rule": "cited_non_citable_role", "severity": "high", "detail": f"{sid} ({entry['role']}) is cited in the text; its role is not a citation source"})
    return problems

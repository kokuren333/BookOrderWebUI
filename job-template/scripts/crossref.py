"""Stable semantic cross-references and numbering for chapters, sections, figures, tables and equations.

Canonical Markdown writes @ch:intro, @sec:method, @fig:model, @tbl:results or @eq:loss (Pandoc parses these
as citations). Numbers are computed from document order at render time, so inserting or reordering content
never requires editing references. Equations are fenced divs with a LaTeX display-math paragraph:

    ::: {.equation #eq-bayes}
    $$P(A \\mid B) = \\frac{P(B \\mid A)P(A)}{P(B)}$$
    :::
"""
import copy
from common import walk, plain

PREFIXES = {"ch": "ch", "sec": "sec", "fig": "fig", "tbl": "tbl", "eq": "eq"}
LABELS = {
    "ja": {"ch": "第{n}章", "sec": "{n}節", "fig": "図{n}", "tbl": "表{n}", "eq": "式({n})", "chapter_short": "第{n}章"},
    "en": {"ch": "Chapter {n}", "sec": "Section {n}", "fig": "Figure {n}", "tbl": "Table {n}", "eq": "Equation ({n})", "chapter_short": "Chapter {n}"},
}


def labels(lang):
    return LABELS.get((lang or "en").split("-")[0].lower(), LABELS["en"])


def target_id(key):
    """Map a citation key to a document ID, or None when it is a bibliography key."""
    if ":" in key:
        prefix, name = key.split(":", 1)
        if prefix in PREFIXES and name: return f"{prefix}-{name}"
        return None
    for prefix in PREFIXES:
        if key.startswith(prefix + "-") and len(key) > len(prefix) + 1: return key
    return None


def _str(text):
    return {"t": "Str", "c": text}


def _span(classes, text):
    return {"t": "Span", "c": [["", classes, []], [_str(text)]]}


def _caption_blocks(node):
    if node["t"] == "Figure": return node["c"][1][1]
    if node["t"] == "Table": return node["c"][1][1]
    return []


def _table_id(node):
    identifier = node["c"][0][0]
    if identifier: return identifier
    for inner in walk(node["c"][1]):
        if inner["t"] == "Span" and inner["c"][0][0].startswith("tbl-"): return inner["c"][0][0]
    return ""


def _prefix_caption(node, text):
    blocks = _caption_blocks(node)
    label = [_span(["caption-label"], text), _str(" ")]
    if blocks and blocks[0]["t"] in ("Plain", "Para"): blocks[0]["c"][:0] = label
    else: blocks.insert(0, {"t": "Plain", "c": label[:1]})


def number(doc, lang="ja"):
    """Number the combined book in place. Returns {id: {kind, number, label, chapter}}."""
    names = labels(lang); registry = {}
    chapter = 0; sections = [0, 0]; counters = {"fig": 0, "tbl": 0, "eq": 0}; chapter_id = None
    for node in list(walk(doc["blocks"])):
        kind = node.get("t")
        if kind == "Header":
            level, attr = node["c"][0], node["c"][1]
            identifier, classes = attr[0], attr[1]
            if "unnumbered" in classes:
                if identifier: registry[identifier] = {"kind": "sec", "number": "", "label": plain(node["c"][2]), "chapter": chapter_id}
                continue
            if level == 1:
                chapter += 1; sections = [0, 0]; counters = {k: 0 for k in counters}; chapter_id = identifier
                attr[2] = [pair for pair in attr[2] if pair[0] not in ("data-number", "data-chapter-label")]
                attr[2] += [["data-number", str(chapter)], ["data-chapter-label", names["chapter_short"].format(n=chapter)]]
                if identifier: registry[identifier] = {"kind": "ch", "number": str(chapter), "label": names["ch"].format(n=chapter), "chapter": identifier}
            elif level in (2, 3) and chapter:
                if level == 2: sections = [sections[0] + 1, 0]
                else: sections[1] += 1
                numbering = f"{chapter}.{sections[0]}" + (f".{sections[1]}" if level == 3 else "")
                node["c"][2][:0] = [_span(["section-number"], numbering), {"t": "Space"}]
                attr[2] = [pair for pair in attr[2] if pair[0] != "data-number"] + [["data-number", numbering]]
                if identifier: registry[identifier] = {"kind": "sec", "number": numbering, "label": names["sec"].format(n=numbering), "chapter": chapter_id}
        elif kind == "Figure":
            identifier = node["c"][0][0]
            counters["fig"] += 1; numbering = f"{chapter}.{counters['fig']}" if chapter else str(counters["fig"])
            text = names["fig"].format(n=numbering); _prefix_caption(node, text)
            if identifier: registry[identifier] = {"kind": "fig", "number": numbering, "label": text, "chapter": chapter_id}
        elif kind == "Table":
            identifier = _table_id(node)
            counters["tbl"] += 1; numbering = f"{chapter}.{counters['tbl']}" if chapter else str(counters["tbl"])
            text = names["tbl"].format(n=numbering); _prefix_caption(node, text)
            if identifier: registry[identifier] = {"kind": "tbl", "number": numbering, "label": text, "chapter": chapter_id}
        elif kind == "Div" and "equation" in node["c"][0][1]:
            identifier = node["c"][0][0]
            counters["eq"] += 1; numbering = f"{chapter}.{counters['eq']}" if chapter else str(counters["eq"])
            attr = node["c"][0]
            attr[2] = [pair for pair in attr[2] if pair[0] != "data-number"] + [["data-number", numbering]]
            if identifier: registry[identifier] = {"kind": "eq", "number": numbering, "label": names["eq"].format(n=numbering), "chapter": chapter_id}
    return registry


def resolve(doc, registry, errors=None):
    """Replace cross-reference citations by links with rendered labels. Unknown targets are reported."""
    errors = errors if errors is not None else []
    def inline_list(items):
        output = []
        for item in items:
            if isinstance(item, dict) and item.get("t") == "Cite":
                citations = item["c"][0]
                targets = [target_id(c["citationId"]) for c in citations]
                if targets and all(targets):
                    for index, (citation, identifier) in enumerate(zip(citations, targets)):
                        if index: output.append(_str(", "))
                        entry = registry.get(identifier)
                        if not entry:
                            errors.append(f"Broken cross-reference: @{citation['citationId']}")
                            output.append({"t": "Strong", "c": [_str("??" + citation["citationId"])]}); continue
                        suppress = citation.get("citationMode", {}).get("t") == "SuppressAuthor"
                        text = (f"({entry['number']})" if entry["kind"] == "eq" else entry["number"]) if suppress else entry["label"]
                        output.append({"t": "Link", "c": [["", ["cross-ref", "ref-" + entry["kind"]], []], [_str(text)], ["#" + identifier, ""]]})
                    continue
            output.append(transform(item))
        return output
    def transform(value):
        if isinstance(value, list):
            if value and all(isinstance(x, dict) and "t" in x for x in value): return inline_list(value)
            return [transform(x) for x in value]
        if isinstance(value, dict): return {key: transform(item) for key, item in value.items()}
        return value
    doc["blocks"] = transform(doc["blocks"])
    return errors


def crossref_keys(ast):
    """Cross-reference keys used in a chapter AST (for validation)."""
    found = []
    for node in walk(ast["blocks"]):
        if node["t"] == "Cite":
            for citation in node["c"][0]:
                identifier = target_id(citation["citationId"])
                if identifier: found.append((citation["citationId"], identifier))
    return found


def apply(doc, lang):
    registry = number(doc, lang)
    errors = resolve(doc, registry)
    return registry, errors

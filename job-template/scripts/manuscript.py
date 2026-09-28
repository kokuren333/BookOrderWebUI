"""Measurements over canonical chapter Markdown: size, headings, citations, cross-references, assets."""
import hashlib
import re
from pathlib import Path

from common import ROOT, parse_markdown, walk, plain, chapter_files
import crossref

PLACEHOLDER = re.compile(r"\b(?:TODO|FIXME|TBD|PLACEHOLDER|lorem ipsum)\b|ここに.*(?:記入|挿入)|未執筆|（?後で書く）?", re.I)
SKIP_BLOCKS = {"CodeBlock", "RawBlock"}
SKIP_INLINES = {"Code", "Math", "RawInline"}


def prose_text(value):
    """Reader-facing prose; code, raw markup and math are not counted as manuscript characters."""
    parts = []
    def visit(node):
        if isinstance(node, list):
            for item in node: visit(item)
            return
        if not isinstance(node, dict) or "t" not in node: return
        kind = node["t"]
        if kind in SKIP_BLOCKS or kind in SKIP_INLINES: return
        if kind == "Div" and "slot" in node["c"][0][1]: return  # a reserved device, not the chapter's prose
        if kind == "Str": parts.append(node["c"]); return
        if kind in ("Space", "SoftBreak", "LineBreak"): parts.append(" "); return
        if kind == "Cite": return  # rendered citation text is not authored prose
        if kind in ("Para", "Plain", "Header"): parts.append("\n")
        content = node.get("c")
        if isinstance(content, (list, dict)): visit(content if isinstance(content, list) else [content])
    visit(value)
    return "".join(parts)


def count_chars(text):
    return len(re.sub(r"\s+", "", text))


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def analyze_file(path):
    text = path.read_text(encoding="utf-8")
    ast = parse_markdown(text)
    blocks = ast["blocks"]
    headings = []; cites = []; refs = []; figures = []; tables = []; equations = []; images = []; components = []; slots = []
    section = None; chapter_id = None
    for node in walk(blocks):
        kind = node["t"]
        if kind == "Header":
            level, attr = node["c"][0], node["c"][1]
            headings.append({"level": level, "id": attr[0], "title": plain(node["c"][2]), "classes": attr[1]})
            if level == 1 and chapter_id is None: chapter_id = attr[0]
            section = attr[0]
        elif kind == "Cite":
            for citation in node["c"][0]:
                key = citation["citationId"]
                target = crossref.target_id(key)
                if target: refs.append({"key": key, "target": target, "section": section})
                else: cites.append({"key": key, "section": section})
        elif kind == "Figure" and node["c"][0][0]: figures.append(node["c"][0][0])
        elif kind == "Table":
            identifier = crossref._table_id(node)
            tables.append(identifier)
        elif kind == "Div":
            classes = node["c"][0][1]
            if "equation" in classes: equations.append(node["c"][0][0])
            elif "slot" in classes:
                slots.append({"id": node["c"][0][0], "kind": dict(node["c"][0][2]).get("kind", ""), "section": section, "text": plain(node["c"][1])})
            elif classes: components.append({"type": classes[0], "id": node["c"][0][0]})
        elif kind == "Image": images.append(node["c"][2][0])
        elif kind == "Link" and node["c"][2][0].startswith("#"):
            refs.append({"key": node["c"][2][0], "target": node["c"][2][0][1:], "section": section})
    prose = prose_text(blocks)
    anchors = {h["id"] for h in headings if h["id"]} | set(figures) | {t for t in tables if t} | {e for e in equations if e}
    for node in walk(blocks):
        if node["t"] in ("Div", "Span", "CodeBlock") and node["c"][0][0]: anchors.add(node["c"][0][0])
    return {"path": path.relative_to(ROOT).as_posix(), "id": chapter_id, "text": text, "sha256": sha(text), "ast": ast,
            "prose": prose, "chars": count_chars(prose), "headings": headings, "cites": cites, "refs": refs,
            "figures": figures, "tables": tables, "equations": equations, "images": images, "components": components, "slots": slots,
            "anchors": sorted(anchors), "placeholders": bool(PLACEHOLDER.search(text)),
            "h1_count": sum(1 for h in headings if h["level"] == 1),
            "starts_with_h1": bool(blocks) and blocks[0]["t"] == "Header" and blocks[0]["c"][0] == 1}


def analyze_all():
    return {record["path"]: record for record in (analyze_file(path) for path in chapter_files())}


def by_chapter(records, outline):
    """Map outline chapters to manuscript analyses by planned file path."""
    return {chapter["id"]: records.get(chapter["file"]) for chapter in outline}


def usage(records):
    result = {}
    for record in records.values():
        for cite in record["cites"]:
            result.setdefault(cite["key"], [])
            entry = {"chapter": record["id"], "section": cite["section"]}
            if entry not in result[cite["key"]]: result[cite["key"]].append(entry)
    return result


def fingerprint(records=None):
    """Manuscript fingerprint for audit freshness: chapters + canonical metadata + assets."""
    digest = hashlib.sha256()
    paths = list(chapter_files())
    for folder in ("source/metadata", "source/assets", "source/references"):
        paths += [p for p in (ROOT / folder).rglob("*") if p.is_file()]
    generated = {p.stem for p in (ROOT / "source/assets/diagrams").glob("*.yaml")}
    for path in sorted(set(paths)):
        relative = path.relative_to(ROOT).as_posix()
        if relative in ("source/metadata/sources.yaml", "source/metadata/figures.yaml", "source/references/references.json"): continue  # generated
        if relative.startswith("source/assets/figures/") and path.stem in generated and path.suffix in (".svg", ".png"): continue  # theme-dependent renders
        digest.update(path.relative_to(ROOT).as_posix().encode()); digest.update(path.read_bytes())
    return digest.hexdigest()

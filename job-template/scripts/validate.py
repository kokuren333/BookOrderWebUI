"""Validate canonical source and requested outputs. Nonzero on any structural error."""
import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit
import zipfile
from common import ROOT, read_project, chapters, yaml_data, walk, attr, local_path, output_paths, fingerprint, report, run, tool, combined, bibliography_files, bibliography_keys
import crossref


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__(); self.ids = []; self.links = []; self.assets = []
        self.feed(path.read_text(encoding="utf-8"))
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"): self.ids.append(values["id"])
        if tag == "a" and values.get("href"): self.links.append(values["href"])
        if tag in ("img", "script") and values.get("src"): self.assets.append(values["src"])
        if tag == "link" and values.get("href"): self.assets.append(values["href"])


def validate_html(directory, errors):
    pages = {p.resolve(): Page(p) for p in directory.rglob("*.html")}
    for path, page in pages.items():
        for identifier, count in Counter(page.ids).items():
            if count > 1: errors.append(f"Duplicate HTML ID {identifier}: {path.relative_to(ROOT)}")
        for url in page.links + page.assets:
            parts = urlsplit(url)
            if parts.scheme or parts.netloc: continue
            dest = (path.parent / unquote(parts.path)).resolve() if parts.path else path
            if not dest.is_file(): errors.append(f"Broken HTML link/asset: {path.relative_to(ROOT)} -> {url}"); continue
            if parts.fragment and dest in pages and unquote(parts.fragment) not in pages[dest].ids:
                errors.append(f"Broken HTML anchor: {path.relative_to(ROOT)} -> {url}")


def validate(source_only=False):
    errors = []; warnings = []; project = None
    try:
        project = read_project()
        from design import load_design
        from diagrams import outputs as diagram_outputs
        from book_ir import create_ir
        load_design()
        planned_diagrams = diagram_outputs()
        source_stage = source_only or not (ROOT / 'reports/build-report.json').exists()
        metadata = {}
        for name in ("outline", "sources", "glossary", "figures"):
            path = ROOT / f"source/metadata/{name}.yaml"
            if not path.is_file() or not path.read_text(encoding="utf-8").strip(): errors.append(f"Missing/empty {path.relative_to(ROOT)}")
            else: metadata[name] = yaml_data(path)
        bib = ROOT / "source/references/references.bib"
        if not bib.is_file() and not (ROOT / "source/references/references.json").is_file(): errors.append("Missing references.json / references.bib")
        if not (ROOT / "source/assets").is_dir(): errors.append("Missing source/assets")
        items = chapters()
        for _, ast in items: create_ir(ast)
        ids = []; citations = []; internal_links = []; chapter_ids = []
        for path, ast in items:
            text = path.read_text(encoding="utf-8")
            if not text.strip(): errors.append(f"Empty manuscript: {path.name}")
            if re.search(r"\b(?:TODO|FIXME|TBD|PLACEHOLDER|lorem ipsum)\b|ここに.*(?:記入|挿入)|未執筆", text, re.I): errors.append(f"Unfinished placeholder: {path.name}")
            heads = [b for b in ast["blocks"] if b["t"] == "Header" and b["c"][0] == 1]
            if len(heads) != 1 or not ast["blocks"] or ast["blocks"][0]["t"] != "Header" or ast["blocks"][0]["c"][0] != 1:
                errors.append(f"Chapter must begin with exactly one level-one heading: {path.name}")
            if heads: chapter_ids.append(heads[0]["c"][1][0])
            explicit_ids = set(re.findall(r"\{[^}\n]*#([^\s}]+)", text))
            for node in walk(ast["blocks"]):
                attributes = attr(node)
                if attributes and attributes[0]: ids.append(attributes[0])
                if node["t"] == "Header" and node["c"][1][0] not in explicit_ids:
                    errors.append(f"Heading needs explicit stable ID: {path.name}: {node['c'][1][0]}")
                if node["t"] == "Cite":
                    for item in node["c"][0]:
                        target = crossref.target_id(item["citationId"])
                        if target: internal_links.append(target)
                        else: citations.append(item["citationId"])
                if node["t"] in ("Image", "Link"):
                    url = node["c"][2][0]
                    if url.startswith("#"): internal_links.append(unquote(url[1:])); continue
                    local = local_path(url)
                    if local is not None and not local.is_file() and not (source_stage and local.relative_to(ROOT).as_posix() in planned_diagrams): errors.append(f"Missing local asset/link: {url} in {path.name}")
                    if node["t"] == "Image" and local is None: errors.append(f"Remote image must be saved locally with provenance: {url}")
                if node["t"] == "CodeBlock" and any(x in node["c"][0][1] for x in ("mermaid", "dot", "graphviz")):
                    errors.append(f"Unrendered diagram in {path.name}; compile it to a figure")
                if node["t"] in ("RawInline", "RawBlock"):
                    errors.append(f"Raw markup is not portable across all outputs: {path.name}; use Pandoc Markdown")
                if node["t"] == "Div" and "slot" in node["c"][0][1] and not source_stage:
                    errors.append(f"Unresolved slot #{node['c'][0][0]} ({dict(node['c'][0][2]).get('kind', '?')}) in {path.name}: produce the planned device or fall it back")
        for identifier, count in Counter(ids).items():
            if count > 1: errors.append(f"Duplicate stable ID: {identifier}")
        for identifier in internal_links:
            if identifier not in ids: errors.append(f"Broken cross-reference: #{identifier}")
        if bibliography_files() or citations:
            keys = bibliography_keys()
            for key, count in Counter(keys).items():
                if count > 1: errors.append(f"Duplicate bibliography key: {key}")
            for key in sorted(set(citations) - set(keys)): errors.append(f"Unresolved citation: {key}")
        plan = metadata.get("outline", {}).get("chapters", [])
        if not plan: errors.append("outline.yaml must contain planned chapters")
        else:
            if [chapter.get("id") for chapter in plan] != chapter_ids: errors.append("Outline order/IDs do not match manuscript chapters")
            planned_files = []
            for chapter in plan:
                for field in ("id", "title", "file", "purpose"):
                    if not str(chapter.get(field, "")).strip(): errors.append(f"Outline chapter missing {field}: {chapter.get('id')}")
                if not str(chapter.get("target_characters") or chapter.get("target_words") or "").strip(): errors.append(f"Outline chapter missing target_characters: {chapter.get('id')}")
                planned_files.append(chapter.get("file"))
            if planned_files != [p.relative_to(ROOT).as_posix() for p, _ in items]: errors.append("Outline file order does not match manuscript filenames")
        registry = metadata.get("sources", {}).get("sources", [])
        provided = project.get("input", {})
        for source in provided.get("sources", []):
            if not (ROOT / source["path"]).is_file(): errors.append(f"Missing provided source: {source['path']}")
            if not any(item.get("path") == source["path"] for item in registry): errors.append(f"Source not inventoried: {source['path']}")
        for url in provided.get("urls", []):
            if not any(item.get("url") == url for item in registry): errors.append(f"URL not inventoried: {url}")
        source_ids = [item.get("id") for item in registry]
        if any(not value for value in source_ids) or len(source_ids) != len(set(source_ids)): errors.append("Source registry has missing or duplicate IDs")
        for figure in metadata.get("figures", {}).get("figures", []):
            if not all(figure.get(key) for key in ("id", "chapter", "type", "path", "caption")): errors.append("Incomplete figure registry entry")
            elif not (ROOT / figure["path"]).is_file() and not (source_stage and figure['path'] in planned_diagrams): errors.append(f"Missing registered figure: {figure['path']}")
        if not registry: warnings.append("Source inventory is empty; ensure the book requires no external evidence")
        build_file = ROOT / "reports/build-report.json"
        if not source_only and build_file.exists():
            build = json.loads(build_file.read_text(encoding="utf-8"))
            if not build.get("ok"): errors.append("Latest build failed")
            if build.get("fingerprint") != fingerprint(): errors.append("Source/templates/scripts/input changed since the last build; rebuild")
            import hashlib
            for relative, expected in build.get("artifact_hashes", {}).items():
                artifact = ROOT / relative
                if not artifact.is_file() or hashlib.sha256(artifact.read_bytes()).hexdigest() != expected:
                    errors.append(f"Built artifact changed or disappeared: {relative}; rebuild")
            for output in output_paths(project):
                if not output.is_file() or output.stat().st_size == 0: errors.append(f"Missing/empty requested output: {output.relative_to(ROOT)}")
            if project["outputs"].get("pdf") and (ROOT / "publish/book.pdf").exists():
                if not (ROOT / "publish/book.pdf").read_bytes().startswith(b"%PDF-"): errors.append("Invalid PDF signature")
            if project["outputs"].get("semantic_html"): validate_html(ROOT / "interchange", errors)
            if project["outputs"].get("static_site"):
                site = ROOT / "publish/site"
                validate_html(site, errors)
                if len(list((site / "chapters").glob("*.html"))) != len(items): errors.append("Static site chapter count mismatch")
                if not (site / "search-index.json").is_file(): errors.append("Missing website search index")
            for key, path in (("docx", "interchange/book.docx"), ("epub", "publish/book.epub")):
                file = ROOT / path
                if project["outputs"].get(key) and file.exists():
                    try:
                        with zipfile.ZipFile(file) as archive:
                            if archive.testzip(): errors.append(f"Corrupt archive: {path}")
                            if key == "docx" and "word/styles.xml" not in archive.namelist(): errors.append("DOCX missing styles")
                            if key == "epub" and archive.read("mimetype") != b"application/epub+zip": errors.append("Invalid EPUB mimetype")
                    except Exception as exc: errors.append(f"Invalid {key}: {exc}")
        elif not source_only:
            warnings.append("No build report yet: validating canonical source only. Build and validate again before packaging.")
    except Exception as exc:
        errors.append(str(exc))
    result = {"ok": not errors, "phase": "source" if source_only or not (ROOT / "reports/build-report.json").exists() else "final", "errors": errors, "warnings": warnings, "fingerprint": fingerprint()}
    report("validation-report.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--source-only", action="store_true")
    result = validate(parser.parse_args().source_only)
    print(json.dumps(result, ensure_ascii=False, indent=2)); sys.exit(0 if result["ok"] else 1)

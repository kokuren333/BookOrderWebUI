"""Build all selected outputs from one Pandoc AST; no custom Markdown/DTP engine."""
import copy
import hashlib
import html
import json
from pathlib import Path
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from common import math_option, ROOT, read_project, chapters, combined, walk, attr, local_path, plain, tool, run, fingerprint, report, output_paths
from validate import validate
from design import load_design, normalize, write_theme_css
from book_ir import create_ir, prepare_ast, editorial_candidates, registry
from diagrams import generate as generate_diagrams
from renderers import renderer, assess_outputs


# Keep conventional OOXML prefixes when Word parts are re-serialized (Word tooling expects them).
for _prefix, _uri in {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main", "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
                      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships", "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
                      "a": "http://schemas.openxmlformats.org/drawingml/2006/main", "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
                      "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006", "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
                      "v": "urn:schemas-microsoft-com:vml", "o": "urn:schemas-microsoft-com:office:office"}.items():
    ET.register_namespace(_prefix, _uri)


def pandoc(doc, *options):
    return run([tool("pandoc"), "-f", "json", *options], json.dumps(doc, ensure_ascii=False))


def absolute_images(doc, raster=False):
    result = copy.deepcopy(doc)
    for node in walk(result["blocks"]):
        if node["t"] == "Image":
            path = local_path(node["c"][2][0])
            if path:
                if raster and path.suffix == '.svg' and path.with_suffix('.png').is_file(): path = path.with_suffix('.png')
                node["c"][2][0] = path.as_posix()
    return result


def portable_assets(doc, destination, prefix):
    result = copy.deepcopy(doc)
    for node in walk(result["blocks"]):
        if node["t"] in ("Image", "Link"):
            url = node["c"][2][0]
            path = local_path(url)
            if path and path.is_file():
                relative = path.relative_to(ROOT)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                from urllib.parse import quote, urlsplit
                fragment = urlsplit(url).fragment
                node["c"][2][0] = prefix + quote(relative.as_posix()) + ("#" + fragment if fragment else "")
    return result


def reference_docx(path, tokens):
    # Pandoc supplies the valid reference package; only semantic style display names/layout are edited.
    with tempfile.TemporaryDirectory(dir=ROOT / ".build") as folder:
        original = Path(folder) / "reference.docx"
        run([tool("pandoc"), "-o", original, "--print-default-data-file", "reference.docx"])
        namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        q = lambda name: f"{{{namespace}}}{name}"
        ET.register_namespace("w", namespace)
        names = json.loads((ROOT / "templates/docx/styles.json").read_text(encoding="utf-8"))
        with zipfile.ZipFile(original) as archive, zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as out:
            for entry in archive.infolist():
                data = archive.read(entry.filename)
                if entry.filename == "word/styles.xml":
                    styles = ET.fromstring(data)
                    for style in styles.findall(q("style")):
                        name = style.find(q("name"))
                        if name is not None:
                            old = name.get(q("val"), "")
                            match = next((key for key in names if key.lower() == old.lower()), None)
                            if match: name.set(q("val"), names[match])
                    from docx_design import apply_styles
                    apply_styles(styles, tokens)
                    data = ET.tostring(styles, encoding="utf-8", xml_declaration=True)
                out.writestr(entry, data)


def docx_styles(path, tokens):
    # Ensure custom caption and bibliography names as well as Pandoc's built-in style IDs.
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    q = lambda name: f"{{{namespace}}}{name}"
    with zipfile.ZipFile(path) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    styles = ET.fromstring(contents["word/styles.xml"])
    names = json.loads((ROOT / "templates/docx/styles.json").read_text(encoding="utf-8"))
    for style in styles.findall(q("style")):
        name = style.find(q("name"))
        if name is not None:
            old = name.get(q("val"), "")
            match = next((key for key in names if key.lower() == old.lower()), None)
            if match: name.set(q("val"), names[match])
    present = {style.find(q("name")).get(q("val")) for style in styles.findall(q("style")) if style.find(q("name")) is not None}
    for name in names.values():
        if name not in present:
            style = ET.SubElement(styles, q("style"), {q("type"): "paragraph", q("styleId"): name.replace(" ", "")})
            ET.SubElement(style, q("name"), {q("val"): name})
            ET.SubElement(style, q("basedOn"), {q("val"): "BodyText"})
    contents["word/styles.xml"] = ET.tostring(styles, encoding="utf-8", xml_declaration=True)
    document = ET.fromstring(contents["word/document.xml"])
    for paragraph_style in document.iter(q("pStyle")):
        if paragraph_style.get(q("val")) == "FirstParagraph":
            paragraph_style.set(q("val"), "BodyText")
    from docx_design import apply_page
    apply_page(document, tokens)
    contents["word/document.xml"] = ET.tostring(document, encoding="utf-8", xml_declaration=True)
    temporary = path.with_suffix(".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as out:
        for name, data in contents.items(): out.writestr(name, data)
    temporary.replace(path)


def semantic_html(doc, project, tokens):
    prepared = portable_assets(doc, ROOT / "interchange/assets", "assets/")
    body = pandoc(prepared, "-t", "html5", "--section-divs", math_option()).replace('class="level1"', 'class="chapter level1"')
    book = project["book"]
    files, _ = write_theme_css(tokens, ROOT / 'interchange/theme')
    links = ''.join(f'<link rel="stylesheet" href="theme/{path.name}">' for path in files)
    content = f'<!doctype html>\n<html lang="{html.escape(book["language"], quote=True)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(book["title"])}</title>{links}</head><body><article><header><h1 class="book-title">{html.escape(book["title"])}</h1></header>{body}</article></body></html>'
    (ROOT / "interchange/book.html").write_text(content, encoding="utf-8")


def website(doc, project, items, tokens):
    site = ROOT / "publish/site"
    (site / "chapters").mkdir(parents=True, exist_ok=True)
    # Remove only previously generated chapter pages, so renamed/deleted chapters cannot linger.
    for old in (site / "chapters").glob("*.html"):
        if old.is_file(): old.unlink()
    for folder in ("css", "js", "images"): (site / "assets" / folder).mkdir(parents=True, exist_ok=True)
    css_files, _ = write_theme_css(tokens, site / 'assets/css')
    shutil.copy2(ROOT / "templates/web/search.js", site / "assets/js/search.js")
    chunks = []; current = None
    for block in doc["blocks"]:
        if block["t"] == "Header" and block["c"][0] == 1:
            current = {"id": block["c"][1][0], "title": plain(block["c"][2]), "label": dict(block["c"][1][2]).get("data-chapter-label", ""), "blocks": []}
            chunks.append(current)
        if current is not None: current["blocks"].append(block)
    if len(chunks) != len(items): raise ValueError("Website chapter split does not match manuscripts")
    for chunk, (path, _) in zip(chunks, items): chunk["filename"] = path.stem + ".html"
    id_pages = {}
    for chunk in chunks:
        for node in walk(chunk["blocks"]):
            attributes = attr(node)
            if attributes and attributes[0]: id_pages[attributes[0]] = chunk["filename"]
    title = html.escape(project["book"]["title"])
    lang = html.escape(project["book"]["language"], quote=True)
    def shell(page_title, body, prefix, nav=""):
        links = ''.join(f'<link rel="stylesheet" href="{prefix}assets/css/{path.name}">' for path in css_files)
        return f'<!doctype html>\n<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(page_title)} · {title}</title>{links}</head><body><header><a class="bar" href="{prefix}index.html">{title}</a></header><main>{body}{nav}</main><footer>{title}</footer></body></html>'
    search = []
    toc = []
    from urllib.parse import quote
    for i, chunk in enumerate(chunks):
        page_doc = {**doc, "blocks": chunk["blocks"]}
        prepared = portable_assets(page_doc, site / "assets/images", "../assets/images/")
        for node in walk(prepared["blocks"]):
            if node["t"] == "Link" and node["c"][2][0].startswith("#"):
                target = node["c"][2][0][1:]
                if target in id_pages and id_pages[target] != chunk["filename"]:
                    node["c"][2][0] = quote(id_pages[target]) + "#" + quote(target)
            if node["t"] == "Header":
                target = node["c"][1][0]
                node["c"][2].append({"t": "Link", "c": [["", ["anchor"], [["aria-label", "Link to this heading"]]], [{"t": "Str", "c": "#"}], ["#" + target, ""]]})
        body = pandoc(prepared, "-t", "html5", "--section-divs", math_option()).replace('class="level1"', 'class="chapter level1"')
        prev = f'<a rel="prev" href="{quote(chunks[i-1]["filename"])}">← {html.escape(chunks[i-1]["title"])}</a>' if i else '<span></span>'
        nxt = f'<a rel="next" href="{quote(chunks[i+1]["filename"])}">{html.escape(chunks[i+1]["title"])} →</a>' if i + 1 < len(chunks) else '<span></span>'
        nav = f'<nav class="chapter-nav" aria-label="Chapter navigation">{prev}<a href="../index.html">Contents</a>{nxt}</nav>'
        (site / "chapters" / chunk["filename"]).write_text(shell(chunk["title"], body, "../", nav), encoding="utf-8")
        url = "chapters/" + quote(chunk["filename"])
        toc.append(f'<li><a href="{url}"><span class="toc-number">{html.escape(chunk["label"])}</span><span>{html.escape(chunk["title"])}</span></a></li>')
        search.append({"title": chunk["title"], "url": url, "text": plain(chunk["blocks"])})
    data = json.dumps(search, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    (site / "search-index.json").write_text(data, encoding="utf-8")
    body = f'<h1 class="book-cover-title">{title}</h1><nav aria-label="Table of contents"><h2>Contents / 目次</h2><ol>{"".join(toc)}</ol></nav><section class="search"><h2>Search / 検索</h2><label for="book-search">書籍内を検索</label><input type="search" id="book-search" autocomplete="off"><ul id="search-results" aria-live="polite"></ul></section><script type="application/json" id="search-data">{data}</script><script src="assets/js/search.js" defer></script>'
    (site / "index.html").write_text(shell(project["book"]["title"], body, ""), encoding="utf-8")


def repair_epub_links(path):
    # Pandoc routes heading links across EPUB chapters but may leave figure/span links local.
    # Resolve those fragment-only links against IDs in the actual generated XHTML documents.
    import posixpath
    from urllib.parse import urlsplit, unquote, quote
    ET.register_namespace("", "http://www.w3.org/1999/xhtml")
    ET.register_namespace("epub", "http://www.idpf.org/2007/ops")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        data = {entry.filename: archive.read(entry.filename) for entry in entries}
    documents = {name: ET.fromstring(content) for name, content in data.items() if name.endswith(".xhtml")}
    id_pages = {}
    for name, document in documents.items():
        for node in document.iter():
            if node.attrib.get("id"): id_pages.setdefault(node.attrib["id"], []).append(name)
    for name, document in documents.items():
        changed = False
        own_ids = {node.attrib["id"] for node in document.iter() if "id" in node.attrib}
        for node in document.iter():
            href = node.attrib.get("href", "")
            if not href.startswith("#"): continue
            target = unquote(href[1:])
            pages = id_pages.get(target, [])
            if target not in own_ids and len(pages) == 1:
                relative = posixpath.relpath(pages[0], posixpath.dirname(name))
                node.set("href", quote(relative) + "#" + quote(target)); changed = True
        if changed: data[name] = ET.tostring(document, encoding="utf-8", xml_declaration=True)
    temporary = path.with_suffix(".epub.tmp")
    with zipfile.ZipFile(temporary, "w") as archive:
        for entry in entries: archive.writestr(entry, data[entry.filename])
    temporary.replace(path)


def epub_check(path):
    # Baseline container/manifest checks, plus epubcheck when available.
    with zipfile.ZipFile(path) as archive:
        if archive.testzip(): raise ValueError("EPUB archive has corrupt entries")
        if archive.read("mimetype") != b"application/epub+zip": raise ValueError("Invalid EPUB mimetype")
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = next(element for element in container.iter() if element.tag.endswith("rootfile"))
        package_path = rootfile.attrib["full-path"]
        package = ET.fromstring(archive.read(package_path))
        from urllib.parse import unquote, urlsplit
        import posixpath
        documents = {}
        manifest_ids = set()
        for item in package.iter():
            if item.tag.endswith("}item"):
                manifest_ids.add(item.attrib["id"])
                resource = (Path(package_path).parent / unquote(item.attrib["href"])).as_posix()
                if resource not in archive.namelist(): raise ValueError(f"Missing EPUB manifest resource: {resource}")
                if item.attrib.get("media-type") == "application/xhtml+xml":
                    document = ET.fromstring(archive.read(resource))
                    ids = [node.attrib["id"] for node in document.iter() if "id" in node.attrib]
                    if len(ids) != len(set(ids)): raise ValueError(f"Duplicate EPUB IDs: {resource}")
                    documents[resource] = (document, set(ids))
        for item in package.iter():
            if item.tag.endswith("}itemref") and item.attrib.get("idref") not in manifest_ids:
                raise ValueError("EPUB spine references a missing manifest item")
        for resource, (document, _) in documents.items():
            for node in document.iter():
                for field in ("href", "src"):
                    if field not in node.attrib: continue
                    url = urlsplit(node.attrib[field])
                    if url.scheme or url.netloc: continue
                    dest = posixpath.normpath(posixpath.join(posixpath.dirname(resource), unquote(url.path))) if url.path else resource
                    if dest not in archive.namelist(): raise ValueError(f"Broken EPUB resource: {resource} -> {dest}")
                    if url.fragment and dest in documents and unquote(url.fragment) not in documents[dest][1]:
                        raise ValueError(f"Broken EPUB anchor: {resource} -> {node.attrib[field]}")
    checker = shutil.which("epubcheck")
    if checker: run([checker, path])
    return "epubcheck passed" if checker else "container, manifest, spine, XHTML, link and archive checks passed; epubcheck unavailable"


def build(theme=None):
    project = read_project(); outputs = project['outputs']
    spec = load_design(theme)
    if theme:
        # Preserve the selected design in result.zip so a later default build reproduces it.
        (ROOT / 'book.design.yaml').write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tokens = normalize(spec, require_pdf=bool(outputs.get('pdf')))
    # Resolve every semantic planning artifact before anything is fingerprinted: a standalone build must not
    # leave plan/profile.resolved.yaml to be created later (by validation), which would stale the build.
    import publication_profile
    if publication_profile.load_resolved() is None and publication_profile.RESOLVED.parent.parent == ROOT:
        try: publication_profile.write(publication_profile.resolve(project, spec))
        except ValueError: pass  # workspaces without profiles/ (theme previews) build exactly as before
    import layout_spec
    layout_definition = layout_spec.load_or_create(project=project, design=spec)
    tokens = layout_spec.apply_to_tokens(tokens, layout_definition)
    import style_bible
    visual_language = style_bible.load_or_resolve(project=project, design=spec)
    tokens = style_bible.compile_tokens(visual_language, layout_definition, tokens)
    import visual_grammar
    visual_grammar.report(visual_language)
    import image_assets, assets, visual_review
    image_decisions = visual_review.decisions() or {}
    image_assets.prepare(assets.assets(), image_decisions, visual_language, layout_definition, project)
    image_check = image_assets.check(assets.assets(), image_decisions)
    if image_check['summary']['high']:
        raise RuntimeError(f"Generated image QA failed: {image_check['summary']['high']} required issue(s); see reports/image-assets-check.yaml")
    capabilities = assess_outputs(layout_definition, outputs, tokens['pdf_backend'])
    report('layout-capabilities.json', capabilities)
    if not capabilities['ok']:
        raise RuntimeError('LayoutSpec exceeds renderer capability: ' + '; '.join(
            f"{name}: {', '.join(reasons)}" for name, reasons in capabilities['errors'].items()))
    tokens['language'] = str(project['book'].get('language', 'en')).split('-')[0].lower()
    tokens['cover'] = cover_image()
    for folder in ('.build', 'interchange', 'publish'): (ROOT / folder).mkdir(exist_ok=True)
    diagrams = generate_diagrams(tokens, raster=bool(outputs.get('docx') or outputs.get('epub')))
    import style_check
    style_findings = style_check.run(visual_language, tokens)
    import figure_check, figure_spec
    figure_spec.write_reference(tokens)
    figures = figure_check.check(tokens)['summary']  # read by the Typst renderer for printed widths
    if figures.get('fail', 0):
        raise RuntimeError(f"Figure legibility check failed: {figures['fail']} figure(s) print text below the minimum label size; see reports/figure-check.json")
    result = validate(source_only=True)
    if not result['ok']: raise ValueError('Source validation failed: ' + '; '.join(result['errors']))
    from check_env import main as check_env
    if check_env(): raise RuntimeError('Environment check failed')
    items = chapters(); crossrefs = {}
    ir = create_ir(combined(project, items, crossrefs)); ir['crossrefs'] = crossrefs; editorial_candidates(ir)
    (ROOT / 'interchange/book-ir.json').write_text(json.dumps(ir, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'interchange/design-tokens.json').write_text(json.dumps(tokens, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    html_doc = prepare_ast(ir, 'html', tokens); notes = []
    if outputs.get('docx'):
        reference = ROOT / '.build/reference.docx'; reference_docx(reference, tokens)
        path = ROOT / 'interchange/book.docx'
        pandoc(absolute_images(prepare_ast(ir, 'docx'), raster=True), '-t', 'docx', '--reference-doc', reference, '--toc', '-o', path)
        docx_styles(path, tokens)
    if outputs.get('semantic_html'): semantic_html(html_doc, project, tokens)
    layout = None
    if outputs.get('pdf'):
        renderer(tokens['pdf_backend']).render(ir, tokens, ROOT / 'publish/book.pdf', layout_definition)
        if not project['book'].get('preview'): layout = measure_layout(tokens)
    if outputs.get('epub'):
        path = ROOT / 'publish/book.epub'
        _, css = write_theme_css(tokens, ROOT / '.build/epub-theme')
        pandoc(absolute_images(prepare_ast(ir, 'epub', tokens), raster=True), '-t', 'epub3', '--toc', '--split-level=1', '--css', css, '-o', path)
        repair_epub_links(path); notes.append(epub_check(path))
    if outputs.get('static_site'): website(html_doc, project, items, tokens)
    import art_direction_qa
    art_check = art_direction_qa.run(visual_language, tokens,
        pdf_path=ROOT / 'publish/book.pdf' if outputs.get('pdf') else False)
    hashes = artifact_hashes(project)
    report('build-report.json', {'ok': True, 'fingerprint': fingerprint(), 'theme': tokens['theme'],
        'outputs': [p.relative_to(ROOT).as_posix() for p in output_paths(project)], 'artifact_hashes': hashes, 'notes': notes, 'diagrams': diagrams,
        'layout': layout, 'layout_capabilities': capabilities, 'style_check': style_findings['summary'],
        'art_direction_check': art_check['summary'], 'image_assets_check': image_check['summary'], 'figures': figures})
    print('Build complete. Inspect publications, then run validate.py and package.py.')


def measure_layout(tokens):
    """Page-level metrics of the PDF just built (reports/layout-metrics.json). A measuring failure is reported,
    not fatal: the PDF itself is valid."""
    import layout_metrics
    from planning import load_outline
    try:
        metrics = layout_metrics.measure(tokens, outline_chapters=load_outline())
    except Exception as exc:
        print(f'Layout metrics unavailable: {exc}')
        return {'ok': False, 'error': str(exc)[:500]}
    print(layout_metrics.summary(metrics))
    return {'ok': True, 'report': 'reports/layout-metrics.json', 'generated_at': metrics['generated_at'],
            'summary': layout_metrics.summary(metrics), 'totals': metrics['totals']}


def cover_image():
    """A planned cover asset (plan/assets-plan.yaml type: cover) is placed on the PDF title page."""
    try:
        import assets
        for asset in assets.assets():
            if asset.get('type') == 'cover' and (ROOT / str(asset.get('path'))).is_file(): return str(asset.get('path'))
    except Exception: pass
    return None


def artifact_hashes(project):
    paths = set(output_paths(project))
    for key, folder in (("static_site", "publish/site"), ("semantic_html", "interchange/assets"), ("semantic_html", "interchange/theme")):
        if project["outputs"].get(key): paths.update(p for p in (ROOT / folder).rglob("*") if p.is_file())
    paths.update(ROOT / ('interchange/' + name) for name in ('book-ir.json', 'design-tokens.json'))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}


if __name__ == "__main__":
    try:
        import argparse
        parser = argparse.ArgumentParser(); parser.add_argument('--theme'); build(parser.parse_args().theme)
    except Exception as exc:
        report("build-report.json", {"ok": False, "fingerprint": fingerprint(), "error": str(exc)})
        print(str(exc), file=sys.stderr); sys.exit(1)

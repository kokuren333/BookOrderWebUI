"""Design integration checks with real Pandoc/Typst and isolated preview books."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

REPO = Path(__file__).resolve().parent.parent
WORK = REPO / '.test-output/design-job'
WORK.mkdir(parents=True, exist_ok=True)
for name in ('scripts', 'themes', 'schemas', 'templates', 'docs'):
    shutil.copytree(REPO / 'job-template' / name, WORK / name, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('book.design.yaml', 'custom.css', 'custom.typ'):
    shutil.copy2(REPO / 'job-template' / name, WORK / name)
sys.path.insert(0, str(WORK / 'scripts'))
from design import load_design, normalize, css_tokens, merge
from schema import validate_schema
from book_ir import create_ir, prepare_ast, registry
from diagrams import svg, TYPES, specs
from common import fingerprint

def rejects(function, match):
    try: function()
    except ValueError as exc:
        assert match.lower() in str(exc).lower(), str(exc)
    else: raise AssertionError('Invalid input was accepted')

schema = json.loads((WORK / 'schemas/design.schema.json').read_text(encoding='utf-8'))
base = load_design()
for patch, message in [({'unknown': 1}, 'unknown'), ({'colors': {'accent': 'red'}}, 'format'),
                       ({'typography': {'body': {'size': '100pt'}}}, 'format'),
                       ({'components': {'table': 'impossible'}}, 'unknown')]:
    rejects(lambda patch=patch: validate_schema(merge(base, patch), schema), message)
original = (WORK / 'book.design.yaml').read_text(encoding='utf-8')
(WORK / 'book.design.yaml').write_text(json.dumps({'page': {'margin': {'inner': '200mm'}}}), encoding='utf-8')
rejects(load_design, 'text area')
(WORK / 'book.design.yaml').write_text(original, encoding='utf-8')
tokens = normalize(base, require_pdf=True)
fallback = normalize(merge(base, {'typography': {'body': {'japanese': 'Missing font test 9000', 'latin': 'Missing font test 9000'}}}), require_pdf=True)
assert fallback['typography']['body']['resolved_japanese'] != 'Missing font test 9000'
assert 'Missing font test 9000 ->' in (WORK / 'reports/design-report.json').read_text(encoding='utf-8')
changed = normalize(merge(base, {'typography': {'body': {'japanese': 'Yu Gothic', 'latin': 'Arial'}}}), require_pdf=True)
assert changed['typography']['body']['requested_families'] == ['Arial', 'Yu Gothic']
assert changed['typography']['code'] == tokens['typography']['code']
assert 'Yu Gothic' in css_tokens(changed)

# All component types remain semantic in IR and receive output-specific attributes.
ast = {'pandoc-api-version': [1, 23, 1, 1], 'meta': {}, 'blocks': [
    {'t': 'Div', 'c': [[f'component-{kind}', [kind], [['title', kind]]], [{'t': 'Para', 'c': [{'t': 'Str', 'c': '本文'}]}]]}
    for kind in registry() if kind != 'equation']}
ir = create_ir(ast)
assert len(ir['components']) == 24  # plus the separately numbered equation type
assert all('custom-style' not in str(block) for block in ir['ast']['blocks'])
assert all('custom-style' in str(block) for block in prepare_ast(ir, 'docx')['blocks'])
assert all('book-component' in str(block) for block in prepare_ast(ir, 'html')['blocks'])

# Every layout type emits parseable, escaped vector content.
diagram_schema = json.loads((WORK / 'schemas/diagram.schema.json').read_text(encoding='utf-8'))
for kind in TYPES:
    diagram = {'type': kind, 'title': '図 <safe>', 'nodes': [{'id': 'a', 'label': '概念 A & B'}, {'id': 'b', 'label': '長い日本語のラベルを安全に折り返す'}], 'edges': [{'from': 'a', 'to': 'b'}]}
    validate_schema(diagram, diagram_schema)
    parsed = ET.fromstring(svg(diagram, tokens))
    assert parsed.tag.endswith('svg')
    assert '&amp;' in svg(diagram, tokens)
bad = WORK / 'source/assets/diagrams/invalid.yaml'; bad.parent.mkdir(parents=True, exist_ok=True)
bad.write_text(json.dumps({'type': 'flow', 'title': 'test', 'nodes': [{'id': 'a', 'label': 'A'}], 'edges': [{'from': 'a', 'to': 'missing'}]}), encoding='utf-8')
rejects(specs, 'endpoint'); bad.unlink()

# This exact override must survive both Web and EPUB at the end of CSS.
(WORK / 'custom.css').write_text('.warning { border-left-width: 7px; } /* acceptance-override */', encoding='utf-8')
manuscript = WORK / 'source/manuscript/keep.md'; manuscript.parent.mkdir(parents=True, exist_ok=True)
manuscript.write_text('canonical sentinel', encoding='utf-8')
themes = ['modern-technical', 'academic-jp', 'medical-textbook', 'minimal-monochrome', 'business-reference']
outputs = []
for theme in themes:
    result = subprocess.run([sys.executable, str(WORK / 'scripts/cli.py'), 'theme', 'preview', theme], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr
    output = WORK / '.previews' / theme
    assert json.loads((output / 'reports/validation-report.json').read_text(encoding='utf-8'))['ok']
    assert (output / 'publish/book.pdf').stat().st_size > 10000
    assert (output / 'interchange/theme/book.css').read_text(encoding='utf-8').endswith('/* acceptance-override */')
    html = (output / 'interchange/book.html').read_text(encoding='utf-8')
    assert html.index('theme/epub.css') < html.index('theme/custom.css')
    assert 'data-chapter-style' in html
    for kind in ('warning', 'note', 'definition', 'key-point'): assert f'class="{kind} book-component"' in html
    with zipfile.ZipFile(output / 'publish/book.epub') as epub:
        css = '\n'.join(epub.read(name).decode('utf-8') for name in epub.namelist() if name.endswith('.css'))
        assert 'acceptance-override' in css
    with zipfile.ZipFile(output / 'interchange/book.docx') as docx:
        document = docx.read('word/document.xml').decode('utf-8')
        for style in ('Warning', 'Note', 'Definition', 'KeyPoint'): assert f'val="{style}"' in document
    outputs.append(output)
assert manuscript.read_text(encoding='utf-8') == 'canonical sentinel'
irs = [json.loads((output / 'interchange/book-ir.json').read_text(encoding='utf-8')) for output in outputs]
assert all(ir == irs[0] for ir in irs)
assert len({(output / 'publish/book.pdf').read_bytes() for output in outputs}) == len(themes)
assert len({(output / 'interchange/theme/tokens.css').read_text(encoding='utf-8') for output in outputs}) == len(themes)
selected = subprocess.run([sys.executable, str(outputs[-1] / 'scripts/cli.py'), 'build', '--theme', 'academic-jp'], capture_output=True, text=True, encoding='utf-8')
assert selected.returncode == 0, selected.stdout + selected.stderr
assert json.loads((outputs[-1] / 'book.design.yaml').read_text(encoding='utf-8'))['theme'] == 'academic-jp'
before = fingerprint(); (WORK / 'custom.css').write_text('/* changed */', encoding='utf-8'); assert fingerprint() != before
print('PASS: strict schema, independent fonts/fallback, 24 components, nine SVG types, five real all-format previews, shared IR, CSS overrides and preview isolation.')

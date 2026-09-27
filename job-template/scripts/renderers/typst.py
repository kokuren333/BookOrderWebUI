"""Typst adapter. Backend markup is introduced here, after semantic validation."""
import copy
import json
import re
import shutil
from common import ROOT, run, tool, local_path
from design import theme_path
from book_ir import registry

LABEL = re.compile(r"[A-Za-z0-9_.:-]+")


def raw(text):
    return {'t': 'RawBlock', 'c': ['typst', text]}


def label(identifier):
    return f' <{identifier}>' if identifier and LABEL.fullmatch(identifier) else ''


def pdf_ast(ir):
    ast = copy.deepcopy(ir['ast']); components = registry()
    def transform(value):
        if isinstance(value, list):
            output = []
            for item in value:
                transformed = transform(item)
                output.extend(transformed if isinstance(item, dict) and item.get('t') in ('Div', 'Header') and isinstance(transformed, list) else [transformed])
            return output
        if not isinstance(value, dict): return value
        if value.get('t') == 'Cite': return {'t': 'Span', 'c': [['', [], []], transform(value['c'][1])]}
        if value.get('t') == 'Span' and 'section-number' in value['c'][0][1]:
            from common import plain
            return {'t': 'RawInline', 'c': ['typst', '#book-secnum(' + json.dumps(plain(value['c'][1])) + ')']}
        if value.get('t') == 'Span' and 'caption-label' in value['c'][0][1]:
            from common import plain
            return {'t': 'RawInline', 'c': ['typst', '#caption-label(' + json.dumps(plain(value['c'][1]), ensure_ascii=False) + ')']}
        if value.get('t') == 'Header' and value['c'][0] == 1:
            attributes = dict(value['c'][1][2])
            number = attributes.get('data-number', '') if 'unnumbered' not in value['c'][1][1] else ''
            mark = raw('#book-chapter-mark(' + json.dumps(number) + ', ' + json.dumps(attributes.get('data-chapter-label', ''), ensure_ascii=False) + ')')
            return [mark, {key: transform(item) for key, item in value.items()}]
        if value.get('t') == 'Div':
            identifier, classes, attributes = value['c'][0]
            kind = next((name for name in classes if name in components), None)
            if identifier == 'refs':
                return [raw('#book-bibliography['), *transform(value['c'][1]), raw(']')]
            if kind == 'equation':
                number = dict(attributes).get('data-number', '')
                return [raw('#book-equation(number: ' + json.dumps(number) + ')['), *transform(value['c'][1]), raw(']' + label(identifier))]
            if kind:
                body = transform(value['c'][1]); title = dict(attributes).get('title', '')
                begin = '#book-component(' + json.dumps(kind) + ', title: ' + json.dumps(title, ensure_ascii=False) + ')['
                return [raw(begin), *body, raw(']' + label(identifier))]
        if value.get('t') == 'Image':
            path = local_path(value['c'][2][0])
            if path: value['c'][2][0] = '/' + path.relative_to(ROOT).as_posix()
        return {key: transform(item) for key, item in value.items()}
    ast['blocks'] = transform(ast['blocks'])
    for key in ('bibliography', 'csl', 'link-citations'): ast['meta'].pop(key, None)
    return ast


class TypstRenderer:
    def render(self, ir, tokens, output):
        folder = ROOT / '.build'; folder.mkdir(exist_ok=True)
        (folder / 'design-tokens.json').write_text(json.dumps(tokens, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        shutil.copy2(theme_path(tokens['theme']) / 'typst/theme.typ', folder / 'theme.typ')
        shutil.copy2(ROOT / 'templates/design/conf.typ', folder / 'conf.typ')
        override = ROOT / 'custom.typ'
        header = (folder / 'theme.typ').read_text(encoding='utf-8') + '\n' + (override.read_text(encoding='utf-8') if override.exists() else '')
        (folder / 'design-header.typ').write_text(header, encoding='utf-8')
        ast = pdf_ast(ir)
        from common import read_project
        book = read_project()['book']
        colophon = book.get('colophon', 'Publication information / 出版情報: supplied by the author or publisher.')
        (folder / 'colophon.typ').write_text('#book-colophon(' + json.dumps(colophon, ensure_ascii=False) + ')\n', encoding='utf-8')
        source = folder / 'book.typ'
        run([tool('pandoc'), '-f', 'json', '-t', 'typst', '--standalone', *([] if book.get('preview') else ['--toc', '-V', 'toc-depth=2']),
             '-V', 'template=conf.typ', '--include-in-header', folder / 'design-header.typ',
             *([] if book.get('preview') else ['--include-before-body', folder / 'colophon.typ']), '-o', source], json.dumps(ast, ensure_ascii=False))
        run([tool('typst'), 'compile', '--root', ROOT, source, output])

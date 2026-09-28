"""Typst adapter. Backend markup is introduced here, after semantic validation."""
import copy
import json
import re
import shutil
from common import ROOT, run, tool, local_path
from design import theme_path
from book_ir import registry
from common import walk, plain

LABEL = re.compile(r"[A-Za-z0-9_.:-]+")
NUMBER = re.compile(r"^[+−-]?(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?%?$")


def apply_numeric_table_alignment(table, grammar):
    """Right-align numeric columns when the table grammar requests it.

    Pandoc/Typst has no decimal tab stop; right alignment is the readable fallback.
    Explicit authored alignments remain authoritative.
    """
    if not grammar or grammar.get('numeric_alignment') not in ('decimal', 'right'):
        return table
    value = copy.deepcopy(table)
    try:
        colspecs = value['c'][2]
        bodies = value['c'][4]
        rows = [row for body in bodies for row in body[3]]
        for column, spec in enumerate(colspecs):
            if spec[0].get('t') not in ('AlignDefault', 'AlignLeft'): continue
            values = []
            for row in rows:
                cells = row[1]
                if column < len(cells) and cells[column][3] == 1:
                    content = plain(cells[column][4]).replace(' ', '').strip()
                    if content: values.append(content)
            if len(values) >= 2 and sum(bool(NUMBER.fullmatch(v)) for v in values) / len(values) >= .75:
                spec[0] = {'t': 'AlignRight'}
    except (IndexError, KeyError, TypeError):
        return table
    return value


def raw(text):
    return {'t': 'RawBlock', 'c': ['typst', text]}


def mark(**value):
    """Invisible layout mark read back by scripts/layout_metrics.py (see templates/design/layout-probe.typ)."""
    fields = ', '.join(f'{key}: {json.dumps(str(item), ensure_ascii=False)}' for key, item in value.items())
    return raw(f'#metadata(({fields},))<bo-mark>')


def label(identifier):
    return f' <{identifier}>' if identifier and LABEL.fullmatch(identifier) else ''


def figure_placements():
    """Figure id -> printed geometry and measured text size (reports/figure-check.json, written before rendering)."""
    report = ROOT / 'reports/figure-check.json'
    if not report.is_file(): return {}
    return {f['id']: f for f in json.loads(report.read_text(encoding='utf-8')).get('figures', []) if f.get('id')}


def place_figure(value, placement):
    """Give the figure's image its planned printed width, so Typst never rescales it implicitly."""
    for inner in walk(value['c'][2]):
        if inner['t'] == 'Image':
            attributes = [kv for kv in inner['c'][0][2] if kv[0] not in ('width', 'height')]
            attributes.append(['width', f"{placement['planned_width_mm']}mm"])
            inner['c'][0][2] = attributes
            break


def pdf_ast(ir, layout=None, grammar=None):
    ast = copy.deepcopy(ir['ast']); components = registry(); placements = figure_placements()
    columns = ((layout or {}).get('body') or {}).get('columns', 1)
    spans = (layout or {}).get('spans') or {}
    def span_wrapper(body, span, identifier):
        if span not in (1, 2, 'full') or (isinstance(span, int) and span > columns):
            raise ValueError(f"element {identifier} span {span!r} exceeds LayoutSpec body.columns={columns}")
        if columns == 1 or span == 1: return body
        return [raw('#place(top + center, scope: "parent", float: true)['), *body,
                raw(']'), mark(el='span', id=identifier, span=span)]
    def transform(value):
        if isinstance(value, list):
            output = []
            for item in value:
                transformed = transform(item)
                output.extend(transformed if isinstance(item, dict) and item.get('t') in ('Div', 'Header', 'Figure', 'Table') and isinstance(transformed, list) else [transformed])
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
            chapter_label = attributes.get('data-chapter-label', '')
            chapter = raw('#book-chapter-mark(' + json.dumps(number) + ', ' + json.dumps(chapter_label, ensure_ascii=False) + ')')
            return [chapter, mark(el='chapter', id=value['c'][1][0], number=number, label=chapter_label),
                    {key: transform(item) for key, item in value.items()}]
        if value.get('t') == 'Div':
            identifier, classes, attributes = value['c'][0]
            kind = next((name for name in classes if name in components), None)
            if 'slot' in classes:  # proof placeholder for a planned device (validation fails while it remains)
                kind_name = dict(attributes).get('kind', '')
                return [mark(el='begin', sub='slot'), raw('#book-slot(' + json.dumps(kind_name) + ', ' + json.dumps(identifier) + ')['),
                        *transform(value['c'][1]), raw(']'), mark(el='end', sub='slot')]
            if identifier == 'refs':
                return [mark(el='back-matter', sub='bibliography'), raw('#book-bibliography['), *transform(value['c'][1]), raw(']')]
            if kind == 'equation':
                number = dict(attributes).get('data-number', '')
                span = dict(attributes).get('span', spans.get('equation', 1))
                if str(span).isdigit(): span = int(span)
                if span != 1:
                    raise ValueError(f"equation {identifier} span {span} is not supported by Typst adapter")
                math_source = ' '.join(node['c'][1] for node in walk(value['c'][1]) if node.get('t') == 'Math' and node['c'][0].get('t') == 'DisplayMath')
                if columns > 1 and span == 1 and len(math_source) > 60:
                    raise ValueError(f"equation {identifier} may overflow a single column; shorten it or use a one-column LayoutSpec")
                return [raw('#book-equation(number: ' + json.dumps(number) + ')['),
                        *transform(value['c'][1]), raw(']' + label(identifier))]
            if kind:
                body = [mark(el='begin', sub=kind), *transform(value['c'][1]), mark(el='end', sub=kind)]
                title = dict(attributes).get('title', '')
                begin = '#book-component(' + json.dumps(kind) + ', title: ' + json.dumps(title, ensure_ascii=False) + ')['
                rendered = [raw(begin), *body, raw(']' + label(identifier))]
                explicit_span = dict(attributes).get('span')
                span = explicit_span if explicit_span is not None else spans.get('callout', 1)
                if str(span).isdigit(): span = int(span)
                if span != 1 and kind in ('key-point', 'note', 'tip', 'warning', 'definition', 'example', 'exercise', 'checklist', 'sidebar', 'step-by-step', 'glossary-term', 'counterpoint'):
                    return span_wrapper(rendered, span, identifier)
                if explicit_span is not None and span != 1:
                    raise ValueError(f"component {identifier} ({kind}) span {span} is not supported by Typst adapter")
                return rendered
        if value.get('t') == 'Figure' and value['c'][0][0] in placements:
            placement = placements[value['c'][0][0]]
            if placement.get('planned_width_mm'): place_figure(value, placement)
            geometry = mark(el='figure-geometry', id=value['c'][0][0], placement=placement.get('placement', 'column'),
                            span=placement.get('span', 1), region=placement.get('region', 'column'),
                            width_mm=placement.get('placed_width_mm') or placement.get('planned_width_mm') or '',
                            min_text_pt=placement.get('min_text_pt', ''), status=placement.get('status', ''))
            return span_wrapper([geometry, {key: transform(item) for key, item in value.items()}], placement.get('span', 1), value['c'][0][0])
        if value.get('t') == 'Table':
            value = apply_numeric_table_alignment(value, (grammar or {}).get('table'))
            identifier = value['c'][0][0]
            planned = __import__('figure_spec').planned_geometry().get(identifier, {})
            geometry = __import__('figure_spec').resolve(planned, {'layout_spec': layout}, 'table')
            rendered = {key: transform(item) for key, item in value.items()}
            if columns == 1: return rendered
            table_mark = mark(el='figure-geometry', id=identifier, placement=geometry['placement'],
                              span=geometry['span'], region=geometry['region'], width_mm=geometry['width_mm'])
            return span_wrapper([table_mark, rendered], geometry['span'], identifier)
        if value.get('t') == 'Image':
            path = local_path(value['c'][2][0])
            if path: value['c'][2][0] = '/' + path.relative_to(ROOT).as_posix()
        return {key: transform(item) for key, item in value.items()}
    ast['blocks'] = transform(ast['blocks']) + [mark(el='doc-end')]
    for key in ('bibliography', 'csl', 'link-citations'): ast['meta'].pop(key, None)
    return ast


class TypstRenderer:
    def render(self, ir, tokens, output, layout=None):
        if layout and layout['writing_mode'] != 'horizontal-tb':
            raise ValueError('Typst renderer does not support vertical-rl')
        folder = ROOT / '.build'; folder.mkdir(exist_ok=True)
        (folder / 'design-tokens.json').write_text(json.dumps(tokens, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        shutil.copy2(theme_path(tokens['theme']) / 'typst/theme.typ', folder / 'theme.typ')
        shutil.copy2(ROOT / 'templates/design/conf.typ', folder / 'conf.typ')
        override = ROOT / 'custom.typ'
        header = (folder / 'theme.typ').read_text(encoding='utf-8') + '\n' + (override.read_text(encoding='utf-8') if override.exists() else '')
        header += '\n' + (ROOT / 'templates/design/layout-marks.typ').read_text(encoding='utf-8')
        header += '\n' + (ROOT / 'templates/design/slots.typ').read_text(encoding='utf-8')
        shutil.copy2(ROOT / 'templates/design/layout-probe.typ', folder / 'layout-probe.typ')
        (folder / 'design-header.typ').write_text(header, encoding='utf-8')
        ast = pdf_ast(ir, layout, ((tokens.get('style') or {}).get('visual_grammar') or {}))
        from common import read_project
        book = read_project()['book']
        colophon = book.get('colophon', 'Publication information / 出版情報: supplied by the author or publisher.')
        (folder / 'colophon.typ').write_text('#book-colophon(' + json.dumps(colophon, ensure_ascii=False) + ')\n', encoding='utf-8')
        source = folder / 'book.typ'
        run([tool('pandoc'), '-f', 'json', '-t', 'typst', '--standalone', *([] if book.get('preview') else ['--toc', '-V', 'toc-depth=2']),
             '-V', 'template=conf.typ', '--include-in-header', folder / 'design-header.typ',
             *([] if book.get('preview') else ['--include-before-body', folder / 'colophon.typ']), '-o', source], json.dumps(ast, ensure_ascii=False))
        run([tool('typst'), 'compile', '--root', ROOT, source, output])

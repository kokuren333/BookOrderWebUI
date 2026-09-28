"""Semantic Book IR over Pandoc AST; no output-format styling or raw markup."""
import copy
import json
from pathlib import Path
from common import ROOT, walk, plain, report
from schema import validate_schema

def registry():
    return json.loads((ROOT / 'schemas/components.json').read_text(encoding='utf-8'))

def create_ir(ast):
    components = registry(); found = []
    for node in walk(ast['blocks']):
        if node['t'] == 'Div':
            identifier, classes, attributes = node['c'][0]
            semantic = [name for name in classes if name in components]
            if len(semantic) > 1: raise ValueError(f'A component must have one semantic type: {classes}')
            if semantic: found.append({'type': semantic[0], 'id': identifier, 'title': dict(attributes).get('title', ''), 'text': plain(node['c'][1])})
    ir = {'format': 'bookorder-book-ir', 'version': '1', 'ast': copy.deepcopy(ast), 'components': found}
    # Keep IR location-independent: project-internal paths are stored relative to the job root.
    meta = ir['ast'].get('meta', {})
    values = [meta.get('csl')] + ([meta['bibliography']] if meta.get('bibliography', {}).get('t') == 'MetaString' else meta.get('bibliography', {}).get('c', []) if meta.get('bibliography') else [])
    for value in values:
        if value and value.get('t') == 'MetaString':
            path = Path(value['c'])
            if path.is_absolute() and path.is_relative_to(ROOT): value['c'] = path.relative_to(ROOT).as_posix()
    return validate_schema(ir, json.loads((ROOT / 'schemas/book-ir.schema.json').read_text(encoding='utf-8')))

def prepare_ast(ir, output, tokens=None):
    ast = copy.deepcopy(ir['ast']); components = registry()
    chapter = 0
    def transform(value):
        nonlocal chapter
        if isinstance(value, list): return [transform(x) for x in value]
        if not isinstance(value, dict): return value
        if value.get('t') == 'Header' and value['c'][0] == 1 and 'unnumbered' not in value['c'][1][1] and output in ('html', 'epub'):
            chapter += 1
            value['c'][1][2].append(['data-chapter-number', f'{chapter:02}'])
            if tokens: value['c'][1][2].append(['data-chapter-style', tokens['components']['chapter_opener']])
        if value.get('t') == 'Header' and value['c'][0] == 1 and output == 'docx':
            label = dict(value['c'][1][2]).get('data-chapter-label')
            if label: value = {**value, 'c': [value['c'][0], value['c'][1], [{'t': 'Str', 'c': label}, {'t': 'Str', 'c': '\u3000'}] + value['c'][2]]}
        if value.get('t') == 'Div':
            identifier, classes, attributes = value['c'][0]
            kind = next((name for name in classes if name in components), None)
            if 'slot' in classes:  # proof placeholder for a planned device
                label = {'t': 'Strong', 'c': [{'t': 'Str', 'c': f"［slot {dict(attributes).get('kind', '')}: {identifier}］"}]}
                body = transform(value['c'][1])
                if body and body[0]['t'] in ('Para', 'Plain'): body[0] = {**body[0], 'c': [label, {'t': 'Space'}] + body[0]['c']}
                else: body.insert(0, {'t': 'Para', 'c': [label]})
                extra = [['custom-style', 'Note']] if output == 'docx' else []
                return {'t': 'Div', 'c': [[identifier, ['slot-placeholder'], extra], body]}
            if kind == 'equation':
                body = transform(value['c'][1]); number = dict(attributes).get('data-number', '')
                label = {'t': 'Str', 'c': f'({number})'} if number else None
                if output == 'docx':
                    attributes = [pair for pair in attributes if pair[0] != 'custom-style'] + [['custom-style', components[kind]['docx_style']]]
                    if label and body and body[-1]['t'] in ('Para', 'Plain'): body[-1] = {**body[-1], 'c': body[-1]['c'] + [{'t': 'Str', 'c': '\u2003'}, label]}
                elif output in ('html', 'epub') and label:
                    classes = classes + ['book-equation']
                    body = body + [{'t': 'Plain', 'c': [{'t': 'Span', 'c': [['', ['eq-number'], []], [label]]}]}]
                return {'t': 'Div', 'c': [[identifier, classes, attributes], body]}
            if kind:
                title = dict(attributes).get('title')
                body = transform(value['c'][1])
                if output == 'docx':
                    attributes = [pair for pair in attributes if pair[0] != 'custom-style'] + [['custom-style', components[kind]['docx_style']]]
                elif output in ('html', 'epub'):
                    classes = classes + ['book-component']
                    if title: body.insert(0, {'t': 'Para', 'c': [{'t': 'Span', 'c': [['', ['component-title'], []], [{'t': 'Str', 'c': title}]]}]})
                return {'t': 'Div', 'c': [[identifier, classes, attributes], body]}
        return {key: transform(item) for key, item in value.items()}
    ast['blocks'] = transform(ast['blocks']); return ast

def editorial_candidates(ir):
    suggestions = []; paragraph_run = 0
    for block in ir['ast']['blocks']:
        if block['t'] == 'Para':
            paragraph_run += len(plain(block['c']))
            if paragraph_run > 4000:
                suggestions.append({'reason': 'Long continuous prose; inspect actual page count', 'candidate': 'figure or subsection', 'excerpt': plain(block['c'])[:120]}); paragraph_run = 0
        else: paragraph_run = 0
        if block['t'] in ('OrderedList', 'BulletList'):
            suggestions.append({'reason': 'Structured list', 'candidate': 'step-by-step or checklist; retain the original meaning'})
    report('editorial-design-candidates.json', {'automatic_rewrite': False, 'suggestions': suggestions,
                                               'policy': 'Agent reviews candidates; ordinary prose remains primary. No semantic changes.'})

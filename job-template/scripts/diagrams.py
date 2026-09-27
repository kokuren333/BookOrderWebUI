"""Library-neutral Diagram IR -> vector SVG and optional Typst-rendered PNG."""
import html
import json
import math
from pathlib import Path
import re
import unicodedata
from common import ROOT, yaml_data, run, tool
from schema import validate_schema

TYPES = ('flow', 'concept-map', 'hierarchy', 'timeline', 'comparison', 'cycle', 'process', 'network', 'matrix')

def specs():
    schema = json.loads((ROOT / 'schemas/diagram.schema.json').read_text(encoding='utf-8'))
    result = []
    for path in sorted((ROOT / 'source/assets/diagrams').glob('*.yaml')):
        spec = validate_schema(yaml_data(path), schema, str(path.relative_to(ROOT)), coerce=True)
        ids = [node['id'] for node in spec['nodes']]
        if len(set(ids)) != len(ids): raise ValueError(f'Duplicate diagram node IDs: {path.name}')
        for edge in spec.get('edges', []):
            if edge['from'] not in ids or edge['to'] not in ids: raise ValueError(f'Unknown diagram edge endpoint: {path.name}')
        result.append((path, spec))
    return result

def outputs():
    return {f'source/assets/figures/{path.stem}.svg' for path, _ in specs()}

def wrap(text, width=19):
    lines = []; line = ''; units = 0
    for char in text:
        step = 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
        if char == '\n' or units + step > width:
            lines.append(line); line = ''; units = 0
        if char != '\n': line += char; units += step
    if line: lines.append(line)
    return lines

def svg(spec, tokens):
    nodes = spec['nodes']; count = len(nodes)
    box_w = 172; box_h = max(72, max(len(wrap(node['label'])) for node in nodes) * 22 + 28)
    gap = 50; kind = spec['type']; positions = {}
    columns = min(3, count)
    if kind in ('cycle', 'network', 'concept-map'):
        radius = max(155, count * 28); width = height = radius * 2 + 230
        if kind == 'concept-map':
            positions[nodes[0]['id']] = (width / 2, height / 2)
            ring = nodes[1:]
        else: ring = nodes
        for i, node in enumerate(ring):
            angle = -math.pi / 2 + 2 * math.pi * i / max(len(ring), 1)
            positions[node['id']] = (width / 2 + radius * math.cos(angle), height / 2 + radius * math.sin(angle))
    elif kind == 'hierarchy':
        incoming = {node['id']: set() for node in nodes}
        for edge in spec.get('edges', []): incoming[edge['to']].add(edge['from'])
        remaining = set(incoming); levels = []
        while remaining:
            level = [node['id'] for node in nodes if node['id'] in remaining and not incoming[node['id']].intersection(remaining)]
            if not level: raise ValueError('Hierarchy diagram contains a cycle; use cycle/network instead')
            levels.append(level); remaining.difference_update(level)
        columns = max(map(len, levels)); width = columns * (box_w + gap) + 60; height = len(levels) * (box_h + gap) + 80
        for row, level in enumerate(levels):
            for col, identifier in enumerate(level): positions[identifier] = (width / 2 + (col - (len(level) - 1) / 2) * (box_w + gap), 55 + box_h / 2 + row * (box_h + gap))
    else:
        rows = math.ceil(count / columns); width = columns * (box_w + gap) + 60; height = rows * (box_h + gap) + 90
        for i, node in enumerate(nodes):
            row, col = divmod(i, columns)
            if kind in ('flow', 'process', 'timeline') and row % 2: col = columns - 1 - col
            positions[node['id']] = (55 + box_w / 2 + col * (box_w + gap), 65 + box_h / 2 + row * (box_h + gap))
    colors = tokens['colors']; primary = colors['primary'] if tokens['figures']['style'] != 'monochrome' else '#303030'
    stroke = {'thin': 1.2, 'regular': 1.8, 'bold': 2.6}[tokens['figures']['line_weight']]
    font = html.escape(', '.join(tokens['typography']['heading']['resolved_families']) + ', sans-serif', quote=True)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="diagram-title">',
           f'<title id="diagram-title">{html.escape(spec["title"])}</title>',
           f'<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="{primary}"/></marker></defs>',
           '<rect width="100%" height="100%" fill="white"/>']
    edges = spec.get('edges', [])
    if kind in ('flow', 'process', 'timeline', 'cycle') and not edges:
        edges = [{'from': nodes[i]['id'], 'to': nodes[(i + 1) % count]['id']} for i in range(count if kind == 'cycle' else count - 1)]
    if kind == 'concept-map' and not edges: edges = [{'from': nodes[0]['id'], 'to': node['id']} for node in nodes[1:]]
    for edge in edges:
        x1, y1 = positions[edge['from']]; x2, y2 = positions[edge['to']]
        if (x1, y1) == (x2, y2): raise ValueError('Self edges are not supported; use a multi-node cycle')
        dx, dy = x2-x1, y2-y1
        ratio = min(box_w / 2 / abs(dx) if dx else float('inf'), box_h / 2 / abs(dy) if dy else float('inf'))
        ax, ay = x1+dx*ratio, y1+dy*ratio; bx, by = x2-dx*ratio, y2-dy*ratio
        route = f'M {ax} {ay} L {bx} {by}'
        if kind in ('flow', 'process', 'timeline') and y1 == y2 and abs(dx) > box_w + gap + 1:
            # Route feedback/skipping edges outside the row rather than through intermediate nodes.
            track = y1 - box_h / 2 - 28
            route = f'M {x1} {y1-box_h/2} L {x1} {track} L {x2} {track} L {x2} {y2-box_h/2}'
        out.append(f'<path d="{route}" fill="none" stroke="{primary}" stroke-width="{stroke}" marker-end="url(#arrow)"/>')
        if edge.get('label'): out.append(f'<text x="{(x1+x2)/2}" y="{(y1+y2)/2-7}" text-anchor="middle" font-family="{font}" font-size="12" fill="{primary}">{html.escape(edge["label"])}</text>')
    for i, node in enumerate(nodes):
        x, y = positions[node['id']]; lines = wrap(node['label'])
        if kind == 'timeline': out.append(f'<circle cx="{x}" cy="{y-box_h/2-14}" r="4" fill="{primary}"/>')
        out.append(f'<rect x="{x-box_w/2}" y="{y-box_h/2}" width="{box_w}" height="{box_h}" fill="white" stroke="{primary}" stroke-width="{stroke}"/>')
        if tokens['figures']['labeling'] == 'numbered': out.append(f'<text x="{x-box_w/2+9}" y="{y-box_h/2+15}" font-family="{font}" font-size="10" fill="{colors["muted"]}">{i+1:02}</text>')
        out.append(f'<text text-anchor="middle" font-family="{font}" font-size="16" fill="{colors["text"]}">')
        for j, line in enumerate(lines): out.append(f'<tspan x="{x}" y="{y + (j-(len(lines)-1)/2)*22 + 6}">{html.escape(line)}</tspan>')
        out.append('</text>')
    out.append('</svg>'); return '\n'.join(out)

def generate(tokens, raster=False):
    records = []
    for path, spec in specs():
        output = ROOT / 'source/assets/figures' / (path.stem + '.svg'); output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(svg(spec, tokens), encoding='utf-8')
        if raster:
            temp = ROOT / '.build/diagrams'; temp.mkdir(parents=True, exist_ok=True)
            source = temp / (path.stem + '.typ')
            source.write_text('#set page(width: auto, height: auto, margin: 0pt)\n#image(' + json.dumps('/' + output.relative_to(ROOT).as_posix()) + ', width: 150mm)\n', encoding='utf-8')
            run([tool('typst'), 'compile', '--root', ROOT, '--format', 'png', '--ppi', '160', source, output.with_suffix('.png')])
        records.append({'source': path.relative_to(ROOT).as_posix(), 'svg': output.relative_to(ROOT).as_posix(), 'type': spec['type']})
    return records

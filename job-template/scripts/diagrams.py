"""Library-neutral Diagram IR -> vector SVG and optional Typst-rendered PNG."""
import html
import json
import math
from pathlib import Path
import re
import unicodedata
from common import ROOT, yaml_data, run, tool
from schema import validate_schema
from figure_spec import PT_PER_MM, figure_tokens, frames, resolve

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

def _units(char):
    return 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1

def wrap(text, width=19):
    """Break a label into lines of at most `width` units (East Asian wide characters count 2), balancing the
    lines so a label never ends with a single orphaned character."""
    lines = _greedy(text, width)
    if len(lines) > 1 and '\n' not in text:
        balanced = _greedy(text, math.ceil(sum(map(_units, text)) / len(lines)) + 1)
        if len(balanced) == len(lines): lines = balanced
    return lines

def _greedy(text, width):
    lines = []; line = ''; units = 0; width = max(2, int(width))
    for char in text:
        step = _units(char)
        if char == '\n' or units + step > width:
            lines.append(line); line = ''; units = 0
        if char != '\n': line += char; units += step
    if line: lines.append(line)
    return lines

MARGIN_PT = 4.0

def svg(spec, tokens, geometry=None):
    """Lay the diagram out at its final printed width. One SVG user unit is one point, the root carries the
    physical size, so the book places it at 100% and every font size below is the printed size."""
    ft = figure_tokens(tokens); geometry = geometry or resolve(None, tokens, 'diagram')
    grammar = ((tokens.get('style') or {}).get('visual_grammar') or {}).get('diagram') or {}
    width = geometry['width_mm'] * PT_PER_MM
    label_pt, small_pt = ft['preferred_label_pt'], ft['annotation_pt']
    pitch = label_pt * ft['line_height']; pad = ft['node_padding_mm'] * PT_PER_MM
    whitespace = {'compact': .8, 'regular': 1, 'generous': 1.4}.get(grammar.get('whitespace'), 1)
    gap = max(ft['node_gap_mm'] * PT_PER_MM * whitespace, 3 * ft['marker_size_pt'] + 4)
    edge_labels = [e.get('label', '') for e in spec.get('edges', []) if e.get('label')]
    if edge_labels:  # a labelled edge needs room for its label between the boxes
        gap = max(gap, max(sum(map(_units, label)) for label in edge_labels) * small_pt / 2 + 6)
    row_space = max(gap * 1.5, small_pt * 3.2 if edge_labels else 0)
    nodes = spec['nodes']; count = len(nodes); kind = spec['type']; positions = {}
    numbered = tokens['figures']['labeling'] == 'numbered'
    head = small_pt * 1.2 if numbered else 0  # room for the node number above the label
    usable = width - 2 * MARGIN_PT

    def box_for(box_w):
        units = (box_w - 2 * pad) / (label_pt / 2)
        lines = max(len(wrap(node['label'], units)) for node in nodes)
        return box_w, lines * pitch + 2 * pad + head, units

    top = MARGIN_PT
    if kind in ('cycle', 'network', 'concept-map'):
        ring = nodes[1:] if kind == 'concept-map' else nodes
        # Three boxes side by side (left ring node, centre, right ring node) must fit the width, and the two
        # nodes next to the top/bottom of the ring must not collide horizontally.
        limit = min((usable - 2 * gap) / 3, 42 * PT_PER_MM)
        if len(ring) >= 3:
            sine = math.sin(math.pi / len(ring)); limit = min(limit, (usable * sine - gap / 2) / (1 + sine))
        box_w, box_h, units = box_for(limit)
        rx = (usable - box_w) / 2; ry = box_h + row_space

        def place(ry):
            cx, cy = width / 2, MARGIN_PT + box_h / 2 + ry
            points = {nodes[0]['id']: (cx, cy)} if kind == 'concept-map' else {}
            for i, node in enumerate(ring):
                angle = -math.pi / 2 + 2 * math.pi * i / max(len(ring), 1)
                points[node['id']] = (cx + rx * math.cos(angle), cy + ry * math.sin(angle))
            return points

        def clear(points):
            values = list(points.values())
            return all(abs(a[0] - b[0]) >= box_w + gap / 2 or abs(a[1] - b[1]) >= box_h + gap / 2
                       for i, a in enumerate(values) for b in values[i + 1:])

        # Grow the ring downwards (width is fixed) until no two boxes touch; if that would exceed the frame's
        # height, go round a rectangle of grid cells instead.
        max_height = frames(tokens)[geometry['placement']]['max_height_mm'] * PT_PER_MM
        while not clear(place(ry)) and 2 * ry + box_h + 2 * MARGIN_PT <= max_height: ry += box_h / 4
        if clear(place(ry)) and 2 * ry + box_h + 2 * MARGIN_PT <= max_height:
            positions = place(ry); height = 2 * ry + box_h + 2 * MARGIN_PT
        else:
            columns = 3 if kind == 'concept-map' or (usable - 2 * gap) / 3 >= 22 * PT_PER_MM else 2  # the hub needs a middle column
            box_w, box_h, units = box_for((usable - (columns - 1) * gap) / columns)
            rows = 3
            while 2 * columns + 2 * (rows - 2) < len(ring): rows += 1
            slots = [(0, c) for c in range(columns)] + [(r, columns - 1) for r in range(1, rows - 1)] \
                + [(rows - 1, c) for c in range(columns - 1, -1, -1)] + [(r, 0) for r in range(rows - 2, 0, -1)]
            cell = lambda r, c: (width / 2 + (c - (columns - 1) / 2) * (box_w + gap), MARGIN_PT + box_h / 2 + r * (box_h + row_space))
            if kind == 'concept-map': positions[nodes[0]['id']] = cell((rows - 1) / 2, (columns - 1) / 2)
            for i, node in enumerate(ring): positions[node['id']] = cell(*slots[round(i * len(slots) / len(ring)) % len(slots)])
            height = 2 * MARGIN_PT + rows * box_h + (rows - 1) * row_space
    elif kind == 'hierarchy':
        incoming = {node['id']: set() for node in nodes}
        for edge in spec.get('edges', []): incoming[edge['to']].add(edge['from'])
        remaining = set(incoming); levels = []
        while remaining:
            level = [node['id'] for node in nodes if node['id'] in remaining and not incoming[node['id']].intersection(remaining)]
            if not level: raise ValueError('Hierarchy diagram contains a cycle; use cycle/network instead')
            levels.append(level); remaining.difference_update(level)
        columns = max(map(len, levels))
        box_w, box_h, units = box_for(min((usable - (columns - 1) * gap) / columns, 45 * PT_PER_MM))
        row_gap = row_space
        height = 2 * MARGIN_PT + len(levels) * box_h + (len(levels) - 1) * row_gap
        for row, level in enumerate(levels):
            for col, identifier in enumerate(level):
                positions[identifier] = (width / 2 + (col - (len(level) - 1) / 2) * (box_w + gap), top + box_h / 2 + row * (box_h + row_gap))
    else:
        columns = min(3, count)
        # Never squeeze a label box below 24 mm: use fewer columns instead.
        while columns > 1 and (usable - (columns - 1) * gap) / columns < 24 * PT_PER_MM: columns -= 1
        box_w, box_h, units = box_for((usable - (columns - 1) * gap) / columns)
        rows = math.ceil(count / columns); row_gap = row_space
        track = small_pt * 2.5 if kind in ('flow', 'process', 'timeline') else 0
        dot = 10 if kind == 'timeline' else 0
        top = MARGIN_PT + track + dot
        height = top + rows * box_h + (rows - 1) * row_gap + MARGIN_PT
        for i, node in enumerate(nodes):
            row, col = divmod(i, columns)
            if kind in ('flow', 'process', 'timeline') and row % 2: col = columns - 1 - col
            used = columns * box_w + (columns - 1) * gap
            positions[node['id']] = ((width - used) / 2 + box_w / 2 + col * (box_w + gap), top + box_h / 2 + row * (box_h + row_gap))
    colors = tokens['colors']; style = tokens.get('style') or {}; palette = style.get('palette') or {}
    primary = (palette.get('ink', colors['text']) if tokens['figures']['style'] == 'monochrome'
               else palette.get('secondary_accent', colors['primary']))
    background = palette.get('background', '#FFFFFF')
    stroke = ft['stroke_width_pt'] * (1.15 if grammar.get('edge_emphasis') == 'directional' else .85 if grammar.get('edge_emphasis') == 'relational' else 1)
    radius = (0 if grammar.get('node_shape') == 'rectangle' else box_h / 2 if grammar.get('node_shape') == 'pill'
              else ft['corner_radius_mm'] * PT_PER_MM)
    marker = ft['marker_size_pt']
    font = html.escape(', '.join(ft['font_families']) + ', sans-serif', quote=True)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.2f}pt" height="{height:.2f}pt" viewBox="0 0 {width:.2f} {height:.2f}" role="img" aria-labelledby="diagram-title">',
           f'<title id="diagram-title">{html.escape(spec["title"])}</title>',
           f'<defs><marker id="arrow" markerUnits="userSpaceOnUse" markerWidth="{marker}" markerHeight="{marker}" refX="{marker - 0.5}" refY="{marker / 2}" orient="auto"><path d="M0,0 L{marker},{marker / 2} L0,{marker}" fill="{primary}"/></marker></defs>',
           f'<rect width="100%" height="100%" fill="{background}"/>']
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
        route = f'M {ax:.2f} {ay:.2f} L {bx:.2f} {by:.2f}'
        lx, ly, anchor = (x1 + x2) / 2, (y1 + y2) / 2 - small_pt * 0.6, 'middle'
        if abs(dy) > abs(dx): lx, ly, anchor = (ax + bx) / 2 + small_pt * 0.5, (ay + by) / 2 + small_pt * 0.35, 'start'  # beside an upright line
        if kind in ('flow', 'process', 'timeline') and y1 == y2 and abs(dx) > box_w + gap + 1:
            # Route feedback/skipping edges outside the row rather than through intermediate nodes.
            track = y1 - box_h / 2 - small_pt * 2
            route = f'M {x1:.2f} {y1-box_h/2:.2f} L {x1:.2f} {track:.2f} L {x2:.2f} {track:.2f} L {x2:.2f} {y2-box_h/2:.2f}'
            ly, anchor = track - small_pt * 0.4, 'middle'
        out.append(f'<path d="{route}" fill="none" stroke="{primary}" stroke-width="{stroke}" marker-end="url(#arrow)"/>')
        if edge.get('label'):
            if grammar.get('annotation_style') == 'below-node': ly += small_pt * 1.5
            out.append(f'<text x="{lx:.2f}" y="{ly:.2f}" text-anchor="{anchor}" font-family="{font}" font-size="{small_pt}" fill="{primary}">{html.escape(edge["label"])}</text>')
    for i, node in enumerate(nodes):
        x, y = positions[node['id']]; lines = wrap(node['label'], units)
        if kind == 'timeline': out.append(f'<circle cx="{x:.2f}" cy="{y-box_h/2-5:.2f}" r="2.5" fill="{primary}"/>')
        out.append(f'<rect x="{x-box_w/2:.2f}" y="{y-box_h/2:.2f}" width="{box_w:.2f}" height="{box_h:.2f}" rx="{radius:.2f}" fill="{background}" stroke="{primary}" stroke-width="{stroke}"/>')
        if numbered: out.append(f'<text x="{x-box_w/2+pad:.2f}" y="{y-box_h/2+pad+small_pt*0.8:.2f}" font-family="{font}" font-size="{small_pt}" fill="{colors["muted"]}">{i+1:02}</text>')
        out.append(f'<text text-anchor="middle" font-family="{font}" font-size="{label_pt}" fill="{colors["text"]}">')
        centre = y + head / 2
        for j, line in enumerate(lines): out.append(f'<tspan x="{x:.2f}" y="{centre + (j-(len(lines)-1)/2)*pitch + label_pt*0.35:.2f}">{html.escape(line)}</tspan>')
        out.append('</text>')
    out.append('</svg>'); return '\n'.join(out)

def asset_geometry(tokens):
    """Diagram IR path -> resolved print geometry, from the asset plan (default: text column)."""
    geometry = {}
    try:
        from assets import assets
        for asset in assets():
            if asset.get('type') == 'diagram' and asset.get('source'):
                geometry[Path(str(asset['source'])).as_posix()] = resolve(asset.get('geometry'), tokens, 'diagram') | {'id': asset.get('id')}
    except Exception: pass
    return geometry

def skipped_sources():
    """Diagram IR files whose candidate was rejected or is pending (scripts/visual_review.py): not generated."""
    try:
        import visual_review
        from assets import assets
        decided = visual_review.decisions() or {}
        return {Path(str(a['source'])).as_posix() for a in assets() if a.get('type') == 'diagram' and a.get('source') and decided.get(str(a.get('id'))) in ('rejected', 'pending')}
    except Exception: return set()

def generate(tokens, raster=False):
    records = []; geometries = asset_geometry(tokens); skipped = skipped_sources()
    for path, spec in specs():
        source = path.relative_to(ROOT).as_posix()
        if source in skipped: continue
        geometry = geometries.get(source) or resolve(None, tokens, 'diagram')
        output = ROOT / 'source/assets/figures' / (path.stem + '.svg'); output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(svg(spec, tokens, geometry), encoding='utf-8')
        if raster:
            temp = ROOT / '.build/diagrams'; temp.mkdir(parents=True, exist_ok=True)
            typ = temp / (path.stem + '.typ')
            typ.write_text('#set page(width: auto, height: auto, margin: 0pt)\n#image(' + json.dumps('/' + output.relative_to(ROOT).as_posix()) + f', width: {geometry["width_mm"]}mm)\n', encoding='utf-8')
            run([tool('typst'), 'compile', '--root', ROOT, '--format', 'png', '--ppi', '300', typ, output.with_suffix('.png')])
        records.append({'source': source, 'svg': output.relative_to(ROOT).as_posix(), 'type': spec['type'],
                        'placement': geometry['placement'], 'width_mm': geometry['width_mm']})
    return records

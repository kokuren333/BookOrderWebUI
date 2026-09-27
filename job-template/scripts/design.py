"""Design Spec -> output-neutral tokens -> CSS. Theme packages contain styles."""
import copy
import json
import re
from pathlib import Path
from common import ROOT, yaml_data, tool, run, report
from schema import validate_schema

CSS_ORDER = ['tokens', 'typography', 'layout', 'components', 'figures', 'tables', 'code', 'print', 'epub']

def merge(base, patch):
    result = copy.deepcopy(base)
    for key, value in patch.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else copy.deepcopy(value)
    return result

def theme_path(name):
    if not re.fullmatch(r'[a-z][a-z0-9-]*', name): raise ValueError('Invalid theme identifier')
    path = ROOT / 'themes' / name
    if not (path / 'theme.yaml').is_file(): raise ValueError(f'Unknown theme: {name}')
    return path

def load_design(theme=None):
    path = ROOT / 'book.design.yaml'
    user = yaml_data(path) if path.exists() else {}
    name = theme or user.get('theme', 'modern-technical')
    if theme and user.get('theme', 'modern-technical') != theme:
        previous = yaml_data(theme_path(user.get('theme', 'modern-technical')) / 'theme.yaml')
        def differences(patch, defaults):
            output = {}
            for key, value in patch.items():
                if isinstance(value, dict) and isinstance(defaults.get(key), dict):
                    nested = differences(value, defaults[key])
                    if nested: output[key] = nested
                elif value != defaults.get(key): output[key] = value
            return output
        user = differences(user, previous)
    base = yaml_data(theme_path(name) / 'theme.yaml')
    for role, settings in user.get('typography', {}).items():
        if isinstance(settings, dict) and 'family' in settings and role in base['typography']:
            base['typography'][role].pop('japanese', None); base['typography'][role].pop('latin', None)
    spec = merge(base, user); spec['theme'] = name
    # --theme selects a package's defaults; user overrides still win.
    schema = json.loads((ROOT / 'schemas/design.schema.json').read_text(encoding='utf-8'))
    spec = validate_schema(spec, schema, coerce=True)
    sizes = {'A5': (148, 210), 'B5': (176, 250), 'A4': (210, 297), 'Letter': (215.9, 279.4)}
    width, height = sizes[spec['page']['size']]
    if spec['page']['orientation'] == 'landscape': width, height = height, width
    def mm(value):
        match = re.fullmatch(r'([0-9.]+)(mm|cm|pt|in)', value)
        return float(match[1]) * {'mm': 1, 'cm': 10, 'pt': 25.4 / 72, 'in': 25.4}[match[2]]
    margins = {key: mm(value) for key, value in spec['page']['margin'].items()}
    if any(value < 2 for value in margins.values()) or width - margins['inner'] - margins['outer'] < 50 or height - margins['top'] - margins['bottom'] < 50:
        raise ValueError('Page margins must be at least 2mm and leave a text area of at least 50mm in each direction')
    return spec

def available_fonts():
    return sorted(set(line.strip() for line in run([tool('typst'), 'fonts']).splitlines() if line.strip()))

def normalize(spec, require_pdf=False):
    tokens = copy.deepcopy(spec)
    warnings = []; fonts = []
    try: fonts = available_fonts()
    except RuntimeError:
        if require_pdf: raise
        warnings.append('Typst unavailable: PDF font resolution not checked; browser/EPUB fonts depend on reader.')
    for role, settings in tokens['typography'].items():
        requested = [settings.get('latin'), settings.get('japanese'), settings.get('family')]
        requested = list(dict.fromkeys(x for x in requested if x))
        fallbacks = settings['fallback']
        resolved = []
        for family in requested:
            substitute = family if not fonts or family in fonts else next((name for name in fallbacks if name in fonts), None)
            if not substitute: raise ValueError(f'No usable font for {role}: {family}. Run bookorder fonts and set a fallback.')
            resolved.append(substitute)
            for key in ('japanese', 'latin', 'family'):
                if settings.get(key) == family: settings['resolved_' + key] = substitute
            if family != substitute: warnings.append(f'{role}: {family} -> {substitute}')
        settings['requested_families'] = requested
        settings['resolved_families'] = list(dict.fromkeys(resolved + [f for f in fallbacks if f in fonts]))
    factor = {'compact': .8, 'standard': 1, 'spacious': 1.25}[tokens['layout']['density']]
    tokens['spacing'] = {'sm': .5 * factor, 'md': factor, 'lg': 1.75 * factor}
    report('design-report.json', {'theme': spec['theme'], 'font_fallbacks': warnings, 'available_fonts': fonts,
                                 'browser_fonts': 'CSS uses requested families and fallbacks; browser/EPUB reader availability differs.'})
    return tokens

def css_tokens(tokens):
    values = {f'color-{key}': value for key, value in tokens['colors'].items()}
    for role, settings in tokens['typography'].items():
        # CSS keeps the declared typography, rather than assuming the reader has PDF fonts.
        families = settings['requested_families'] + settings['fallback']
        values[f'font-{role}'] = ', '.join(json.dumps(name, ensure_ascii=False) for name in dict.fromkeys(families)) + (', monospace' if role == 'code' else ', serif')
        values[f'size-{role}'] = settings['size']; values[f'weight-{role}'] = settings['weight']
        values[f'line-{role}'] = settings['line_height']
    values.update({f'space-{key}': f'{value}rem' for key, value in tokens['spacing'].items()})
    values['page-size'] = tokens['page']['size']
    c = tokens['components']
    values.update({'callout-fill': 'var(--book-color-surface)' if c['callout'] == 'card' else 'transparent',
                   'callout-border': '0' if c['callout'] == 'plain' else '2px solid var(--book-color-secondary)',
                   'definition-border': '1px solid var(--book-color-secondary)' if c['definition'] == 'boxed' else '0',
                   'summary-fill': 'var(--book-color-surface)' if c['summary'] == 'shaded' else 'transparent',
                   'table-border': '1px solid var(--book-color-secondary)' if c['table'] == 'grid' else '0',
                   'table-stripe': 'var(--book-color-surface)' if c['table'] == 'striped' else 'transparent',
                   'paragraph-space': {'small': '.35em', 'medium': '.7em', 'large': '1.1em'}[tokens['layout']['paragraph_spacing']],
                   'heading-space': {'compact': '1em', 'standard': '1.4em', 'generous': '1.8em'}[tokens['layout']['heading_spacing']]})
    values['warning-fill'] = 'transparent' if c['warning'] == 'plain' else 'var(--book-color-surface)'
    values['warning-border'] = '1px solid var(--book-color-accent)' if c['warning'] == 'boxed' else '0'
    # A left accent is kept separate from the all-sides border.
    values['warning-left'] = '3px solid var(--book-color-accent)' if c['warning'] == 'accent-border' else values['warning-border']
    for key, value in tokens['page']['margin'].items(): values['margin-' + key] = value
    values['code-fill'] = 'var(--book-color-surface)' if c['code_block'] == 'technical' else 'transparent'
    values['caption-gap'] = '.5em' if c['figure_caption'] == 'compact' else '1em'
    return ':root {\n' + ''.join(f'  --book-{key}: {value};\n' for key, value in values.items()) + '}\n'

WEB_FONTS = {  # Latin OFL fonts bundled with the runtime; CJK fonts are too large to ship with web pages.
    'Inter': ('inter', [('Inter-Regular.ttf', 400, 'normal'), ('Inter-SemiBold.ttf', 600, 'normal'), ('Inter-Bold.ttf', 700, 'normal')]),
    'Source Serif 4': ('source-serif-4', [('SourceSerif4-Regular.otf', 400, 'normal'), ('SourceSerif4-It.otf', 400, 'italic'), ('SourceSerif4-Bold.otf', 700, 'normal')]),
    'JetBrains Mono': ('jetbrains-mono', [('JetBrainsMono-Regular.ttf', 400, 'normal'), ('JetBrainsMono-Bold.ttf', 700, 'normal')]),
}


def web_fonts(tokens, destination):
    """Copy used, bundled Latin web fonts with their OFL licence; returns @font-face CSS ('' if unavailable)."""
    import shutil
    used = {family for settings in tokens['typography'].values() for family in settings.get('requested_families', [])}
    rules = []
    for family, (slug, files) in WEB_FONTS.items():
        licence = next((p for p in (ROOT / 'third-party/licenses' / slug).glob('*') if p.is_file()), None) if (ROOT / 'third-party/licenses' / slug).is_dir() else None
        sources = [(ROOT / 'runtime/fonts' / name, weight, style) for name, weight, style in files]
        if family not in used or not licence or not all(path.is_file() for path, _, _ in sources): continue
        folder = destination / 'fonts'; folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(licence, folder / f'{slug}-LICENSE.txt')
        for path, weight, style in sources:
            shutil.copy2(path, folder / path.name)
            kind = 'truetype' if path.suffix == '.ttf' else 'opentype'
            rules.append(f'@font-face{{font-family:"{family}";src:url("fonts/{path.name}") format("{kind}");font-weight:{weight};font-style:{style};font-display:swap}}')
    return '\n'.join(rules) + ('\n' if rules else '')


def write_theme_css(tokens, destination):
    destination.mkdir(parents=True, exist_ok=True)
    package = theme_path(tokens['theme']) / 'css'
    files = []
    faces = web_fonts(tokens, destination)
    if faces:
        path = destination / 'fonts.css'; path.write_text(faces, encoding='utf-8'); files.append(path)
    for name in CSS_ORDER:
        path = destination / (name + '.css')
        text = css_tokens(tokens) if name == 'tokens' else (package / (name + '.css')).read_text(encoding='utf-8')
        path.write_text(text, encoding='utf-8'); files.append(path)
    custom = ROOT / 'custom.css'
    path = destination / 'custom.css'
    path.write_text(custom.read_text(encoding='utf-8') if custom.exists() else '', encoding='utf-8'); files.append(path)
    # Pandoc EPUB's --css embeds a flattened stylesheet. Custom CSS stays last.
    bundle = destination / 'book.css'
    bundle.write_text('\n'.join(path.read_text(encoding='utf-8') for path in files if path.name != 'fonts.css'), encoding='utf-8')
    return files, bundle

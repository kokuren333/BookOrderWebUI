"""Map shared typography/component semantics to Word paragraph styles."""
import re
import xml.etree.ElementTree as ET
from book_ir import registry

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
def q(name): return '{' + NS + '}' + name
def child(parent, name):
    found = parent.find(q(name))
    return found if found is not None else ET.SubElement(parent, q(name))
def set_attrs(element, **values):
    for key, value in values.items(): element.set(q(key), str(value))

def apply_styles(styles, tokens):
    components = {item['docx_style']: kind for kind, item in registry().items()}
    existing = {s.find(q('name')).get(q('val')): s for s in styles.findall(q('style')) if s.find(q('name')) is not None}
    for name in components:
        if name not in existing:
            element = ET.SubElement(styles, q('style'), {q('type'): 'paragraph', q('styleId'): name.replace(' ', '')})
            set_attrs(child(element, 'name'), val=name); set_attrs(child(element, 'basedOn'), val='BodyText'); existing[name] = element
    for name, style in existing.items():
        role = 'heading' if name in ('Book Title', 'Chapter Title', 'Section Heading', 'Subsection Heading') else 'code' if name in ('Code Block', 'Source Code', 'Code Listing', 'Terminal Session') else 'caption' if 'Caption' in name else 'footnote' if 'footnote' in name.lower() else 'body'
        setting = tokens['typography'][role]; fonts = setting['resolved_families']
        run = child(style, 'rPr'); set_attrs(child(run, 'rFonts'), ascii=setting.get('resolved_latin', fonts[0]), hAnsi=setting.get('resolved_latin', fonts[0]), eastAsia=setting.get('resolved_japanese', fonts[0]))
        points = float(setting['size'][:-2]); set_attrs(child(run, 'sz'), val=round(points * 2)); set_attrs(child(run, 'szCs'), val=round(points * 2))
        set_attrs(child(run, 'color'), val=tokens['colors']['primary' if role == 'heading' else 'text'][1:])
        set_attrs(child(run, 'b'), val='1' if setting['weight'] >= 600 else '0')
        paragraph = child(style, 'pPr'); set_attrs(child(paragraph, 'spacing'), line=round(setting['line_height'] * 240), lineRule='auto', after=90)
        if name in components:
            kind = components[name]
            if kind in ('Warning', 'warning', 'summary', 'definition', 'key-point'):
                set_attrs(child(paragraph, 'shd'), fill=tokens['colors']['surface'][1:], val='clear')
            if kind in ('warning', 'note', 'definition', 'key-point'):
                border = child(child(paragraph, 'pBdr'), 'left')
                set_attrs(border, val='single', sz=12, space=8, color=tokens['colors']['accent' if kind == 'warning' else 'primary'][1:])

def twips(value):
    number, unit = re.fullmatch(r'([0-9.]+)(mm|pt|cm|in)', value).groups()
    return round(float(number) * {'mm': 1440/25.4, 'cm': 1440/2.54, 'pt': 20, 'in': 1440}[unit])

def apply_page(document, tokens):
    width, height = {'A5': (148, 210), 'B5': (176, 250), 'A4': (210, 297), 'Letter': (215.9, 279.4)}[tokens['page']['size']]
    if tokens['page']['orientation'] == 'landscape': width, height = height, width
    margins = tokens['page']['margin']
    for section in document.iter(q('sectPr')):
        set_attrs(child(section, 'pgSz'), w=twips(f'{width}mm'), h=twips(f'{height}mm'), orient=tokens['page']['orientation'])
        set_attrs(child(section, 'pgMar'), top=twips(margins['top']), bottom=twips(margins['bottom']), left=twips(margins['inner']), right=twips(margins['outer']))

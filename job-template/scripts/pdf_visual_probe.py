"""Small, dependency-free visual probe for Typst-produced PDF content streams.

It records vector colors, text sizes, line weights and drawing anchors. It is
intentionally narrower than a general PDF interpreter; unsupported PDFs return
an explicit unavailable result instead of fabricated measurements.
"""
import re
import zlib
from pathlib import Path

NUMBER = rb"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
OBJECT = re.compile(rb"(?m)^(\d+)\s+0\s+obj\b(.*?)\bendobj", re.S)
PAGE = re.compile(rb"/Type\s*/Page\b")
CONTENTS = re.compile(rb"/Contents\s+(\d+)\s+0\s+R")
MEDIABOX = re.compile(rb"/MediaBox\s*\[\s*(" + NUMBER + rb")\s+(" + NUMBER + rb")\s+(" + NUMBER + rb")\s+(" + NUMBER + rb")\s*\]")
STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)
GROUP = re.compile(rb"(?:^|\n)q\s+(.*?)\s+Q(?:\n|$)", re.S)
RGB_FILL = re.compile(rb"(" + NUMBER + rb")\s+(" + NUMBER + rb")\s+(" + NUMBER + rb")\s+(?:scn|rg)\b")
RGB_STROKE = re.compile(rb"(" + NUMBER + rb")\s+(" + NUMBER + rb")\s+(" + NUMBER + rb")\s+(?:SCN|RG)\b")
FONT = re.compile(rb"/([A-Za-z0-9]+)\s+(" + NUMBER + rb")\s+Tf\b")
WIDTH = re.compile(rb"(" + NUMBER + rb")\s+w\b")
MATRIX = re.compile(rb"(" + NUMBER + rb")\s+(" + NUMBER + rb")\s+(" + NUMBER + rb")\s+(" + NUMBER + rb")\s+(" + NUMBER + rb")\s+(" + NUMBER + rb")\s+cm\b")
POINT = re.compile(rb"(" + NUMBER + rb")\s+(" + NUMBER + rb")\s+[ml]\b")
RESOURCES = re.compile(rb"/Resources\s+(\d+)\s+0\s+R")
XOBJECT = re.compile(rb"/([A-Za-z0-9]+)\s+(\d+)\s+0\s+R")
DRAW = re.compile(rb"/([A-Za-z0-9]+)\s+Do\b")
PIXELS = re.compile(rb"/Width\s+(\d+)\s*/Height\s+(\d+)")


def _color(match):
    if not match: return None
    values = [max(0, min(255, round(float(value) * 255))) for value in match.groups()]
    return "#" + "".join(f"{value:02X}" for value in values)


def _stream(body):
    match = STREAM.search(body)
    if not match: return None
    raw = match[1]
    if b"FlateDecode" in body[:match.start()]:
        try: return zlib.decompress(raw)
        except zlib.error: return None
    return raw


def inspect(path):
    path = Path(path)
    if not path.is_file(): return {"status": "unavailable", "reason": "PDF missing", "pages": []}
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        return {"status": "unavailable", "reason": "not a PDF", "pages": []}
    objects = {int(match[1]): match[2] for match in OBJECT.finditer(data)}
    pages = []
    for body in objects.values():
        if not PAGE.search(body): continue
        media = MEDIABOX.search(body)
        contents = CONTENTS.search(body)
        if not media or not contents: continue
        width, height = float(media[3]) - float(media[1]), float(media[4]) - float(media[2])
        stream = _stream(objects.get(int(contents[1]), b""))
        if stream is None:
            return {"status": "unavailable", "reason": "unsupported PDF content stream", "pages": []}
        runs, strokes, fills, images = [], [], [], []
        resource = RESOURCES.search(body)
        definitions = objects.get(int(resource[1]), b"") if resource else b""
        xobjects = {name: objects.get(int(number), b"") for name, number in XOBJECT.findall(definitions)}
        for group in GROUP.finditer(stream):
            chunk = group[1]
            matrices = list(MATRIX.finditer(chunk))
            matrix = matrices[-1] if matrices else None
            x = float(matrix[5]) if matrix else None
            y = height - float(matrix[6]) if matrix else None
            fill = _color(RGB_FILL.search(chunk))
            stroke = _color(RGB_STROKE.search(chunk))
            widths = list(WIDTH.finditer(chunk))
            line = float(widths[-1][1]) if widths else None
            fonts = list(FONT.finditer(chunk))
            if fonts and b"BT" in chunk:
                font = fonts[-1]
                runs.append({"size_pt": round(float(font[2]), 2), "font_ref": font[1].decode("ascii"),
                             "color": fill, "x_pt": round(x, 2) if x is not None else None,
                             "y_pt": round(y, 2) if y is not None else None})
            if line is not None and (b"\nS" in chunk or b" S" in chunk):
                strokes.append({"width_pt": round(line, 3), "color": stroke,
                                "x_pt": round(x, 2) if x is not None else None,
                                "y_pt": round(y, 2) if y is not None else None})
            if fill is not None and (b"\nf" in chunk or b" f" in chunk):
                points = [(float(point[1]), float(point[2])) for point in POINT.finditer(chunk)]
                bbox = None
                if points and x is not None and y is not None:
                    bbox = [round(x + min(px for px, _ in points), 2), round(y + min(py for _, py in points), 2),
                            round(x + max(px for px, _ in points), 2), round(y + max(py for _, py in points), 2)]
                fills.append({"color": fill, "bbox_pt": bbox})
            draw = DRAW.search(chunk)
            if draw and matrix and b"/Subtype/Image" in xobjects.get(draw[1], b""):
                a, b, c, d, e, f = (float(value) for value in matrix.groups())
                corners = [(e, f), (e+a, f+b), (e+c, f+d), (e+a+c, f+b+d)]
                pixels = PIXELS.search(xobjects[draw[1]])
                images.append({"xobject": draw[1].decode("ascii"),
                               "bbox_pt": [round(min(px for px, _ in corners), 2), round(height - max(py for _, py in corners), 2),
                                           round(max(px for px, _ in corners), 2), round(height - min(py for _, py in corners), 2)],
                               "dimensions_px": {"width": int(pixels[1]), "height": int(pixels[2])} if pixels else None})
        pages.append({"page": len(pages) + 1, "width_pt": round(width, 2), "height_pt": round(height, 2),
                      "text": runs, "strokes": strokes, "fills": fills, "images": images})
    if not pages: return {"status": "unavailable", "reason": "no inspectable pages", "pages": []}
    return {"status": "measured", "method": "Typst PDF vector streams", "pages": pages}

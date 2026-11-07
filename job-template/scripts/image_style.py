"""Keep generated images in the book's design.

Generated illustrations drift: each prompt is answered in a slightly different style, and a set of individually
nice pictures looks pasted into the book. Three things bind them to the approved design:

1. plan/image-style.md — the image style sheet. Claude writes it from the approved design (book.design.yaml, the
   resolved StyleBible palette, the reference-book analysis): medium, line, texture, lighting, palette use, paper
   and background treatment, composition and negative space, what never appears. Its "Prompt prefix" section is sent
   verbatim with every image request; its hash is part of each request, so editing it regenerates the images.
2. A style anchor — one approved sample image (design/image-anchor.png). Every request passes it to Codex as a
   reference image ("match this series"), so the images read as one set. `bookorder images samples` makes
   candidates from the style sheet; the user picks one with Claude; `bookorder images anchor <png>` fixes it.
3. A check — palette conformance of every generated PNG against the StyleBible palette (and its tints toward the
   paper colour), plus a contact sheet (proofs/images.html) that shows the whole series side by side for Claude and
   the user to review. Conformance is advisory; the human/Claude review is what accepts an image.
"""
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

from common import ROOT

STYLE_SHEET = ROOT / "plan/image-style.md"
ANCHOR = ROOT / "design/image-anchor.png"
SAMPLES = ROOT / "design/image-samples"
REPORT = ROOT / "reports/image-style-check.json"
SHEET = ROOT / "proofs/images.html"
CONFORMANCE_WARN = 0.6


def style_sheet_text():
    return STYLE_SHEET.read_text(encoding="utf-8") if STYLE_SHEET.is_file() else ""


def prompt_prefix():
    """The '## Prompt prefix' section of the style sheet (or the whole sheet when it has no such section)."""
    text = style_sheet_text()
    match = re.search(r"^##\s*Prompt prefix\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S | re.I)
    return (match.group(1) if match else text).strip()


def binding():
    """What a request is bound to; included in the request so a style change regenerates the images."""
    value = {}
    if STYLE_SHEET.is_file(): value["style_sheet_sha256"] = hashlib.sha256(STYLE_SHEET.read_bytes()).hexdigest()
    if ANCHOR.is_file(): value["style_anchor_sha256"] = hashlib.sha256(ANCHOR.read_bytes()).hexdigest()
    return value


# ---------------------------------------------------------------- pixels

def _pixels(path, max_samples=60000):
    """Sampled RGB pixels of an 8-bit non-interlaced PNG (RGB/RGBA/grey), pure Python; Pillow when available."""
    try:
        from PIL import Image  # optional, much faster
        with Image.open(path) as image:
            image = image.convert("RGBA"); image.thumbnail((320, 320))
            return [(r, g, b) for r, g, b, a in image.getdata() if a > 32]
    except ImportError:
        pass
    data = Path(path).read_bytes(); at = 8; idat = []; width = height = depth = ctype = interlace = None
    while at + 12 <= len(data):
        length = struct.unpack(">I", data[at:at + 4])[0]; tag = data[at + 4:at + 8]; body = data[at + 8:at + 8 + length]
        if tag == b"IHDR": width, height, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT": idat.append(body)
        elif tag == b"IEND": break
        at += 12 + length
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(ctype)
    if depth != 8 or not channels or interlace: raise ValueError("unsupported PNG for palette check")
    raw = zlib.decompress(b"".join(idat)); stride = width * channels
    step = max(1, int((width * height / max_samples) ** 0.5))
    previous = bytearray(stride); out = []; pos = 0
    for y in range(height):
        kind = raw[pos]; line = bytearray(raw[pos + 1:pos + 1 + stride]); pos += 1 + stride
        if kind == 1:
            for i in range(channels, stride): line[i] = (line[i] + line[i - channels]) & 255
        elif kind == 2:
            for i in range(stride): line[i] = (line[i] + previous[i]) & 255
        elif kind == 3:
            for i in range(stride): line[i] = (line[i] + ((line[i - channels] if i >= channels else 0) + previous[i]) // 2) & 255
        elif kind == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0; b = previous[i]; c = previous[i - channels] if i >= channels else 0
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        previous = line
        if y % step: continue
        for x in range(0, width, step):
            i = x * channels
            if channels >= 3:
                if channels == 4 and line[i + 3] <= 32: continue
                out.append((line[i], line[i + 1], line[i + 2]))
            else: out.append((line[i],) * 3)
    return out


def _hex(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _segment_distance(p, a, b):
    """Distance from colour p to the segment a–b in RGB (tints/shades between a palette colour and paper/ink)."""
    ab = [b[i] - a[i] for i in range(3)]; ap = [p[i] - a[i] for i in range(3)]
    denom = sum(x * x for x in ab) or 1
    t = max(0.0, min(1.0, sum(ap[i] * ab[i] for i in range(3)) / denom))
    return sum((p[i] - (a[i] + t * ab[i])) ** 2 for i in range(3)) ** 0.5


def conformance(path, palette, tolerance=48):
    """Share of the image's dominant colours that lie on the palette's tint/shade lines. 1.0 = fully on palette."""
    pixels = _pixels(path)
    if not pixels: return {"score": None, "detail": "no opaque pixels"}
    buckets = {}
    for r, g, b in pixels:
        key = (r >> 4, g >> 4, b >> 4); buckets[key] = buckets.get(key, 0) + 1
    total = sum(buckets.values()); dominant = []; covered = 0
    for key, count in sorted(buckets.items(), key=lambda kv: -kv[1]):
        dominant.append((tuple(v * 16 + 8 for v in key), count)); covered += count
        if covered >= .85 * total or len(dominant) >= 40: break
    colors = [_hex(c) for c in palette.values() if isinstance(c, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", c)]
    paper = _hex(palette.get("background", "#FFFFFF")) if re.fullmatch(r"#[0-9A-Fa-f]{6}", str(palette.get("background", ""))) else (255, 255, 255)
    ink = _hex(palette.get("ink", "#18181B")) if re.fullmatch(r"#[0-9A-Fa-f]{6}", str(palette.get("ink", ""))) else (24, 24, 27)
    anchors = colors + [paper, ink, (255, 255, 255)]
    on = 0; off = []
    for color, count in dominant:
        distance = min([_segment_distance(color, a, paper) for a in anchors] + [_segment_distance(color, a, ink) for a in anchors])
        if distance <= tolerance: on += count
        else: off.append("#%02X%02X%02X" % color)
    return {"score": round(on / covered, 3), "off_palette_colours": off[:8]}


def check(palette, assets_dir=None):
    """Conformance of every generated image; writes reports/image-style-check.json."""
    folder = Path(assets_dir or ROOT / "source/assets/images")
    results = []
    for path in sorted(folder.glob("*.png")):
        try: value = conformance(path, palette)
        except Exception as exc: value = {"score": None, "detail": str(exc)[:200]}
        value["file"] = path.relative_to(ROOT).as_posix()
        value["severity"] = "medium" if value.get("score") is not None and value["score"] < CONFORMANCE_WARN else "ok"
        results.append(value)
    report = {"style_sheet": STYLE_SHEET.is_file(), "anchor": ANCHOR.is_file(), "threshold": CONFORMANCE_WARN, "images": results}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def contact_sheet(palette=None):
    """proofs/images.html: anchor, samples and every generated image with its caption intent and score."""
    report = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.is_file() else {"images": []}
    scores = {item["file"]: item for item in report.get("images", [])}
    def card(path, label):
        rel = "../" + path.relative_to(ROOT).as_posix()
        score = scores.get(path.relative_to(ROOT).as_posix(), {}).get("score")
        return (f'<figure><img src="{rel}" loading="lazy"><figcaption>{label}'
                + (f' · palette {score:.0%}' if isinstance(score, (int, float)) else "") + "</figcaption></figure>")
    cards = []
    if ANCHOR.is_file(): cards.append(card(ANCHOR, "<b>style anchor</b>"))
    cards += [card(p, "sample " + p.stem) for p in sorted(SAMPLES.glob("*.png"))] if SAMPLES.is_dir() else []
    cards += [card(p, p.stem) for p in sorted((ROOT / "source/assets/images").glob("*.png"))]
    swatches = "".join(f'<span style="background:{v}" title="{k} {v}"></span>' for k, v in (palette or {}).items())
    html = ("<!doctype html><meta charset=utf-8><title>Image series</title><style>body{font:14px system-ui;margin:24px;background:#f4f4f2}"
            "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}figure{margin:0;background:#fff;padding:8px}"
            "img{width:100%;display:block}.sw span{display:inline-block;width:28px;height:28px;margin-right:4px}</style>"
            f"<h1>Image series</h1><p class=sw>{swatches}</p><main>{''.join(cards)}</main>")
    SHEET.parent.mkdir(parents=True, exist_ok=True); SHEET.write_text(html, encoding="utf-8")
    return SHEET


# ---------------------------------------------------------------- Codex provider

def codex_prompt(request, out_path, width_px, height_px):
    prefix = prompt_prefix()
    art = request.get("art_direction") or {}
    palette = ", ".join(f"{k} {v}" for k, v in (art.get("palette") or {}).items())
    lines = [
        "Generate ONE book illustration with your image generation tool, then save it as a PNG file.",
        "",
        "## Book image style (binding — every image in this book follows it)",
        prefix or "(no style sheet yet: restrained editorial illustration in the book palette)",
        "",
        f"Palette (use only these hues and their tints toward the paper colour): {palette}",
        f"Tone: {art.get('visual_tone')}; realism: {art.get('illustration_style')}; composition: {request.get('composition')}; "
        f"background: {art.get('background_treatment')}.",
    ]
    if ANCHOR.is_file():
        lines.append("The attached reference image is this book's STYLE ANCHOR: match its medium, line weight, texture, palette use, lighting and "
                     "level of detail exactly, so the new image reads as part of the same series. Do not copy its subject or layout.")
    lines += ["", "## This image",
              f"Subject: {request.get('subject')}", f"Purpose in the book: {request.get('purpose')}",
              f"Context (the caption is printed by the book, not in the image): {request.get('context')}",
              "Must show: " + ("; ".join(request.get("must_show") or []) or "(see subject)"),
              "Must not show: " + "; ".join(request.get("must_not_show") or []),
              "No text, letters, numbers, labels, logos, watermarks or signatures anywhere in the image.",
              "", "## File",
              f"Final size: at least {width_px}×{height_px} px, aspect ratio {request.get('preferred_aspect_ratio')}. If the generated image is smaller "
              "or another ratio, centre-crop to the ratio and upscale with a high-quality filter (e.g. Pillow LANCZOS) to at least that size.",
              f"Save it as an 8-bit RGB PNG, non-interlaced, at exactly this path (relative to the working folder): {out_path}",
              "Do not create or modify any other file in this folder. Reply with one line: the saved path and its pixel size."]
    return "\n".join(lines)


class CodexImageProvider:
    """project.json image_generation.provider = "codex": Codex CLI's image generation, bound to the style sheet and anchor."""
    name = "codex"

    def __init__(self, project):
        settings = dict((project.get("image_generation") or {}))
        self.cli = settings.get("cli") or "codex"; self.model_name = settings.get("model")
        self.timeout = float(settings.get("timeout_minutes") or 15) * 60
        self.model = "codex-imagegen" + (f"/{self.model_name}" if self.model_name else "")

    def generate(self, request, out_rel=None, anchor=True):
        import math, shutil, subprocess, time
        from image_assets import MIN_DPI, inspect_png
        executable = shutil.which(self.cli)
        if not executable: raise RuntimeError(f"{self.cli} not found on PATH (Codex CLI is needed for image generation)")
        width = max(1, math.ceil(float(request["final_width_mm"]) / 25.4 * MIN_DPI))
        height = max(1, math.ceil(float(request["final_height_mm"]) / 25.4 * MIN_DPI))
        out_rel = out_rel or f".build/imagegen/{request['asset_id']}.png"
        out = ROOT / out_rel; out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists(): out.unlink()
        prompt = codex_prompt(request, out_rel, width, height)
        log_dir = ROOT / "research/delegations" / ("imagegen-" + time.strftime("%Y%m%d-%H%M%S") + "-" + str(request["asset_id"]))
        log_dir.mkdir(parents=True, exist_ok=True); (log_dir / "prompt.md").write_text(prompt, encoding="utf-8")
        args = [executable, "exec", "--cd", str(ROOT), "--skip-git-repo-check", "--sandbox", "workspace-write",
                "--enable", "image_generation", "--output-last-message", str(log_dir / "last-message.md")]
        if self.model_name: args += ["--model", str(self.model_name)]
        if anchor and ANCHOR.is_file(): args += ["--image", str(ANCHOR)]
        args.append("-")
        with open(log_dir / "events.log", "w", encoding="utf-8") as log:
            result = subprocess.run(args, input=prompt, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, encoding="utf-8",
                                    errors="replace", timeout=self.timeout)
        if result.returncode: raise RuntimeError(f"codex exited with {result.returncode}; see {log_dir.relative_to(ROOT).as_posix()}/events.log")
        if not out.is_file(): raise RuntimeError(f"codex did not save {out_rel}; see {log_dir.relative_to(ROOT).as_posix()}")
        info = inspect_png(out)
        if info.get("error"): raise RuntimeError(f"generated file is not a usable PNG ({info['error']}); ask for an 8-bit non-interlaced PNG")
        data = out.read_bytes()
        return {"bytes": data, "dimensions_px": {"width": info["width"], "height": info["height"]}, "model": self.model,
                "seed": int(hashlib.sha256(data).hexdigest()[:8], 16)}


def samples(project, style, count=3, subject=None):
    """Style-anchor candidates from the style sheet: the same neutral subject in the book's image style."""
    if not STYLE_SHEET.is_file(): raise ValueError("Write plan/image-style.md first (skills/design/image-style.md)")
    provider = CodexImageProvider(project); SAMPLES.mkdir(parents=True, exist_ok=True); made = []
    art = {"visual_tone": style["tone"], "palette": style["palette"], "illustration_style": style["imagery"]["realism"],
           "background_treatment": style["imagery"]["palette_relationship"]}
    for number in range(1, count + 1):
        request = {"asset_id": f"sample-{number}", "final_width_mm": 120, "final_height_mm": 80, "preferred_aspect_ratio": "3:2",
                   "subject": subject or "a calm, generic scene that shows the style (objects and space, no people, no text)",
                   "purpose": f"style anchor candidate {number} of {count}: show the medium, line, texture and palette use",
                   "context": "", "must_show": [], "must_not_show": ["text", "letters", "labels"], "composition": style["imagery"]["composition"],
                   "art_direction": art}
        rel = f"design/image-samples/sample-{number}.png"
        provider.generate(request, out_rel=rel, anchor=False); made.append(rel)
    return made


def set_anchor(path):
    import shutil
    source = Path(path).resolve()
    if not source.is_file() or source.suffix.lower() != ".png": raise ValueError("Choose a PNG (for example design/image-samples/sample-2.png)")
    ANCHOR.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, ANCHOR)
    return ANCHOR

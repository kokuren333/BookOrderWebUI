"""Provider-independent generation and print QA for accepted pictorial assets.

Only the visual review can admit an image. No provider is selected by default;
fake is an explicit, deterministic integration-test provider.
"""
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import re
import struct
import zlib

from common import ROOT, as_list, read_project, write_yaml
from figure_spec import resolve as resolve_figure
from schema import validate_schema

REQUEST_SCHEMA = "bookorder/image-generation-request@1"
ASSET_SCHEMA = "bookorder/visual-asset@1"
REPORT = "reports/image-assets-check.yaml"
MIN_DPI = 300  # chartkit also renders print rasters at 300 dpi
PROMPT_VERSION = "bookorder-image-prompt@1"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _schema(name):
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _write_json_if_changed(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if not path.is_file() or path.read_text(encoding="utf-8") != body:
        path.write_text(body, encoding="utf-8")


def _ratio(value):
    try:
        a, b = str(value).replace("x", ":").split(":", 1)
        return float(a) / float(b)
    except (ValueError, ZeroDivisionError):
        return None


def _truth(value):
    return value is True or str(value).strip().lower() in ("true", "yes", "1")


def _safe_image_path(path):
    value = Path(str(path or ""))
    if value.is_absolute() or ".." in value.parts or value.suffix.lower() != ".png" or value.parts[:3] != ("source", "assets", "images"):
        raise ValueError("Generated image path must be a PNG under source/assets/images/")
    return value


def request_from_asset(asset, style, layout, *, provider=None):
    """Translate editorial intent and resolved book design into a neutral request."""
    if asset.get("type") != "image": raise ValueError("Only image assets can become ImageGenerationRequest")
    if not re.fullmatch(r"fig-[a-z0-9-]+", str(asset.get("id") or "")):
        raise ValueError("Generated image asset ID must be a safe fig- identifier")
    _safe_image_path(asset.get("path"))
    basis = asset.get("factuality") or ("illustrative" if asset.get("factual_basis") == "illustrative" else
                                      "conceptual" if (asset.get("information_shape") or {}).get("kind") == "abstract" else "factual")
    if basis not in ("decorative", "illustrative", "conceptual", "factual"): raise ValueError("Unknown image factuality")
    if basis == "factual": raise ValueError("Factual visual must use a source-grounded chart, diagram, table or screenshot")
    if (asset.get("information_shape") or {}).get("kind") != "abstract": raise ValueError("Imagegen requires an abstract/pictorial intent")
    if asset.get("role") not in style["imagery"].get("allowed_roles", []):
        raise ValueError("Image role is not allowed by the resolved StyleBible")
    if style["imagery"].get("text_in_image") or asset.get("typography_policy") not in (None, "forbidden"):
        raise ValueError("Generated image text is forbidden; render headings, captions and labels in the book")
    from style_bible import validate as validate_style
    style = validate_style(style)
    tokens = {"layout_spec": layout, "page": {"size": layout["page_size"],
              "margin": {"top": layout["page"]["margin_top_mm"], "bottom": layout["page"]["margin_bottom_mm"],
                         "inner": layout["page"]["margin_inner_mm"], "outer": layout["page"]["margin_outer_mm"]}}}
    geometry = resolve_figure(asset.get("geometry") or {}, tokens, kind="image")
    ratio = _ratio(geometry.get("aspect_ratio")) or 1.5
    width = float(geometry["width_mm"])
    height = float(geometry["height_mm"] or width / ratio)
    art = {"visual_tone": style["tone"], "palette": style["palette"],
           "contrast": style["accessibility"]["minimum_contrast"], "complexity": style["imagery"]["abstraction"],
           "density": style["visual_grammar"]["rhythm"], "composition_tendency": style["imagery"]["composition"],
           "illustration_style": style["imagery"]["realism"], "photography_preference": style["imagery"]["realism"],
           "background_treatment": style["imagery"]["palette_relationship"], "imagery": style["imagery"]}
    payload = {"schema": REQUEST_SCHEMA, "request_id": "igr-" + str(asset["id"]), "asset_id": str(asset["id"]),
               "purpose": str(asset.get("purpose") or ""), "semantic_role": str(asset.get("role") or "editorial_illustration"),
               "chapter_id": str(asset.get("chapter") or ""), "slot_id": str(asset.get("device") or asset["id"]),
               "source_ids": [str(s) for s in as_list(asset.get("source_ids"))], "factuality": basis,
               "subject": str(asset.get("subject") or asset.get("prompt") or asset.get("purpose") or ""),
               "context": str(asset.get("context") or asset.get("caption") or ""),
               "must_show": [str(s) for s in as_list(asset.get("must_show"))],
               "must_not_show": [str(s) for s in as_list(asset.get("must_not_show"))] + ["text", "letters", "labels", "captions"],
               "composition": str(asset.get("composition") or style["imagery"]["composition"]),
               "art_direction": art, "preferred_aspect_ratio": geometry.get("aspect_ratio") or "3:2",
               "preferred_span": geometry["span"], "placement": geometry["placement"],
               "final_width_mm": round(width, 2), "final_height_mm": round(height, 2),
               "typography_policy": "forbidden", "provider": provider or "none",
               "provider_status": "ready" if provider else "pending_provider", "prompt_version": PROMPT_VERSION,
               "required": not _truth(asset.get("optional")), "file_path": str(_safe_image_path(asset.get("path"))).replace("\\", "/")}
    validate_schema(payload, _schema("image-generation-request.schema.json"))
    return payload


class ImageGenerationProvider:
    name = "abstract"
    model = ""

    def generate(self, request):
        raise NotImplementedError


class PendingProvider(ImageGenerationProvider):
    name = "none"

    def generate(self, request):
        raise RuntimeError("pending_provider: configure an image generation provider")


def _png_chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)


class FakeImageProvider(ImageGenerationProvider):
    """Deterministic patterned print raster. It contains no typography or factual depiction."""
    name = "fake"
    model = "fake-pattern-v1"

    def generate(self, request):
        width = max(1, math.ceil(float(request["final_width_mm"]) / 25.4 * MIN_DPI))
        height = max(1, math.ceil(float(request["final_height_mm"]) / 25.4 * MIN_DPI))
        if width * height > 14_000_000: raise ValueError("Fake image exceeds fixture pixel budget")
        seed = _hash({"asset_id": request["asset_id"], "role": request["semantic_role"],
                      "ratio": request["preferred_aspect_ratio"], "subject": request["subject"]})
        palette = request["art_direction"]["palette"]
        roles = ("accent", "secondary_accent", "success", "muted", "surface")
        colors = [tuple(int(palette[role][index:index+2], 16) for index in (1, 3, 5))
                  for role in roles if role in palette]
        if not colors: raise ValueError("Fake provider needs a resolved StyleBible palette")
        border_color = tuple(int(palette["ink"][index:index+2], 16) for index in (1, 3, 5))
        compressor = zlib.compressobj(6)
        chunks = []
        for y in range(height):
            row = bytearray(b"\x00")
            band = (y * 5 // height) % 5
            for x in range(width):
                tile = ((x * 7 // width) + band + int(seed[(x * 7 // width) % 16], 16)) % len(colors)
                border = x < 5 or y < 5 or x >= width - 5 or y >= height - 5
                row.extend(border_color if border else colors[tile])
            chunks.append(compressor.compress(bytes(row)))
        chunks.append(compressor.flush())
        png = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        png += _png_chunk(b"IDAT", b"".join(chunks)) + _png_chunk(b"IEND", b"")
        return {"bytes": png, "dimensions_px": {"width": width, "height": height}, "model": self.model,
                "seed": int(seed[:8], 16)}


def provider_for(project):
    name = ((project.get("image_generation") or {}).get("provider") or "none").lower()
    if name == "fake": return FakeImageProvider()
    if name in ("none", "disabled"): return PendingProvider()
    raise ValueError(f"Image provider {name!r} is not installed; no real API is called")


def inspect_png(path):
    try:
        data = Path(path).read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n": raise ValueError("not PNG")
        at = 8; width = height = None; bit_depth = color_type = interlace = None; compressed = []; finished = False
        while at + 12 <= len(data):
            length = struct.unpack(">I", data[at:at+4])[0]
            tag = data[at+4:at+8]; body = data[at+8:at+8+length]
            crc = struct.unpack(">I", data[at+8+length:at+12+length])[0]
            if len(body) != length or zlib.crc32(tag + body) & 0xffffffff != crc: raise ValueError("bad PNG chunk")
            if tag == b"IHDR": width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if tag == b"IDAT": compressed.append(body)
            at += 12 + length
            if tag == b"IEND": finished = True; break
        if not finished or not width or not height or not compressed: raise ValueError("incomplete PNG")
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
        if bit_depth != 8 or channels is None or interlace != 0 or width * height > 50_000_000:
            raise ValueError("unsupported or oversized PNG pixel format")
        raw = zlib.decompress(b"".join(compressed))
        stride = 1 + width * channels
        if len(raw) != height * stride or any(raw[y * stride] > 4 for y in range(height)):
            raise ValueError("invalid PNG scanlines")
        return {"width": width, "height": height, "sha256": hashlib.sha256(data).hexdigest()}
    except (OSError, ValueError, struct.error, zlib.error) as exc:
        return {"error": str(exc)}


def _metadata(request, provider, *, status, previous=None, generated=None):
    previous = previous or {}
    value = {"schema": ASSET_SCHEMA, "asset_id": request["asset_id"], "kind": "generated-image",
             "source_request_id": request["request_id"], "provider": provider.name, "model": generated.get("model") if generated else previous.get("model"),
             "created_at": previous.get("created_at") or (now() if generated else None), "file_path": request["file_path"],
             "dimensions_px": generated.get("dimensions_px") if generated else previous.get("dimensions_px"),
             "final_width_mm": request["final_width_mm"], "final_height_mm": request["final_height_mm"],
             "effective_dpi": previous.get("effective_dpi"), "prompt_hash": _hash(request),
             "prompt_version": PROMPT_VERSION, "source_ids": request["source_ids"], "generation_status": status,
             "qa_status": "pending", "accepted": False, "rejection_reasons": [], "seed": generated.get("seed") if generated else previous.get("seed"),
             "required": request["required"], "art_direction": request["art_direction"], "placement": request["placement"],
             "preferred_aspect_ratio": request["preferred_aspect_ratio"], "typography_policy": request["typography_policy"]}
    validate_schema(value, _schema("visual-asset.schema.json"))
    return value


def prepare(plan_assets, decisions, style, layout, project=None, root=None, provider=None):
    """Generate only accepted image candidates and write request/asset artifacts."""
    root = Path(root or ROOT); project = project or read_project(); provider = provider or provider_for(project)
    results = []
    for asset in plan_assets:
        if asset.get("type") != "image" or decisions.get(str(asset.get("id"))) != "accepted": continue
        request = request_from_asset(asset, style, layout, provider=None if provider.name == "none" else provider.name)
        meta_dir = root / "source/assets/generated"
        request_path = meta_dir / f"{asset['id']}.request.json"
        metadata_path = meta_dir / f"{asset['id']}.json"
        _write_json_if_changed(request_path, request)
        previous = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
        output = root / request["file_path"]
        if provider.name == "none":
            meta = _metadata(request, provider, status="pending_provider")
        elif (previous.get("prompt_hash") == _hash(request) and previous.get("generation_status") == "generated"
              and output.is_file() and inspect_png(output).get("width")):
            meta = previous
        else:
            try:
                generated = provider.generate(request)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(generated["bytes"])
                meta = _metadata(request, provider, status="generated", generated=generated)
            except Exception as exc:
                meta = _metadata(request, provider, status="failed")
                meta["rejection_reasons"] = [str(exc)]
        _write_json_if_changed(metadata_path, meta)
        results.append(meta)
    return results


def check(plan_assets, decisions, *, root=None, write=True):
    root = Path(root or ROOT); checks = []; seen = {}
    for asset in plan_assets:
        if asset.get("type") != "image": continue
        ident = str(asset.get("id")); decision = decisions.get(ident)
        if decision == "rejected": continue
        if decision != "accepted": continue
        path = root / "source/assets/generated" / f"{ident}.json"
        meta = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        required = not _truth(asset.get("optional"))
        reasons = []
        if not meta: reasons.append("VisualAsset metadata missing")
        else:
            request_path = root / "source/assets/generated" / f"{ident}.request.json"
            try: request = json.loads(request_path.read_text(encoding="utf-8"))
            except (OSError, ValueError): request = None
            if not request or _hash(request) != meta.get("prompt_hash"):
                reasons.append("ImageGenerationRequest or prompt hash missing/stale")
            elif (request.get("final_width_mm") != meta.get("final_width_mm") or
                  request.get("final_height_mm") != meta.get("final_height_mm") or
                  request.get("provider_status") != "ready" or
                  request.get("source_ids") != meta.get("source_ids") or
                  request.get("art_direction") != meta.get("art_direction")):
                reasons.append("VisualAsset does not match the resolved print request")
            if meta.get("generation_status") != "generated": reasons.append(meta.get("generation_status") or "generation failed")
            if meta.get("source_request_id") != "igr-" + ident or not meta.get("prompt_hash") or not meta.get("prompt_version") or not meta.get("provider") or not meta.get("model") or not meta.get("created_at"):
                reasons.append("generation provenance incomplete")
            try: image = inspect_png(root / _safe_image_path(meta.get("file_path")))
            except ValueError as exc: image = {"error": str(exc)}
            if image.get("error"): reasons.append("missing or invalid image: " + image["error"])
            else:
                width, height = image["width"], image["height"]
                if meta.get("dimensions_px") != {"width": width, "height": height}:
                    reasons.append("VisualAsset dimensions differ from the image file")
                expected = float(meta["final_width_mm"]) / float(meta["final_height_mm"])
                if abs(width / height / expected - 1) > .08: reasons.append("aspect ratio differs from request by over 8%")
                dpi = min(width / float(meta["final_width_mm"]), height / float(meta["final_height_mm"])) * 25.4
                meta["effective_dpi"] = round(dpi, 1)
                if dpi < MIN_DPI - 0.1: reasons.append(f"effective DPI {dpi:.1f} below {MIN_DPI}")
                if width < math.ceil(float(meta["final_width_mm"]) / 25.4 * MIN_DPI - .01) or height < math.ceil(float(meta["final_height_mm"]) / 25.4 * MIN_DPI - .01):
                    reasons.append("minimum pixel dimensions below print policy")
                if image["sha256"] in seen: reasons.append("duplicate image bytes with " + seen[image["sha256"]])
                seen[image["sha256"]] = ident
            if meta.get("typography_policy") != "forbidden": reasons.append("text in generated image is not permitted")
            if meta.get("accepted") is False and meta.get("qa_status") == "rejected": reasons.append("rejected asset cannot be used")
            meta["qa_status"] = "fail" if reasons else "pass"
            meta["accepted"] = not reasons
            meta["rejection_reasons"] = reasons
            _write_json_if_changed(path, meta)
        for reason in reasons:
            checks.append({"asset_id": ident, "severity": "high" if required else "medium", "category": "image_asset_qa",
                           "detail": reason, "required": required})
    result = {"schema": "bookorder/image-assets-check@1", "summary": {"high": sum(c["severity"] == "high" for c in checks),
              "medium": sum(c["severity"] == "medium" for c in checks), "status": "fail" if any(c["severity"] == "high" for c in checks) else "warn" if checks else "pass"},
              "checks": checks, "provider_activity": {"real_api_requests": 0, "available_adapters": ["fake", "pending"]},
              "routed_to_imagegen": [a["id"] for a in plan_assets if a.get("type") == "image" and decisions.get(str(a.get("id"))) == "accepted"],
              "not_routed": [{"id": a.get("id"), "type": a.get("type"), "decision": decisions.get(str(a.get("id")))}
                             for a in plan_assets if a.get("type") != "image" or decisions.get(str(a.get("id"))) != "accepted"]}
    if write: write_yaml(root / REPORT, result, "Generated image routing and print QA; required high findings block completion.")
    return result

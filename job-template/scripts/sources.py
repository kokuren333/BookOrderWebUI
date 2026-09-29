"""Stable source registry and ingestion. Every supplied source is attempted and its content persisted.

Registering a URL is not reading it: a source only becomes fully_ingested when readable content has been
extracted and stored under research/<origin>/<id>/source.md, or when the agent submits extracted content.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import urllib.error
import urllib.request

from common import ROOT, read_project, run, tool, write_json

INDEX = ROOT / "research/index.json"
STATUS_FILE = ROOT / "research/source-status.json"
PENDING = ("pending", "fetching", "needs_agent_fetch", "needs_agent_extraction")
TERMINAL = ("fully_ingested", "partially_ingested", "unavailable", "duplicate")
USABLE = ("fully_ingested", "partially_ingested")
MIN_FULL_CHARS = 600
PAYWALL = re.compile(r"subscribe to (?:continue|read)|sign in to (?:continue|read)|enable javascript|please enable cookies|"
                     r"access denied|are you a robot|続きを読むには|有料会員|会員登録が必要|ログインして(?:続き|全文)", re.I)
DROP_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "iframe", "button", "template", "select"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
KEEP_ATTRS = {"href", "src", "alt", "colspan", "rowspan", "title"}
PANDOC_FORMATS = {".docx": "docx", ".odt": "odt", ".epub": "epub", ".rtf": "rtf", ".ipynb": "ipynb", ".html": "html", ".htm": "html",
                  ".xhtml": "html", ".tex": "latex", ".rst": "rst", ".org": "org", ".textile": "textile"}
TEXT_EXT = {".md", ".markdown", ".txt", ".csv", ".tsv", ".json", ".yaml", ".yml", ".xml", ".bib"}


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_url(url):
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_")])
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def empty_index():
    return {"format": "bookorder-research-index", "version": 1, "next_id": 1, "sources": []}


def load_index():
    if not INDEX.is_file(): return empty_index()
    return json.loads(INDEX.read_text(encoding="utf-8"))


def save_index(index):
    write_json(INDEX, index)
    write_json(STATUS_FILE, status_report(index))


def by_id(index):
    return {source["id"]: source for source in index["sources"]}


def get(index, identifier):
    source = by_id(index).get(identifier)
    if not source: raise ValueError(f"Unknown source ID: {identifier}")
    return source


def folder(source):
    return ROOT / "research" / ("supplied" if source["origin"] == "supplied" else "discovered") / source["id"]


def allocate(index):
    identifier = f"src-{index['next_id']:04d}"
    index["next_id"] += 1
    return identifier


def register(index, *, kind, url=None, path=None, origin="supplied", original_name=None, **extra):
    """Register a source with a new, permanent ID. IDs are never reused or renumbered."""
    identifier = allocate(index)
    source = {"id": identifier, "origin": origin, "kind": kind, "url": url, "path": path, "original_name": original_name,
              "normalized": normalize_url(url) if url else None, "ingest_status": "pending", "attempts": [],
              "title": None, "author": None, "published": None, "site": None, "source_type": None, "language": None,
              "retrieved_at": None, "chars": 0, "sha256": None, "content_path": None, "raw_path": None,
              "limitations": [], "duplicate_of": None, "post_draft": False, "added_at": now()}
    source.update({k: v for k, v in extra.items() if v is not None})
    if url:
        for other in index["sources"]:
            if other.get("normalized") == source["normalized"] and not other.get("duplicate_of"):
                source["duplicate_of"] = other["id"]; source["ingest_status"] = "duplicate"
                source["attempts"].append({"at": now(), "method": "registry", "result": "duplicate", "detail": f"Same URL as {other['id']}"})
                break
    index["sources"].append(source)
    return source


def init_supplied(index=None):
    """Idempotently register every user-supplied file and URL, in the order supplied."""
    index = index or load_index()
    project = read_project()
    known_paths = {s["path"] for s in index["sources"] if s["origin"] == "supplied" and s["kind"] == "file"}
    known_urls = [s["url"] for s in index["sources"] if s["origin"] == "supplied" and s["kind"] == "url"]
    import source_roles
    by_path = {s["path"]: s for s in index["sources"] if s["origin"] == "supplied" and s["kind"] == "file"}
    for item in project["input"].get("sources", []):
        # Per-file role metadata from the WebUI (source_roles.py). Files that are not content never reach this list.
        usage = source_roles.usage(item) or None
        if item["path"] not in known_paths:
            register(index, kind="file", path=item["path"], original_name=item.get("original_name"), usage=usage)
        elif usage and by_path[item["path"]].get("usage") != usage: by_path[item["path"]]["usage"] = usage
    remaining = list(known_urls)
    url_usage = project["input"].get("url_usage") if isinstance(project["input"].get("url_usage"), dict) else {}
    for url in project["input"].get("urls", []):
        if url in remaining: remaining.remove(url); continue
        usage = source_roles.usage({"usage": url_usage.get(url)}) or None
        # A reference-only URL (layout / visual / style reference) is not content: it never enters the corpus.
        if usage and usage.get("role") in source_roles.ROLES and not source_roles.ROLES[usage["role"]]["content"]: continue
        register(index, kind="url", url=url, usage=usage)
    for source in index["sources"]:
        if source["origin"] == "supplied" and source["kind"] == "url" and source.get("url") in url_usage:
            usage = source_roles.usage({"usage": url_usage[source["url"]]}) or None
            if usage and source.get("usage") != usage: source["usage"] = usage
    save_index(index)
    return index


# ---------------------------------------------------------------- HTML readability

class _Node:
    __slots__ = ("tag", "attrs", "children", "parent")
    def __init__(self, tag, attrs=(), parent=None):
        self.tag, self.attrs, self.children, self.parent = tag, list(attrs), [], parent


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root"); self.current = self.root; self.meta = {}; self.title = []; self.in_title = False; self.lang = None
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "html" and values.get("lang"): self.lang = values["lang"]
        if tag == "meta":
            key = (values.get("name") or values.get("property") or values.get("itemprop") or "").lower()
            if key and values.get("content"): self.meta.setdefault(key, values["content"].strip())
        if tag == "title": self.in_title = True
        node = _Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in VOID: self.current = node
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.current.tag == tag: self.current = self.current.parent
    def handle_endtag(self, tag):
        if tag == "title": self.in_title = False
        node = self.current
        while node is not None and node.tag != tag: node = node.parent
        if node is not None and node.parent is not None: self.current = node.parent
    def handle_data(self, data):
        if self.in_title: self.title.append(data)
        self.current.children.append(data)


def _text_length(node):
    total = 0
    for child in node.children:
        if isinstance(child, str): total += len(child.strip())
        elif child.tag not in DROP_TAGS: total += _text_length(child)
    return total


def _find(node, tag, found):
    for child in node.children:
        if not isinstance(child, str):
            if child.tag == tag: found.append(child)
            _find(child, tag, found)
    return found


def _serialize(node, out):
    for child in node.children:
        if isinstance(child, str): out.append(html.escape(child, quote=False)); continue
        if child.tag in DROP_TAGS or child.tag in ("head", "title", "meta", "link"): continue
        attributes = "".join(f' {k}="{html.escape(v or "", quote=True)}"' for k, v in child.attrs if k in KEEP_ATTRS)
        out.append(f"<{child.tag}{attributes}>")
        if child.tag not in VOID:
            _serialize(child, out); out.append(f"</{child.tag}>")
    return out


def extract_html(text, url=None):
    """Main-content HTML -> Markdown, plus bibliographic metadata from meta tags."""
    builder = _TreeBuilder(); builder.feed(text); builder.close()
    candidates = _find(builder.root, "article", []) or _find(builder.root, "main", []) or _find(builder.root, "body", []) or [builder.root]
    main = max(candidates, key=_text_length)
    if main.tag == "article":
        # Prefer the whole main element when several article cards split the content.
        mains = _find(builder.root, "main", [])
        if mains and _text_length(mains[0]) > 1.6 * _text_length(main): main = mains[0]
    body = "".join(_serialize(main, []))
    markdown = run([tool("pandoc"), "-f", "html-native_divs-native_spans", "-t", "gfm-raw_html", "--wrap=none"], body)
    meta = builder.meta
    first = lambda *keys: next((meta[k] for k in keys if meta.get(k)), None)
    metadata = {
        "title": first("citation_title", "og:title", "dc.title", "twitter:title") or " ".join("".join(builder.title).split()) or None,
        "author": first("citation_author", "author", "article:author", "dc.creator", "parsely-author"),
        "published": first("citation_publication_date", "article:published_time", "dc.date", "date", "datepublished", "citation_date"),
        "site": first("og:site_name", "application-name") or (urlsplit(url).netloc if url else None),
        "language": builder.lang,
        "description": first("description", "og:description"),
    }
    return markdown, metadata


# ---------------------------------------------------------------- content extraction

def decode(data, charset=None):
    candidates = [charset] if charset else []
    head = data[:4096].decode("ascii", "ignore")
    match = re.search(r"""charset=["']?([A-Za-z0-9_-]+)""", head)
    if match: candidates.append(match.group(1))
    for encoding in candidates + ["utf-8", "cp932", "euc_jp", "latin-1"]:
        try: return data.decode(encoding)
        except (LookupError, UnicodeDecodeError): continue
    return data.decode("utf-8", "replace")


def nonspace(text):
    return len(re.sub(r"\s+", "", text))


def extract_file(path, content_type=None, url=None, charset=None):
    """Return (markdown or None, metadata, limitations). None means the agent must extract."""
    suffix = path.suffix.lower()
    limitations = []
    if content_type in ("text/html", "application/xhtml+xml") or (content_type is None and suffix in (".html", ".htm", ".xhtml")):
        text, meta = extract_html(decode(path.read_bytes(), charset), url)
        return text, meta, limitations
    if content_type == "application/pdf" or suffix == ".pdf":
        pdftotext = shutil.which("pdftotext")
        if not pdftotext: return None, {}, ["PDF text extraction requires the agent (pdftotext unavailable)"]
        result = subprocess.run([pdftotext, "-layout", "-enc", "UTF-8", str(path), "-"], capture_output=True)
        if result.returncode: return None, {}, ["pdftotext failed; agent extraction required"]
        text = result.stdout.decode("utf-8", "replace")
        if nonspace(text) < 200: return None, {}, ["PDF has little extractable text (scanned?); agent extraction/OCR required"]
        return text, {}, ["Extracted with pdftotext -layout; figures and tables may be flattened"]
    if suffix in PANDOC_FORMATS and suffix not in (".html", ".htm", ".xhtml"):
        return run([tool("pandoc"), str(path), "-f", PANDOC_FORMATS[suffix], "-t", "gfm-raw_html", "--wrap=none"]), {}, limitations
    if (content_type or "").startswith("text/") or content_type in ("application/json", "application/xml") or suffix in TEXT_EXT:
        return decode(path.read_bytes(), charset), {}, limitations
    return None, {}, [f"Unsupported format ({content_type or suffix or 'unknown'}); agent extraction required"]


def classify(text, truncated=False):
    """Heuristic ingestion status. Short, truncated or paywalled content is only partially ingested."""
    count = nonspace(text)
    limitations = []
    if truncated: limitations.append("Download exceeded the size limit and was truncated")
    if PAYWALL.search(text[:20000]) and count < 6000: limitations.append("Content appears gated (login/paywall/bot check)")
    if count < MIN_FULL_CHARS: limitations.append(f"Short extraction ({count} characters); confirm it is the complete work")
    return ("partially_ingested" if limitations else "fully_ingested"), limitations


def store(source, text, metadata, status, limitations, method, raw=None, raw_name=None):
    directory = folder(source); directory.mkdir(parents=True, exist_ok=True)
    body = text.strip() + "\n"
    header = f"<!-- {source['id']} · {source.get('url') or source.get('path')} · retrieved {now()} · {method} -->\n\n"
    (directory / "source.md").write_text(header + body, encoding="utf-8")
    if raw is not None and raw_name:
        (directory / raw_name).write_bytes(raw); source["raw_path"] = (directory / raw_name).relative_to(ROOT).as_posix()
    for key in ("title", "author", "published", "site", "language", "description"):
        if metadata.get(key) and not source.get(key + "_locked"): source[key] = metadata[key]
    source.update({"ingest_status": status, "retrieved_at": now(), "chars": nonspace(body),
                   "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                   "content_path": (directory / "source.md").relative_to(ROOT).as_posix()})
    source["limitations"] = list(dict.fromkeys(limitations))
    write_json(directory / "metadata.json", {k: v for k, v in source.items() if k != "attempts"} | {"attempts": source["attempts"]})


def fetch_url(url, timeout=30, max_bytes=25 * 1024 * 1024):
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; BookOrder research fetcher; +https://example.invalid/bookorder)",
        "Accept": "text/html,application/xhtml+xml,application/pdf,text/plain;q=0.9,*/*;q=0.5",
        "Accept-Language": "ja,en;q=0.8"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(max_bytes + 1)
        return {"data": data[:max_bytes], "truncated": len(data) > max_bytes, "content_type": response.headers.get_content_type(),
                "charset": response.headers.get_content_charset(), "final_url": response.geturl(), "status": response.status}


def _attempt_url(source):
    """Worker: fetch + extract one URL. Returns an outcome dict; never raises."""
    started = now(); last = None; response = None
    for attempt in range(2):
        try:
            response = fetch_url(source["url"]); break
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if exc.code not in (408, 429, 500, 502, 503, 504): break
        except Exception as exc:  # network, TLS, DNS, timeout
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(1.0 * (attempt + 1))
    if response is None:
        return {"id": source["id"], "ok": False, "attempt": {"at": started, "method": "bookorder-fetch", "result": "error", "detail": last}}
    suffix = {"application/pdf": ".pdf", "text/html": ".html", "application/xhtml+xml": ".html"}.get(response["content_type"], Path(urlsplit(response["final_url"]).path).suffix or ".bin")
    scratch = ROOT / ".build/fetch" / (source["id"] + suffix)
    scratch.parent.mkdir(parents=True, exist_ok=True); scratch.write_bytes(response["data"])
    try: text, metadata, limitations = extract_file(scratch, response["content_type"], response["final_url"], response["charset"])
    except Exception as exc:
        text, metadata, limitations = None, {}, [f"Extraction failed: {exc}"]
    detail = f"HTTP {response['status']} {response['content_type']} {len(response['data'])} bytes"
    return {"id": source["id"], "ok": True, "text": text, "metadata": metadata, "limitations": limitations, "truncated": response["truncated"],
            "raw": response["data"] if suffix in (".pdf", ".bin") or text is None else None, "raw_name": "raw" + suffix,
            "attempt": {"at": started, "method": "bookorder-fetch", "result": "fetched", "detail": detail, "final_url": response["final_url"]}}


def apply_outcome(source, outcome):
    source["attempts"].append(outcome["attempt"])
    if not outcome["ok"]:
        source["ingest_status"] = "needs_agent_fetch"
        source["limitations"] = [f"Automatic fetch failed: {outcome['attempt']['detail']}"]
        return
    if outcome["text"] is None:
        if outcome.get("raw") is not None:
            directory = folder(source); directory.mkdir(parents=True, exist_ok=True)
            (directory / outcome["raw_name"]).write_bytes(outcome["raw"])
            source["raw_path"] = (directory / outcome["raw_name"]).relative_to(ROOT).as_posix()
        source["ingest_status"] = "needs_agent_extraction"; source["limitations"] = outcome["limitations"]
        return
    status, limitations = classify(outcome["text"], outcome["truncated"])
    store(source, outcome["text"], outcome["metadata"], status, outcome["limitations"] + limitations, "bookorder-fetch",
          outcome.get("raw"), outcome.get("raw_name"))


def ingest_file(source):
    path = (ROOT / source["path"]).resolve()
    attempt = {"at": now(), "method": "bookorder-extract", "result": "error", "detail": ""}
    if not path.is_file():
        attempt["detail"] = "Supplied file is missing from the job"; source["attempts"].append(attempt)
        source["ingest_status"] = "unavailable"; source["limitations"] = [attempt["detail"]]; return
    try: text, metadata, limitations = extract_file(path)
    except Exception as exc: text, metadata, limitations = None, {}, [f"Extraction failed: {exc}"]
    attempt.update(result="extracted" if text is not None else "needs_agent", detail=f"{path.suffix or 'no extension'} {path.stat().st_size} bytes")
    source["attempts"].append(attempt)
    if text is None:
        source["ingest_status"] = "needs_agent_extraction"; source["limitations"] = limitations; source["raw_path"] = source["path"]; return
    status, extra = classify(text)
    metadata.setdefault("title", source.get("original_name") or path.name)
    store(source, text, metadata, status, limitations + extra, "bookorder-extract")


def ingest(ids=None, limit=40, workers=8, index=None):
    """Attempt pending sources (files locally, URLs over HTTP). Bounded so each command stays short."""
    index = index or load_index()
    targets = [s for s in index["sources"] if s["ingest_status"] == "pending" and (ids is None or s["id"] in ids)][:limit]
    for source in targets:
        if source["kind"] == "file": ingest_file(source)
    urls = [s for s in targets if s["kind"] == "url"]
    for source in urls: source["ingest_status"] = "fetching"
    save_index(index)
    table = by_id(index)
    if urls:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for outcome in pool.map(_attempt_url, urls): apply_outcome(table[outcome["id"]], outcome)
    save_index(index)
    return [s["id"] for s in targets]


def reset_interrupted(index):
    """A crash during fetching leaves 'fetching'; return those to pending on resume."""
    changed = False
    for source in index["sources"]:
        if source["ingest_status"] == "fetching": source["ingest_status"] = "pending"; changed = True
    if changed: save_index(index)
    return index


def submit(identifier, file, status="fully_ingested", method="agent", note=None, title=None, author=None, published=None, site=None):
    """Agent-extracted content (browser fetch, PDF reading, OCR). Stored exactly like tool output."""
    if status not in USABLE: raise ValueError("submit status must be fully_ingested or partially_ingested")
    index = load_index(); source = get(index, identifier)
    locked = locked_ids()
    if identifier in locked and source["ingest_status"] in USABLE:
        raise ValueError(f"{identifier} is frozen in research-lock.json; add a new post-draft source instead")
    text = Path(file).read_text(encoding="utf-8")
    if nonspace(text) < 80: raise ValueError("Submitted content is nearly empty; use `source unavailable` with a reason instead")
    source["attempts"].append({"at": now(), "method": method, "result": "submitted", "detail": note or ""})
    metadata = {"title": title, "author": author, "published": published, "site": site}
    limitations = [] if status == "fully_ingested" else [note or "Agent reported partial content"]
    store(source, text, metadata, status, limitations, method)
    if status == "fully_ingested" and nonspace(text) < MIN_FULL_CHARS:
        source["limitations"].append(f"Short source ({nonspace(text)} characters) confirmed complete by agent")
    save_index(index)
    return source


def confirm_complete(identifier, note):
    """Agent attests that a short extraction is the complete work (e.g. a short announcement)."""
    if not note or len(note.strip()) < 10: raise ValueError("Explain why the extracted content is complete (--note)")
    index = load_index(); source = get(index, identifier)
    if source["ingest_status"] != "partially_ingested": raise ValueError(f"{identifier} is {source['ingest_status']}, not partially_ingested")
    if any("gated" in item or "truncated" in item for item in source["limitations"]):
        raise ValueError("Gated or truncated content cannot be confirmed complete; submit the full text instead")
    source["attempts"].append({"at": now(), "method": "agent-review", "result": "confirmed-complete", "detail": note})
    source["ingest_status"] = "fully_ingested"; source["limitations"].append("Confirmed complete by agent: " + note)
    save_index(index); return source


def accept_partial(identifier, note):
    """Agent reviewed a partial extraction and records what is missing; the limitation stays visible."""
    if not note or len(note.strip()) < 10: raise ValueError("Describe what is missing and why (--note)")
    index = load_index(); source = get(index, identifier)
    if source["ingest_status"] != "partially_ingested": raise ValueError(f"{identifier} is {source['ingest_status']}, not partially_ingested")
    source["attempts"].append({"at": now(), "method": "agent-review", "result": "accepted-partial", "detail": note})
    source["limitations"].append("Partial access: " + note)
    save_index(index); return source


def mark_unavailable(identifier, reason, attempt=None):
    if not reason or len(reason.strip()) < 8: raise ValueError("A specific --reason is required")
    index = load_index(); source = get(index, identifier)
    if attempt: source["attempts"].append({"at": now(), "method": "agent", "result": "failed", "detail": attempt})
    if not source["attempts"]: raise ValueError(f"{identifier} was never attempted; run the fetch or record your attempt with --attempt")
    source["ingest_status"] = "unavailable"; source["limitations"] = [reason]
    save_index(index); return source


def add_discovered(url=None, path=None, title=None, reason=None, query=None, gap=None, post_draft=False, issue=None,
                   role=None, authority=None, citation_allowed=None, intended_usage=None, intended_chapter=None, notes=None):
    """A source found by the agent's research, with the same role metadata as supplied files and URLs
    (role_origin: agent — below the user's choices, same meaning: evidence may be cited, background is read only)."""
    import source_roles
    raw = {"role": role, "authority": authority, "citation_allowed": citation_allowed, "intended_usage": intended_usage,
           "intended_chapter": intended_chapter, "notes": notes}
    usage = source_roles.usage({"usage": {k: v for k, v in raw.items() if v not in (None, "")}}) or None
    if usage: usage["role_origin"] = "agent"
    errors = source_roles.validate_usage({"usage": usage or {}}, "input.sources[discovered]")
    if errors: raise ValueError("; ".join(errors))
    index = load_index()
    if post_draft and not reason: raise ValueError("Post-draft sources require --reason (and preferably --issue)")
    source = register(index, kind="url" if url else "file", url=url, path=path, origin="discovered", title=title,
                      discovery={"query": query, "gap": gap, "reason": reason, "issue": issue}, post_draft=post_draft, usage=usage)
    save_index(index)
    if post_draft:
        from research import record_post_draft
        record_post_draft(source["id"], reason, issue)
    return source


def locked_ids():
    lock = ROOT / "research/research-lock.json"
    if not lock.is_file(): return set()
    return set(json.loads(lock.read_text(encoding="utf-8")).get("sources", []))


def counts(index, origin=None):
    sources = [s for s in index["sources"] if origin is None or s["origin"] == origin]
    result = {"total": len(sources)}
    for state in PENDING + TERMINAL: result[state] = sum(1 for s in sources if s["ingest_status"] == state)
    result["pending_total"] = sum(result[s] for s in PENDING)
    result["attempted"] = sum(1 for s in sources if s["attempts"])
    return result


def status_report(index):
    notes = ROOT / "research/notes"
    return {"generated_at": now(), "supplied": counts(index, "supplied"), "discovered": counts(index, "discovered"),
            "sources": [{"id": s["id"], "origin": s["origin"], "post_draft": s.get("post_draft", False), "kind": s["kind"],
                         "location": s.get("url") or s.get("path"), "status": s["ingest_status"],
                         "analyzed": (notes / f"{s['id']}.yaml").is_file(), "chars": s.get("chars", 0),
                         "attempts": len(s["attempts"]), "title": s.get("title"), "limitations": s.get("limitations", []),
                         "duplicate_of": s.get("duplicate_of")} for s in index["sources"]]}

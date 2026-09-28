"""Shared portable helpers. Markdown and YAML are parsed by Pandoc, never a custom parser."""
from pathlib import Path
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def tool(name):
    configured = os.environ.get(name.upper())
    bundled = list((ROOT / "runtime/tools" / name).rglob(name + (".exe" if os.name == "nt" else "")))
    found = configured or (str(bundled[0]) if len(bundled) == 1 else None) or shutil.which(name)
    if not found or not Path(found).is_file():
        raise RuntimeError(f"Missing {name}. Install/provide it yourself or set {name.upper()} to its executable path.")
    return str(found)


def run(args, data=None):
    result = subprocess.run([str(x) for x in args], cwd=ROOT, input=data,
                            encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(map(str, args))}\n{result.stderr}")
    # Citation and format warnings must not silently become a successful publication.
    if result.stderr.strip():
        print(result.stderr.strip())
        if re.search(r"not found|could not|couldn't|unsupported|missing character|undefined", result.stderr, re.I):
            raise RuntimeError(result.stderr.strip())
    return result.stdout


SUPPORTED_VERSIONS = ("0.1", "0.2")


def read_project():
    project = json.loads((ROOT / "project.json").read_text(encoding="utf-8"))
    if project.get("format") != "portable-publishing-job" or project.get("format_version") not in SUPPORTED_VERSIONS:
        raise ValueError("Unsupported project format/version; expected portable-publishing-job 0.1 or 0.2")
    # 0.1 jobs predate the orchestrated pipeline; fill the new policy fields with defaults.
    research = project.setdefault("research", {})
    research.setdefault("allow_web_research", True)
    research.setdefault("require_supplied_coverage", True)
    project.setdefault("citations", {}).setdefault("style", "numeric")
    project.setdefault("figures", {})
    project.setdefault("input", {}).setdefault("urls", [])
    project["input"].setdefault("sources", [])
    if not project.get("outputs", {}).get("canonical_markdown"):
        raise ValueError("Canonical Markdown is required")
    for key in ("title", "description", "target_readers", "language"):
        if not str(project.get("book", {}).get(key, "")).strip():
            raise ValueError(f"Missing book.{key}")
    return project


def walk(value):
    if isinstance(value, dict):
        if "t" in value:
            yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def plain(value):
    parts = []
    for node in walk(value):
        if node["t"] == "Str": parts.append(node["c"])
        elif node["t"] in ("Space", "SoftBreak", "LineBreak"): parts.append(" ")
        elif node["t"] in ("Code", "Math"): parts.append(node["c"][1])
    return "".join(parts)


def meta_value(value):
    kind, content = value["t"], value.get("c")
    if kind == "MetaMap": return {k: meta_value(v) for k, v in content.items()}
    if kind == "MetaList": return [meta_value(v) for v in content]
    if kind == "MetaBool": return content
    if kind == "MetaString": return content
    return plain(content)


def _cached(kind, text, producer):
    """Content-addressed cache for Pandoc parses; long books re-check the same files often."""
    key = hashlib.sha256((kind + "\0" + text).encode("utf-8")).hexdigest()
    folder = ROOT / ".build/cache" / kind
    path = folder / (key + ".json")
    if path.is_file():
        try: return json.loads(path.read_text(encoding="utf-8"))
        except ValueError: pass
    value = producer()
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return value


def yaml_text(text, label="YAML"):
    """Parse YAML with Pandoc's YAML reader (no custom parser). Top level must be a mapping."""
    if not text.strip(): return {}
    def parse():
        doc = json.loads(run([tool("pandoc"), "-f", "markdown-smart", "-t", "json"], "---\n" + text.rstrip() + "\n---\n"))
        return {k: meta_value(v) for k, v in doc["meta"].items()}
    try: return _cached("yaml", text, parse)
    except RuntimeError as exc: raise ValueError(f"Invalid YAML in {label}: {exc}") from exc


def yaml_data(path):
    return yaml_text(Path(path).read_text(encoding="utf-8"), str(path))


def _yaml_scalar(value):
    if value is None: return "null"
    if isinstance(value, bool): return "true" if value else "false"
    if isinstance(value, (int, float)): return json.dumps(value)
    return json.dumps(str(value), ensure_ascii=False)


def dump_yaml(value, indent=0):
    """Emit block YAML. Strings are always double-quoted JSON strings, which YAML accepts verbatim."""
    pad = "  " * indent
    if isinstance(value, dict):
        if not value: return pad + "{}\n"
        out = []
        for key, item in value.items():
            name = _yaml_scalar(str(key)) if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", str(key)) else str(key)
            if isinstance(item, (dict, list)) and item: out.append(f"{pad}{name}:\n" + dump_yaml(item, indent + 1))
            else: out.append(f"{pad}{name}: " + (("{}" if isinstance(item, dict) else "[]") if isinstance(item, (dict, list)) else _yaml_scalar(item)) + "\n")
        return "".join(out)
    if isinstance(value, list):
        if not value: return pad + "[]\n"
        out = []
        for item in value:
            if isinstance(item, dict) and item:
                body = dump_yaml(item, indent + 1)
                out.append(pad + "- " + body[len(pad) + 2:])
            elif isinstance(item, list) and item:
                out.append(pad + "-\n" + dump_yaml(item, indent + 1))
            else: out.append(pad + "- " + (("{}" if isinstance(item, dict) else "[]") if isinstance(item, (dict, list)) else _yaml_scalar(item)) + "\n")
        return "".join(out)
    return pad + _yaml_scalar(value) + "\n"


def write_if_changed(path, text):
    """Write only real changes so generated metadata does not make builds stale."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_text(encoding="utf-8") == text: return False
    path.write_text(text, encoding="utf-8"); return True


def write_yaml(path, value, header=None):
    text = ("# " + header + "\n" if header else "") + dump_yaml(value)
    return write_if_changed(path, text)


def write_json(path, value):
    return write_if_changed(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def as_list(value):
    if value is None or value == "": return []
    return value if isinstance(value, list) else [value]


def as_int(value, default=0):
    try: return int(float(str(value).replace(",", "").replace("_", "")))
    except (TypeError, ValueError): return default


CITE_PATTERN = re.compile(r"\[cite:\s*([A-Za-z0-9_.:-]+(?:\s*[,;]\s*[A-Za-z0-9_.:-]+)*)(?:\s*,\s*(p{1,2}\.?\s*[^\]]+))?\]")


XREF_PATTERN = re.compile(r"(?<![A-Za-z0-9_\[\]@-])(-?)@(ch|sec|fig|tbl|eq):([A-Za-z0-9](?:[A-Za-z0-9_-]*[A-Za-z0-9])?)")


def preprocess_markdown(text):
    """Canonical citations are [cite:src-0042] or [cite:src-0042,src-0061]. Convert them to Pandoc
    citations (outside code) so visible numbering is decided only by the renderer's CSL style."""
    out = []; fence = None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            if fence is None: fence = marker.group(1)[0]
            elif marker.group(1)[0] == fence: fence = None
            out.append(line); continue
        if fence is None:
            def replace(match):
                keys = [k.strip() for k in re.split(r"[,;]", match.group(1)) if k.strip()]
                locator = (", " + match.group(2).strip()) if match.group(2) else ""
                return "[" + "; ".join("@" + k for k in keys) + locator + "]"
            parts = re.split(r"(`+[^`]*`+)", line)
            # Bare @fig:x style references are bracketed so they also parse next to CJK text (e.g. 「と@tbl:x」).
            line = "".join(part if part.startswith("`") else XREF_PATTERN.sub(r"[\1@\2:\3]", CITE_PATTERN.sub(replace, part)) for part in parts)
        out.append(line)
    return "".join(out)


def parse_markdown(text):
    source = preprocess_markdown(text)
    return _cached("markdown", source, lambda: json.loads(run([tool("pandoc"), "-f", "markdown", "-t", "json"], source)))


def chapter_files():
    return sorted((ROOT / "source/manuscript").glob("*.md"))


def chapters():
    found = chapter_files()
    if not found: raise ValueError("No manuscript chapters found")
    return [(path, parse_markdown(path.read_text(encoding="utf-8"))) for path in found]


def attr(node):
    kind, content = node["t"], node.get("c")
    if kind == "Header": return content[1]
    if kind in ("Div", "Span", "Code", "CodeBlock", "Link", "Image", "Table", "Figure"): return content[0]
    return None


def local_path(url):
    from urllib.parse import unquote, urlsplit
    parts = urlsplit(url)
    if parts.scheme or parts.netloc or not parts.path: return None
    path = (ROOT / unquote(parts.path)).resolve()
    if not path.is_relative_to(ROOT): raise ValueError(f"Asset escapes project: {url}")
    return path


def fingerprint():
    digest = hashlib.sha256()
    paths = [ROOT / name for name in ('project.json', 'TASK.md', 'book.design.yaml', 'custom.css', 'custom.typ')]
    for folder in ("source", "templates", "scripts", "input", "themes", "styles", "schemas"):
        paths.extend(p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    for path in sorted(paths):
        if path.is_file():
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    # These are explicit semantic inputs to publication. Do not hash plan/ wholesale:
    # reports and generated planning aids live there too, and would self-invalidate.
    for path in semantic_artifact_paths():
        if path.is_file():
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(json.dumps(_semantic_yaml(path), ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8"))
    return digest.hexdigest()


def semantic_artifact_paths():
    """The small, explicit set of planning artifacts that affect the published book."""
    paths = [ROOT / "plan/profile.resolved.yaml", ROOT / "plan/layout-spec.yaml", ROOT / "plan/style-bible.yaml",
             ROOT / "source/metadata/outline.yaml",
             ROOT / "plan/assets-plan.yaml", ROOT / "source/metadata/figures.yaml",
             ROOT / "reports/visual-review.yaml"]
    editorial = ROOT / "plan/editorial"
    if editorial.is_dir(): paths.extend(editorial.glob("*.yaml"))
    return sorted(set(paths))


def editorial_plan_fingerprint():
    """Fingerprint only the semantic EditorialPlan source artifacts."""
    digest = hashlib.sha256()
    folder = ROOT / "plan/editorial"
    paths = sorted(folder.glob("*.yaml")) if folder.is_dir() else []
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(json.dumps(_semantic_yaml(path), ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")).encode("utf-8"))
    return digest.hexdigest()


def _semantic_yaml(path):
    """Canonical parsed YAML: formatting/comments and generated time fields do not affect freshness."""
    value = yaml_data(path)
    ignored = {"generated_at", "updated_at", "created_at", "timestamp"}
    def clean(item):
        if isinstance(item, dict):
            return {key: clean(val) for key, val in item.items() if str(key).lower() not in ignored}
        if isinstance(item, list): return [clean(val) for val in item]
        return item
    return clean(value)


def report(name, content):
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / name).write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def output_paths(project):
    mapping = {"docx": "interchange/book.docx", "semantic_html": "interchange/book.html", "pdf": "publish/book.pdf", "epub": "publish/book.epub", "static_site": "publish/site/index.html"}
    return [ROOT / path for key, path in mapping.items() if project["outputs"].get(key)]


_MATH = []


def math_option():
    """MathML for HTML/EPUB: static, accessible, no script; option spelling depends on the Pandoc version."""
    if not _MATH:
        version = version_tuple(run([tool("pandoc"), "--version"]).splitlines()[0])
        _MATH.append("--math-method=mathml" if version >= (3, 8, 0) else "--mathml")
    return _MATH[0]


def version_tuple(value):
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", value)
    return tuple(int(x or 0) for x in match.groups()) if match else (0, 0, 0)


CSL_STYLES = {"numeric": "templates/csl/numeric.csl", "author-year": None, "note": "templates/csl/note.csl"}


def bibliography_files():
    files = []
    generated = ROOT / "source/references/references.json"
    if generated.is_file() and generated.read_text(encoding="utf-8").strip() not in ("", "[]"): files.append(generated)
    manual = ROOT / "source/references/references.bib"
    if manual.is_file() and "@" in manual.read_text(encoding="utf-8"): files.append(manual)
    return files


def bibliography_keys():
    keys = []
    for path in bibliography_files():
        if path.suffix == ".json": keys += [entry["id"] for entry in json.loads(path.read_text(encoding="utf-8"))]
        else: keys += [entry["id"] for entry in json.loads(run([tool("pandoc"), path, "-f", "biblatex", "-t", "csljson"]))]
    return keys


def combined(project, items, registry_out=None):
    """One book AST: cross-references numbered/resolved, then citations rendered once by CSL."""
    import crossref
    doc = copy.deepcopy(items[0][1])
    doc["blocks"] = [copy.deepcopy(block) for _, ast in items for block in ast["blocks"]]
    book = project["book"]
    registry, errors = crossref.apply(doc, book["language"])
    # Pipe-table dash counts are an accident of source formatting; let each renderer size columns from content.
    for node in walk(doc["blocks"]):
        if node["t"] == "Table":
            node["c"][2] = [[spec[0], {"t": "ColWidthDefault"}] for spec in node["c"][2]]
    if errors: raise ValueError("; ".join(sorted(set(errors))))
    if registry_out is not None: registry_out.update(registry)
    doc["meta"] = {"title": {"t": "MetaString", "c": book["title"]}, "lang": {"t": "MetaString", "c": book["language"]}}
    if book.get("author"): doc["meta"]["author"] = {"t": "MetaString", "c": book["author"]}
    files = bibliography_files()
    cites = any(node["t"] == "Cite" for node in walk(doc["blocks"]))
    if not files:
        if cites: raise ValueError("Citations exist but no bibliography was generated; run bookorder goal (reference assignment)")
        return doc
    doc["meta"]["bibliography"] = {"t": "MetaList", "c": [{"t": "MetaString", "c": str(path)} for path in files]}
    style = CSL_STYLES.get(project.get("citations", {}).get("style", "numeric"), CSL_STYLES["numeric"])
    if style: doc["meta"]["csl"] = {"t": "MetaString", "c": str(ROOT / style)}
    doc["meta"]["link-citations"] = {"t": "MetaBool", "c": True}
    japanese = str(book["language"]).lower().startswith("ja")
    if cites and not any(node["t"] == "Div" and node["c"][0][0] == "refs" for node in walk(doc["blocks"])):
        title = "参考文献" if japanese else "References"
        if not any(node["t"] == "Header" and node["c"][1][0] == "sec-references" for node in walk(doc["blocks"])):
            doc["blocks"].append({"t": "Header", "c": [2, ["sec-references", ["unnumbered"], []], [{"t": "Str", "c": title}]]})
        doc["blocks"].append({"t": "Div", "c": [["refs", ["references"], []], []]})
    # Citation resolution happens once for the whole book, before splitting website pages.
    return json.loads(run([tool("pandoc"), "-f", "json", "-t", "json", "--citeproc"], json.dumps(doc)))

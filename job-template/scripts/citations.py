"""Reference registry: stable source IDs -> CSL JSON. Visible numbering is left to the CSL renderer."""
import re

from common import ROOT, write_json, write_yaml, as_list
import research
import sources as registry


def date_parts(value):
    if not value: return None
    match = re.match(r"(\d{4})(?:[-/.年](\d{1,2}))?(?:[-/.月](\d{1,2}))?", str(value).strip())
    if not match: return None
    parts = [int(x) for x in match.groups() if x]
    return {"date-parts": [parts]}


def names(value):
    result = []
    for item in as_list(value):
        if isinstance(item, dict): result.append({k: v for k, v in item.items() if k in ("family", "given", "literal")})
        else:
            for name in re.split(r"\s*(?:;|、| and )\s*", str(item)):
                if name.strip(): result.append({"literal": name.strip()})
    return result


def csl_entry(source, note):
    biblio = (note or {}).get("bibliographic") or {}
    kind = biblio.get("type") or ("webpage" if source["kind"] == "url" else "document")
    entry = {"id": source["id"], "type": kind,
             "title": biblio.get("title") or source.get("title") or source.get("original_name") or source.get("url") or source["id"]}
    authors = names(biblio.get("authors") or biblio.get("author") or source.get("author"))
    if authors: entry["author"] = authors
    issued = date_parts(biblio.get("published") or source.get("published"))
    if issued: entry["issued"] = issued
    if source["kind"] == "url":
        entry["URL"] = source.get("url")
        accessed = date_parts(source.get("retrieved_at"))
        if accessed: entry["accessed"] = accessed
    container = biblio.get("container") or biblio.get("container_title") or source.get("site")
    if container and container != entry["title"]: entry["container-title"] = container
    if biblio.get("publisher"): entry["publisher"] = biblio["publisher"]
    for key in ("volume", "issue", "page", "DOI", "ISBN"):
        if biblio.get(key.lower()) or biblio.get(key): entry[key] = str(biblio.get(key.lower()) or biblio.get(key))
    return entry


def generate():
    """references.json holds every usable source by stable ID; sources.yaml mirrors the registry for DTP/validators."""
    index = registry.load_index(); notes = research.load_notes()
    entries = [csl_entry(s, notes.get(s["id"])) for s in index["sources"] if s["ingest_status"] in registry.USABLE]
    write_json(ROOT / "source/references/references.json", entries)
    inventory = []
    for source in index["sources"]:
        item = {"id": source["id"], "type": source["kind"], "origin": source["origin"], "status": source["ingest_status"],
                "title": source.get("title"), "access_date": (source.get("retrieved_at") or "")[:10] or None,
                "content": source.get("content_path"), "limitations": source.get("limitations", [])}
        if source["kind"] == "url": item["url"] = source.get("url")
        else: item["path"] = source.get("path")
        if source.get("post_draft"): item["post_draft"] = True
        inventory.append(item)
    write_yaml(ROOT / "source/metadata/sources.yaml", {"sources": inventory}, "Generated from research/index.json. Use bookorder source commands to change it.")
    return entries

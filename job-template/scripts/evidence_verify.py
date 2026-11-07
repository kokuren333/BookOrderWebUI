"""`bookorder evidence verify`: deterministic checks of the evidence map and of the citations in the manuscript.

What a model cannot be trusted to self-report is checked here mechanically:

- every source ID in research/evidence/<chapter>.yaml exists in research/index.json;
- every quote in the evidence map really occurs in the persisted source text (after Unicode/whitespace/punctuation
  normalisation) — a quote that is not there is a fabricated or misattributed locator;
- claims the author is told to state or attribute have at least one source, and that source's role allows citation
  (evidence); background / general-knowledge sources never carry a factual claim;
- every [cite:src-…] in the chapter points to a known source whose role allows citation, so only real evidence
  reaches the 引用文献 list (background sources stay out of the book's back matter);
- the fact check's problem verdicts are surfaced (unsupported / miscited / needs_citation).

Findings: high (blocks the Claude-mode evidence gate), medium, low (advice). Report: reports/evidence-verification.json.
"""
import json
import re
import unicodedata

from common import ROOT, as_list, read_project, yaml_data

CITE = re.compile(r"\[cite:([^\]]+)\]")
PROBLEM_VERDICTS = {"unsupported", "miscited", "needs_citation"}


def normalise(text):
    text = unicodedata.normalize("NFKC", str(text or "")).lower()
    return re.sub(r"[\s\"'“”‘’「」『』（）()\[\]、。,.・:：;；!！?？\-–—…]+", "", text)


def _source_texts():
    import sources as registry
    index = registry.load_index(); texts = {}
    for source in index.get("sources", []):
        path = ROOT / str(source.get("content_path") or "")
        texts[source["id"]] = path if source.get("content_path") and path.is_file() else None
    return texts


def _roles():
    import source_roles
    try: return source_roles.table(write=False)
    except Exception: return {}


def cited_ids(text):
    ids = []
    for match in CITE.finditer(text):
        for part in match.group(1).split(","):
            token = part.strip()
            if re.fullmatch(r"src-\d+", token): ids.append(token)
    return ids


def chapter(chapter, project=None, texts=None, roles=None, cache=None):
    texts = texts if texts is not None else _source_texts(); roles = roles if roles is not None else _roles()
    cache = cache if cache is not None else {}
    findings = []

    def add(severity, kind, detail): findings.append({"severity": severity, "type": kind, "chapter": chapter["id"], "detail": detail})

    def source_text(ident):
        if ident not in cache:
            path = texts.get(ident); cache[ident] = normalise(path.read_text(encoding="utf-8", errors="replace")) if path else None
        return cache[ident]

    evidence = ROOT / "research/evidence" / f"{chapter['id']}.yaml"
    claims = []
    if evidence.is_file():
        try: data = yaml_data(evidence)
        except ValueError as exc: data = {}; add("high", "invalid_yaml", f"{evidence.name}: {str(exc)[:160]}")
        claims = [c for c in as_list(data.get("claims")) if isinstance(c, dict)]
        for claim in claims:
            cid = claim.get("id") or "?"; use = claim.get("use") or "state"
            refs = [r for r in as_list(claim.get("sources")) if isinstance(r, dict)]
            if use != "avoid" and not refs: add("high", "claim_without_source", f"{cid}: claim has no source ({str(claim.get('claim'))[:60]})")
            for ref in refs:
                ident = str(ref.get("src") or "")
                if ident not in texts: add("high", "unknown_source", f"{cid}: unknown source ID {ident or '(empty)'}"); continue
                role = roles.get(ident) or {}
                if use in ("state", "attribute", "contrast") and role and not role.get("citation_allowed", True):
                    add("high", "non_evidence_support", f"{cid}: {ident} is a {role.get('role')} source (not citable) but supports a factual claim")
                quote = normalise(ref.get("quote"))
                if not quote: add("low", "no_quote", f"{cid}: {ident} has no verbatim quote to verify"); continue
                text = source_text(ident)
                if text is None: add("medium", "source_text_missing", f"{cid}: no persisted text for {ident}; quote unverifiable"); continue
                if quote in text: continue
                head = quote[:max(12, len(quote) // 3)]
                if len(quote) >= 12 and head in text: add("medium", "quote_approximate", f"{cid}: quote from {ident} only partly matches the source text")
                else: add("high", "quote_not_in_source", f"{cid}: quote attributed to {ident} ({str(ref.get('quote'))[:50]}…) does not occur in its text")
    manuscript = ROOT / str(chapter.get("file") or "")
    used = []
    if manuscript.is_file():
        used = cited_ids(manuscript.read_text(encoding="utf-8"))
        for ident in sorted(set(used)):
            if ident not in texts: add("high", "unknown_citation", f"[cite:{ident}] is not a known source"); continue
            role = roles.get(ident) or {}
            if role and not role.get("citation_allowed", True):
                add("high", "cites_non_evidence", f"[cite:{ident}] cites a {role.get('role')} source; general-knowledge/background sources are not cited — "
                    "cite an evidence source or state it without a citation if it is general knowledge")
        strong = {str(r.get("src")) for c in claims if c.get("strength") == "strong" and (c.get("use") or "state") == "state"
                  for r in as_list(c.get("sources")) if isinstance(r, dict)}
        unused = sorted(strong - set(used))
        if claims and unused: add("low", "strong_evidence_unused", "strong evidence never cited in the chapter: " + ", ".join(unused[:8]))
    factcheck = ROOT / "research/factcheck" / f"{chapter['id']}.yaml"
    if factcheck.is_file():
        try: items = [i for i in as_list(yaml_data(factcheck).get("items")) if isinstance(i, dict)]
        except ValueError: items = []; add("medium", "invalid_yaml", f"{factcheck.name} is not valid YAML")
        problems = [i for i in items if i.get("verdict") in PROBLEM_VERDICTS]
        if problems:
            add("medium", "factcheck_problems", f"fact check: {len(problems)} sentence(s) unsupported/miscited/uncited — copy real ones into plan/audit/{chapter['id']}.yaml, e.g. "
                + str(problems[0].get("excerpt"))[:60])
    return {"chapter": chapter["id"], "claims": len(claims), "citations": len(used), "findings": findings}


def run(chapter_filter=None, write=True):
    from planning import load_outline
    project = read_project(); texts = _source_texts(); roles = _roles(); cache = {}
    results = [chapter(c, project, texts, roles, cache) for c in load_outline() if not chapter_filter or c["id"] == chapter_filter]
    summary = {s: sum(1 for r in results for f in r["findings"] if f["severity"] == s) for s in ("high", "medium", "low")}
    report = {"schema": "bookorder/evidence-verification@1", "summary": summary, "chapters": results}
    if write and not chapter_filter:
        (ROOT / "reports").mkdir(exist_ok=True)
        (ROOT / "reports/evidence-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def text(report):
    lines = [f"Evidence verification: {report['summary']['high']} high, {report['summary']['medium']} medium, {report['summary']['low']} low"]
    for r in report["chapters"]:
        lines.append(f"  {r['chapter']}: {r['claims']} mapped claims, {r['citations']} citations")
        for f in r["findings"]: lines.append(f"    [{f['severity']}] {f['type']}: {f['detail']}")
    return "\n".join(lines)

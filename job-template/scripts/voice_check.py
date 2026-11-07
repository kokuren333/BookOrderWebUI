"""`bookorder voice`: a self-review aid for over-cautious prose. Advisory only — it never blocks a gate.

Counts hedging and boilerplate-caution phrases per 1,000 characters for each chapter, lists the densest
paragraphs, and — when research/evidence/<chapter>.yaml exists — points out hedged sentences that cite sources the
evidence map rates strong. A hedge is right when the evidence is uncertain; it is noise when the evidence is strong.
Phrases live in config/prose-signals/<lang>.json under "hedges" and "boilerplate" so a book can tune them.
"""
import json
import re

from common import ROOT, as_list, read_project, yaml_data

DEFAULT_HEDGES = {
    "ja": ["と考えられる", "と考えられます", "可能性がある", "可能性があります", "かもしれない", "かもしれません", "と言えるだろう",
           "と言えるでしょう", "といえる", "と思われる", "と思われます", "であろう", "でしょう", "一概には言えない", "一概には言えません",
           "場合がある", "場合があります", "ことがある", "こともある", "傾向がある", "とされる", "とされています", "と言われている",
           "と言われています", "必ずしも", "ある程度", "ではないだろうか", "ではないでしょうか"],
    "en": ["may ", "might ", "could ", "possibly", "perhaps", "it seems", "it appears", "arguably", "to some extent",
           "it is generally", "it is often said", "tends to", "in some cases", "not necessarily"],
}
DEFAULT_BOILERPLATE = {
    "ja": ["注意が必要", "注意が必要です", "慎重な検討", "慎重に検討", "総合的に判断", "専門家に相談", "状況によって異なる",
           "ケースバイケース", "さまざまな要因", "様々な要因", "今後の研究が待たれる", "今後の動向", "重要である", "重要です",
           "求められる", "求められます", "留意する必要"],
    "en": ["it is important to note", "careful consideration", "consult a professional", "depends on the situation",
           "a variety of factors", "further research is needed", "it should be noted"],
}
CITE = re.compile(r"\[cite:([^\]]+)\]")


def phrases(language):
    lang = (language or "ja").split("-")[0].lower()
    path = ROOT / f"config/prose-signals/{lang}.json"
    data = {}
    if path.is_file():
        try: data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError: data = {}
    return (data.get("hedges") or DEFAULT_HEDGES.get(lang, DEFAULT_HEDGES["en"]),
            data.get("boilerplate") or DEFAULT_BOILERPLATE.get(lang, DEFAULT_BOILERPLATE["en"]))


def strong_sources(chapter_id):
    path = ROOT / f"research/evidence/{chapter_id}.yaml"
    if not path.is_file(): return set()
    try: data = yaml_data(path)
    except ValueError: return set()
    found = set()
    for claim in as_list(data.get("claims")):
        if isinstance(claim, dict) and claim.get("strength") == "strong":
            for source in as_list(claim.get("sources")):
                if isinstance(source, dict) and source.get("src"): found.add(str(source["src"]))
    return found


def analyse(chapter_filter=None):
    from planning import load_outline
    project = read_project(); hedges, boiler = phrases(project.get("book", {}).get("language"))
    chapters = []
    for chapter in load_outline():
        if chapter_filter and chapter["id"] != chapter_filter: continue
        path = ROOT / chapter["file"]
        if not path.is_file(): continue
        text = path.read_text(encoding="utf-8")
        body = "\n".join(line for line in text.splitlines() if not line.startswith(("#", ":::", "|", "![", "Table:")))
        size = max(1, len(re.sub(r"\s", "", body)))
        count = lambda words, s: sum(s.count(w) for w in words)
        h = count(hedges, body); b = count(boiler, body)
        paragraphs = []
        for para in re.split(r"\n\s*\n", body):
            plain = re.sub(r"\s", "", para)
            if len(plain) < 80: continue
            n = count(hedges, para) + count(boiler, para)
            if n: paragraphs.append({"density": round(1000 * n / len(plain), 1), "hits": n, "start": para.strip()[:70]})
        paragraphs.sort(key=lambda p: -p["density"])
        strong = strong_sources(chapter["id"]); overhedged = []
        if strong:
            for sentence in re.split(r"(?<=[。．.!?！？])\s*", body):
                cited = {x.strip().split(",")[0].strip() for m in CITE.finditer(sentence) for x in m.group(1).split(",")}
                if cited & strong and any(w in sentence for w in hedges):
                    overhedged.append(sentence.strip()[:120])
        chapters.append({"chapter": chapter["id"], "chars": size, "hedges": h, "boilerplate": b,
                         "per_1000": round(1000 * (h + b) / size, 2), "dense_paragraphs": paragraphs[:5], "overhedged_strong_claims": overhedged[:10]})
    return chapters


def text(results):
    if not results: return "No drafted chapters to check."
    lines = ["Hedging / boilerplate per 1,000 characters (advisory; aim for hedges only where the evidence is uncertain):"]
    for r in sorted(results, key=lambda r: -r["per_1000"]):
        lines.append(f"  {r['chapter']:<28} {r['per_1000']:>6}   hedges {r['hedges']:>4}  boilerplate {r['boilerplate']:>4}  ({r['chars']:,} chars)")
        for p in r["dense_paragraphs"][:3]: lines.append(f"      dense ¶ ({p['density']}/1000): {p['start']}…")
        for s in r["overhedged_strong_claims"][:5]: lines.append(f"      hedged but evidence is strong: {s}")
    return "\n".join(lines)

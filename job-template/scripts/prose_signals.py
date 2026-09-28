"""Descriptive manuscript features for contextual whole-book review.

No phrase or metric here establishes authorship, quality, or a required edit.
"""
from collections import Counter, defaultdict
import json
import re

from common import ROOT

HEADING = re.compile(r"^(#{1,3})\s+(.+?)(?:\s+\{#.*)?$")


def sections(markdown):
    result, current = [], None
    for line in markdown.splitlines():
        match = HEADING.match(line)
        if match:
            if current is not None: result.append(current)
            current = {"level": len(match.group(1)), "title": match.group(2), "lines": []}
        elif current is not None:
            current["lines"].append(line)
    if current is not None: result.append(current)
    for section in result:
        section["paragraphs"] = [p.strip() for p in re.split(r"\n\s*\n", "\n".join(section.pop("lines")))
                                 if p.strip() and not p.lstrip().startswith(("```", ":::"))]
    return result


def compact(value):
    return re.sub(r"\s+", "", value)


def analyze(chapters, genre="general", policy=None):
    """Return lexical, structural, repetition and distribution signals only."""
    policy = policy if policy is not None else json.loads((ROOT / "config/prose-signals/ja.json").read_text(encoding="utf-8"))
    phrases = tuple(policy.get("phrases") or ())
    window = int(policy.get("lexical_window", 24))
    ngram_size = int(policy.get("ngram_size", 8))
    counts = Counter()
    by_chapter = []
    openings, endings, ngrams = defaultdict(list), defaultdict(list), defaultdict(list)
    review_candidates = []
    for chapter in chapters:
        cid = chapter["id"]
        parts = sections(chapter["text"])
        prose = "\n".join("\n".join(s["paragraphs"]) for s in parts)
        size = max(1, len(compact(prose)))
        phrase_counts = {phrase: prose.count(phrase) for phrase in phrases}
        counts.update(phrase_counts)
        section_data = []
        for index, part in enumerate(parts):
            paragraphs = part["paragraphs"]
            lengths = [len(compact(p)) for p in paragraphs]
            section_data.append({"index": index, "level": part["level"], "title": part["title"],
                                 "characters": sum(lengths), "paragraph_lengths": lengths})
            for paragraph_index, paragraph in enumerate(paragraphs):
                plain = compact(paragraph)
                if not plain: continue
                location = {"chapter": cid, "section_index": index, "paragraph_index": paragraph_index}
                openings[plain[:window]].append(location)
                endings[plain[-window:]].append(location)
                for phrase in phrases:
                    if phrase in paragraph:
                        review_candidates.append({"span": location, "weak_signals": ["configured_phrase:" + phrase],
                                                  "requires_context_review": True})
                for gram in set(plain[i:i + ngram_size] for i in range(max(0, len(plain) - ngram_size + 1))):
                    if len(gram) == ngram_size: ngrams[gram].append(location)
        by_chapter.append({"chapter": cid, "characters": size, "sections": section_data,
                           "phrase_frequency": phrase_counts,
                           "per_1000_characters": {p: round(n * 1000 / size, 2) for p, n in phrase_counts.items()}})
    repeated = {}
    for kind, groups in (("openings", openings), ("endings", endings), ("ngrams", ngrams)):
        repeated[kind] = [{"text": token, "locations": locations}
                          for token, locations in groups.items()
                          if token and len({loc["chapter"] for loc in locations}) > 1]
        repeated[kind].sort(key=lambda item: (-len(item["locations"]), item["text"]))
        repeated[kind] = repeated[kind][:100]
        for item in repeated[kind]:
            for location in item["locations"]:
                review_candidates.append({"span": location, "weak_signals": ["repeated_" + kind],
                                          "requires_context_review": True})
    by_span = {}
    for candidate in review_candidates:
        key = tuple(candidate["span"][field] for field in ("chapter", "section_index", "paragraph_index"))
        by_span.setdefault(key, {"span": candidate["span"], "weak_signals": set(), "requires_context_review": True})
        by_span[key]["weak_signals"].update(candidate["weak_signals"])
    review_candidates = [{**candidate, "weak_signals": sorted(candidate["weak_signals"])}
                         for candidate in by_span.values()]
    return {"schema": "bookorder/prose-signals@2", "genre_context": genre,
            "signals": {"lexical": {"phrase_frequency": dict(counts), "configured_phrases": list(phrases)},
                        "structural": {"chapters": [{"chapter": c["chapter"], "characters": c["characters"],
                                                    "sections": c["sections"]} for c in by_chapter]},
                        "repetition": repeated,
                        "distribution": {"chapters": [{key: c[key] for key in ("chapter", "characters", "phrase_frequency", "per_1000_characters")}
                                                      for c in by_chapter]}},
            "review_candidates": review_candidates,
            "note": "No single phrase is evidence of AI writing. No deterministic signal is a verdict. The unit of judgment is the manuscript."}


def run(outline, genre="general"):
    chapters = [{"id": c["id"], "text": (ROOT / c["file"]).read_text(encoding="utf-8")}
                for c in outline if (ROOT / c["file"]).is_file()]
    result = analyze(chapters, genre)
    destination = ROOT / "reports/prose-signals.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result

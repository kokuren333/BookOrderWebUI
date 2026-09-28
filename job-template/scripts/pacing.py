"""Layout pacing gate: text walls measured on the typeset pages.

The authority is reports/layout-metrics.json (scripts/layout_metrics.py), i.e. real pages after typesetting.
The manuscript-based estimate in audit.pacing_issues is only a hint. This module turns the measured text-only
page runs into findings with a severity, audit-ledger issues and machine-readable revision candidates, and
decides completion gate 17 (reports/pacing-report.json).

What breaks a run is defined once, in layout_metrics.PAUSE (figure, table, callout, pull quote, case study,
chapter opener, chapter summary, each taking at least MIN_PAUSE_LINES of the page). Headings, lists, code,
equations, white space and rules never do.
"""
from datetime import datetime, timezone
import json
import statistics

from common import ROOT, read_project

SCHEMA = "bookorder/pacing@1"
REPORT = ROOT / "reports/pacing-report.json"
METRICS = ROOT / "reports/layout-metrics.json"
BUILD_REPORT = ROOT / "reports/build-report.json"
ISSUE_TYPE = "layout-pacing"

# Used only when no PublicationProfile can be resolved (plan/profile.resolved.yaml is the authority).
TIER_LIMITS = {"short": 3, "standard": 4, "long": 4, "monograph": 6}
# book.target_pages -> tier when no tier is requested; shared with the WebUI (schemas/publication-presets.json).
_TIER_RULE = __import__("json").loads((ROOT / "schemas/publication-presets.json").read_text(encoding="utf-8"))["tier_from_pages"]
PAGE_TIERS = tuple((int(bound), name) for bound, name in _TIER_RULE["bounds"])


def limits(project=None, profile=None):
    """Pacing limits: rhythm.max_text_only_pages of the resolved PublicationProfile; a page-target fallback only
    when no profile can be resolved."""
    project = project or read_project()
    pacing = project.get("pacing") or {}
    allow = bool(pacing.get("allow_unmeasured"))
    if profile is None:
        import publication_profile
        profile = publication_profile.load_resolved()
        source = "plan/profile.resolved.yaml"
        if profile is None:
            try:
                from design import load_design
                try: design = load_design()
                except Exception: design = {}
                profile = publication_profile.resolve(project, design); source = "profile resolved from project.json"
            except Exception: profile = None
    else: source = "profile"
    if profile:
        return {"tier": profile["tier"], "max_text_only_pages": int(profile["rhythm"]["max_text_only_pages"]),
                "source": f"{source} ({profile['id']})", "profile": profile["id"], "allow_unmeasured": allow,
                "nonprose_share_target": profile["scale"]["nonprose_share_target"]}
    pages = int(float((project.get("book") or {}).get("target_pages") or 0))
    tier = pacing.get("tier") if pacing.get("tier") in TIER_LIMITS else next((name for bound, name in PAGE_TIERS if pages <= bound), _TIER_RULE["above"])
    limit = int(pacing["max_text_only_pages"]) if str(pacing.get("max_text_only_pages", "")).isdigit() else TIER_LIMITS[tier]
    return {"tier": tier, "max_text_only_pages": limit, "source": f"compatibility fallback (book.target_pages={pages})",
            "profile": None, "allow_unmeasured": allow, "nonprose_share_target": None}


def load_metrics():
    """(metrics, problem). The metrics must belong to the current build; otherwise problem names why not."""
    if not BUILD_REPORT.is_file(): return None, "no build report"
    build = json.loads(BUILD_REPORT.read_text(encoding="utf-8"))
    layout = build.get("layout") or {}
    if not layout: return None, "the last build did not measure the layout (preview build or older BookOrder)"
    if not layout.get("ok"): return None, "layout measurement failed: " + str(layout.get("error", ""))[:300]
    if not METRICS.is_file(): return None, "reports/layout-metrics.json is missing"
    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    if layout.get("generated_at") and layout["generated_at"] != metrics.get("generated_at"):
        return None, "reports/layout-metrics.json does not belong to the last build"
    return metrics, None


# ---------------------------------------------------------------- findings

def _break_pages(run, limit):
    """Pages where a pause would bring every remaining stretch down to the limit."""
    needed = max(1, run["length"] // (limit + 1))
    return [run["start"] + k * (limit + 1) - 1 for k in range(1, needed + 1)]


def _sections(metrics, chapter, first, last):
    """Sections (h1 intro, h2, h3) running through pages first..last, with the pages each spans without a new heading."""
    pages = [p for p in metrics["pages"] if p.get("chapter") == chapter]
    spans, current = [], None
    for page in pages:
        for heading in page.get("headings", []):
            if heading["level"] in (1, 2, 3):  # level 1: the chapter's opening text before its first section
                current = {"label": heading.get("label"), "text": heading["text"], "start": page["page"], "end": page["page"]}
                spans.append(current)
        if current: current["end"] = page["page"]
    return [dict(s, pages=min(s["end"], last) - max(s["start"], first) + 1) for s in spans if s["end"] >= first and s["start"] <= last]


def actions_for(run, chapter, metrics, limit, median_chars):
    """Ranked, machine-readable revision candidates for one text-only run."""
    first, last = run["start"], run["end"]
    at = _break_pages(run, limit)
    elements = chapter.get("elements", {})
    pages = [p for p in metrics["pages"] if first <= p["page"] <= last]
    density = statistics.mean(p["prose_chars"] for p in pages) if pages else 0
    base = {"chapter": chapter.get("id"), "pages": [first, last], "at_pages": at}
    out = []
    for section in sorted(_sections(metrics, chapter.get("id"), first, last), key=lambda s: -s["pages"]):
        if section["pages"] >= limit:
            out.append({"op": "split_section", **base, "section": section["label"], "section_title": section["text"],
                        "why": f"section runs {section['pages']} pages of this wall without a heading or pause"})
    if not elements.get("table"):
        out.append({"op": "convert_comparison_to_table", **base, "why": "chapter has no table; turn a passage comparing 3+ items on parallel attributes into one"})
    if not chapter.get("visuals") or (chapter.get("visuals_per_10k_chars") or 0) < 1.0:
        out.append({"op": "add_visual", **base, "why": f"chapter has {chapter.get('visuals', 0)} figures/tables; draw a process, structure or quantity the text explains"})
    if not elements.get("summary"):
        out.append({"op": "insert_summary", **base, "why": "no summary in this chapter; a mid-chapter key-point summary rests the reader at the break page"})
    if not elements.get("case-study"):
        out.append({"op": "add_case_study", **base, "why": "abstract stretch with no case study; use a sourced example"})
    if not elements.get("callout"):
        out.append({"op": "add_counterpoint", **base, "why": "no callout in this chapter; set a counter-argument or limitation apart"})
    if not elements.get("pull-quote"):
        out.append({"op": "add_pull_quote", **base, "why": "no pull quote; quote the source passage the argument rests on"})
    if median_chars and density > 1.1 * median_chars:
        out.append({"op": "shorten_paragraphs", **base, "why": f"{density:.0f} prose characters per page vs book median {median_chars:.0f}"})
    return out


def evaluate(metrics, limit_info):
    """Findings for the measured layout. High: a run over the limit, two or more runs at/over the limit in one
    chapter, or a run straddling a chapter boundary. Medium (reported, not blocking): runs at the limit or one
    below, limit-length runs in several chapters, text-only spreads and low non-prose share."""
    limit = limit_info["max_text_only_pages"]
    chapters = {c.get("id") or c.get("label"): c for c in metrics.get("chapters", [])}
    runs = metrics.get("text_only_runs", [])
    main = [p for p in metrics.get("pages", []) if p.get("region") == "main"]
    median_chars = statistics.median([p["prose_chars"] for p in main if p["prose_chars"]]) if any(p["prose_chars"] for p in main) else 0
    findings = []

    def add(level, rule, chapter, detail, **extra):
        findings.append({"severity": level, "rule": rule, "chapter": chapter, "detail": detail, **extra})

    for run in sorted(runs, key=lambda r: r["start"]):
        chapter = chapters.get(run.get("chapter"), {})
        spanned = {p.get("chapter") for p in metrics.get("pages", []) if run["start"] <= p["page"] <= run["end"]}
        where = f"pp. {run['start']}–{run['end']}" + (f" (folios {run['folios'][0]}–{run['folios'][1]})" if run.get("folios") else "")
        if len(spanned) > 1:
            add("high", "run_crosses_chapters", run.get("chapter"), f"{run['length']} text-only pages cross a chapter boundary at {where}",
                run=run, actions=actions_for(run, chapter, metrics, limit, median_chars))
        elif run["length"] > limit:
            add("high", "run_over_limit", run.get("chapter"), f"{run['length']} consecutive text-only pages at {where}; the {limit_info['tier']} limit is {limit}",
                run=run, actions=actions_for(run, chapter, metrics, limit, median_chars))
        elif run["length"] >= limit - 1 and run["length"] >= 2:
            add("medium", "run_near_limit", run.get("chapter"), f"{run['length']} consecutive text-only pages at {where} (limit {limit})", run=run)

    at_limit = [r for r in runs if r["length"] >= limit]
    by_chapter = {}
    for run in sorted(at_limit, key=lambda r: r["start"]): by_chapter.setdefault(run.get("chapter"), []).append(run)
    for chapter, own in by_chapter.items():
        if len(own) > 1:
            add("high", "repeated_walls_in_chapter", chapter,
                f"{len(own)} text-only runs of {limit}+ pages in one chapter (" + ", ".join(f"pp. {r['start']}–{r['end']}" for r in own) + ")",
                runs=own, actions=[a for r in own for a in actions_for(r, chapters.get(chapter, {}), metrics, limit, median_chars)[:2]])
    exact = {r.get("chapter") for r in at_limit if r["length"] == limit}
    if len(exact) > 1:  # a pattern worth fixing, but each wall is within the limit
        add("medium", "walls_in_several_chapters", None, f"text-only runs at the limit ({limit} pages) in {len(exact)} chapters: " + ", ".join(sorted(map(str, exact))),
            chapters=sorted(map(str, exact)))

    for chapter in metrics.get("chapters", []):
        cid = chapter.get("id") or chapter.get("label")
        target = limit_info.get("nonprose_share_target")
        share = chapter.get("nonprose_share")
        if target is not None and share is not None and target - share >= 0.12:
            corroboration = any(f.get("chapter") == cid and f["rule"] in ("run_over_limit", "repeated_walls_in_chapter", "text_only_spreads") for f in findings)
            add("medium", "chapter_nonprose_below_target", cid,
                f"non-prose share {share:.0%} is {target - share:.0%} below the {target:.0%} editorial target" +
                ("; combined with measured text walls, review existing prose for a suitable pause" if corroboration else "; target alone does not call for adding a device"),
                corroborated_by_text_wall=corroboration)
        spreads = [s for s in metrics.get("spreads", []) if s.get("chapter") == cid and s.get("text_only") and s.get("region") == "main"]
        if len(spreads) >= 2:
            add("medium", "text_only_spreads", cid, f"{len(spreads)} spreads with no pause on either page (" + ", ".join(f"pp. {s['pages'][0]}–{s['pages'][-1]}" for s in spreads[:4]) + ")")
    totals = metrics.get("totals", {})
    target = limit_info.get("nonprose_share_target")
    share = totals.get("nonprose_share")
    if target is not None and share is not None and target - share >= 0.12:
        corroboration = any(f["severity"] == "high" and f["rule"] in ("run_over_limit", "repeated_walls_in_chapter", "run_crosses_chapters") for f in findings)
        add("medium", "book_nonprose_below_target", None,
            f"book non-prose share {share:.0%} is {target - share:.0%} below the {target:.0%} editorial target" +
            ("; measured wall findings provide revision context" if corroboration else "; target alone does not call for adding devices"),
            corroborated_by_text_wall=corroboration)

    summary = {"max_text_only_run": totals.get("max_text_only_run", 0), "runs_3_plus": sum(r["length"] >= 3 for r in runs),
               "runs_5_plus": sum(r["length"] >= 5 for r in runs), "text_only_spreads": totals.get("text_only_spreads", 0),
               "book_nonprose_share": totals.get("nonprose_share"), "nonprose_share_target": limit_info.get("nonprose_share_target"),
               "chapters": [{"id": c.get("id"), "max_text_only_run": c.get("max_text_only_run", 0), "nonprose_share": c.get("nonprose_share"),
                             "text_only_pages": c.get("text_only_pages", 0), "page_count": c.get("page_count")} for c in metrics.get("chapters", [])],
               "chapters_over_limit": sorted({f["chapter"] for f in findings if f["rule"] == "run_over_limit"} - {None}),
               "high": sum(f["severity"] == "high" for f in findings), "medium": sum(f["severity"] == "medium" for f in findings)}
    return {"schema": SCHEMA, "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "metrics_generated_at": metrics.get("generated_at"), "limits": limit_info,
            "pause_definition": metrics.get("definitions"), "verdict": "fail" if summary["high"] else "pass",
            "summary": summary, "findings": findings}


def unmeasured(problem, limit_info):
    level = "medium" if limit_info.get("allow_unmeasured") else "high"
    return {"schema": SCHEMA, "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "limits": limit_info,
            "verdict": "fail" if level == "high" else "pass", "summary": {"high": int(level == "high"), "medium": int(level == "medium")},
            "findings": [{"severity": level, "rule": "layout_unmeasured", "chapter": None,
                          "detail": f"pacing cannot be verified: {problem}. Rebuild the PDF (`bookorder goal`); if measuring keeps failing, "
                                    "fix the build or, with the user's approval, set project.json pacing.allow_unmeasured: true"}]}


def check(project=None):
    """Evaluate the current build and write reports/pacing-report.json."""
    limit_info = limits(project)
    metrics, problem = load_metrics()
    result = unmeasured(problem, limit_info) if problem else evaluate(metrics, limit_info)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def ledger_issues(result):
    """Audit-ledger issues (scope "layout"); the revision candidates ride along for tasks and reports."""
    from audit import issue
    found = []
    for finding in result["findings"]:
        item = issue(ISSUE_TYPE, finding["severity"], finding.get("chapter"), finding["detail"], action="layout",
                     evidence=finding["rule"])
        if finding.get("actions"): item["actions"] = finding["actions"]
        found.append(item)
    return found


def task_lines(result, chapter):
    """Instructions for revising one chapter's text walls."""
    lines = []
    for finding in result["findings"]:
        if finding["severity"] != "high" or finding.get("chapter") != chapter: continue
        lines.append(f"- {finding['detail']}")
        for action in finding.get("actions", [])[:5]:
            target = f" section {action['section']}" if action.get("section") else ""
            lines.append(f"    candidate {action['op']}{target} near page(s) {', '.join(map(str, action['at_pages']))}: {action['why']}")
    return lines

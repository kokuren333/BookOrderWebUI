"""Claude-orchestrated jobs (project.json workflow.mode = "claude-orchestrated").

Claude Code runs the job end to end: it is the orchestrator, the author and the designer. Research-type work —
fetching and extracting sources, supplementary web research, per-source notes, chapter evidence maps and post-draft
fact checks — is delegated to an external research agent (Codex CLI by default) through `bookorder delegate`.
The delegate returns structured evidence, never manuscript prose; Claude reviews it and writes the book.

Design is a conversation: Claude proposes directions, renders proof pages (`bookorder proof`), revises the design
from the user's natural-language feedback and only finishes the design phase after the user approves it
(`bookorder design-approve --user-approval "<the user's words>"`).

Legacy jobs (no mode) are unaffected: every function here returns early for them.
"""
import json
import os
from pathlib import Path

from common import ROOT

MODE = "claude-orchestrated"
# Task ids that belong to the research delegate. `synthesize` stays with Claude: the book's thesis and argument map
# are authorial decisions, made from the delegate's notes.
DELEGATED_PREFIXES = ("ingest:", "verify:", "research:", "analyze:")
VOICE_PREFIXES = ("draft:", "expand:", "rewrite:", "prose:", "integrate", "manuscript-revision", "architecture")
DEFAULT_AGENTS = {"orchestrator": "claude-code", "researcher": "codex-cli", "writer": "claude-code",
                  "designer": "claude-code", "reviewer": "claude-code"}
DEFAULT_DELEGATE = {"cli": "codex", "search": True, "sandbox": "workspace-write", "network": True,
                    "model": None, "reasoning_effort": None, "timeout_minutes": 45, "extra_args": []}
VOICE_SKILL = "skills/authoring/voice.md"
RESEARCH_SKILL = "skills/research/evidence-research.md"
DESIGN_SKILL = "skills/design/design-dialogue.md"


def config(project):
    return ((project or {}).get("workflow") or {})


def active(project):
    return config(project).get("mode") == MODE


def delegate_settings(project):
    settings = dict(DEFAULT_DELEGATE)
    settings.update(config(project).get("delegate") or {})
    return settings


def evidence_required(project):
    return active(project) and config(project).get("evidence_maps", True) is not False


def design_dialogue(project):
    return active(project) and config(project).get("design_dialogue", True) is not False


def agents(project):
    return {**DEFAULT_AGENTS, **(config(project).get("agents") or {})} if active(project) else (config(project).get("agents") or {})


def light(project):
    """Loose harness (the default for Claude-orchestrated jobs): invariants are enforced — sources, citations,
    evidence, user intent, outputs, legibility — while structural heuristics (editorial-plan device counts, text-wall
    pacing, art-direction drift, architecture QA findings) are reported as advice instead of blocking."""
    return active(project) and config(project).get("strictness", "light") != "strict"


ADVISORY_GATES = {17: "layout pacing", 18: "editorial plan heuristics", 20: "art direction drift", 23: "architecture QA"}


def relax_gates(project, gates):
    if not light(project): return gates
    for gate in gates:
        if gate["id"] in ADVISORY_GATES and not gate["passed"]:
            gate["passed"] = True; gate["advisory"] = True
            gate["detail"] = "advisory (light harness): " + str(gate["detail"])
    return gates


def factcheck_required(project):
    return active(project) and config(project).get("factcheck", True) is not False


def research_brief_path():
    return ROOT / "plan/research-brief.md"


def research_requirements(project):
    return str(((project or {}).get("research") or {}).get("requirements") or "").strip()


def design_references(project):
    """project.json design_references: {books: "titles the user named", auto_collect: true}."""
    value = (project or {}).get("design_references") or {}
    return {"books": str(value.get("books") or "").strip(), "auto_collect": value.get("auto_collect", True) is not False}


def evidence_path(chapter_id):
    return ROOT / "research/evidence" / f"{chapter_id}.yaml"


def factcheck_path(chapter_id):
    return ROOT / "research/factcheck" / f"{chapter_id}.yaml"


def manuscript_digest(chapter_file):
    import hashlib
    path = ROOT / str(chapter_file)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def factcheck_current(chapter):
    """The fact check was run on the chapter text as it is now."""
    meta = ROOT / "research/factcheck" / f"{chapter['id']}.meta.json"
    if not factcheck_path(chapter["id"]).is_file() or not meta.is_file(): return False
    try: recorded = json.loads(meta.read_text(encoding="utf-8")).get("manuscript_sha256")
    except ValueError: return False
    return recorded == manuscript_digest(chapter["file"])


def audit_problems(project, chapter):
    """Evidence verification that must pass before a chapter audit is accepted (Claude mode)."""
    if not active(project): return []
    cmd = launcher(); problems = []
    if factcheck_required(project) and not factcheck_current(chapter):
        problems.append(f"research/factcheck/{chapter['id']}.yaml missing or older than the chapter text — run `{cmd} delegate factcheck {chapter['id']}`")
    import evidence_verify
    problems += [p["detail"] for p in evidence_verify.chapter(chapter, project)["findings"] if p["severity"] == "high"][:12]
    return problems


def launcher():
    """The command the agent should type in this job folder."""
    if (ROOT / "bookorder.cmd").is_file() and os.name == "nt": return "bookorder.cmd"
    if (ROOT / "bookorder").is_file() and os.name != "nt": return "sh bookorder"
    return "python scripts/cli.py"


def delegated(item):
    return str(item.get("id", "")).startswith(DELEGATED_PREFIXES) and item.get("kind", "agent") == "agent"


def role(item, project):
    if not active(project): return None
    if delegated(item): return "researcher"
    return None


def decorate(item, project):
    """Add Claude-mode routing to a task printed by the orchestrator. Never removes the original instructions."""
    if not active(project) or item.get("claude_mode"): return item
    item["claude_mode"] = True
    ident = str(item.get("id", "")); cmd = launcher()
    lines = list(item.get("instructions") or [])
    skills = list(item.get("skills") or [])
    if delegated(item):
        item["delegate"] = f"{cmd} delegate {ident}"
        lines = [f"DELEGATE (research agent): run `{cmd} delegate {ident}`. It runs Codex CLI non-interactively with this task, "
                 "the user's instructions and the research skill. Then YOU review what it wrote (spot-check locators against the source text, "
                 "fix or re-run with `--note \"what to redo\"`) before `bookorder done`. Independent analyze:/ingest: tasks may run as parallel "
                 "background commands; research:supplementary runs alone.",
                 "The text below is what the delegate is asked to do:"] + lines
        if ident == "research:supplementary":
            brief = research_brief_path().relative_to(ROOT).as_posix()
            if not research_brief_path().is_file():
                lines = [f"BRIEF FIRST (you, not the delegate): write {brief} from the user's goal, instructions and research requirements "
                         "(docs/research-brief.md): research questions, claim types that need evidence, acceptable source tiers, recency, languages, "
                         "exclusions, and what counts as general knowledge that needs no citation. The delegate builds the corpus from it — the user "
                         "does not have to supply sources."] + lines
    elif ident.startswith("draft:") and evidence_required(project):
        chapter = ident.split(":", 1)[1]
        rel = evidence_path(chapter).relative_to(ROOT).as_posix()
        if not evidence_path(chapter).is_file():
            lines = [f"EVIDENCE FIRST: run `{cmd} delegate evidence {chapter}` (Codex maps every claim this chapter needs to sources, locators and "
                     f"strength, plus sharp findings and contested points) and review {rel}. The chapter is not counted as drafted until it exists."] + lines
        lines.append(f"Write from {rel}: state strongly supported claims plainly and cite them; hedge only where the map says the evidence is "
                     "contested or weak, and then say once, precisely, what is uncertain. Build the chapter around its sharp findings, not around a survey.")
    elif ident.startswith(("audit:", "reaudit:")) and ident != "audit:book":
        chapter = ident.split(":", 1)[1]
        rel = factcheck_path(chapter).relative_to(ROOT).as_posix()
        lines.append((f"EVIDENCE VERIFICATION: run `{cmd} delegate factcheck {chapter}` (Codex checks every factual sentence against the cited source "
                      f"text and flags unsupported, miscited, uncited and over-hedged sentences → {rel}) and `{cmd} evidence verify --chapter {chapter}` "
                      "(deterministic: quotes in the evidence map exist in the source text, every citation points to an evidence-role source). "
                      "Copy every real problem into this audit file as an issue; dismiss false alarms with a one-line reason."
                      if factcheck_required(project) else
                      f"Optional: `{cmd} delegate factcheck {chapter}` and `{cmd} evidence verify --chapter {chapter}`."))
    if ident.startswith(VOICE_PREFIXES) and VOICE_SKILL not in skills: skills.append(VOICE_SKILL)
    if ident == "design" and design_dialogue(project) and DESIGN_SKILL not in skills: skills.append(DESIGN_SKILL)
    if ident.startswith(("research:", "analyze:")) and RESEARCH_SKILL not in skills: skills.append(RESEARCH_SKILL)
    item["instructions"] = lines; item["skills"] = skills
    return item


def drafting_problems(project, chapter_id):
    if not evidence_required(project) or evidence_path(chapter_id).is_file(): return []
    return [f"research/evidence/{chapter_id}.yaml missing — run `{launcher()} delegate evidence {chapter_id}` before drafting"]


def evidence_gate(project, chapters):
    """Gate 24 (Claude mode): every chapter has an evidence map, a current fact check (unless switched off) and no
    high-severity verification finding (quote not in the source, citation of a non-evidence source, unknown ID)."""
    import evidence_verify
    problems = []
    for chapter in chapters:
        if evidence_required(project) and not evidence_path(chapter["id"]).is_file(): problems.append(f"{chapter['id']}: no evidence map")
        if factcheck_required(project) and not factcheck_current(chapter): problems.append(f"{chapter['id']}: fact check missing or stale")
        high = [f for f in evidence_verify.chapter(chapter, project)["findings"] if f["severity"] == "high"]
        if high: problems.append(f"{chapter['id']}: {len(high)} verification problem(s), e.g. {high[0]['detail'][:120]}")
    return {"passed": not problems, "detail": "; ".join(problems[:6]) or f"{len(chapters)} chapters mapped and verified"}


# ---------------------------------------------------------------- generated images

def image_review_task(project, state, style):
    """After images are generated: series check, contact sheet, and Claude's (and the user's) review."""
    if not active(project): return None
    images = sorted((ROOT / "source/assets/images").glob("*.png")) if (ROOT / "source/assets/images").is_dir() else []
    generated = [p for p in images if (ROOT / "source/assets/generated" / (p.stem + ".json")).is_file()]
    if not generated: return None
    import image_style
    report = image_style.check(style["palette"]); sheet = image_style.contact_sheet(style["palette"])
    review = ROOT / "plan/image-review.md"
    newest = max(p.stat().st_mtime for p in generated)
    if review.is_file() and review.stat().st_mtime >= newest and "image-review" in (state or {}).get("reported", {}): return None
    weak = [f"{i['file']}: palette conformance {i['score']:.0%} (off-palette {', '.join(i.get('off_palette_colours') or [])})"
            for i in report["images"] if i.get("severity") == "medium"]
    cmd = launcher()
    return ("image-review", "asset_generation", "Review the generated images as one series against the design", [
        f"Open {sheet.relative_to(ROOT).as_posix()} (every generated image beside the style anchor and the palette) and the proof pages where they sit "
        f"(`{cmd} proof`). Judge them as a set: same medium, line, texture, palette use, lighting and level of detail as plan/image-style.md "
        "and design/image-anchor.png; nothing that fights the page (busy backgrounds behind text, clashing colour, wrong paper tone, "
        "accidental text or watermark, fake data).",
        "Regenerate an outlier by refining its subject/must_not_show in plan/assets-plan.yaml (or the style sheet if the whole set drifts) and "
        f"running `{cmd} goal` — a changed request regenerates only that image. If the style sheet changes, all images regenerate.",
        "Show the user the contact sheet when the images matter to the book's look (openers, part pages) and apply their feedback.",
        "Write plan/image-review.md: for each image keep / regenerated (why), what you checked, and the user's comments; then "
        "`bookorder done image-review`.", *(["Automatic palette check flagged:"] + weak if weak else [])],
        (), (), None, weak)


# ---------------------------------------------------------------- design dialogue

def design_approval(state):
    return (state or {}).get("design_approval")


def approve_design(state, quote, note=None):
    from orchestrator import now
    quote = (quote or "").strip()
    if len(quote) < 2: raise ValueError("--user-approval must quote what the user said when approving the design")
    state["design_approval"] = {"at": now(), "user_approval": quote, "note": note, "fingerprint": design_fingerprint()}
    return state["design_approval"]


def design_fingerprint():
    """Hash of everything that decides the book's appearance; an approval is for this exact design."""
    import hashlib
    digest = hashlib.sha256()
    paths = [ROOT / "book.design.yaml", ROOT / "custom.css", ROOT / "custom.typ", ROOT / "plan/image-style.md", ROOT / "design/image-anchor.png"]
    try:
        theme = json.loads((ROOT / "book.design.yaml").read_text(encoding="utf-8")).get("theme")
    except (OSError, ValueError):
        theme = None
    if theme and (ROOT / "themes" / str(theme)).is_dir():
        paths += sorted(p for p in (ROOT / "themes" / str(theme)).rglob("*") if p.is_file() and p.suffix != ".png")
    for path in paths:
        if path.is_file():
            digest.update(path.relative_to(ROOT).as_posix().encode("utf-8")); digest.update(path.read_bytes())
    return digest.hexdigest()


def design_dialogue_errors(project, state):
    if not design_dialogue(project): return []
    approval = design_approval(state)
    if not approval:
        return ["Design not approved by the user yet: show proof pages, iterate in conversation, then "
                f"`{launcher()} design-approve --user-approval \"<the user's words>\"`"]
    if approval.get("fingerprint") != design_fingerprint():
        return ["The design changed after the user approved it: show the user the new proof pages and record a new approval"]
    return []


def design_task_lines(project):
    if not design_dialogue(project): return []
    cmd = launcher()
    refs = design_references(project)
    named = f" The user named: {refs['books']}." if refs["books"] else ""
    return [
        "DESIGN IS A CONVERSATION WITH THE USER (skills/design/design-dialogue.md). Do not finish this task alone.",
        "0. Reference books first: list 4–6 well-designed books this book should learn from (same genre and reading mode, plus one or two "
        f"exemplary outliers).{named} " + (f"`{cmd} delegate design-refs` has Codex find them and collect publisher sample pages / preview images "
        "into design/references/ (design/references.yaml records title, publisher, why, page types and source URLs). "
        if refs["auto_collect"] else "Collect sample pages only from what the user supplies. ") +
        "Open the images, analyse them (grid, margins, type sizes and contrast, heading hierarchy, opener, tables, figures, callouts, colour "
        "use) into plan/design-references.yaml, and show the user the list before proposing directions. Learn the principles; never copy text, "
        "artwork, logos or a recognisable trade dress.",
        "1. Read the manuscript's character (plan/book-bible.yaml, two representative chapters) and the user's art direction. Propose 2–3 clearly "
        "different directions in words (mood, type pairing, page rhythm, chapter opener, colour, how figures and callouts look), each with a reason "
        "tied to this book. The WebUI theme and values are only a starting point; any theme may be replaced.",
        f"2. Build the chosen direction freely: a book-specific theme is allowed and encouraged (`{cmd} theme fork <base> book` copies a theme to "
        "themes/book/ for you to rewrite — CSS and Typst — and selects it). book.design.yaml, custom.typ and custom.css are all yours.",
        f"3. Render proofs and LOOK at them: `{cmd} proof` (chapter opener, a dense text spread, a figure/table page, a callout page) writes PNGs "
        "under proofs/ and proofs/<run>/compare.html (proof pages beside the reference samples). Open the PNGs, critique them against the "
        "references and skills/design/design-dialogue.md's checklist, fix what is obviously wrong, then show the user and ask what to change.",
        "4. Apply the user's natural-language feedback, re-proof, repeat. Their words in this conversation outrank the WebUI design values "
        "(record each request and how you applied it in plan/design-dialogue.md). Outputs, citations and manuscript text stay as they are.",
        "4b. If the book has generated images (figures policy allows them; image_generation.provider = codex): write plan/image-style.md from "
        "the approved direction (skills/design/image-style.md), run `" + cmd + " images samples` for style-anchor candidates, choose one with the "
        "user and fix it with `" + cmd + " images anchor design/image-samples/sample-N.png`. Every image is then generated in that style.",
        f"5. When the user says it is good, run `{cmd} design-approve --user-approval \"<quote the user>\"`, write plan/design-decisions.yaml, "
        "then `bookorder done design`. Changing the design afterwards needs a new approval.",
    ]

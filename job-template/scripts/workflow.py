"""Portable writer/designer/reviewer handoff and stage boundaries. The host runs agents."""
import hashlib
import json
import copy
from pathlib import Path
import zipfile

from common import ROOT, write_json, yaml_data

WRITE_PHASES = ("source_ingestion", "supplementary_research", "corpus_analysis", "research_frozen",
                "publication_planning", "architecture", "reference_assignment", "editorial_planning",
                "visual_planning", "drafting", "chapter_review", "asset_planning", "integration", "audit",
                "rewrite", "prose_audit", "prose_editing", "final_audit")
DESIGN_PHASES = ("design", "asset_generation")
RENDER_PHASES = ("layout", "build", "validation", "package", "complete")
STAGES = {"write": WRITE_PHASES, "design": DESIGN_PHASES, "render": RENDER_PHASES}
REVIEW_PHASES = {"audit", "final_audit", "prose_audit", "chapter_review", "validation"}


def separated(project=None, state=None):
    return bool((state or {}).get("stage_protocol") or ((project or {}).get("workflow") or {}).get("separated"))


def phase_order(state, legacy):
    return list(WRITE_PHASES + DESIGN_PHASES + RENDER_PHASES) if separated(state=state) else legacy


def stage_of(phase):
    return next((stage for stage, phases in STAGES.items() if phase in phases), "write")


def role_of(phase):
    return "reviewer" if phase in REVIEW_PHASES else "writer" if stage_of(phase) == "write" else "designer"


def protected_paths(root):
    root = Path(root)
    paths = list((root / "source/manuscript").glob("*.md"))
    paths += list((root / "source/references").rglob("*"))
    paths += list((root / 'source/assets/data').rglob('*'))
    paths += [root / "source/metadata" / name for name in ("outline.yaml", "sources.yaml", "glossary.yaml")]
    return [p for p in sorted(set(paths)) if p.is_file()]


def semantic_assets(root):
    """The designer may adjust geometry/style; factual payloads, labels, IDs and captions stay with the writer."""
    root = Path(root); path = root / 'plan/assets-plan.yaml'
    plan = yaml_data(path) if path.is_file() else {}
    assets = [{k: v for k, v in asset.items() if k not in ('geometry', 'style')}
              for asset in plan.get('assets', []) if isinstance(asset, dict)]
    diagrams = {}
    for asset in assets:
        source = root / str(asset.get('source', ''))
        if asset.get('type') == 'diagram' and source.is_file():
            spec = yaml_data(source)
            diagrams[str(asset['id'])] = {
                'title': spec.get('title'),
                'nodes': [{k: node.get(k) for k in ('id', 'label') if k in node} for node in spec.get('nodes', [])],
                'edges': [{k: edge.get(k) for k in ('from', 'to', 'label') if k in edge} for edge in spec.get('edges', [])]}
    return {'assets': assets, 'existing_diagram_content': diagrams}


def hashes(root=None):
    root = Path(root or ROOT)
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected_paths(root)}


def freeze(project, root=None):
    """Snapshot the actual canonical inputs, not a summary. Each revision replaces the handoff manifest."""
    root = Path(root or ROOT)
    frozen = hashes(root)
    if not any(p.startswith("source/manuscript/") for p in frozen): raise ValueError("Cannot hand off an empty manuscript")
    manifest = {"schema": "bookorder/manuscript-handoff@1", "files": frozen, 'semantic_assets': semantic_assets(root),
                "body": "source/manuscript/", "chapter_structure": "source/metadata/outline.yaml",
                "citations": "source/references/", "source_ids": "research/index.json",
                "source_roles": "plan/source-roles.yaml", "figure_content_and_intent": ["plan/visual-plan.yaml", "plan/assets-plan.yaml", "plan/editorial/"],
                "design_requirements": {"user_instructions": project.get("user_instructions", ""),
                                        "design": project.get("design", {}), "layout_spec": project.get("layout_spec", {}),
                                        "layout_preset": project.get("layout_preset"), "style_controls": project.get("style_controls", {}),
                                        "resolved_files": ['book.design.yaml', 'plan/layout-spec.yaml', 'plan/style-bible.yaml', 'plan/book-bible.yaml']},
                "change_prohibited": {"files": list(frozen), "sections": (project.get("workflow") or {}).get("protected_sections", []),
                                      "rule": "Design/render may create assets and adjust appearance; request text/citation changes from the writer."}}
    for name in frozen:
        target = root / "handoff" / name
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes((root / name).read_bytes())
    content_paths = [root / 'plan/assets-plan.yaml']
    plan = yaml_data(root / 'plan/assets-plan.yaml') if (root / 'plan/assets-plan.yaml').is_file() else {}
    content_paths += [root / str(a['source']) for a in plan.get('assets', []) if isinstance(a, dict) and a.get('type') == 'diagram' and a.get('source')]
    manifest['content_snapshots'] = {}
    for source in content_paths:
        if not source.is_file(): continue
        name = source.relative_to(root).as_posix(); target = root / 'handoff' / name
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(source.read_bytes())
        manifest['content_snapshots'][name] = hashlib.sha256(source.read_bytes()).hexdigest()
    write_json(root / "handoff/manifest.json", manifest)
    return manifest


def check_frozen(root=None):
    root = Path(root or ROOT); path = root / "handoff/manifest.json"
    if not path.is_file(): return ["Missing handoff/manifest.json; finish the write stage first"]
    manifest = json.loads(path.read_text(encoding="utf-8")); original = manifest['files']
    current = hashes(root)
    changed = [name for name in sorted(set(original) | set(current)) if original.get(name) != current.get(name)]
    before = manifest.get('semantic_assets')
    if before is not None:
        after = semantic_assets(root)
        # New Diagram IR is created by the designer from the writer's content specification.
        after['existing_diagram_content'] = {k: v for k, v in after['existing_diagram_content'].items() if k in before['existing_diagram_content']}
        if before != after: changed.append('plan/assets-plan.yaml / diagram semantic content')
    return changed


def restore(root=None):
    """Restore the frozen text before a writer revision, so designer edits cannot silently become canonical."""
    root = Path(root or ROOT)
    manifest = json.loads((root / "handoff/manifest.json").read_text(encoding="utf-8"))
    snapshots = {**manifest['files'], **manifest.get('content_snapshots', {})}
    for name in snapshots:
        backup = root / "handoff" / name
        if not backup.is_file() or hashlib.sha256(backup.read_bytes()).hexdigest() != snapshots[name]:
            raise ValueError(f"Handoff snapshot corrupt: {name}")
    for name, digest in hashes(root).items():
        if name not in manifest['files'] or digest != manifest['files'][name]:
            source = root / name
            backup = root / 'handoff/rejected-changes' / (digest[:12] + '-' + Path(name).name)
            backup.parent.mkdir(parents=True, exist_ok=True); backup.write_bytes(source.read_bytes())
            if name not in manifest['files']: source.unlink()
    for name in snapshots:
        target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / "handoff" / name).read_bytes())


def export(path, root=None):
    root = Path(root or ROOT); path = Path(path).resolve()
    if not (root / "handoff/manifest.json").is_file(): raise ValueError("No manuscript handoff yet")
    path.parent.mkdir(parents=True, exist_ok=True)
    folders = ("source", "input", "research", "plan", "handoff", "scripts", "skills", "schemas", "config", "themes", "templates", "docs", "third-party", "reports", "runtime")
    paths = [p for folder in folders for p in (root / folder).rglob("*") if p.is_file()]
    paths += [p for p in root.iterdir() if p.is_file() and p.suffix not in (".zip", ".tmp")]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(set(paths)):
            relative = item.relative_to(root)
            if item.resolve() == path or "__pycache__" in relative.parts or item.suffix == ".pyc": continue
            # Original runtime archives are portable; expanded runtime executables are host-specific caches.
            if relative.parts[0] == "runtime" and len(relative.parts) > 2 and relative.parts[1] not in ("archives", "fonts"): continue
            archive.write(item, "publishing-job/" + relative.as_posix())
    return path


def attach_task(item, project, state):
    role = 'writer' if item.get('id') == 'manuscript-revision' or str(item.get('id', '')).startswith('expand:') else role_of(item["phase"])
    agents = {**((project.get("workflow") or {}).get("agents") or {}), **state.get("agent_overrides", {})}
    item.update(stage=stage_of(item["phase"]), role=role, agent=agents.get(role))
    if separated(project, state) and item["stage"] != "write":
        item["inputs"] = list(dict.fromkeys(item["inputs"] + ["handoff/manifest.json"]))
        item["instructions"] = item["instructions"] + [
            "Canonical manuscript and citation files are frozen in handoff/manifest.json. Do not rewrite them.",
            "Create diagrams/images at the paths and IDs already specified by the writer; change design/layout only.",
            'For a necessary text change run: bookorder revision request --reason "..." [--chapter ch-id]. Then resume bookorder write.']
    return item


def asset_content_errors(ctx):
    import assets
    import visual_review
    errors = []; records = ctx.by_chapter(); decisions = visual_review.decisions() or {}
    for asset in assets.assets():
        ident = str(asset.get('id')); kind = asset.get('type')
        if decisions.get(ident) == 'rejected': continue
        record = records.get(asset.get('chapter')) or {}
        if kind in ('diagram', 'chart', 'image', 'screenshot'):
            if ident not in record.get('figures', []): errors.append(f'{ident}: place the figure link/ID/caption in the manuscript before handoff')
            expected = assets.diagram_output(asset) if kind == 'diagram' else asset.get('path')
            if expected not in record.get('images', []): errors.append(f'{ident}: figure path must be {expected}')
        elif kind == 'table' and ident not in record.get('tables', []): errors.append(f'{ident}: write the table content before handoff')
        elif kind == 'equation' and ident not in record.get('equations', []): errors.append(f'{ident}: write the equation content before handoff')
        if kind == 'diagram' and not asset.get('content') and not (ROOT / str(asset.get('source', ''))).is_file():
            errors.append(f'{ident}: specify nodes, relations and labels in content or a Diagram IR file')
        if kind == 'chart' and not (ROOT / str(asset.get('data', ''))).is_file(): errors.append(f'{ident}: save the factual chart data before handoff')
    return errors


def request_revision(project, state, reason, chapter=None, page_count=None):
    import orchestrator
    if state.get("revision_request"): raise ValueError("A writer revision is already pending")
    if not reason or len(reason.strip()) < 5: raise ValueError("Describe the requested manuscript change")
    if not (ROOT / "handoff/manifest.json").is_file(): raise ValueError("Finish the write stage before requesting a revision")
    if chapter:
        known = [c["id"] for c in orchestrator.Context(project, state).outline()]
        if chapter not in known: raise ValueError(f"Unknown chapter {chapter}")
    if check_frozen(): raise ValueError("Frozen manuscript changed; restore it before requesting revision")
    request = {"reason": reason, "chapter": chapter, "page_count": page_count, "before": hashes(), "status": "pending",
               "resume_stage": state.get('execution_stage', 'all')}
    state["revision_request"] = request
    state["status"] = "running"
    orchestrator.reopen(state, "chapter_review", reason)
    state["execution_stage"] = "write"
    write_json(ROOT / "plan/manuscript-revision-request.json", request)
    orchestrator.save_state(state)
    return request


def revision_task(ctx):
    import orchestrator
    request = ctx.state["revision_request"]
    lines = [request["reason"], "Revise only the requested content. Preserve citations, source IDs, required topics and protected sections.",
             "Update changed chapter summaries; later integration and citation audits will run again."]
    pages = request.get("page_count")
    if pages:
        ratio = pages["target_pages"] / pages["actual_pages"]
        scale = ctx.state["scale"]
        lines += [f"Measured PDF: {pages['actual_pages']} pages; target {pages['target_pages']}. Suggested body multiplier: {ratio:.3f}.",
                  f"Revise chapter budgets in source/metadata/outline.yaml to a total near {round(scale['target_characters'] * ratio)} characters.",
                  "Compress redundant prose or add source-supported explanations within the user's scope. Do not shrink fonts/margins to fit."]
    item = orchestrator.task("manuscript-revision", "chapter_review", "Writer revision requested by design/render", lines,
                             outputs=["source/manuscript/", "plan/summaries/"])
    return attach_task(item, ctx.project, ctx.state)


def protected_sections_changed(project, root=None):
    import re
    root = Path(root or ROOT)
    protected = (project.get("workflow") or {}).get("protected_sections", [])
    def section(text, ident):
        lines = text.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if "#" + ident + "}" in line or re.search(r"\{[^}]*#" + re.escape(ident) + r"(?:\s|\})", line):
                match = re.match(r"^(#{1,6})\s", line)
                if not match: raise ValueError(f"Protected ID {ident} must identify a heading")
                level = len(match[1]); end = len(lines)
                for j in range(i + 1, len(lines)):
                    heading = re.match(r"^(#{1,6})\s", lines[j])
                    if heading and len(heading[1]) <= level: end = j; break
                return "".join(lines[i:end])
        return None
    for ident in protected:
        old = []; new = []
        manifest = json.loads((root / 'handoff/manifest.json').read_text(encoding='utf-8'))
        for name in manifest['files']:
            if not name.startswith('source/manuscript/') or not name.endswith('.md'): continue
            path = root / 'handoff' / name
            old.append(section(path.read_text(encoding="utf-8"), str(ident)))
        for path in (root / "source/manuscript").glob("*.md"):
            new.append(section(path.read_text(encoding="utf-8"), str(ident)))
        old = [v for v in old if v is not None]; new = [v for v in new if v is not None]
        if len(old) != 1 or old != new: return str(ident)
    return None


def complete_revision(ctx):
    request = ctx.state.get("revision_request")
    if not request: raise ValueError("No writer revision pending")
    current = hashes()
    changed = [p for p in set(current) | set(request['before']) if p.startswith('source/manuscript/') and request['before'].get(p) != current.get(p)]
    if not changed: raise ValueError("The requested manuscript revision has not changed any chapter")
    protected = protected_sections_changed(ctx.project)
    if protected: raise ValueError(f"Protected section changed or missing: {protected}")
    if request.get("chapter"):
        allowed = next(c["file"] for c in ctx.outline() if c["id"] == request["chapter"])
        if any(p != allowed for p in changed): raise ValueError("Revision changed chapters outside the requested scope")
    pages = request.get("page_count")
    if pages:
        import publication_profile as pp
        from planning import check_outline
        ratio = pages["target_pages"] / pages["actual_pages"]
        scale = copy.deepcopy(ctx.state['scale'])
        scale["target_characters"] = round(scale["target_characters"] * ratio)
        scale["minimum_characters"] = round(scale["target_characters"] * scale["minimum_ratio"])
        errors, chapters = check_outline(scale, ctx.project)
        budgets = sum(c['target_characters'] for c in chapters)
        if not .95 * scale['target_characters'] <= budgets <= 1.1 * scale['target_characters']:
            errors.append(f"Chapter budgets must total 95–110% of the revised {scale['target_characters']} character target (got {budgets})")
        if errors: raise ValueError('Update chapter budgets/structure for the page revision: ' + '; '.join(errors))
        ctx.state['scale'] = scale
        profile = pp.load_resolved()
        if profile:
            profile["scale"]["target_body_chars"] = scale["target_characters"]; pp.write(profile)
        ctx.state["counters"]["page_feedback_rounds"] = ctx.state["counters"].get("page_feedback_rounds", 0) + 1
    request["status"] = "submitted"
    write_json(ROOT / "plan/manuscript-revision-request.json", request)
    ctx.state.pop("revision_request")
    ctx.state["accepted"].pop("integrate", None); ctx.state["accepted"].pop("audit", None)
    for key in list(ctx.state.get("reported", {})):
        if key in ("integrate", "audit:book", "design", "layout-review") or key.startswith(("audit:", "reaudit:", "prose:")):
            ctx.state["reported"].pop(key, None)
    if request.get('resume_stage') == 'all': ctx.state['execution_stage'] = 'all'


def design_feedback(ctx, pages):
    options = ctx.project.get("page_feedback") or {}
    if pages.get("status") not in ("over_target", "under_target") or options.get("enabled", True) is False: return None
    if ctx.state["counters"].get("page_feedback_rounds", 0) >= int(options.get("max_rounds", 3)):
        return {"category": "page count", "detail": "Page feedback round limit reached; review reports/page-count.json and adjust the plan or tolerance."}
    request_revision(ctx.project, ctx.state, "PDF page count differs substantially from the target; compress or expand the manuscript and re-typeset.", page_count=pages)
    return "requested"

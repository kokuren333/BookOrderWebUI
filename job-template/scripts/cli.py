"""BookOrder CLI. `bookorder goal` is the single entry point that owns the publication lifecycle.

Publication:  goal | done <task> | status [--json] | gates | block | unblock
Stages:       write | design | render [--restart] [--agent role=assignment] | handoff --export ZIP
Feedback:     pages | revision request --reason ... [--chapter ch-id]
Sources:      source list | fetch | submit | confirm | accept-partial | unavailable | add
Research:     research log | research status
Audit:        audit resolve <id> --note ... [--wontfix] | audit report
Design:       build [--theme] | fonts | theme list | theme preview <name> | theme fork <base> [<name>]
Claude mode:  delegate <task-id> | delegate evidence|factcheck <chapter> | delegate ask "<question>"
              proof [--pages 3,10-11] | design-approve --user-approval "..." | voice [--chapter ch-id]
              delegate design-refs | evidence verify [--chapter ch-id]
              images samples [--count 3] | images anchor <png> | images check | images sheet
"""
import argparse
from contextlib import redirect_stdout, nullcontext
import json
from pathlib import Path
import shutil
import subprocess
import sys
from common import ROOT, run, tool


def preview(theme):
    from design import load_design, theme_path
    theme_path(theme)
    destination = ROOT / '.previews' / theme
    destination.mkdir(parents=True, exist_ok=True)
    for folder in ('scripts', 'themes', 'schemas', 'templates'):
        shutil.copytree(ROOT / folder, destination / folder, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(ROOT / 'templates/preview/source', destination / 'source', dirs_exist_ok=True)
    for name in ('custom.css', 'custom.typ'):
        if (ROOT / name).exists(): shutil.copy2(ROOT / name, destination / name)
    spec = load_design(theme)
    (destination / 'book.design.yaml').write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')
    project = {'format': 'portable-publishing-job', 'format_version': '0.2',
               'book': {'title': 'BookOrder Design Preview', 'description': 'Design fixture', 'target_readers': 'Editors', 'language': 'ja', 'preview': True},
               'citations': {'style': 'numeric'},
               'outputs': {'canonical_markdown': True, 'docx': True, 'semantic_html': True, 'pdf': True, 'epub': True, 'static_site': True}, 'input': {'sources': [], 'urls': []}}
    (destination / 'project.json').write_text(json.dumps(project, ensure_ascii=False), encoding='utf-8')
    for script in ('build.py', 'validate.py'):
        # Windows embeddable Python has a fixed ._pth. Explicitly select the isolated
        # preview scripts before imports, rather than importing the real book's common.py.
        entry = str(destination / 'scripts' / script)
        runner = 'import sys,runpy; sys.path.insert(0,sys.argv[1]); entry=sys.argv[2]; sys.argv=[entry]; runpy.run_path(entry,run_name="__main__")'
        result = subprocess.run([sys.executable, '-c', runner, str(destination / 'scripts'), entry], cwd=destination)
        if result.returncode: raise RuntimeError(f'Theme preview {script} failed')
    print(f'Preview HTML: {destination / "publish/site/index.html"}\nPreview PDF: {destination / "publish/book.pdf"}')


def split(value):
    return [x.strip() for x in (value or '').split(',') if x.strip()]


def load_items(path):
    if not path: return []
    from common import yaml_data
    file = Path(path)
    if file.suffix == '.json': return json.loads(file.read_text(encoding='utf-8'))
    data = yaml_data(file)
    return data.get('candidates', data)


def print_goal(as_json=False, stage=None, restart=False, agents=None):
    import orchestrator
    with redirect_stdout(sys.stderr) if as_json else nullcontext():
        state, tasks, info = orchestrator.advance(stage=stage, restart=restart, agent_overrides=agents)
    if as_json: print(json.dumps({'status': state['status'], 'phase': state['phase'], 'phases': state['phases'], 'tasks': tasks, 'info': info, 'blockers': state['blockers']}, ensure_ascii=False, indent=2))
    else: print(orchestrator.status_text(state, tasks, info))
    return 0


def main():
    if (ROOT / 'runtime/manifest.json').is_file():
        from bootstrap import initialize
        initialize()
    parser = argparse.ArgumentParser(prog='bookorder', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    goal = commands.add_parser('goal', help='Start or resume the publication; prints the next tasks'); goal.add_argument('--json', action='store_true')
    nxt = commands.add_parser('next', help='Alias of goal'); nxt.add_argument('--json', action='store_true')
    for stage_name in ('write', 'design', 'render'):
        stage_parser = commands.add_parser(stage_name, help='Run/resume the ' + stage_name + ' stage')
        stage_parser.add_argument('--json', action='store_true'); stage_parser.add_argument('--restart', action='store_true')
        stage_parser.add_argument('--agent', action='append', default=[], metavar='ROLE=ASSIGNMENT', help='Role routing metadata; the host runs this agent')
    goal.add_argument('--agent', action='append', default=[], metavar='ROLE=ASSIGNMENT')
    handoff = commands.add_parser('handoff', help='Show or export the portable manuscript handoff')
    handoff.add_argument('--export', metavar='ZIP_PATH'); handoff.add_argument('--restore', action='store_true')
    revision = commands.add_parser('revision').add_subparsers(dest='revision_command', required=True)
    request = revision.add_parser('request', help='Return a required text change to the writer')
    request.add_argument('--reason', required=True); request.add_argument('--chapter')
    commands.add_parser('pages', help='Measure actual PDF pages and show the target difference')
    done = commands.add_parser('done', help='Report a task finished; BookOrder re-verifies and advances')
    done.add_argument('task'); done.add_argument('--note'); done.add_argument('--json', action='store_true')
    status = commands.add_parser('status'); status.add_argument('--json', action='store_true')
    commands.add_parser('gates', help='Evaluate publication completion gates (read-only)')
    blk = commands.add_parser('block', help='Stop with a blocker that needs the user'); blk.add_argument('task'); blk.add_argument('--category', required=True); blk.add_argument('--reason', required=True)
    unb = commands.add_parser('unblock'); unb.add_argument('--note', required=True)
    rescale = commands.add_parser('rescale', help='Change the page target (only with explicit user approval)')
    rescale.add_argument('--pages', type=int, required=True); rescale.add_argument('--user-approval', required=True)

    src = commands.add_parser('source').add_subparsers(dest='source_command', required=True)
    src.add_parser('list')
    fetch = src.add_parser('fetch'); fetch.add_argument('ids', nargs='*'); fetch.add_argument('--limit', type=int, default=40)
    sub = src.add_parser('submit'); sub.add_argument('id'); sub.add_argument('--file', required=True)
    sub.add_argument('--status', default='fully_ingested'); sub.add_argument('--method', default='agent'); sub.add_argument('--note')
    for key in ('title', 'author', 'published', 'site'): sub.add_argument('--' + key)
    conf = src.add_parser('confirm'); conf.add_argument('id'); conf.add_argument('--note', required=True)
    part = src.add_parser('accept-partial'); part.add_argument('id'); part.add_argument('--note', required=True)
    una = src.add_parser('unavailable'); una.add_argument('id'); una.add_argument('--reason', required=True); una.add_argument('--attempt')
    add = src.add_parser('add'); add.add_argument('--url'); add.add_argument('--file'); add.add_argument('--title'); add.add_argument('--reason')
    add.add_argument('--query'); add.add_argument('--gap'); add.add_argument('--post-draft', action='store_true'); add.add_argument('--issue'); add.add_argument('--no-fetch', action='store_true')
    add.add_argument('--role', help='evidence | background | structure_reference | redraw_source (what the source may be used for)')
    add.add_argument('--authority', help='guideline, governmental, peer_reviewed, institutional, textbook, expert_commentary, professional_experience, anecdotal, …')
    add.add_argument('--citation', choices=['auto', 'yes', 'no'], default='auto', help='yes/no overrides the role default for citing it')
    add.add_argument('--intended-usage'); add.add_argument('--intended-chapter'); add.add_argument('--notes')

    res = commands.add_parser('research').add_subparsers(dest='research_command', required=True)
    log = res.add_parser('log'); log.add_argument('--query', required=True); log.add_argument('--gap'); log.add_argument('--tool')
    log.add_argument('--candidates', help='JSON/YAML file with [{url, title, note}]'); log.add_argument('--selected'); log.add_argument('--rejected', action='append', default=[]); log.add_argument('--note')
    res.add_parser('status')

    aud = commands.add_parser('audit').add_subparsers(dest='audit_command', required=True)
    resolve = aud.add_parser('resolve'); resolve.add_argument('id'); resolve.add_argument('--note', required=True); resolve.add_argument('--wontfix', action='store_true')
    aud.add_parser('report')

    edi = commands.add_parser('editorial', help='EditorialPlan: check the plans, or fall back a device').add_subparsers(dest='editorial_command', required=True)
    edi.add_parser('check')
    fb = edi.add_parser('fallback', help='Replace a device (e.g. a rejected visual) with table, prose, case_study or summary')
    fb.add_argument('device'); fb.add_argument('--to', required=True, choices=['table', 'prose', 'case_study', 'summary']); fb.add_argument('--reason', required=True)

    build = commands.add_parser('build'); build.add_argument('--theme')
    commands.add_parser('layout', help='Re-measure page layout of the last PDF build (reports/layout-metrics.json)')
    prof = commands.add_parser('profile', help='Show the resolved PublicationProfile; --apply re-plans with it (user approval)')
    prof.add_argument('--apply', action='store_true'); prof.add_argument('--user-approval')
    pub = commands.add_parser('publication', help='Check the tier/genre, layout and style requested in project.json (read-only)'); pub.add_argument('--json', action='store_true')
    arc = commands.add_parser('architecture', help='Show the publication architecture, source roles, uploads and QA (read-only)'); arc.add_argument('--json', action='store_true')
    commands.add_parser('fonts')
    theme = commands.add_parser('theme'); sub_theme = theme.add_subparsers(dest='theme_command', required=True)
    sub_theme.add_parser('list'); show = sub_theme.add_parser('preview'); show.add_argument('name')
    fork = sub_theme.add_parser('fork', help='Copy a theme to themes/<name>/ for free editing and select it in book.design.yaml')
    fork.add_argument('base'); fork.add_argument('name', nargs='?', default='book'); fork.add_argument('--no-select', action='store_true')

    dele = commands.add_parser('delegate', help='Run a research task with the research delegate (Codex CLI) - Claude-orchestrated jobs')
    dele.add_argument('target', help='a task id from bookorder goal, or: evidence | factcheck | ask')
    dele.add_argument('argument', nargs='?', help='chapter id (evidence/factcheck) or the question (ask)')
    dele.add_argument('--note', help='extra instruction, e.g. what to redo'); dele.add_argument('--dry-run', action='store_true')
    dele.add_argument('--timeout', type=float, help='minutes'); dele.add_argument('--json', action='store_true')
    prf = commands.add_parser('proof', help='Typeset the PDF with the current design and export representative pages as PNG (proofs/)')
    prf.add_argument('--pages', help='e.g. 3,10-11 (default: chosen from the measured layout)'); prf.add_argument('--ppi', type=int, default=110)
    prf.add_argument('--no-build', action='store_true'); prf.add_argument('--label')
    apr = commands.add_parser('design-approve', help="Record the user's approval of the current design (design dialogue)")
    apr.add_argument('--user-approval', required=True, help="the user's own words"); apr.add_argument('--note')
    voi = commands.add_parser('voice', help='Advisory report of hedging / boilerplate density per chapter')
    voi.add_argument('--chapter'); voi.add_argument('--json', action='store_true')
    evi = commands.add_parser('evidence', help='Deterministic evidence-map and citation verification').add_subparsers(dest='evidence_command', required=True)
    ver = evi.add_parser('verify'); ver.add_argument('--chapter'); ver.add_argument('--json', action='store_true')
    img = commands.add_parser('images', help='Generated-image style: samples, anchor, palette check, contact sheet').add_subparsers(dest='images_command', required=True)
    smp = img.add_parser('samples', help='Style-anchor candidates from plan/image-style.md (Codex imagegen)')
    smp.add_argument('--count', type=int, default=3); smp.add_argument('--subject')
    anc = img.add_parser('anchor', help='Fix the style anchor every image is generated against'); anc.add_argument('path')
    img.add_parser('check', help='Palette conformance of generated images'); img.add_parser('sheet', help='proofs/images.html contact sheet')
    args = parser.parse_args()

    if args.command in ('goal', 'next', 'write', 'design', 'render'):
        agents = {}
        for assignment in getattr(args, 'agent', []):
            role, sep, value = assignment.partition('=')
            if not sep or role not in ('writer', 'designer', 'reviewer', 'researcher') or not value.strip():
                raise ValueError('--agent expects writer|designer|reviewer|researcher=assignment')
            agents[role] = value
        return print_goal(args.json, 'all' if args.command == 'goal' else None if args.command == 'next' else args.command,
                          getattr(args, 'restart', False), agents)
    if args.command == 'delegate':
        import delegate
        meta = delegate.run(args.target, args.argument, args.note, args.dry_run, args.timeout)
        if args.json: print(json.dumps(meta, ensure_ascii=False, indent=2))
        elif not meta.get('dry_run'): print(delegate.summary_text(meta))
        return 0 if meta.get('dry_run') or meta.get('status') == 'ok' else 1
    if args.command == 'proof':
        import proof
        manifest, folder = proof.make(args.pages, args.ppi, not args.no_build, args.label)
        print(proof.summary(manifest, folder)); return 0
    if args.command == 'design-approve':
        import orchestrator, claude_mode
        project, state = orchestrator.load_state()
        approval = claude_mode.approve_design(state, args.user_approval, args.note)
        orchestrator.log_event('design', 'user_approval', user_approval=args.user_approval, fingerprint=approval['fingerprint'])
        orchestrator.save_state(state)
        print('Design approval recorded for the current design files. Changing them later needs a new approval.'); return 0
    if args.command == 'evidence':
        import evidence_verify
        report = evidence_verify.run(args.chapter)
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else evidence_verify.text(report))
        return 1 if report['summary']['high'] else 0
    if args.command == 'images':
        import image_style, style_bible
        from common import read_project
        from design import load_design
        project = read_project()
        style = style_bible.load_or_resolve(project=project, design=load_design())
        if args.images_command == 'samples':
            made = image_style.samples(project, style, args.count, args.subject)
            image_style.contact_sheet(style['palette'])
            print('Style-anchor candidates:\n' + '\n'.join('  ' + m for m in made) +
                  '\nOpen them (and proofs/images.html), choose one with the user, then: bookorder images anchor <file>')
        elif args.images_command == 'anchor':
            print(f"Style anchor: {image_style.set_anchor(args.path).relative_to(ROOT).as_posix()} — every image request now references it.")
        elif args.images_command == 'check':
            report = image_style.check(style['palette'])
            for item in report['images']: print(f"{item['file']}: palette {item.get('score')} {item.get('off_palette_colours') or ''}")
        else:
            print(image_style.contact_sheet(style['palette']).relative_to(ROOT).as_posix())
        return 0
    if args.command == 'voice':
        import voice_check
        results = voice_check.analyse(args.chapter)
        print(json.dumps(results, ensure_ascii=False, indent=2) if args.json else voice_check.text(results)); return 0
    if args.command == 'pages':
        import page_budget
        from common import read_project
        result = page_budget.measure(read_project()); print(page_budget.summary(result))
        return 0 if result['actual_pages'] is not None else 1
    if args.command == 'handoff':
        import workflow
        if args.restore: workflow.restore(); print('Frozen manuscript restored.'); return 0
        if args.export: print(workflow.export(args.export)); return 0
        path = ROOT / 'handoff/manifest.json'
        if not path.is_file(): raise ValueError('No handoff; finish bookorder write first')
        print(path.read_text(encoding='utf-8')); return 0
    if args.command == 'revision':
        import workflow, orchestrator
        project, state = orchestrator.load_state()
        workflow.request_revision(project, state, args.reason, args.chapter)
        return print_goal(stage='write')
    if args.command == 'done':
        import orchestrator
        orchestrator.report_done(args.task, args.note)
        return print_goal(args.json)
    if args.command == 'status':
        import orchestrator
        project, state = orchestrator.load_state()
        summary = orchestrator.write_summary(orchestrator.Context(project, state))
        if args.json: print(json.dumps(summary, ensure_ascii=False, indent=2))
        else: print(orchestrator.status_text(state, [], ['Run `bookorder goal` for the next tasks.']))
        return 0
    if args.command == 'gates':
        import orchestrator
        project, state = orchestrator.load_state()
        gates = orchestrator.completion_gates(orchestrator.Context(project, state))
        for gate in gates: print(f"[{'PASS' if gate['passed'] else 'FAIL'}] {gate['id']:>2}. {gate['name']}: {gate['detail']}")
        return 0 if all(g['passed'] for g in gates) else 1
    if args.command == 'block':
        import orchestrator
        orchestrator.block(args.task, args.category, args.reason); print('Blocked. The publication is NOT complete.'); return 0
    if args.command == 'unblock':
        import orchestrator
        orchestrator.unblock(args.note); return print_goal()
    if args.command == 'rescale':
        import orchestrator
        from planning import compute_scale
        from design import load_design
        project, state = orchestrator.load_state()
        project['book']['target_pages'] = args.pages
        previous = state['scale']
        state['scale'] = compute_scale(project, load_design())
        raw = json.loads((ROOT / 'project.json').read_text(encoding='utf-8'))
        raw['book']['target_pages'] = args.pages
        (ROOT / 'project.json').write_text(json.dumps(raw, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        orchestrator.log_event('goal', 'rescale', previous_pages=previous['requested_pages'], pages=args.pages, user_approval=args.user_approval)
        orchestrator.reopen(state, 'architecture', f'rescaled from {previous["requested_pages"]} to {args.pages} pages')
        orchestrator.save_state(state); print(json.dumps(state['scale'], indent=2)); return 0

    if args.command == 'architecture':
        import publication_architecture as pa, source_roles, bibliography, architecture_qa
        from common import read_project
        project = read_project(); arch = pa.load(project)
        data = {"architecture": arch, "check": pa.check(project), "source_roles": source_roles.table(write=False),
                "uploaded_assets": source_roles.uploaded_assets(project), "citations": bibliography.policy(project)}
        try: data["qa"] = architecture_qa.run(write=False)["summary"]
        except Exception as exc: data["qa"] = {"error": str(exc)[:200]}
        if args.json: print(json.dumps(data, ensure_ascii=False, indent=2)); return 0
        print('\n'.join(pa.summary_lines(arch)))
        print('Citations: ' + data["citations"]["summary"])
        print('\n'.join(source_roles.summary_lines(data["source_roles"])) or 'Source roles: (no sources yet)')
        for a in data["uploaded_assets"]: print(f"Upload {a['id']} {a['label']}: {a['role']}/{a['asset_role']} chapter {a.get('intended_chapter') or '-'} — {a.get('instruction') or ''}")
        for e in data["check"]: print('PROBLEM: ' + e)
        return 1 if data["check"] else 0
    if args.command == 'publication':
        import publication_request
        from common import read_project
        from design import load_design
        try: design = load_design()
        except Exception: design = {}
        report = publication_request.check(read_project(), design)
        if args.json: print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            layout = report.get('layout') or {}
            if report.get('profile'): print(f"profile {report['profile']['id']} ≈ {report['profile']['target_pages']} pages")
            if layout: print(f"layout {layout['page_size']} {layout['width_mm']}×{layout['height_mm']} mm, {layout['columns']} column(s), "
                             f"column {layout['column_width_mm']} mm, gutter {layout['gutter_mm']} mm, body {layout['body_width_mm']} mm, {layout['writing_mode']}")
            if report.get('style'): print(f"style template {report['style']['template']} preset {report['style']['preset'] or '(genre default)'}")
            for issue in report['issues']: print(f"ERROR {issue['field']}: {issue['message']} [{issue['code']}]")
        return 0 if report['ok'] else 1
    if args.command == 'profile':
        import orchestrator, publication_profile
        from design import load_design
        project, state = orchestrator.load_state()
        try: design = load_design()
        except Exception: design = {}
        profile = publication_profile.resolve(project, design)
        current = (state.get('scale') or {}).get('profile', {}).get('inputs_fingerprint')
        print('\n'.join(publication_profile.summary_lines(profile)))
        print(f"inputs_fingerprint {profile['inputs_fingerprint']} (plan uses {current or 'no profile'})")
        if not args.apply:
            if current != profile['inputs_fingerprint']: print('project.json asks for a different profile; run with --apply --user-approval "<quote the user>" to re-plan')
            return 0
        if not args.user_approval: raise ValueError('--apply changes the book plan; pass --user-approval "<quote the user>"')
        from planning import compute_scale
        state['scale'] = compute_scale(project, design)
        orchestrator.log_event('goal', 'profile', profile=profile['id'], fingerprint=profile['inputs_fingerprint'], user_approval=args.user_approval)
        orchestrator.reopen(state, 'architecture', f"publication profile changed to {profile['id']}")
        orchestrator.save_state(state); return 0
    if args.command == 'source':
        with registry_lock(args.source_command != 'list'):
            return source_command(args)
    if args.command == 'research':
        with registry_lock(args.research_command == 'log'):
            return research_command(args)
    return other_command(args)


def source_command(args):
    if True:
        import sources
        c = args.source_command
        if c == 'list':
            index = sources.load_index()
            for s in index['sources']:
                print(f"{s['id']}  {s['origin']:<10} {s['ingest_status']:<22} {s.get('chars', 0):>8}  {s.get('url') or s.get('path')}")
            print(json.dumps(sources.counts(index, 'supplied'), ensure_ascii=False))
        elif c == 'fetch':
            done_ids = sources.ingest(ids=set(args.ids) or None, limit=args.limit)
            print(f"Attempted {len(done_ids)} sources"); print(json.dumps(sources.counts(sources.load_index()), ensure_ascii=False))
        elif c == 'submit':
            s = sources.submit(args.id, args.file, args.status, args.method, args.note, args.title, args.author, args.published, args.site)
            print(f"{s['id']}: {s['ingest_status']} ({s['chars']} characters) -> {s['content_path']}")
        elif c == 'confirm': print(sources.confirm_complete(args.id, args.note)['ingest_status'])
        elif c == 'accept-partial': print(sources.accept_partial(args.id, args.note)['ingest_status'])
        elif c == 'unavailable': print(sources.mark_unavailable(args.id, args.reason, args.attempt)['ingest_status'])
        elif c == 'add':
            if not (args.url or args.file): raise ValueError('--url or --file is required')
            path = None
            if args.file:
                file = Path(args.file).resolve()
                if not file.is_relative_to(ROOT): raise ValueError('Copy the file into the job (e.g. input/discovered/) first')
                path = file.relative_to(ROOT).as_posix()
            s = sources.add_discovered(url=args.url, path=path, title=args.title, reason=args.reason, query=args.query, gap=args.gap, post_draft=args.post_draft, issue=args.issue,
                                        role=args.role, authority=args.authority, citation_allowed={'yes': True, 'no': False}.get(args.citation),
                                        intended_usage=args.intended_usage, intended_chapter=args.intended_chapter, notes=args.notes)
            if not args.no_fetch and s['ingest_status'] == 'pending': sources.ingest(ids={s['id']})
            s = sources.get(sources.load_index(), s['id'])
            print(f"{s['id']}: {s['ingest_status']} {s.get('chars', 0)} characters" + (f" (duplicate of {s['duplicate_of']})" if s.get('duplicate_of') else '') + ('' if s['ingest_status'] in sources.USABLE else f" — limitations: {'; '.join(s.get('limitations', []))}"))
        return 0


def research_command(args):
    if True:
        import research
        if args.research_command == 'log':
            rejected = [dict(zip(('url', 'reason'), (item.split('=', 1) + [''])[:2])) for item in args.rejected]
            entry = research.log_search(args.query, args.gap, args.tool, load_items(args.candidates), split(args.selected), rejected, args.note)
            print(f"Logged {entry['id']}: {entry['query']}")
        else:
            print('\n'.join(research.check_research_plan()) or 'Supplementary research plan passes')
        return 0


def other_command(args):
    if args.command == 'audit':
        import audit
        if args.audit_command == 'resolve':
            entry = audit.resolve(args.id, args.note, args.wontfix); print(f"{entry['id']}: {entry['status']}")
        else: print(json.dumps(audit.render_report(), ensure_ascii=False, indent=2))
        return 0

    if args.command == 'editorial':
        import editorial_plan
        from planning import load_outline
        chapters = load_outline()
        if args.editorial_command == 'check':
            result = editorial_plan.run(chapters)
            for f in editorial_plan.all_findings(result):
                print(f"[{f['severity']}{' waived' if f.get('waived') else ''}] {f.get('chapter') or 'book'} {f.get('section') or ''} {f.get('device') or ''} {f['rule']}: {f['detail']}")
            print(json.dumps(result['summary'], ensure_ascii=False))
            return 0 if result['ok'] else 1
        chapter = editorial_plan.find_chapter(args.device, chapters)
        if not chapter: raise ValueError(f'{args.device} is not a device in plan/editorial/*.yaml')
        codes = []
        try:
            import visual_review
            codes = [r['code'] for c in visual_review.run(chapters, write=False)['candidates'] if (c.get('device') or c['id']) == args.device for r in c.get('rejection_reasons', [])]
        except Exception: pass
        new_id = editorial_plan.apply_fallback(chapter, args.device, args.to, args.reason, codes)
        print(f"{args.device}: fallback to {args.to}" + (f" -> new device {new_id} (fill in its fields, then replace the slot)" if new_id else " (remove its slot and keep it in prose)"))
        return 0

    if args.command == 'build':
        from build import build
        build(args.theme)
    elif args.command == 'layout':
        import layout_metrics
        layout_metrics.main()
    elif args.command == 'fonts':
        from design import available_fonts
        print(json.dumps(available_fonts(), ensure_ascii=False, indent=2))
    elif args.theme_command == 'list':
        print('\n'.join(path.parent.name for path in sorted((ROOT / 'themes').glob('*/theme.yaml'))))
    elif args.theme_command == 'fork':
        fork_theme(args.base, args.name, not args.no_select)
    else: preview(args.name)
    return 0


def fork_theme(base, name, select=True):
    """A book-specific theme: a copy of `base` under a new name, free to rewrite (CSS modules and typst/theme.typ)."""
    import re
    from design import theme_path
    source = theme_path(base)
    if not re.fullmatch(r'[a-z][a-z0-9-]*', name): raise ValueError('Theme name: lowercase letters, digits and hyphens')
    target = ROOT / 'themes' / name
    if target.exists(): raise ValueError(f'themes/{name} already exists; edit it directly or choose another name')
    shutil.copytree(source, target, ignore=shutil.ignore_patterns('preview.png'))
    meta = json.loads((target / 'theme.yaml').read_text(encoding='utf-8')); meta['theme'] = name
    (target / 'theme.yaml').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if select:
        spec_path = ROOT / 'book.design.yaml'
        spec = json.loads(spec_path.read_text(encoding='utf-8')) if spec_path.is_file() else {}
        spec['theme'] = name
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'themes/{name}/ created from {base}' + (' and selected in book.design.yaml' if select else '') +
          '. Edit theme.yaml (defaults), css/*.css (HTML/EPUB/site) and typst/theme.typ (PDF) freely; run bookorder proof to see it.')


class registry_lock:
    """Serialise commands that rewrite research/index.json or the search log (parallel delegates call them)."""
    def __init__(self, active=True):
        self.active = active; self.path = ROOT / '.build/registry.lock'; self.fd = None

    def __enter__(self):
        if not self.active: return self
        import os, time
        self.path.parent.mkdir(parents=True, exist_ok=True); deadline = time.monotonic() + 600
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.write(self.fd, str(os.getpid()).encode()); return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 900: self.path.unlink(); continue  # stale (crashed holder)
                except FileNotFoundError: continue
                if time.monotonic() > deadline: raise RuntimeError('Registry busy (.build/registry.lock); retry')
                time.sleep(0.5)

    def __exit__(self, *exc):
        if self.active and self.fd is not None:
            import os
            os.close(self.fd)
            try: self.path.unlink()
            except FileNotFoundError: pass
        return False


if __name__ == '__main__':
    try: sys.exit(main() or 0)
    except Exception as exc: print(str(exc), file=sys.stderr); sys.exit(1)

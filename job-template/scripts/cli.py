"""BookOrder CLI. `bookorder goal` is the single entry point that owns the publication lifecycle.

Publication:  goal | done <task> | status [--json] | gates | block | unblock
Sources:      source list | fetch | submit | confirm | accept-partial | unavailable | add
Research:     research log | research status
Audit:        audit resolve <id> --note ... [--wontfix] | audit report
Design:       build [--theme] | fonts | theme list | theme preview <name>
"""
import argparse
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


def print_goal(as_json=False):
    import orchestrator
    state, tasks, info = orchestrator.advance()
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
    args = parser.parse_args()

    if args.command in ('goal', 'next'): return print_goal(args.json)
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
            s = sources.add_discovered(url=args.url, path=path, title=args.title, reason=args.reason, query=args.query, gap=args.gap, post_draft=args.post_draft, issue=args.issue)
            if not args.no_fetch and s['ingest_status'] == 'pending': sources.ingest(ids={s['id']})
            s = sources.get(sources.load_index(), s['id'])
            print(f"{s['id']}: {s['ingest_status']} {s.get('chars', 0)} characters" + (f" (duplicate of {s['duplicate_of']})" if s.get('duplicate_of') else '') + ('' if s['ingest_status'] in sources.USABLE else f" — limitations: {'; '.join(s.get('limitations', []))}"))
        return 0
    if args.command == 'research':
        import research
        if args.research_command == 'log':
            rejected = [dict(zip(('url', 'reason'), (item.split('=', 1) + [''])[:2])) for item in args.rejected]
            entry = research.log_search(args.query, args.gap, args.tool, load_items(args.candidates), split(args.selected), rejected, args.note)
            print(f"Logged {entry['id']}: {entry['query']}")
        else:
            print('\n'.join(research.check_research_plan()) or 'Supplementary research plan passes')
        return 0
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
    else: preview(args.name)
    return 0


if __name__ == '__main__':
    try: sys.exit(main() or 0)
    except Exception as exc: print(str(exc), file=sys.stderr); sys.exit(1)

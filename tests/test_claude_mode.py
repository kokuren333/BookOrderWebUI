"""Claude-orchestrated jobs: research routing to the Codex delegate, evidence-map gate before drafting, design
approval, delegate prompts/commands, the voice report and book-specific themes. No model is called."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import _tools
import test_orchestrator as fixture

CLAUDE = {'separated': True, 'mode': 'claude-orchestrated'}


class ClaudeModeTests(unittest.TestCase):
    def setUp(self):
        self.root, modules = fixture.make_job(self.id().split('.')[-1], pages=50)
        self.orch = modules['orchestrator']
        import claude_mode, workflow, delegate
        self.cm = claude_mode; self.workflow = workflow; self.delegate = delegate
        self.project = json.loads((self.root / 'project.json').read_text(encoding='utf-8'))
        self.project['workflow'] = dict(CLAUDE)
        self.project['user_instructions'] = '教科書的にしない。断定してよいところは断定する。'
        (self.root / 'project.json').write_text(json.dumps(self.project, ensure_ascii=False), encoding='utf-8')
        self.state = self.orch.new_state(self.project)
        fixture.write(self.root, 'source/metadata/outline.yaml',
                      'chapters:\n  - id: ch-one\n    title: "One"\n    file: source/manuscript/01-one.md\n    purpose: "Explain one thing"\n'
                      '    required_topics: ["alpha"]\n    required_sections: [{id: sec-a, title: "A"}]\n')

    def task(self, ident, phase):
        return self.workflow.attach_task(self.orch.task(ident, phase, 'T', ['do it'], outputs=['research/notes/src-0001.yaml']), self.project, self.state)

    def test_research_tasks_route_to_codex_and_writing_stays_with_claude(self):
        analyze = self.task('analyze:src-0001', 'corpus_analysis')
        self.assertEqual((analyze['role'], analyze['agent']), ('researcher', 'codex-cli'))
        self.assertIn('delegate analyze:src-0001', analyze['delegate'])
        self.assertTrue(analyze['instructions'][0].startswith('DELEGATE'))
        self.assertIn('do it', analyze['instructions'])
        synth = self.task('synthesize', 'corpus_analysis')
        self.assertEqual((synth['role'], synth['agent']), ('writer', 'claude-code'))
        draft = self.task('draft:ch-one', 'drafting')
        self.assertEqual(draft['agent'], 'claude-code')
        self.assertTrue(draft['instructions'][0].startswith('EVIDENCE FIRST'))
        self.assertIn('skills/authoring/voice.md', draft['skills'])
        once = self.workflow.attach_task(draft, self.project, self.state)
        self.assertEqual(sum(l.startswith('EVIDENCE FIRST') for l in once['instructions']), 1)
        design = self.task('design', 'design')
        self.assertIn('skills/design/design-dialogue.md', design['skills'])

    def test_legacy_jobs_unchanged(self):
        self.project['workflow'] = {'separated': True, 'agents': {}}
        (self.root / 'project.json').write_text(json.dumps(self.project, ensure_ascii=False), encoding='utf-8')
        item = self.task('analyze:src-0001', 'corpus_analysis')
        self.assertEqual(item['role'], 'writer'); self.assertNotIn('delegate', item)
        self.assertEqual(item['instructions'], ['do it'])
        self.assertEqual(self.cm.drafting_problems(self.project, 'ch-one'), [])
        self.assertEqual(self.cm.design_dialogue_errors(self.project, self.state), [])
        with self.assertRaises(ValueError): self.delegate.run('analyze:src-0001', dry_run=True)

    def test_evidence_map_gates_drafting(self):
        self.assertTrue(self.cm.drafting_problems(self.project, 'ch-one'))
        fixture.write(self.root, 'research/evidence/ch-one.yaml', 'chapter: ch-one\nclaims: []\n')
        self.assertEqual(self.cm.drafting_problems(self.project, 'ch-one'), [])
        self.project['workflow']['evidence_maps'] = False
        (self.root / 'research/evidence/ch-one.yaml').unlink()
        self.assertEqual(self.cm.drafting_problems(self.project, 'ch-one'), [])

    def test_design_needs_user_approval_of_the_exact_design(self):
        fixture.write(self.root, 'book.design.yaml', {'theme': 'modern-technical'})
        self.assertTrue(self.cm.design_dialogue_errors(self.project, self.state))
        with self.assertRaises(ValueError): self.cm.approve_design(self.state, ' ')
        self.cm.approve_design(self.state, 'これでOKです')
        self.assertEqual(self.cm.design_dialogue_errors(self.project, self.state), [])
        fixture.write(self.root, 'custom.typ', '#set text(size: 10pt)\n')
        self.assertIn('changed after', self.cm.design_dialogue_errors(self.project, self.state)[0])
        self.project['workflow']['design_dialogue'] = False
        self.assertEqual(self.cm.design_dialogue_errors(self.project, self.state), [])

    def test_delegate_prompts_and_command(self):
        item = self.task('analyze:src-0001', 'corpus_analysis')
        fixture.write(self.root, '.build/next-tasks.json', {'tasks': [item]})
        prompt = self.delegate.prompt_for_task(self.delegate.find_task('analyze:src-0001'), 'bookorder.cmd', note='redo claims')
        self.assertIn('RESEARCH DELEGATE', prompt); self.assertIn('- do it', prompt)
        self.assertNotIn('DELEGATE (research agent)', prompt)
        self.assertIn(self.project['user_instructions'], prompt)
        self.assertIn('redo claims', prompt)
        with self.assertRaises(ValueError): self.delegate.find_task('analyze:missing')
        evidence, outputs = self.delegate.prompt_for_evidence('ch-one', 'bookorder.cmd')
        self.assertEqual(outputs, ['research/evidence/ch-one.yaml'])
        for text in ('sharp_findings', 'strength: strong', 'Explain one thing', 'alpha', self.project['user_instructions']): self.assertIn(text, evidence)
        with self.assertRaises(ValueError): self.delegate.prompt_for_factcheck('ch-one', 'bookorder.cmd')  # not drafted yet
        fixture.write(self.root, 'source/manuscript/01-one.md', '# One {#ch-one}\n\nText [cite:src-0001].\n')
        check, _ = self.delegate.prompt_for_factcheck('ch-one', 'bookorder.cmd')
        self.assertIn('overhedged', check); self.assertIn('01-one.md', check)
        run_dir = self.root / 'research/delegations/x'
        with patch('shutil.which', return_value=r'C:\npm\codex.cmd'):
            args = self.delegate.codex_command(self.cm.delegate_settings(self.project), run_dir)
        self.assertEqual(args[1:3], ['--search', 'exec'])
        self.assertIn('sandbox_workspace_write.network_access=true', args)
        self.assertEqual(args[args.index('--cd') + 1], str(self.root)); self.assertEqual(args[-1], '-')
        with patch('shutil.which', return_value=None), self.assertRaises(RuntimeError):
            self.delegate.codex_command(self.cm.delegate_settings(self.project), run_dir)

    def test_delegate_refuses_authoring_tasks(self):
        fixture.write(self.root, '.build/next-tasks.json', {'tasks': [self.task('draft:ch-one', 'drafting')]})
        with self.assertRaisesRegex(ValueError, 'not a research task'): self.delegate.run('draft:ch-one', dry_run=True)

    def test_delegate_runs_cli_and_verifies_outputs(self):
        """A fake delegate CLI writes an evidence map with one unknown source: the run is logged and flagged."""
        fake = self.root / '.build/fake_codex.py'
        fixture.write(self.root, '.build/fake_codex.py',
                      'import sys, pathlib\nsys.stdin.read()\nargs = sys.argv\n'
                      'pathlib.Path(args[args.index("--output-last-message") + 1]).write_text("wrote map", encoding="utf-8")\n'
                      'pathlib.Path("research/evidence").mkdir(parents=True, exist_ok=True)\n'
                      'pathlib.Path("research/evidence/ch-one.yaml").write_text("chapter: ch-one\\nclaims:\\n  - id: c-01\\n    claim: x\\n    strength: strong\\n    use: state\\n    sources:\\n      - {src: src-9999, locator: p1}\\n", encoding="utf-8")\n')
        with patch.object(self.delegate, 'codex_command', return_value=[sys.executable, str(fake), '--output-last-message', '{}']) as cmd:
            cmd.side_effect = lambda settings, run_dir: [sys.executable, str(fake), '--output-last-message', str(run_dir / 'last-message.md')]
            meta = self.delegate.run('evidence', 'ch-one')
        self.assertEqual(meta['status'], 'needs_review')
        self.assertTrue(any('src-9999' in p for p in meta['problems']))
        self.assertEqual(meta['report'], 'wrote map')
        run_dir = next((self.root / 'research/delegations').iterdir())
        for name in ('prompt.md', 'events.jsonl', 'meta.json'): self.assertTrue((run_dir / name).is_file(), name)
        self.assertIn('DELEGATION NEEDS_REVIEW', self.delegate.summary_text(meta))

    def test_voice_report_flags_hedged_strong_claims(self):
        import voice_check
        fixture.write(self.root, 'research/evidence/ch-one.yaml',
                      'chapter: ch-one\nclaims:\n  - id: c-01\n    claim: x\n    strength: strong\n    sources:\n      - {src: src-0001, locator: p1}\n')
        body = ('この手法は誤りを減らすと考えられる[cite:src-0001]。' * 3 + 'さまざまな要因があり、注意が必要です。一概には言えません。' * 2)
        fixture.write(self.root, 'source/manuscript/01-one.md', '# One {#ch-one}\n\n' + body + '\n')
        result = voice_check.analyse('ch-one')[0]
        self.assertGreater(result['per_1000'], 10)
        self.assertTrue(result['overhedged_strong_claims'])
        self.assertIn('hedged but evidence is strong', voice_check.text([result]))

    def test_theme_fork_creates_and_selects_book_theme(self):
        fixture.write(self.root, 'book.design.yaml', {'theme': 'modern-technical', 'colors': {'accent': '#123456'}})
        out = subprocess.run([sys.executable, str(self.root / 'scripts/cli.py'), 'theme', 'fork', 'academic-jp', 'book'],
                             cwd=self.root, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(out.returncode, 0, out.stderr)
        spec = json.loads((self.root / 'book.design.yaml').read_text(encoding='utf-8'))
        self.assertEqual(spec, {'theme': 'book', 'colors': {'accent': '#123456'}})
        self.assertEqual(json.loads((self.root / 'themes/book/theme.yaml').read_text(encoding='utf-8'))['theme'], 'book')
        self.assertTrue((self.root / 'themes/book/typst/theme.typ').is_file())
        again = subprocess.run([sys.executable, str(self.root / 'scripts/cli.py'), 'theme', 'fork', 'academic-jp', 'book'],
                               cwd=self.root, capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(again.returncode, 0)

    def test_proof_page_selection_from_layout_metrics(self):
        import proof
        pages = [{'page': n, 'region': 'front' if n < 3 else 'main', 'opener': n in (3, 9), 'text_only': n in (5, 6, 7),
                  'elements': ([{'kind': 'figure'}] if n == 8 else [{'kind': 'table'}] if n == 10 else [])} for n in range(1, 13)]
        fixture.write(self.root, 'reports/layout-metrics.json', {'pages': pages, 'text_only_runs': [{'start': 5, 'length': 3}]})
        chosen = dict(proof.auto_pages())
        self.assertEqual(chosen[3], 'chapter opener'); self.assertIn(4, chosen); self.assertIn('longest', chosen[5])
        self.assertEqual(chosen[8], 'figure'); self.assertEqual(chosen[10], 'table'); self.assertIn(2, chosen)
        self.assertEqual(proof.parse_pages('3, 10-11'), [(3, 'requested'), (10, 'requested'), (11, 'requested')])


class EvidenceImageAndHarnessTests(ClaudeModeTests):
    def test_evidence_verify_catches_fabricated_quotes_and_background_citations(self):
        import evidence_verify
        source = self.root / 'research/supplied/src-0001/source.md'
        fixture.write(self.root, 'research/supplied/src-0001/source.md', '調査の結果、睡眠時間が6時間未満の群では事故率が1.8倍だった。')
        texts = {'src-0001': source, 'src-0002': None}
        roles = {'src-0001': {'role': 'evidence', 'citation_allowed': True}, 'src-0002': {'role': 'background', 'citation_allowed': False}}
        fixture.write(self.root, 'research/evidence/ch-one.yaml',
                      'chapter: ch-one\nclaims:\n'
                      '  - {id: c-01, claim: "a", strength: strong, use: state, sources: [{src: src-0001, quote: "睡眠時間が6時間未満の群では事故率が1.8倍だった"}]}\n'
                      '  - {id: c-02, claim: "b", strength: strong, use: state, sources: [{src: src-0001, quote: "事故率は3倍に跳ね上がる"}]}\n'
                      '  - {id: c-03, claim: "c", strength: moderate, use: state, sources: [{src: src-0002, quote: "x"}]}\n'
                      '  - {id: c-04, claim: "d", use: state, sources: []}\n')
        fixture.write(self.root, 'source/manuscript/01-one.md', '# One {#ch-one}\n\n事故率は1.8倍[cite:src-0001]。一般論[cite:src-0002]。[cite:src-0404]\n')
        chapter = {'id': 'ch-one', 'file': 'source/manuscript/01-one.md'}
        findings = evidence_verify.chapter(chapter, self.project, texts, roles)['findings']
        kinds = {f['type']: f['severity'] for f in findings}
        self.assertEqual(kinds['quote_not_in_source'], 'high')       # c-02 fabricated quote
        self.assertEqual(kinds['non_evidence_support'], 'high')      # c-03 rests on background
        self.assertEqual(kinds['claim_without_source'], 'high')      # c-04
        self.assertEqual(kinds['cites_non_evidence'], 'high')        # [cite:src-0002]
        self.assertEqual(kinds['unknown_citation'], 'high')          # [cite:src-0404]
        self.assertNotIn('c-01', ' '.join(f['detail'] for f in findings))  # the real quote verifies

    def test_factcheck_must_match_current_chapter_text(self):
        chapter = {'id': 'ch-one', 'file': 'source/manuscript/01-one.md'}
        fixture.write(self.root, 'source/manuscript/01-one.md', '# One {#ch-one}\n\nText.\n')
        self.assertFalse(self.cm.factcheck_current(chapter))
        fixture.write(self.root, 'research/factcheck/ch-one.yaml', 'chapter: ch-one\nitems: []\n')
        fixture.write(self.root, 'research/factcheck/ch-one.meta.json', {'manuscript_sha256': self.cm.manuscript_digest(chapter['file'])})
        self.assertTrue(self.cm.factcheck_current(chapter))
        with patch('evidence_verify.chapter', return_value={'findings': []}):
            self.assertEqual(self.cm.audit_problems(self.project, chapter), [])
        fixture.write(self.root, 'source/manuscript/01-one.md', '# One {#ch-one}\n\nEdited text.\n')
        self.assertFalse(self.cm.factcheck_current(chapter))
        with patch('evidence_verify.chapter', return_value={'findings': []}):
            self.assertIn('delegate factcheck ch-one', self.cm.audit_problems(self.project, chapter)[0])

    def test_light_harness_relaxes_heuristic_gates_only(self):
        gates = [{'id': i, 'passed': False, 'detail': 'x'} for i in (11, 17, 18, 20, 23, 24)]
        relaxed = {g['id']: g['passed'] for g in self.cm.relax_gates(self.project, [dict(g) for g in gates])}
        self.assertEqual(relaxed, {11: False, 17: True, 18: True, 20: True, 23: True, 24: False})
        self.project['workflow']['strictness'] = 'strict'
        self.assertFalse(any(g['passed'] for g in self.cm.relax_gates(self.project, [dict(g) for g in gates])))

    def test_research_brief_and_source_policy_reach_the_delegate(self):
        self.project['research']['requirements'] = '公的統計とガイドラインを優先'
        (self.root / 'project.json').write_text(json.dumps(self.project, ensure_ascii=False), encoding='utf-8')
        item = self.workflow.attach_task(self.orch.task('research:supplementary', 'supplementary_research', 'R', ['research']), self.project, self.state)
        self.assertTrue(item['instructions'][2].startswith('BRIEF FIRST') or item['instructions'][0].startswith('BRIEF FIRST'))
        self.assertIn('skills/research/evidence-research.md', item['skills'])
        fixture.write(self.root, 'plan/research-brief.md', '# Brief\n\n- Q1 睡眠と事故\n')
        with patch('sources.load_index', return_value={'sources': []}):
            prompt = self.delegate.prompt_for_task(item, 'bookorder.cmd')
        for text in ('公的統計とガイドラインを優先', 'Q1 睡眠と事故', 'Tier 1', 'background: general knowledge', 'from scratch'):
            self.assertIn(text, prompt)

    def test_design_refs_prompt(self):
        self.project['design_references'] = {'books': '『理科系の作文技術』', 'auto_collect': True}
        prompt, outputs = self.delegate.prompt_for_design_refs(self.project, 'bookorder.cmd')
        self.assertEqual(outputs, ['design/references.yaml', 'design/references/'])
        for text in ('理科系の作文技術', 'paywall', 'design/references/<short-book-id>', 'chapter_opener'): self.assertIn(text, prompt)
        lines = self.cm.design_task_lines(self.project)
        self.assertTrue(any('delegate design-refs' in l for l in lines)); self.assertTrue(any('images samples' in l for l in lines))

    def test_image_style_binds_requests_and_checks_palette(self):
        import image_style, image_assets
        palette = {'ink': '#202020', 'accent': '#C0392B', 'background': '#FAF8F2', 'muted': '#888888'}
        fixture.write(self.root, 'plan/image-style.md', '# Image style\n\n## Medium\nflat\n\n## Prompt prefix\nFlat shapes, warm paper, one red accent.\n\n## Never\ntext\n')
        self.assertEqual(image_style.prompt_prefix(), 'Flat shapes, warm paper, one red accent.')
        before = image_style.binding()
        request = {'asset_id': 'fig-a', 'semantic_role': 'chapter-opener', 'final_width_mm': 50, 'final_height_mm': 30, 'preferred_aspect_ratio': '5:3', 'subject': 'a lamp',
                   'purpose': 'opener', 'context': '', 'must_show': [], 'must_not_show': ['text'], 'composition': 'spacious',
                   'art_direction': {'palette': palette, 'visual_tone': 'calm', 'illustration_style': 'low', 'background_treatment': 'inherit'}}
        prompt = image_style.codex_prompt(request, '.build/imagegen/fig-a.png', 600, 360)
        self.assertIn('Flat shapes, warm paper, one red accent.', prompt); self.assertIn('No text', prompt); self.assertNotIn('STYLE ANCHOR', prompt)
        on = image_assets.FakeImageProvider().generate({**request, 'art_direction': {'palette': {**palette, 'secondary_accent': '#C0392B', 'surface': '#FAF8F2'}}})
        (self.root / 'design/image-samples').mkdir(parents=True, exist_ok=True)
        (self.root / 'design/image-samples/sample-1.png').write_bytes(on['bytes'])
        image_style.set_anchor(self.root / 'design/image-samples/sample-1.png')
        self.assertIn('STYLE ANCHOR', image_style.codex_prompt(request, 'x.png', 1, 1))
        self.assertNotEqual(before, image_style.binding())
        (self.root / 'source/assets/images').mkdir(parents=True, exist_ok=True)
        (self.root / 'source/assets/images/fig-on.png').write_bytes(on['bytes'])
        off = image_assets.FakeImageProvider().generate({**request, 'art_direction': {'palette': {'ink': '#00FF00', 'accent': '#00FFFF', 'muted': '#FF00FF'}}})
        (self.root / 'source/assets/images/fig-off.png').write_bytes(off['bytes'])
        report = {Path(i['file']).stem: i for i in image_style.check(palette)['images']}
        self.assertGreater(report['fig-on']['score'], 0.9); self.assertLess(report['fig-off']['score'], 0.6)
        self.assertEqual(report['fig-off']['severity'], 'medium')
        sheet = image_style.contact_sheet(palette).read_text(encoding='utf-8')
        self.assertIn('style anchor', sheet); self.assertIn('fig-off', sheet)
        with patch('shutil.which', return_value=None), self.assertRaises(RuntimeError):
            image_style.CodexImageProvider(self.project).generate(request)
        self.project['image_generation'] = {'provider': 'codex'}
        self.assertEqual(image_assets.provider_for(self.project).name, 'codex')
        fixture.write(self.root, 'book.design.yaml', {'theme': 'modern-technical'})
        self.cm.approve_design(self.state, 'OK')
        fixture.write(self.root, 'plan/image-style.md', '# changed\n')
        self.assertTrue(self.cm.design_dialogue_errors(self.project, self.state))  # image style is part of the approved design


if __name__ == '__main__':
    unittest.main()

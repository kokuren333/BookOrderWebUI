"""Stage boundaries, portable handoff, real rendered PDF counts and writer feedback regressions."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import zipfile

import _tools
import test_orchestrator as fixture


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.root, modules = fixture.make_job(self.id().split('.')[-1], pages=50)
        self.orch = modules['orchestrator']
        import workflow, page_budget
        self.workflow = workflow; self.pages = page_budget
        self.project = json.loads((self.root / 'project.json').read_text(encoding='utf-8'))
        self.project['workflow'] = {'separated': True, 'agents': {'writer': {'model': 'arbitrary-writer'}, 'designer': 'arbitrary-designer'}}
        (self.root / 'project.json').write_text(json.dumps(self.project), encoding='utf-8')
        fixture.write(self.root, 'source/manuscript/01-book.md', '# Book {#ch-book}\n\n## Locked {#sec-locked}\n\nDo not change this.\n\n## Editable {#sec-edit}\n\nExisting text [cite:src-0001].\n')
        fixture.write(self.root, 'source/references/references.json', [{'id': 'src-0001', 'title': 'Original source'}])
        self.state = self.orch.new_state(self.project)

    def advance(self, stage, restart=False):
        with patch.object(self.orch, 'load_state', return_value=(self.project, self.state)), \
             patch.object(self.orch, 'write_summary'), patch.object(self.orch, 'refresh_page_inputs'), \
             patch.object(self.orch, 'refresh_editorial_plan_dependency'), \
             patch.dict(self.orch.HANDLERS, {p: lambda ctx: self.orch.Result(done=True) for p in self.orch.PHASES}):
            return self.orch.advance(stage=stage, restart=restart)

    def test_write_stops_before_design_and_freezes_handoff(self):
        state, tasks, info = self.advance('write')
        self.assertEqual(state['status'], 'stage_complete')
        self.assertTrue(all(state['phases'][p] == 'complete' for p in self.workflow.WRITE_PHASES))
        self.assertEqual(state['phases']['design'], 'pending')
        self.assertEqual(state['phases']['asset_generation'], 'pending')
        self.assertEqual(self.workflow.check_frozen(), [])
        manifest = json.loads((self.root / 'handoff/manifest.json').read_text(encoding='utf-8'))
        self.assertIn('source/references/references.json', manifest['files'])
        self.assertIn('figure_content_and_intent', manifest)

    def test_design_prerequisite_and_stage_only_restart(self):
        state, _, _ = self.advance('design')
        self.assertEqual(state['status'], 'waiting_for_write')
        self.advance('write')
        state, _, _ = self.advance('design')
        self.assertEqual(state['status'], 'stage_complete')
        self.assertEqual(state['phases']['asset_generation'], 'complete')
        self.assertEqual(state['phases']['layout'], 'pending')
        text = self.workflow.hashes()
        self.advance('design', restart=True)
        self.assertEqual(self.workflow.hashes(), text)
        self.assertTrue(all(state['phases'][p] == 'complete' for p in self.workflow.WRITE_PHASES))

    def test_write_restart_requires_new_drafts_and_render_restart_retains_design(self):
        import common
        common.write_yaml(self.root / 'source/metadata/outline.yaml', {'chapters': [
            {'id': 'ch-book', 'title': 'Book', 'file': 'source/manuscript/01-book.md', 'purpose': 'Explain topic',
             'target_characters': 1000, 'required_sections': ['sec-edit'], 'required_topics': ['Existing']}]})
        self.advance('write'); self.advance('design')
        self.state['reported'] = {'design': {'at': 'previous-design'}}
        self.advance('render', restart=True)
        self.assertEqual(self.state['reported']['design']['at'], 'previous-design')
        self.advance('write', restart=True)
        self.assertIn('ch-book', self.state['redraft_chapters'])
        with patch.object(self.orch, 'load_state', return_value=(self.project, self.state)):
            with self.assertRaisesRegex(ValueError, 'unchanged previous draft'): self.orch.report_done('draft:ch-book')

    def test_frozen_changes_block_design_and_can_be_restored(self):
        self.advance('write')
        chapter = self.root / 'source/manuscript/01-book.md'
        original = chapter.read_bytes(); chapter.write_bytes(original + b'Unauthorized edit')
        state, _, _ = self.advance('design')
        self.assertEqual(state['status'], 'waiting_for_write')
        self.assertEqual(state['phases']['design'], 'pending')
        self.workflow.restore()
        self.assertEqual(chapter.read_bytes(), original)

    def test_handoff_export_contains_resume_state_and_source_ids(self):
        fixture.write(self.root, 'research/index.json', {'sources': [{'id': 'src-0001'}]})
        fixture.write(self.root, 'plan/assets-plan.yaml', {'assets': [{'id': 'fig-test', 'purpose': 'show structure', 'content': {'nodes': ['A', 'B']}}]})
        self.advance('write')
        path = self.workflow.export(self.root / 'transfer.zip')
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            for name in ('project-state.json', 'source/manuscript/01-book.md', 'source/references/references.json', 'research/index.json', 'plan/assets-plan.yaml', 'handoff/manifest.json', 'scripts/cli.py'):
                self.assertIn('publishing-job/' + name, names)
            state = json.loads(archive.read('publishing-job/project-state.json'))
            self.assertEqual(state['phases']['final_audit'], 'complete')
            self.assertEqual(state['phases']['design'], 'pending')

    def test_roles_are_provider_neutral_and_runtime_assignment_wins(self):
        item = {'phase': 'design', 'inputs': [], 'instructions': []}
        result = self.workflow.attach_task(item, self.project, {'agent_overrides': {'designer': {'model': 'runtime-choice', 'host': 'other-host'}}})
        self.assertEqual(result['role'], 'designer')
        self.assertEqual(result['agent']['model'], 'runtime-choice')
        self.assertIn('handoff/manifest.json', result['inputs'])
        self.assertEqual(self.workflow.role_of('audit'), 'reviewer')

    def test_geometry_change_invalidates_render_without_reopening_writing(self):
        self.advance('write'); self.advance('design')
        ctx = self.orch.Context(self.project, self.state)
        self.orch.refresh_page_inputs(ctx)
        self.state['phases']['layout'] = 'complete'
        self.project['layout_spec'] = {'body': {'columns': 2}}
        self.orch.refresh_page_inputs(ctx)
        self.assertEqual(self.state['phases']['layout'], 'pending')
        self.assertEqual(self.state['phases']['design'], 'complete')
        self.assertEqual(self.state['phases']['final_audit'], 'complete')
        self.assertEqual(self.state['page_layout_inputs']['body']['columns'], 2)

    def test_visual_style_is_editable_but_caption_and_facts_are_frozen(self):
        import common
        plan = {'assets': [{'id': 'fig-test', 'caption': 'Original caption', 'content': {'labels': ['A', 'B']}, 'geometry': {'width_mm': 50}}]}
        common.write_yaml(self.root / 'plan/assets-plan.yaml', plan)
        self.workflow.freeze(self.project)
        plan['assets'][0]['geometry']['width_mm'] = 70
        common.write_yaml(self.root / 'plan/assets-plan.yaml', plan)
        self.assertEqual(self.workflow.check_frozen(), [])
        plan['assets'][0]['caption'] = 'Designer rewrote the meaning'
        common.write_yaml(self.root / 'plan/assets-plan.yaml', plan)
        self.assertTrue(self.workflow.check_frozen())
        self.workflow.restore()
        self.assertEqual(self.workflow.check_frozen(), [])

    def test_generated_svg_does_not_invalidate_the_manuscript_audit(self):
        self.advance('write')
        ctx = self.orch.Context(self.project, self.state)
        before = ctx.manuscript_fingerprint()
        fixture.write(self.root, 'source/assets/figures/new.svg', '<svg/>')
        self.assertEqual(ctx.manuscript_fingerprint(), before)
        fixture.write(self.root, 'source/manuscript/01-book.md', '# Changed {#ch-book}\nDifferent text.')
        self.assertNotEqual(ctx.manuscript_fingerprint(), before)

    def test_feedback_reopens_writer_and_requires_actual_revision(self):
        self.advance('write'); self.advance('design')
        self.state['execution_stage'] = 'render'
        ctx = self.orch.Context(self.project, self.state)
        pages = {'status': 'over_target', 'actual_pages': 100, 'target_pages': 50}
        self.assertEqual(self.workflow.design_feedback(ctx, pages), 'requested')
        self.assertEqual(self.state['phases']['chapter_review'], 'pending')
        self.assertEqual(self.state['phases']['design'], 'pending')
        with self.assertRaisesRegex(ValueError, 'not changed'): self.workflow.complete_revision(ctx)
        self.assertEqual(self.workflow.revision_task(ctx)['role'], 'writer')

    def test_revision_preserves_protected_sections_and_citations(self):
        self.project['workflow']['protected_sections'] = ['sec-locked']
        self.advance('write')
        self.workflow.request_revision(self.project, self.state, 'Add a supported example')
        chapter = self.root / 'source/manuscript/01-book.md'
        text = chapter.read_text(encoding='utf-8')
        chapter.write_text(text.replace('Do not change this.', 'Changed.'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Protected section'): self.workflow.complete_revision(self.orch.Context(self.project, self.state))
        chapter.write_text(text + '\nA source-supported example [cite:src-0001].\n', encoding='utf-8')
        refs = (self.root / 'source/references/references.json').read_bytes()
        self.workflow.complete_revision(self.orch.Context(self.project, self.state))
        self.assertNotIn('revision_request', self.state)
        self.assertEqual((self.root / 'source/references/references.json').read_bytes(), refs)

    def test_feedback_is_bounded_and_can_be_disabled(self):
        self.advance('write')
        ctx = self.orch.Context(self.project, self.state)
        self.project['page_feedback'] = {'enabled': False}
        self.assertIsNone(self.workflow.design_feedback(ctx, {'status': 'over_target'}))
        self.project['page_feedback'] = {'max_rounds': 2}
        self.state['counters']['page_feedback_rounds'] = 2
        self.assertEqual(self.workflow.design_feedback(ctx, {'status': 'under_target'})['category'], 'page count')

    def test_page_revision_updates_budgets_then_requires_writer_audits(self):
        import common
        self.state['scale']['target_characters'] = 4000
        self.state['scale']['minimum_characters'] = 3200
        fixture.write(self.root, 'source/manuscript/02-other.md', '# Other {#ch-other}\n\n## Topic {#sec-other}\n\nExisting explanation.\n')
        outline = {'chapters': [
            {'id': 'ch-book', 'title': 'Book', 'file': 'source/manuscript/01-book.md', 'purpose': 'Explain topic',
             'target_characters': 2000, 'required_sections': ['sec-edit'], 'required_topics': ['Existing']},
            {'id': 'ch-other', 'title': 'Other', 'file': 'source/manuscript/02-other.md', 'purpose': 'Explain another topic',
             'target_characters': 2000, 'required_sections': ['sec-other'], 'required_topics': ['explanation']}]}
        common.write_yaml(self.root / 'source/metadata/outline.yaml', outline)
        self.advance('write')
        self.state['reported'] = {'integrate': {}, 'audit:book': {}, 'prose:audit': {}, 'prose:edit': {}, 'design': {}}
        ctx = self.orch.Context(self.project, self.state)
        pages = {'status': 'over_target', 'actual_pages': 100, 'target_pages': 50}
        self.workflow.design_feedback(ctx, pages)
        chapter = self.root / 'source/manuscript/01-book.md'
        chapter.write_text(chapter.read_text(encoding='utf-8') + '\nRevised example [cite:src-0001].\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Chapter budgets'): self.workflow.complete_revision(ctx)
        for item in outline['chapters']: item['target_characters'] = 1000
        common.write_yaml(self.root / 'source/metadata/outline.yaml', outline)
        self.workflow.complete_revision(ctx)
        self.assertEqual(self.state['scale']['target_characters'], 2000)
        self.assertEqual(self.state['scale']['minimum_characters'], 1600)
        self.assertEqual(self.state['counters']['page_feedback_rounds'], 1)
        self.assertNotIn('revision_request', self.state)
        self.assertEqual(self.state['phases']['audit'], 'pending')
        self.assertEqual(self.state['phases']['final_audit'], 'pending')
        self.assertEqual(self.state['phases']['layout'], 'pending')
        self.assertNotIn('prose:audit', self.state['reported'])

    @unittest.skipUnless(_tools.locate('typst'), 'Typst unavailable')
    def test_actual_pdf_pages_include_unmarked_and_blank_pages(self):
        source = self.root / 'count.typ'; pdf = self.root / 'publish/book.pdf'
        pdf.parent.mkdir(exist_ok=True)
        source.write_text('#set page(width: 100mm, height: 100mm)\nFirst\n#pagebreak()\nSecond\n#pagebreak()\n#box()\n', encoding='utf-8')
        subprocess.run([_tools.locate('typst'), 'compile', str(source), str(pdf)], check=True, capture_output=True)
        self.project['book']['target_pages'] = 10
        result = self.pages.measure(self.project)
        self.assertEqual(result['actual_pages'], 3)
        self.assertEqual(result['difference'], -7)
        self.assertEqual(result['status'], 'under_target')
        self.assertIn('difference -7', self.pages.summary(result))

    def test_invalid_pdf_cannot_report_success(self):
        pdf = self.root / 'bad.pdf'; pdf.write_bytes(b'%PDF-1.7\ntruncated')
        result = self.pages.measure(self.project, pdf)
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['actual_pages'])

    def test_guideline_is_authority_and_background_is_not_citable(self):
        import source_roles
        result = source_roles.resolve({'usage': {'role': 'evidence', 'authority': 'guideline'}})
        self.assertEqual((result['role'], result['authority'], result['citation_allowed']), ('evidence', 'guideline', True))
        background = source_roles.resolve({'usage': {'role': 'background', 'authority': 'guideline', 'citation_allowed': True}})
        self.assertFalse(background['citation_allowed'])


if __name__ == '__main__': unittest.main(verbosity=2)

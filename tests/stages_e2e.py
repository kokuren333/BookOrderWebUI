"""Real pipeline across write -> ZIP transfer -> design -> render; scripted author, actual renderers."""
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

import mini_e2e as mini


class StageAgent(mini.MockAgent):
    def handle(self, task):
        if task['id'] == 'asset-content':
            self.check_intent(task)
            path = mini.WORK / 'plan/assets-plan.yaml'
            text = path.read_text(encoding='utf-8')
            text = text.replace('  - id: fig-attention-flow', '  - content: "問い合わせ・鍵の内積、次元でのスケール調整、softmaxによる正規化、値の加重平均を矢印で接続する。"\n    id: fig-attention-flow')
            path.write_text(text, encoding='utf-8')
            self.log.append(task['id'])
        else: super().handle(task)


def run_stage(stage, agent):
    seen = {}
    for _ in range(100):
        result = json.loads(mini.cli(stage, '--json').stdout)
        if result['status'] in ('stage_complete', 'complete'): return result
        assert result['status'] == 'running' and result['tasks'], result
        for task in result['tasks']:
            assert task['stage'] == stage, task
            seen[task['id']] = seen.get(task['id'], 0) + 1
            assert seen[task['id']] <= 4, task
            agent.handle(task)
        for task in result['tasks']: mini.cli('done', task['id'], '--json')
    raise AssertionError('Stage iteration limit')


def main():
    server, base = mini.serve()
    try:
        with tempfile.TemporaryDirectory(prefix='bookorder-stages-') as temp:
            mini.WORK = Path(temp) / 'initial'
            mini.setup(base)
            project_path = mini.WORK / 'project.json'
            project = json.loads(project_path.read_text(encoding='utf-8'))
            project.update(workflow={'separated': True, 'agents': {'writer': 'test-writer', 'designer': 'test-designer', 'reviewer': 'test-reviewer'}},
                           page_feedback={'enabled': False})
            project_path.write_text(json.dumps(project, ensure_ascii=False), encoding='utf-8')
            agent = StageAgent(base)
            run_stage('write', agent)
            assert not (mini.WORK / 'publish/book.pdf').exists(), 'Write must not render a PDF'
            assert not (mini.WORK / 'source/assets/figures/attention-flow.svg').exists(), 'Write must not draw the diagram'
            snapshot = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (mini.WORK / 'source/manuscript').glob('*.md')}
            transfer = Path(temp) / 'handoff.zip'
            mini.cli('handoff', '--export', str(transfer))
            with zipfile.ZipFile(transfer) as archive: archive.extractall(Path(temp) / 'resumed')
            mini.WORK = Path(temp) / 'resumed/publishing-job'
            run_stage('design', agent)
            assert (mini.WORK / 'source/assets/figures/attention-flow.svg').is_file()
            assert not (mini.WORK / 'publish/book.pdf').exists()
            result = run_stage('render', agent)
            assert result['status'] == 'complete'
            assert snapshot == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (mini.WORK / 'source/manuscript').glob('*.md')}
            pages = json.loads((mini.WORK / 'reports/page-count.json').read_text(encoding='utf-8'))
            assert pages['actual_pages'] > 0 and pages['difference'] == pages['actual_pages'] - 8
            with zipfile.ZipFile(mini.WORK / 'publish/result.zip') as archive:
                assert 'publishing-job/handoff/manifest.json' in archive.namelist()
                assert 'publishing-job/research/index.json' in archive.namelist()
            print('PASS stages E2E: write, portable ZIP transfer, design, actual PDF render, unchanged manuscript, final package')
            print(json.dumps(pages, ensure_ascii=False))
            # Turn feedback on for the already generated PDF and verify automatic return to writer.
            project_path = mini.WORK / 'project.json'
            project = json.loads(project_path.read_text(encoding='utf-8'))
            project['page_feedback'] = {'enabled': True, 'tolerance_ratio': 0, 'tolerance_pages': 0}
            project_path.write_text(json.dumps(project, ensure_ascii=False), encoding='utf-8')
            feedback = json.loads(mini.cli('render', '--restart', '--json').stdout)
            assert feedback['status'] == 'waiting_for_write', feedback
            pending = json.loads(mini.cli('write', '--json').stdout)
            assert pending['tasks'][0]['id'] == 'manuscript-revision'
            assert pending['tasks'][0]['role'] == 'writer'
            assert snapshot == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (mini.WORK / 'source/manuscript').glob('*.md')}
            assert (mini.WORK / 'plan/manuscript-revision-request.json').is_file()
            print('PASS actual-PDF feedback: measured deviation returns to writer without editing frozen prose')
    finally: server.shutdown()


if __name__ == '__main__': main()

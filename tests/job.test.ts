import test from 'node:test';
import assert from 'node:assert/strict';
import { readdir, readFile, mkdir, writeFile } from 'node:fs/promises';
import { join, relative } from 'node:path';
import JSZip from 'jszip';
import { createHash } from 'node:crypto';
import { loadRuntime } from '../src/runtime.ts';
import { defaults, generateJob, uniqueNames, safeName, validateForm } from '../src/job.ts';

async function templateFiles(dir = 'job-template'): Promise<Record<string, string | Uint8Array>> {
  const output: Record<string, string | Uint8Array> = {};
  async function scan(path: string) {
    for (const entry of await readdir(path, { withFileTypes: true })) {
      const full = join(path, entry.name);
      if (entry.isDirectory()) await scan(full);
      else output[relative(dir, full).replaceAll('\\', '/')] = entry.name.endsWith('.png') ? new Uint8Array(await readFile(full)) : await readFile(full, 'utf8');
    }
  }
  await scan(dir); return output;
}
test('filenames are portable, traversal-safe and distinct even on case-insensitive systems', () => {
  assert.deepEqual(uniqueNames([{ name: 'Book.pdf' }, { name: 'book.pdf' }, { name: '../Book.pdf' }, { name: 'CON.txt' }]), ['Book.pdf', 'book-2.pdf', '_Book.pdf', 'file-CON.txt']);
  assert.equal(safeName('...'), 'file-untitled');
});
test('required fields, custom scale and URL protocols are validated', () => {
  assert.ok(validateForm(defaults).length >= 3);
  const valid = { ...defaults, title: 'Book', description: 'Goal', targetReaders: 'Engineers' };
  assert.deepEqual(validateForm(valid), []);
  assert.equal(validateForm({ ...valid, urls: 'javascript:alert(1)\nnot-a-url' }).length, 2);
  assert.equal(validateForm({ ...valid, targetPages: 1.5 }).length, 1);
});

test('bundled runtime is mandatory when selected; corrupt or incomplete packs are rejected', async () => {
  const form = { ...defaults, title: 'Book', description: 'Goal', targetReaders: 'Readers' };
  await assert.rejects(generateJob(form, [], {}), /実行環境/);
  const zip = new JSZip(); zip.file('runtime/manifest.json', JSON.stringify({ target: 'windows-x64' }));
  const data = await zip.generateAsync({ type: 'uint8array' });
  const digest = createHash('sha256').update(data).digest('hex');
  const pack = { bytes: data.length, sha256: digest, parts: [{ file: 'mock.000.bin', bytes: data.length, sha256: digest }] };
  const catalog = { format_version: '1' as const, shared: pack, platforms: [{ id: 'windows-x64', label: 'Windows', pack }] };
  await assert.rejects(loadRuntime('windows-x64', catalog, '/missing/', () => {}, async () => new Response(data)), /不完全/);
  await assert.rejects(loadRuntime('windows-x64', catalog, '/corrupt/', () => {}, async () => new Response(new Uint8Array(data.length))), /チェックサム/);
  await assert.rejects(loadRuntime('linux-x64', catalog, '/', () => {}), /実行環境/);
});
test('generated job includes complete executable template, exact source bytes and verbatim instructions', async () => {
  const form = { ...structuredClone(defaults), runtimeTarget: 'none' as const, title: 'Test Technical Book', description: 'AI Agent architectureを解説する技術書', targetReaders: 'Software engineers', targetPages: 50, instructions: '  原文を保存。\n`literal` <text>\n', urls: 'https://pandoc.org/MANUAL.html\nhttps://typst.app/docs/', outputs: { ...defaults.outputs, epub: true } };
  const files = await Promise.all(['reference-1.pdf', 'reference-2.pdf', 'notes.md'].map(async name => { const data = await readFile(join('tests/fixtures', name)); return { name, data: new Uint8Array(data), size: data.length }; }));
  const result = await generateJob(form, files, await templateFiles());
  const zip = await JSZip.loadAsync(result.data);
  const root = 'publishing-job/';
  for (const path of ['AGENTS.md', 'TASK.md', 'project.json', 'source/metadata/outline.yaml', 'skills/research.md', 'templates/technical-book/book.typ', 'templates/docx/styles.json', 'templates/web/search.js', 'scripts/check_env.py', 'scripts/build.py', 'scripts/validate.py', 'scripts/package.py', 'scripts/cli.py']) assert.ok(zip.file(root + path), path);
  const project = JSON.parse(await zip.file(root + 'project.json')!.async('string'));
  assert.equal(project.format_version, '0.2'); assert.equal(project.citations.style, 'numeric'); assert.equal(project.research.require_supplied_coverage, true); assert.equal(project.book.language, 'ja');
  assert.equal(project.outputs.canonical_markdown, true); assert.equal(project.book.target_pages, 50);
  assert.equal(project.user_instructions, form.instructions);
  const design = JSON.parse(await zip.file(root + 'book.design.yaml')!.async('string'));
  assert.equal(design.theme, form.design.theme);
  assert.equal(design.typography.body.japanese, form.design.bodyJapanese);
  for (const theme of ['modern-technical', 'academic-jp', 'medical-textbook', 'minimal-monochrome', 'business-reference']) {
    const png = await zip.file(root + `themes/${theme}/preview.png`)!.async('uint8array');
    assert.deepEqual([...png.slice(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10]);
  }
  const task = await zip.file(root + 'TASK.md')!.async('string');
  assert.ok(task.includes('## Additional user instructions (verbatim)\n' + form.instructions + '\n')); assert.ok(task.includes('/goal'));
  for (const path of ['scripts/orchestrator.py', 'scripts/sources.py', 'scripts/research.py', 'scripts/planning.py', 'scripts/audit.py', 'skills/source-ingestion.md', 'skills/audit.md', 'templates/csl/numeric.csl', 'research/.gitkeep', 'plan/.gitkeep']) assert.ok(zip.file(root + path), path);
  for (const file of files) assert.deepEqual(await zip.file(root + 'input/sources/' + file.name)!.async('uint8array'), file.data);
  await mkdir('.test-output', { recursive: true }); await writeFile('.test-output/generated-job.zip', result.data);
});
test('unselected formats and disallowed research survive serialization; unknown files accepted', async () => {
  const form = { ...structuredClone(defaults), runtimeTarget: 'none' as const, title: '日本語の本', description: 'Purpose', targetReaders: 'Readers', research: { ...defaults.research, allow_web_research: false }, outputs: { canonical_markdown: true as const, docx: false, semantic_html: false, pdf: false, static_site: false, epub: false } };
  const result = await generateJob(form, [{ name: 'data.unusual', data: new Uint8Array([0, 255, 23]), size: 3 }], await templateFiles());
  const zip = await JSZip.loadAsync(result.data); const project = JSON.parse(await zip.file('publishing-job/project.json')!.async('string'));
  assert.equal(project.research.allow_web_research, false); assert.equal(project.outputs.pdf, false);
  assert.ok(zip.file('publishing-job/input/sources/data.unusual')); assert.equal(result.filename, '日本語の本-publishing-job.zip');
});

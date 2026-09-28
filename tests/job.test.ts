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

// ---------------------------------------------------------------- P1-UI publication settings
import { applyLayoutPreset, defaultPublication, previewLayout, publicationPayload, LAYOUT_PRESETS, STYLE_PRESETS } from '../src/publication.ts';
import presetsData from '../job-template/schemas/publication-presets.json' with { type: 'json' };

test('untouched publication settings add nothing to project.json (existing default build)', async () => {
  assert.deepEqual(publicationPayload(defaultPublication), {});
  const form = { ...structuredClone(defaults), runtimeTarget: 'none' as const, title: 'Book', description: 'Goal', targetReaders: 'Readers' };
  const zip = await JSZip.loadAsync((await generateJob(form, [], await templateFiles())).data);
  const project = JSON.parse(await zip.file('publishing-job/project.json')!.async('string'));
  for (const key of ['profile', 'layout_preset', 'layout_spec', 'style_preset', 'style_controls']) assert.ok(!(key in project), key);
  // Resolved plans and reports are generated per job, never shipped from the template.
  assert.equal(zip.file('publishing-job/plan/layout-spec.yaml'), null);
  assert.equal(zip.file('publishing-job/plan/style-bible.yaml'), null);
  assert.ok(zip.file('publishing-job/plan/.gitkeep'));
  assert.ok(zip.file('publishing-job/schemas/publication-presets.json'));
});
test('presets become LayoutSpec requests; edits become a patch over the preset', () => {
  assert.deepEqual(Object.keys(LAYOUT_PRESETS), ['standard-book', 'technical-reference', 'medical-scientific', 'magazine-mook', 'compact-shinsho']);
  assert.deepEqual(Object.keys(STYLE_PRESETS), ['technical-clean', 'medical-evidence', 'practical-guide', 'critical-editorial', 'essay']);
  const technical = applyLayoutPreset(defaultPublication, 'technical-reference');
  assert.deepEqual(publicationPayload(technical), { layout_preset: 'technical-reference' });
  const preview = previewLayout(technical);
  assert.deepEqual([preview.pageSize, preview.widthMm, preview.columns, preview.gutterMm, preview.columnWidthMm, preview.bodyWidthMm], ['B5', 176, 2, 6, 67, 140]);
  const wider = { ...technical, gutterMm: 10, tier: 'long', genre: 'medical_science', stylePreset: 'medical-evidence', styleControls: { table_density: 'compact', visual_tone: 'default' } };
  assert.deepEqual(publicationPayload(wider), { profile: { tier: 'long', genre: 'medical_science' }, layout_preset: 'technical-reference', layout_spec: { body: { gutter_mm: 10 } }, style_preset: 'medical-evidence', style_controls: { table_density: 'compact' } });
  assert.equal(previewLayout(wider).columnWidthMm, 65);
  const custom = { ...applyLayoutPreset(defaultPublication, 'custom'), pageSize: 'custom' as const, customWidthMm: 182, customHeightMm: 257 };
  const request = publicationPayload(custom).layout_spec as { page_size: string; page: { width_mm: number; height_mm: number } };
  assert.deepEqual([request.page_size, request.page.width_mm, request.page.height_mm], ['custom', 182, 257]);
});
test('impossible geometry and vertical writing are reported with user-facing messages', () => {
  const codes = (value: typeof defaultPublication) => previewLayout(value).issues.map(issue => issue.code);
  const shinsho = applyLayoutPreset(defaultPublication, 'compact-shinsho');
  assert.deepEqual(codes({ ...shinsho, columns: 2, gutterMm: 18 }), ['column_too_narrow']);
  assert.ok(codes({ ...shinsho, margins: { top: 15, bottom: 17, inner: 70, outer: 70 } }).includes('margins_exceed_page'));
  assert.deepEqual(codes({ ...applyLayoutPreset(defaultPublication, 'technical-reference'), gutterMm: 30 }), ['gutter_too_large']);
  assert.deepEqual(codes({ ...applyLayoutPreset(defaultPublication, 'magazine-mook'), columns: 1 }), ['span_policy_single_column']);
  assert.deepEqual(codes({ ...applyLayoutPreset(defaultPublication, 'standard-book'), writingMode: 'vertical-rl' }), ['vertical_unsupported']);
  assert.equal(presetsData.writing_modes['vertical-rl'].typst, false);
  const form = { ...structuredClone(defaults), title: 'Book', description: 'Goal', targetReaders: 'Readers', publication: { ...shinsho, columns: 2 as const, gutterMm: 18 } };
  assert.ok(validateForm(form).some(error => error.includes('2段組みには狭すぎます')));
  assert.ok(validateForm({ ...form, publication: { ...shinsho, writingMode: 'vertical-rl' as const } }).some(error => error.includes('縦書き')));
});
test('a named preset page size is mirrored into the Design Spec for legacy consumers', async () => {
  const form = { ...structuredClone(defaults), runtimeTarget: 'none' as const, title: 'Book', description: 'Goal', targetReaders: 'Readers', publication: applyLayoutPreset(defaultPublication, 'medical-scientific') };
  const zip = await JSZip.loadAsync((await generateJob(form, [], await templateFiles())).data);
  assert.equal(JSON.parse(await zip.file('publishing-job/book.design.yaml')!.async('string')).page.size, 'B5');
  const project = JSON.parse(await zip.file('publishing-job/project.json')!.async('string'));
  assert.equal(project.layout_preset, 'medical-scientific');
  assert.ok((await zip.file('publishing-job/TASK.md')!.async('string')).includes('bookorder publication'));
});

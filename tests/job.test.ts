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
  for (const path of ['AGENTS.md', 'TASK.md', 'project.json', 'source/metadata/outline.yaml', 'skills/research/research.md', 'templates/technical-book/book.typ', 'templates/docx/styles.json', 'templates/web/search.js', 'scripts/check_env.py', 'scripts/build.py', 'scripts/validate.py', 'scripts/package.py', 'scripts/cli.py']) assert.ok(zip.file(root + path), path);
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
  for (const path of ['scripts/orchestrator.py', 'scripts/sources.py', 'scripts/research.py', 'scripts/planning.py', 'scripts/audit.py', 'scripts/skills.py', 'scripts/prose_signals.py', 'config/prose-signals/ja.json', 'skills/research/source-ingestion.md', 'skills/quality/audit.md', 'skills/editorial/prose-audit.md', 'skills/editorial/whole-book-review.md', 'skills/editorial/developmental-editing.md', 'skills/editorial/cadence-editing.md', 'templates/csl/numeric.csl', 'research/.gitkeep', 'plan/.gitkeep']) assert.ok(zip.file(root + path), path);
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

test('file picker snapshots the live FileList before the input is reset (attachment regression)', async () => {
  // Browsers empty input.files when the input value is reset; reading it later inside a React updater adds nothing.
  const app = await readFile('src/App.tsx', 'utf8');
  const addFiles = app.slice(app.indexOf('function addFiles'), app.indexOf('\n', app.indexOf('function addFiles')));
  assert.ok(addFiles.indexOf('Array.from(list)') >= 0 && addFiles.indexOf('Array.from(list)') < addFiles.indexOf('setFiles('), addFiles);
  assert.match(app, /type="file"[^>]*onChange=\{e => \{ if \(e\.target\.files\) addFiles\(e\.target\.files\); e\.target\.value = ''; \}\}/);
});

// ---------------------------------------------------------------- IA revision: single authorities, presets, precedence
import { designFromTheme, defaultDesign } from '../src/design.ts';
import { applyPublicationPreset, autoTier, designPage, effectivePublication, presetDeviations, requestPayload } from '../src/publication.ts';
import { jobDesign, projectData, templateTheme } from '../src/job.ts';

const themeYaml = async (theme: string) => JSON.parse(await readFile(`job-template/themes/${theme}/theme.yaml`, 'utf8'));
const themeOf = async (theme: string) => templateTheme({ [`themes/${theme}/theme.yaml`]: await readFile(`job-template/themes/${theme}/theme.yaml`, 'utf8') }, theme)!;
const baseForm = () => ({ ...structuredClone(defaults), title: 'Compat', description: 'Goal', targetReaders: 'Readers', runtimeTarget: 'none' as const });

test('target scale is the only scale input; tier is resolved automatically from it by the shared rule', () => {
  assert.deepEqual([50, 80, 81, 150, 200, 300, 400, 450, 451, 0].map(autoTier), ['short', 'short', 'standard', 'standard', 'standard', 'long', 'long', 'long', 'monograph', 'standard']);
  assert.equal(defaultPublication.tier, 'auto');
  assert.ok(!('profile' in projectData(baseForm(), [], [])));            // automatic tier writes nothing
  assert.deepEqual(projectData({ ...baseForm(), publication: { ...defaultPublication, tier: 'long' } }, [], []).profile, { tier: 'long' });
});
test('a publication preset fills genre, layout, style preset and theme in one step; later edits win', async () => {
  const { publication, theme } = applyPublicationPreset(defaultPublication, 'medical-scientific');
  assert.equal(theme, 'medical-textbook');
  assert.deepEqual([publication.publicationPreset, publication.genre, publication.layoutPreset, publication.stylePreset], ['medical-scientific', 'medical_science', 'medical-scientific', 'medical-evidence']);
  const design = designFromTheme('medical-textbook', await themeYaml('medical-textbook'));
  const form = { ...baseForm(), publication, design };
  const project = projectData(form, [], [], await themeOf('medical-textbook'));
  assert.deepEqual([project.profile, project.layout_preset, project.style_preset], [{ genre: 'medical_science' }, 'medical-scientific', 'medical-evidence']);
  assert.ok(!('layout_spec' in project) && !('style_controls' in project) && !('style_bible' in project));
  assert.deepEqual(jobDesign(form, await themeOf('medical-textbook')).page, { size: 'B5', orientation: 'portrait' });
  assert.deepEqual(presetDeviations(publication, 'medical-textbook'), []);
  assert.deepEqual(presetDeviations({ ...publication, gutterMm: 9, genre: 'technical' }, 'modern-technical'), ['genre', 'layout', 'theme']);
  for (const id of Object.keys(presetsData.publication_presets)) {
    const bundle = presetsData.publication_presets[id as 'compact'];
    assert.ok(bundle.layout in presetsData.layout_presets && (bundle.style === null || bundle.style in presetsData.style_presets), id);
    await readFile(`job-template/themes/${bundle.theme}/theme.yaml`);
  }
});
test('page size and orientation have a single authority (PublicationOptions); the Design Spec page is derived', async () => {
  assert.ok(!('pageSize' in defaultDesign) && !('orientation' in defaultDesign));
  const modern = await themeOf('modern-technical');
  // Theme mode: an explicit Design Spec size/orientation stays on the legacy book.design.yaml path (no layout_spec).
  const legacy = { ...baseForm(), publication: { ...defaultPublication, pageSize: 'B5' as const, orientation: 'landscape' as const } };
  assert.deepEqual(jobDesign(legacy, modern).page, { size: 'B5', orientation: 'landscape' });
  assert.ok(!('layout_spec' in projectData(legacy, [], [], modern)));
  // Layout presets: the LayoutSpec request carries the geometry; the Design Spec mirrors a Design-Spec-legal size only.
  const b6 = { ...baseForm(), publication: applyLayoutPreset(defaultPublication, 'compact-shinsho') };
  assert.deepEqual(jobDesign(b6, modern).page, { size: 'A5', orientation: 'portrait' });
  const rotated = { ...baseForm(), publication: { ...applyLayoutPreset(defaultPublication, 'standard-book'), orientation: 'landscape' as const } };
  assert.equal((projectData(rotated, [], [], modern).layout_spec as { orientation: string }).orientation, 'landscape');
  assert.equal(jobDesign(rotated, modern).page.orientation, 'landscape');
});
test('changing the theme never discards an explicit layout choice; theme-following values follow the new theme', async () => {
  const business = await themeOf('business-reference');                   // theme page: B5
  const follow = { ...baseForm(), design: designFromTheme('business-reference', await themeYaml('business-reference')) };
  assert.deepEqual(jobDesign(follow, business).page, { size: 'B5', orientation: 'portrait' });
  const pinned = { ...follow, publication: { ...defaultPublication, pageSize: 'A4' as const } };
  assert.deepEqual(jobDesign(pinned, business).page, { size: 'A4', orientation: 'portrait' });
  const custom = { ...follow, publication: { ...applyLayoutPreset(defaultPublication, 'technical-reference'), gutterMm: 9 } };
  assert.deepEqual(projectData(custom, [], [], business).layout_spec, { body: { gutter_mm: 9 } });
  assert.equal(effectivePublication(custom.publication, business.page).pageSize, 'B5');
});
test('one control per visual concept: explicit Design Spec edits derive the matching StyleBible request', async () => {
  const modern = await themeOf('modern-technical');
  assert.deepEqual(requestPayload(defaultPublication, defaultDesign, modern), {});
  const edited = requestPayload({ ...defaultPublication, styleControls: { table_density: 'compact' } }, { ...defaultDesign, density: 'spacious', chapterStyle: 'academic', accent: '#123abc' }, modern);
  assert.deepEqual(edited, { style_controls: { visual_density: 'airy', chapter_opener: 'academic', table_density: 'compact' }, style_bible: { palette: { accent: '#123ABC' } } });
  const controls = await readFile('src/DesignPanel.tsx', 'utf8');
  for (const hidden of ["control('visual_density')", "control('chapter_opener')", "control('typography_scale')"]) assert.ok(!controls.includes(hidden), hidden);
});
test('generated project.json and book.design.yaml stay compatible with the previous WebUI', async () => {
  const modern = await themeOf('modern-technical');
  const golden = async (name: string) => JSON.parse(await readFile(`tests/fixtures/webui-compat/${name}.json`, 'utf8'));
  const cases: Record<string, BookFormLike> = {
    default: baseForm(),
    'theme-b5': { ...baseForm(), publication: { ...defaultPublication, pageSize: 'B5' } },   // was DesignOptions.pageSize
    'medical-preset': { ...baseForm(), publication: { ...applyLayoutPreset(defaultPublication, 'medical-scientific'), genre: 'medical_science', stylePreset: 'medical-evidence', tier: 'long' } },
    'custom-geometry': { ...baseForm(), publication: { ...applyLayoutPreset(defaultPublication, 'custom'), pageSize: 'custom', customWidthMm: 182, customHeightMm: 257, columns: 2, figureSpan: 'auto', tableSpan: 'full', margins: { top: 18, bottom: 20, inner: 20, outer: 16 } } },
  };
  for (const [name, form] of Object.entries(cases)) {
    const expected = await golden(name);
    // Every field of the previous WebUI is unchanged. New jobs add the publication architecture (AUTO by default) and
    // decoupled citation / bibliography settings; the legacy citations.style value stays as it was.
    const { publication_architecture, citations, ...rest } = projectData(form, [], [], modern) as Record<string, unknown>;
    const { citations: oldCitations, ...expectedRest } = expected.project;
    assert.deepEqual(rest, expectedRest, name);
    assert.equal((citations as { style: string }).style, oldCitations.style, name);
    assert.deepEqual(publication_architecture, { mode: 'auto' }, name);
    assert.equal((citations as { in_text_citation_style: string }).in_text_citation_style, oldCitations.style, name);
    assert.deepEqual(jobDesign(form, modern), expected.design, name);
  }
});
type BookFormLike = ReturnType<typeof baseForm>;
test('TASK.md gives the free text authority over defaults, structured settings authority over their own fields', async () => {
  const instructions = '教科書的にせず、批評性を残す。\n各章末にまとめを付けない。\n判型はA4にする。';
  const zip = await JSZip.loadAsync((await generateJob({ ...baseForm(), instructions }, [], await templateFiles())).data);
  const task = await zip.file('publishing-job/TASK.md')!.async('string');
  const project = JSON.parse(await zip.file('publishing-job/project.json')!.async('string'));
  assert.equal(project.user_instructions, instructions);
  assert.ok(task.includes('## Additional user instructions (verbatim)\n' + instructions + '\n'));
  assert.ok(task.includes('## Precedence of settings') && task.includes('structured settings'));
  assert.ok(!task.includes('supplement them'), 'the free text is no longer described as a mere supplement');
  for (const words of ["Do not improve the book against the user's explicit intent", 'for the fields they represent', 'editorial and semantic choices',
    'fill only what the user left unspecified', 'Invariants', 'the book stays A5', 'plan/user-intent.yaml', 'docs/user-intent.md'])
    assert.ok(task.includes(words), words);
  assert.ok(zip.file('publishing-job/docs/user-intent.md') && zip.file('publishing-job/scripts/user_intent.py'), 'the job ships the user-intent spec and module');
});
test('an empty instruction field keeps the job valid and states no user intent', async () => {
  const zip = await JSZip.loadAsync((await generateJob({ ...baseForm(), instructions: '' }, [], await templateFiles())).data);
  const project = JSON.parse(await zip.file('publishing-job/project.json')!.async('string'));
  assert.equal(project.user_instructions, '');
  assert.ok((await zip.file('publishing-job/TASK.md')!.async('string')).includes('## Additional user instructions (verbatim)\n\n'));
});

// ---------------------------------------------------------------- audit: theme switching keeps explicit values
import { switchTheme } from '../src/design.ts';
import { pdfAccent } from '../src/publication.ts';
test('the WebUI default design is exactly the default theme (untouched Basic derives no StyleBible request)', async () => {
  assert.deepEqual(defaultDesign, designFromTheme('modern-technical', await themeYaml('modern-technical')));
});
test('switching theme keeps explicit design values and follows the new theme elsewhere', async () => {
  const modern = designFromTheme('modern-technical', await themeYaml('modern-technical'));
  const medical = designFromTheme('medical-textbook', await themeYaml('medical-textbook'));
  const untouched = switchTheme(modern, modern, medical);
  assert.deepEqual(untouched, medical);
  const edited = switchTheme({ ...modern, accent: '#AA3300', bodySize: 10, customCss: '.x{}', artDirection: 'calm' }, modern, medical);
  assert.deepEqual([edited.theme, edited.accent, edited.bodySize, edited.density, edited.customCss, edited.artDirection], ['medical-textbook', '#AA3300', 10, medical.density, '.x{}', 'calm']);
});
test('the summary shows the accent the PDF will actually use', async () => {
  const medical = await themeOf('medical-textbook');
  const design = designFromTheme('medical-textbook', await themeYaml('medical-textbook'));
  const lookup = (t: string) => ({ medical_science: '#116B78' } as Record<string, string>)[t];
  const preset = applyPublicationPreset(defaultPublication, 'medical-scientific').publication;
  assert.equal(pdfAccent(preset, design, medical, lookup), '#116B78');                       // style template beats theme in PDF
  assert.equal(pdfAccent(preset, { accent: '#AA3300' }, medical, lookup), '#AA3300');        // explicit beats template
  assert.equal(pdfAccent(defaultPublication, design, medical, lookup), design.accent);
});

// ---------------------------------------------------------------- intent-driven publication architecture (WebUI → project.json)
import { applyQuickUse, architecturePayload, citationPayload, defaultArchitecture, defaultCitation, detectSignals, inferUsage, VOCAB } from '../src/architecture.ts';
import { execFileSync } from 'node:child_process';
test('files carry roles: content goes to input/sources, references and figures to input/assets', async () => {
  const png = new Uint8Array([137, 80, 78, 71]);
  const files = [
    { name: 'guideline.md', data: new TextEncoder().encode('# g'), size: 3, usage: { ...inferUsage('guideline.md'), authority: 'guideline', roleOrigin: 'user' as const } },
    { name: 'nurse-blog.md', data: new TextEncoder().encode('# b'), size: 3 },                                   // estimated: background
    { name: 'layout-sample.pdf', data: new Uint8Array([37, 80]), size: 2 },                                      // estimated: layout reference
    { name: 'ward-flow.png', data: png, size: 4, type: 'image/png', usage: { ...inferUsage('ward-flow.png', 'image/png'), intendedChapter: '第2章', notes: '第2章の病棟業務の流れを説明する場所で使用', roleOrigin: 'user' as const } },
  ];
  assert.equal(inferUsage('nurse-blog.md').role, 'background');
  assert.equal(inferUsage('layout-sample.pdf').role, 'layout_reference');
  assert.equal(inferUsage('ward-flow.png', 'image/png').assetRole, 'inline_figure');
  assert.equal(applyQuickUse(inferUsage('chart.png'), 'redraw').role, 'redraw_source');
  const form = { ...baseForm(), instructions: '章末問題はいらない。ケースを多く。' };
  const zip = await JSZip.loadAsync((await generateJob(form, files, await templateFiles())).data);
  const project = JSON.parse(await zip.file('publishing-job/project.json')!.async('string'));
  assert.deepEqual(project.input.sources.map((s: { path: string }) => s.path), ['input/sources/guideline.md', 'input/sources/nurse-blog.md']);
  assert.deepEqual(project.input.sources.map((s: { usage: { role: string } }) => s.usage.role), ['evidence', 'background']);
  assert.equal(project.input.sources[1].usage.role_origin, 'inferred');
  assert.deepEqual(project.input.assets.map((a: { id: string; path: string; usage: { role: string } }) => [a.id, a.path, a.usage.role]),
    [['asset-001', 'input/assets/layout-sample.pdf', 'layout_reference'], ['asset-002', 'input/assets/ward-flow.png', 'asset']]);
  assert.equal(project.input.assets[1].usage.intended_chapter, '第2章');
  assert.ok(zip.file('publishing-job/input/assets/ward-flow.png') && !zip.file('publishing-job/input/sources/ward-flow.png'));
  const task = await zip.file('publishing-job/TASK.md')!.async('string');
  assert.ok(task.includes('## Publication architecture') && task.includes('「章末問題はいらない」') && task.includes('## Inputs and their roles'));
  assert.ok(task.includes('input/assets/layout-sample.pdf: layout_reference'));
});
test('structure modes, block policy and decoupled citations are written as chosen', () => {
  assert.deepEqual(architecturePayload(defaultArchitecture), { mode: 'auto' });
  const guided = { ...defaultArchitecture, mode: 'guided' as const, archetype: 'exam_preparation', secondaryArchetype: 'textbook', blocks: { exercises: 'preferred' as const, column: 'forbidden' as const },
    exercisePolicy: 'exam_focused', visualDensity: 'high', visualAvoid: ['workflow'], evidencePriority: 'strict', preferredAuthority: ['guideline'] };
  assert.deepEqual(architecturePayload(guided), { mode: 'guided', archetype: 'exam_preparation', secondary_archetype: 'textbook',
    block_policy: { preferred: ['exercises'], forbidden: ['column'] }, exercise_policy: 'exam_focused', visual_policy: { density: 'high', avoid_types: ['workflow'] },
    evidence_policy: { priority: 'strict', preferred_authority: ['guideline'] } });
  assert.ok(validateForm({ ...baseForm(), architecture: { ...defaultArchitecture, mode: 'guided' } }).some(e => e.includes('GUIDED')));
  // Footnotes in the text, numbered lists at the back; author-year in the text, numbered lists at the back.
  assert.deepEqual(citationPayload('note', defaultCitation), { style: 'note', in_text_citation_style: 'note', footnote_style: 'full', bibliography_style: 'standard',
    bibliography_numbering: 'numbered', numbering_scope: 'per_group', bibliography_grouping: { cited: true, background: true, visual: true, design: false } });
  assert.equal(citationPayload('author-year', defaultCitation).bibliography_style, 'author_date');
  assert.equal(citationPayload('author-year', defaultCitation).bibliography_numbering, 'numbered');
});
test('intent signals are read with the same patterns as the job (TypeScript / Python parity)', () => {
  const text = '章末問題はいらない。ケースを多く、図表を多く。固すぎない文章で。';
  const ts = detectSignals(text).map(s => [s.id, s.quote]);
  assert.deepEqual(ts.map(([id]) => id), ['no_exercises', 'more_cases', 'more_visuals', 'not_stiff']);
  const py = JSON.parse(execFileSync(process.platform === 'win32' ? 'python' : 'python3', ['-c', `import sys, json; sys.path.insert(0, 'job-template/scripts'); import publication_architecture as pa; print(json.dumps([[s['id'], s['quote']] for s in pa.signals(sys.argv[1])], ensure_ascii=False))`, text], { encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } }));
  assert.deepEqual(ts, py);
  assert.ok(VOCAB.blocks.answer_key && VOCAB.visual_types.decision_tree && VOCAB.source_roles.layout_reference.content === false);
});

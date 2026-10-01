import JSZip from 'jszip';
import type { RuntimeBundle, RuntimeTarget } from './runtime.ts';
import { defaultDesign, designSpec, type DesignOptions } from './design.ts';
import { defaultPublication, designPage, issueText, previewLayout, requestPayload, PUBLICATION_PRESETS, type PublicationOptions, type ThemeSpec } from './publication.ts';
import { ARCHETYPES, inferUrlUsage, architecturePayload, citationPayload, defaultArchitecture, defaultCitation, detectSignals, inferUsage, isContent, signalText, SOURCE_ROLES, usagePayload, type ArchitectureOptions, type CitationOptions, type FileUsage, type UiMode } from './architecture.ts';

export interface BookForm {
  title: string; description: string; targetReaders: string; language: string;
  targetPages: number; instructions: string; urls: string;
  runtimeTarget: RuntimeTarget;
  design: DesignOptions;
  publication: PublicationOptions;
  research: { allow_web_research: boolean; prefer_primary_sources: boolean; keep_provenance: boolean; require_supplied_coverage: boolean };
  citationStyle: 'numeric' | 'author-year' | 'note';   // in-text citation form (project.json citations.style / in_text_citation_style)
  bibliography: Omit<CitationOptions, 'inText'>;       // back matter: separate from how the text cites
  urlUsage: Record<string, FileUsage>;                 // per-URL role metadata (same model as files); absent = estimate
  uiMode: UiMode;                                      // Quick / Advanced publishing (UI only; both write the same model)
  architecture: ArchitectureOptions;
  figures: { tables: boolean; diagrams: boolean; charts: boolean; generative_images: boolean };
  outputs: { canonical_markdown: true; docx: boolean; semantic_html: boolean; pdf: boolean; static_site: boolean; epub: boolean };
}
export const defaults: BookForm = {
  title: '', description: '', targetReaders: '', language: 'ja', targetPages: 150, instructions: '', urls: '', runtimeTarget: 'windows-x64',
  design: structuredClone(defaultDesign),
  publication: structuredClone(defaultPublication),
  research: { allow_web_research: true, prefer_primary_sources: true, keep_provenance: true, require_supplied_coverage: true },
  citationStyle: 'numeric', urlUsage: {}, bibliography: structuredClone(defaultCitation), uiMode: 'quick', architecture: structuredClone(defaultArchitecture),
  figures: { tables: true, diagrams: true, charts: true, generative_images: false },
  outputs: { canonical_markdown: true, docx: true, semantic_html: true, pdf: true, static_site: true, epub: false },
};
export interface SourceFile { name: string; data: Blob | Uint8Array; size: number; type?: string; usage?: FileUsage }
/** A URL's role metadata: the user's choice, else the WebUI estimate from the address (role_origin: inferred). */
export const urlUsageOf = (form: BookForm, url: string) => form.urlUsage?.[url] ?? inferUrlUsage(url);
/** A file's role metadata: the user's choice, else the WebUI estimate (role_origin: inferred). */
export const fileUsage = (file: SourceFile) => file.usage ?? inferUsage(file.name, file.type);
/** ZIP path: content files are sources; layout / style / visual references and placed images are assets, never sources. */
export const filePath = (file: SourceFile, name: string) => `input/${isContent(fileUsage(file)) ? 'sources' : 'assets'}/${name}`;

export function safeName(name: string): string {
  const clean = name.normalize('NFC').replace(/[\\/<>:"|?*\u0000-\u001f]/g, '_').replace(/^\.+|[. ]+$/g, '').trim().slice(0, 150);
  return (!clean || /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(clean)) ? `file-${clean || 'untitled'}` : clean;
}
export function uniqueNames(files: { name: string }[]): string[] {
  const used = new Set<string>();
  return files.map(file => {
    const base = safeName(file.name); let name = base; let i = 2;
    const dot = base.lastIndexOf('.'); const stem = dot > 0 ? base.slice(0, dot) : base; const ext = dot > 0 ? base.slice(dot) : '';
    while (used.has(name.toLowerCase())) name = `${stem}-${i++}${ext}`;
    used.add(name.toLowerCase()); return name;
  });
}
export function urlLines(value: string): string[] {
  return value.split(/\r?\n/).map(x => x.trim()).filter(Boolean);
}
export function validateForm(form: BookForm): string[] {
  const errors: string[] = [];
  if (!form.title.trim()) errors.push('書籍タイトルを入力してください。');
  if (!form.description.trim()) errors.push('書籍の概要・目的を入力してください。');
  if (!form.targetReaders.trim()) errors.push('対象読者を入力してください。');
  if (!form.language.trim()) errors.push('言語を入力してください。');
  if (!Number.isInteger(form.targetPages) || form.targetPages < 1 || form.targetPages > 10000) errors.push('ページ数は1〜10,000の整数で入力してください。');
  const design = form.design;
  if (![design.bodySize, design.codeSize, design.captionSize, design.footnoteSize].every(value => Number.isFinite(value) && value >= 5 && value <= 40)) errors.push('文字サイズは5〜40ptで指定してください。');
  if (!/^#[0-9a-fA-F]{6}$/.test(design.accent)) errors.push('アクセント色は6桁のカラーコードで指定してください。');
  if (![design.bodyJapanese, design.bodyLatin, design.headingJapanese, design.headingLatin, design.codeFont, design.captionFont, design.footnoteFont].every(name => name.trim() && name.length <= 120 && !/[\u0000-\u001f]/.test(name))) errors.push('フォント名を指定してください。');
  const a = form.architecture;
  if (a && a.mode === 'guided' && a.archetype === 'auto') errors.push('GUIDEDモードでは出版物タイプを選んでください。');
  if (a && a.archetype !== 'auto' && a.archetype === a.secondaryArchetype) errors.push('副タイプには主タイプと別のタイプを選んでください。');
  if (form.publication && form.publication.layoutPreset !== 'theme') {
    const preview = previewLayout(form.publication);  // non-theme layouts carry explicit page values
    for (const issue of preview.issues) errors.push(`出版形式：${issueText(issue, preview)}`);
  }
  urlLines(form.urls).forEach((url, i) => {
    try { if (!['http:', 'https:'].includes(new URL(url).protocol)) throw Error(); }
    catch { errors.push(`参考URLの${i + 1}行目に有効なHTTP / HTTPS URLを入力してください。`); }
  });
  return errors;
}
/** The selected theme's Design Spec defaults (theme.yaml) from the job template, used to derive linked settings. */
export function templateTheme(templates: Record<string, string | Uint8Array>, theme: string): ThemeSpec | undefined {
  const text = templates[`themes/${theme}/theme.yaml`];
  if (typeof text !== 'string') return undefined;
  const t = JSON.parse(text);
  return { page: { size: t.page.size, orientation: t.page.orientation, margin: t.page.margin }, layout: { density: t.layout.density },
    components: { chapter_opener: t.components.chapter_opener }, colors: { accent: t.colors.accent } };
}
export function projectData(form: BookForm, names: string[], files: SourceFile[], theme?: ThemeSpec) {
  const languageNames: Record<string, string> = { japanese: 'ja', '日本語': 'ja', english: 'en', '英語': 'en', chinese: 'zh', korean: 'ko', french: 'fr', german: 'de', spanish: 'es' };
  const language = languageNames[form.language.trim().toLowerCase()] ?? form.language.trim();
  return {
    format: 'portable-publishing-job', format_version: '0.2',
    book: { title: form.title.trim(), description: form.description, target_readers: form.targetReaders, target_pages: form.targetPages, language },
    user_instructions: form.instructions, research: form.research, figures: form.figures,
    workflow: { separated: true, agents: {} },
    citations: form.bibliography ? citationPayload(form.citationStyle, form.bibliography) : { style: form.citationStyle },
    outputs: { ...form.outputs, canonical_markdown: true },
    runtime: { target: form.runtimeTarget, bundled: form.runtimeTarget !== 'none' },
    design: { spec: 'book.design.yaml', theme: form.design.theme, custom_css: 'custom.css' },
    input: inputPayload(form, names, files),
    // Intent-driven publication architecture (docs/INTENT_DRIVEN_PUBLICATION_ARCHITECTURE.md). Absent = legacy FIXED job.
    ...(form.architecture ? { publication_architecture: architecturePayload(form.architecture) } : {}),
    // Publication request for the existing resolvers (profile / LayoutSpec / StyleBible). Empty when untouched.
    ...requestPayload(form.publication ?? defaultPublication, form.design, theme),
  };
}
/** input.sources (content, with role metadata) and input.assets (not content). A file with an asset role that is also
 *  content (e.g. a PDF used as evidence and redrawn) is listed in sources with its asset_role. */
export function inputPayload(form: BookForm, names: string[], files: SourceFile[]) {
  const sources = []; const assets = [];
  for (let i = 0; i < files.length; i++) {
    const usage = fileUsage(files[i]);
    const entry = { original_name: files[i].name, path: filePath(files[i], names[i]), size_bytes: files[i].size, ...(form.architecture ? { usage: usagePayload(usage) } : {}) };
    if (isContent(usage) || !form.architecture) sources.push(entry);
    else assets.push({ id: `asset-${String(assets.length + 1).padStart(3, '0')}`, ...entry });
  }
  // URLs share the Source Role System: content URLs stay in input.urls (the old format) with input.url_usage beside
  // them; layout / visual reference URLs are not content and go to input.assets, never to the research corpus.
  const urls: string[] = []; const urlUsage: Record<string, unknown> = {};
  for (const url of urlLines(form.urls)) {
    const usage = urlUsageOf(form, url);
    if (!form.architecture || isContent(usage)) { urls.push(url); if (form.architecture) urlUsage[url] = usagePayload(usage); }
    else assets.push({ id: `asset-${String(assets.length + 1).padStart(3, '0')}`, kind: 'url', url, original_name: url, usage: usagePayload(usage) });
  }
  return { urls, ...(Object.keys(urlUsage).length ? { url_usage: urlUsage } : {}), sources, ...(assets.length ? { assets } : {}) };
}
/** TASK.md section: how the book should be designed and what each input is for. */
export function architectureTask(form: BookForm, names: string[], files: SourceFile[]): string {
  const a = form.architecture; if (!a) return '';
  const signals = detectSignals(`${form.instructions}\n${form.description}`);
  const lines = ['## Publication architecture', `Structure mode: ${a.mode.toUpperCase()} (plan/publication-architecture.yaml is decided in the publication_planning phase; docs/publication-architecture.md).`,
    `Publication type: ${a.archetype === 'auto' ? 'inferred from the intent' : ARCHETYPES[a.archetype]?.en + (a.secondaryArchetype ? ' + ' + ARCHETYPES[a.secondaryArchetype]?.en : '')}.`,
    'Blocks (summaries, checklists, exercises, cases, figures …) are a library to combine per chapter, never a template every chapter must repeat. Exercises only where the architecture calls for them, always with answers.'];
  const chosen = Object.entries(a.blocks);
  if (chosen.length) lines.push('Block choices from the WebUI: ' + chosen.map(([b, state]) => `${b}=${state}`).join(', ') + '.');
  if (signals.length) lines.push('Explicit wishes read from the user\'s words (enforced): ' + signals.map(s => `「${s.quote}」→ ${signalText(s.effect)}`).join('; ') + '.');
  lines.push('', '## Inputs and their roles');
  if (!files.length && !urlLines(form.urls).length) lines.push('(No uploaded files or URLs)');
  files.forEach((file, i) => {
    const u = fileUsage(file);
    lines.push(`- ${filePath(file, names[i])}: ${u.role} (${SOURCE_ROLES[u.role]?.label}${u.assetRole ? ', ' + u.assetRole : ''}${u.roleOrigin === 'inferred' ? ', estimated' : ''})`
      + (u.intendedChapter ? `; chapter ${u.intendedChapter}` : '') + (u.notes ? `; instruction: ${u.notes}` : ''));
  });
  for (const url of urlLines(form.urls)) {
    const u = urlUsageOf(form, url);
    lines.push(`- ${url}: ${u.role} (${SOURCE_ROLES[u.role]?.label}${u.roleOrigin === 'inferred' ? ', estimated from the address' : ''}; authority ${u.authority}`
      + (u.citationAllowed !== 'auto' ? `; citation ${u.citationAllowed === 'yes' ? 'allowed' : 'not allowed'}` : '') + ')'
      + (u.intendedChapter ? `; chapter ${u.intendedChapter}` : '') + (u.intendedUsage ? `; usage: ${u.intendedUsage}` : '') + (u.notes ? `; instruction: ${u.notes}` : ''));
  }
  lines.push('Only evidence may be cited for factual claims. Background and structure references inform the author but are not cited or listed. Further-reading sources are never cited and appear in 参考資料 only when explicitly assigned that role. Redraw sources are credited only for figures actually used. Layout, style and visual references are never content or bibliography entries.');
  return lines.join('\n') + '\n\n';
}
/** Design Spec written to the job. A layout request's named page size is mirrored for the legacy CSS/HTML consumers;
 *  plan/layout-spec.yaml (resolved from project.json) stays the geometry authority for PDF. */
export function jobDesign(form: BookForm, theme?: ThemeSpec) {
  return designSpec(form.design, designPage(form.publication ?? defaultPublication, theme?.page));
}
export async function generateJob(form: BookForm, files: SourceFile[], templates: Record<string, string | Uint8Array>, progress?: (percent: number) => void, runtime?: RuntimeBundle) {
  const errors = validateForm(form); if (errors.length) throw new Error(errors.join('\n'));
  const zip = new JSZip(); const root = zip.folder('publishing-job')!;
  if (form.runtimeTarget !== 'none' && (!runtime || runtime.target !== form.runtimeTarget)) throw new Error('選択したOSの実行環境を読み込めていません。');
  for (const [path, text] of Object.entries(templates)) {
    if (path.split('/').includes('__pycache__') || path.endsWith('.pyc')) continue;
    // Generated artifacts (resolved plans, reports) never ship: each job resolves them from its own project.json.
    if (/^(plan|reports)\/(?!\.gitkeep$)/.test(path) || /^tmp[a-z0-9_]+\//.test(path)) continue;
    if (path === 'run.cmd' && !form.runtimeTarget.startsWith('windows')) continue;
    if (path === 'bookorder.cmd' && form.runtimeTarget !== 'none' && !form.runtimeTarget.startsWith('windows')) continue;
    if (path === 'bookorder' && form.runtimeTarget.startsWith('windows')) continue;
    if (path === 'run.sh' && (form.runtimeTarget === 'none' || form.runtimeTarget.startsWith('windows'))) continue;
    root.file(path, text, path === 'run.sh' || path === 'bookorder' ? { unixPermissions: 0o100755 } : undefined);
  }
  if (runtime) for (const [path, data] of Object.entries(runtime.files)) {
    if (!/^(runtime|third-party)\//.test(path) || path.split('/').includes('..')) throw new Error('実行環境に不正なパスがあります。');
    root.file(path, data, { compression: /\.(zip|gz|xz|crate)$/.test(path) ? 'STORE' : 'DEFLATE' });
  }
  const theme = templateTheme(templates, form.design.theme);
  const names = uniqueNames(files); const project = projectData(form, names, files, theme);
  root.file('project.json', JSON.stringify(project, null, 2) + '\n');
  root.file('book.design.yaml', JSON.stringify(jobDesign(form, theme), null, 2) + '\n');
  root.file('custom.css', form.design.customCss + '\n');
  root.file('input/urls.txt', urlLines(form.urls).join('\n') + '\n');
  for (let i = 0; i < files.length; i++) {
    const data = files[i].data;
    root.file(form.architecture ? filePath(files[i], names[i]) : `input/sources/${names[i]}`, data instanceof Blob ? await data.arrayBuffer() : data);
  }
  const requested = ['profile', 'layout_preset', 'layout_spec', 'style_preset', 'style_controls', 'style_bible'].filter(key => key in project);
  const preset = PUBLICATION_PRESETS[(form.publication ?? defaultPublication).publicationPreset];
  root.file('TASK.md', `# Publishing task\n\n## Title\n${form.title}\n\n## Goal\n${form.description}\n\n## Target readers\n${form.targetReaders}\n\n## Language\n${form.language}\n\n## Expected scale\nApproximately ${form.targetPages} pages. This is a planning guide, not a fixed PDF page count.\n\n## Provided sources\n${names.map((n, i) => '- ' + (form.architecture ? filePath(files[i], n) : 'input/sources/' + n)).join('\n') || '(No uploaded files)'}\n\n### URLs\n${urlLines(form.urls).join('\n') || '(No URLs)'}\n\n## Research policy\n${JSON.stringify(form.research, null, 2)}\nIf additional web research is disabled, use only provided files and explicitly supplied URLs. Do not discover additional sources.\n\n## Requested outputs\n${Object.entries(project.outputs).filter(([, v]) => v).map(([key]) => '- ' + key).join('\n')}\n\n## Publication format\n${requested.length ? 'Requested in project.json (' + requested.join(', ') + ')' + (preset ? ', starting from the WebUI publication preset "' + preset.label + '"' : '') + '. BookOrder resolves it into plan/profile.resolved.yaml, plan/layout-spec.yaml and plan/style-bible.yaml; check it with `bookorder publication`.' : 'Theme defaults (no explicit publication request).'} Theme and typography: book.design.yaml.\n\n## Figure policy\n${JSON.stringify(form.figures, null, 2)}\n\n## Citations and bibliography\n${JSON.stringify(project.citations, null, 2)}\nHow the text cites and how the back matter lists are separate settings (docs/publication-architecture.md).\n\n${architectureTask(form, names, files)}## Additional user instructions (verbatim)\n${form.instructions}\n\n## Precedence of settings\nThe additional user instructions above are the book-specific instruction from the user. BookOrder repeats them verbatim in every task it prints; they are never replaced by a summary. From strongest to weakest:\n\n1. Invariants: factual accuracy, citation integrity, source provenance, safety, build validity and the requested outputs. No instruction waives them.\n2. Explicit user choices, each authoritative for what it states:\n   - the structured settings (project.json, book.design.yaml and the plan files resolved from them) for the fields they represent: scale, outputs, page size, layout and the design values selected in the WebUI;\n   - the additional user instructions for the editorial and semantic choices they state: voice and tone, distance to the reader, difficulty, explanation density, topics to cover or leave out, emphasis, cases, structure, what to show as figures or tables, and chapter apparatus such as summaries, exercises or counterarguments.\n3. Derived decisions: the resolved publication profile, Book Bible, outline and editorial plans, which must follow 1 and 2.\n4. BookOrder defaults and Skill heuristics (genre and tier defaults such as chapter summaries, device counts, balanced framing or teaching scaffolding), which fill only what the user left unspecified.\n\nDo not improve the book against the user's explicit intent. A genre preset does not outrank the instructions: with the Medical preset and \"no routine chapter-end summaries\" in the instructions, the chapters get no routine summary. A structured setting does: if the WebUI selects A5 and the instructions ask for A4, the book stays A5. If an instruction cannot be followed (it conflicts with an invariant or a structured setting, the sources do not support it, or it is technically impossible), do not ignore it silently: record the conflict in plan/user-intent.yaml and tell the user in your final report. See docs/user-intent.md.\n\n## How this job runs\nOne instruction runs the whole publication. With Codex: \`/goal AGENTS.mdを読み、bookorder goal が STATUS: COMPLETE を表示するまで出版ジョブを最後まで実行してください。\` BookOrder's orchestrator (\`bookorder goal\`) owns every phase and alone decides completion; a built PDF is not a finished publication.\n`);
  for (const path of ['input/sources', 'input/assets', 'research', 'plan', 'source/manuscript', 'source/assets/figures', 'source/assets/images', 'source/assets/generated', 'source/metadata/chapters', 'interchange', 'publish', 'reports']) root.file(`${path}/.gitkeep`, '');
  root.file('source/references/references.bib', '% Add verified BibTeX records here.\n');
  for (const [file, key] of [['outline', 'chapters'], ['glossary', 'terms'], ['sources', 'sources'], ['figures', 'figures']]) root.file(`source/metadata/${file}.yaml`, `${key}: []\n`);
  return { filename: `${safeName(form.title.trim())}-${form.runtimeTarget === 'none' ? '' : form.runtimeTarget + '-'}publishing-job.zip`, data: await zip.generateAsync({ type: 'uint8array', platform: 'UNIX', streamFiles: true, compression: 'DEFLATE', compressionOptions: { level: 6 } }, meta => progress?.(Math.round(meta.percent))) };
}

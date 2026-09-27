import JSZip from 'jszip';
import type { RuntimeBundle, RuntimeTarget } from './runtime.ts';
import { defaultDesign, designSpec, type DesignOptions } from './design.ts';

export interface BookForm {
  title: string; description: string; targetReaders: string; language: string;
  targetPages: number; instructions: string; urls: string;
  runtimeTarget: RuntimeTarget;
  design: DesignOptions;
  research: { allow_web_research: boolean; prefer_primary_sources: boolean; keep_provenance: boolean; require_supplied_coverage: boolean };
  citationStyle: 'numeric' | 'author-year' | 'note';
  figures: { tables: boolean; diagrams: boolean; charts: boolean; generative_images: boolean };
  outputs: { canonical_markdown: true; docx: boolean; semantic_html: boolean; pdf: boolean; static_site: boolean; epub: boolean };
}
export const defaults: BookForm = {
  title: '', description: '', targetReaders: '', language: 'ja', targetPages: 150, instructions: '', urls: '', runtimeTarget: 'windows-x64',
  design: structuredClone(defaultDesign),
  research: { allow_web_research: true, prefer_primary_sources: true, keep_provenance: true, require_supplied_coverage: true },
  citationStyle: 'numeric',
  figures: { tables: true, diagrams: true, charts: true, generative_images: false },
  outputs: { canonical_markdown: true, docx: true, semantic_html: true, pdf: true, static_site: true, epub: false },
};
export interface SourceFile { name: string; data: Blob | Uint8Array; size: number }

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
  urlLines(form.urls).forEach((url, i) => {
    try { if (!['http:', 'https:'].includes(new URL(url).protocol)) throw Error(); }
    catch { errors.push(`参考URLの${i + 1}行目に有効なHTTP / HTTPS URLを入力してください。`); }
  });
  return errors;
}
export function projectData(form: BookForm, names: string[], files: SourceFile[]) {
  const languageNames: Record<string, string> = { japanese: 'ja', '日本語': 'ja', english: 'en', '英語': 'en', chinese: 'zh', korean: 'ko', french: 'fr', german: 'de', spanish: 'es' };
  const language = languageNames[form.language.trim().toLowerCase()] ?? form.language.trim();
  return {
    format: 'portable-publishing-job', format_version: '0.2',
    book: { title: form.title.trim(), description: form.description, target_readers: form.targetReaders, target_pages: form.targetPages, language },
    user_instructions: form.instructions, research: form.research, figures: form.figures, citations: { style: form.citationStyle },
    outputs: { ...form.outputs, canonical_markdown: true },
    runtime: { target: form.runtimeTarget, bundled: form.runtimeTarget !== 'none' },
    design: { spec: 'book.design.yaml', theme: form.design.theme, custom_css: 'custom.css' },
    input: { urls: urlLines(form.urls), sources: names.map((name, i) => ({ original_name: files[i].name, path: `input/sources/${name}`, size_bytes: files[i].size })) },
  };
}
export async function generateJob(form: BookForm, files: SourceFile[], templates: Record<string, string | Uint8Array>, progress?: (percent: number) => void, runtime?: RuntimeBundle) {
  const errors = validateForm(form); if (errors.length) throw new Error(errors.join('\n'));
  const zip = new JSZip(); const root = zip.folder('publishing-job')!;
  if (form.runtimeTarget !== 'none' && (!runtime || runtime.target !== form.runtimeTarget)) throw new Error('選択したOSの実行環境を読み込めていません。');
  for (const [path, text] of Object.entries(templates)) {
    if (path.split('/').includes('__pycache__') || path.endsWith('.pyc')) continue;
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
  const names = uniqueNames(files); const project = projectData(form, names, files);
  root.file('project.json', JSON.stringify(project, null, 2) + '\n');
  root.file('book.design.yaml', JSON.stringify(designSpec(form.design), null, 2) + '\n');
  root.file('custom.css', form.design.customCss + '\n');
  root.file('input/urls.txt', urlLines(form.urls).join('\n') + '\n');
  for (let i = 0; i < files.length; i++) {
    const data = files[i].data;
    root.file(`input/sources/${names[i]}`, data instanceof Blob ? await data.arrayBuffer() : data);
  }
  root.file('TASK.md', `# Publishing task\n\n## Title\n${form.title}\n\n## Goal\n${form.description}\n\n## Target readers\n${form.targetReaders}\n\n## Language\n${form.language}\n\n## Expected scale\nApproximately ${form.targetPages} pages. This is a planning guide, not a fixed PDF page count.\n\n## Provided sources\n${names.map(n => '- input/sources/' + n).join('\n') || '(No uploaded files)'}\n\n### URLs\n${urlLines(form.urls).join('\n') || '(No URLs)'}\n\n## Research policy\n${JSON.stringify(form.research, null, 2)}\nIf additional web research is disabled, use only provided files and explicitly supplied URLs. Do not discover additional sources.\n\n## Requested outputs\n${Object.entries(project.outputs).filter(([, v]) => v).map(([key]) => '- ' + key).join('\n')}\n\n## Figure policy\n${JSON.stringify(form.figures, null, 2)}\n\n## Additional user instructions (verbatim)\n${form.instructions}\n\n## How this job runs\nOne instruction runs the whole publication. With Codex: \`/goal AGENTS.mdを読み、bookorder goal が STATUS: COMPLETE を表示するまで出版ジョブを最後まで実行してください。\` BookOrder's orchestrator (\`bookorder goal\`) owns every phase and alone decides completion; a built PDF is not a finished publication.\n`);
  for (const path of ['input/sources', 'research', 'plan', 'source/manuscript', 'source/assets/figures', 'source/assets/images', 'source/assets/generated', 'source/metadata/chapters', 'interchange', 'publish', 'reports']) root.file(`${path}/.gitkeep`, '');
  root.file('source/references/references.bib', '% Add verified BibTeX records here.\n');
  for (const [file, key] of [['outline', 'chapters'], ['glossary', 'terms'], ['sources', 'sources'], ['figures', 'figures']]) root.file(`source/metadata/${file}.yaml`, `${key}: []\n`);
  return { filename: `${safeName(form.title.trim())}-${form.runtimeTarget === 'none' ? '' : form.runtimeTarget + '-'}publishing-job.zip`, data: await zip.generateAsync({ type: 'uint8array', platform: 'UNIX', streamFiles: true, compression: 'DEFLATE', compressionOptions: { level: 6 } }, meta => progress?.(Math.round(meta.percent))) };
}

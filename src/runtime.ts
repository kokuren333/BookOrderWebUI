import JSZip from 'jszip';

export const runtimeTargets = [
  { id: 'windows-x64', label: 'Windows 10以降 · x64' },
  { id: 'macos-arm64', label: 'macOS 15以降 · Apple Silicon' },
  { id: 'macos-x64', label: 'macOS 15以降 · Intel' },
  { id: 'linux-x64', label: 'Linux · x64 (glibc 2.17以降)' },
  { id: 'linux-arm64', label: 'Linux · ARM64 (glibc 2.17以降)' },
] as const;
export type RuntimeTarget = typeof runtimeTargets[number]['id'] | 'none';
interface Pack { bytes: number; sha256: string; parts: {file: string; bytes: number; sha256: string}[] }
export interface RuntimeCatalog { format_version: '1'; shared: Pack; platforms: {id: string; label: string; pack: Pack}[] }
export interface RuntimeBundle { target: RuntimeTarget; files: Record<string, Uint8Array> }

const packCache = new Map<string, Promise<Record<string, Uint8Array>>>();
async function hash(data: Uint8Array) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', data as BufferSource))).map(x => x.toString(16).padStart(2, '0')).join('');
}
function relativePart(file: string) {
  if (!/^[a-z0-9-]+\.\d{3}\.bin$/.test(file)) throw new Error('実行環境カタログのファイル名が不正です。');
  return file;
}
export async function runtimeCatalog(base: string, fetcher: typeof fetch = fetch): Promise<RuntimeCatalog> {
  const response = await fetcher(base + 'runtimes/catalog.json', { credentials: 'omit' });
  if (!response.ok) throw new Error('実行環境が配置されていません。配布用ランタイムを準備してください。');
  const catalog = await response.json() as RuntimeCatalog;
  if (catalog.format_version !== '1' || !Array.isArray(catalog.platforms) || !catalog.shared?.parts?.length) throw new Error('実行環境カタログが不正です。');
  return catalog;
}
async function loadPack(base: string, pack: Pack, status: (text: string) => void, fetcher: typeof fetch) {
  const key = base + pack.sha256;
  if (!packCache.has(key)) {
    const pending = (async () => {
      const buffers: Uint8Array[] = []; let bytes = 0;
      for (const part of pack.parts) {
        status(`実行環境を読み込み中… ${Math.round(bytes / 1024 / 1024)} / ${Math.ceil(pack.bytes / 1024 / 1024)} MB`);
        const response = await fetcher(base + 'runtimes/' + relativePart(part.file), { credentials: 'omit' });
        if (!response.ok) throw new Error('実行環境のファイルを取得できませんでした。ZIPは生成していません。');
        const data = new Uint8Array(await response.arrayBuffer());
        if (data.length !== part.bytes || await hash(data) !== part.sha256) throw new Error('実行環境のチェックサムが一致しません。ZIPは生成していません。');
        buffers.push(data); bytes += data.length;
      }
      if (bytes !== pack.bytes) throw new Error('実行環境が不完全です。');
      const data = new Uint8Array(bytes); let offset = 0;
      for (const part of buffers) { data.set(part, offset); offset += part.length; }
      if (await hash(data) !== pack.sha256) throw new Error('実行環境全体のチェックサムが一致しません。');
      const zip = await JSZip.loadAsync(data);
      const files: Record<string, Uint8Array> = {};
      for (const [path, entry] of Object.entries(zip.files)) {
        if (entry.dir) continue;
        if (!/^(runtime|third-party)\//.test(path) || path.split('/').some(p => p === '..' || p === '.') || path.includes('\\') || path.includes(':') || entry.unsafeOriginalName !== path) throw new Error('実行環境のZIPに不正なパスがあります。');
        files[path] = await entry.async('uint8array');
      }
      return files;
    })();
    packCache.set(key, pending);
    pending.catch(() => packCache.delete(key));
  }
  return packCache.get(key)!;
}
export async function loadRuntime(target: RuntimeTarget, catalog: RuntimeCatalog, base: string, status: (text: string) => void, fetcher: typeof fetch = fetch): Promise<RuntimeBundle> {
  const platform = catalog.platforms.find(p => p.id === target);
  if (!platform) throw new Error('選択したOSの実行環境がありません。');
  const shared = await loadPack(base, catalog.shared, status, fetcher);
  const binaries = await loadPack(base, platform.pack, status, fetcher);
  const files = { ...shared, ...binaries };
  const manifest = JSON.parse(new TextDecoder().decode(files['runtime/manifest.json']));
  const mandatory = ['third-party/licenses/pandoc/COPYRIGHT', 'third-party/licenses/pandoc/GPL-2.0.md', 'third-party/licenses/typst/LICENSE', 'third-party/licenses/typst/NOTICE', 'third-party/licenses/noto-serif-cjk/LICENSE', 'runtime/fonts/NotoSerifCJKjp-Regular.otf', 'runtime/fonts/NotoSerifCJKjp-Bold.otf'];
  // Optional OFL font families (added in v0.2 packs) must travel with their licence.
  for (const [prefix, licence] of [['runtime/fonts/NotoSansJP-', 'third-party/licenses/noto-sans-jp/'], ['runtime/fonts/SourceSerif4-', 'third-party/licenses/source-serif-4/'], ['runtime/fonts/Inter-', 'third-party/licenses/inter/'], ['runtime/fonts/JetBrainsMono-', 'third-party/licenses/jetbrains-mono/']]) {
    if (Object.keys(files).some(path => path.startsWith(prefix)) && !Object.keys(files).some(path => path.startsWith(licence))) throw new Error('同梱フォントのライセンスが不足しています。');
  }
  if (manifest.format !== 'portable-publishing-runtime' || manifest.format_version !== '1' || manifest.target !== target || !files[manifest.source_manifest] || mandatory.some(path => !files[path]) || !Object.keys(files).some(path => path.startsWith(`third-party/licenses/${target}/python/`))) throw new Error('実行環境またはライセンス・ソース資料が不完全です。');
  if (!Array.isArray(manifest.artifacts) || manifest.artifacts.length !== 3 || new Set(manifest.artifacts.map((x: {component: string}) => x.component)).size !== 3 || !['python', 'pandoc', 'typst'].every(name => manifest.artifacts.some((x: {component: string}) => x.component === name))) throw new Error('実行環境の構成が不完全です。');
  const sources = JSON.parse(new TextDecoder().decode(files[manifest.source_manifest]));
  if (!Array.isArray(sources.sources) || sources.sources.length === 0 || sources.sources.some((x: {path: string}) => !files[x.path])) throw new Error('対応ソースが不完全です。');
  for (const item of manifest.artifacts) {
    if (!files[item.path] || await hash(files[item.path]) !== item.sha256) throw new Error('実行環境アーカイブのチェックサムが一致しません。');
  }
  files['runtime/target.txt'] = new TextEncoder().encode(target + '\n');
  files['runtime/python.sha256'] = new TextEncoder().encode(manifest.artifacts.find((x: {component: string}) => x.component === 'python').sha256 + '\n');
  return { target, files };
}

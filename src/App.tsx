import { useEffect, useRef, useState, type FormEvent } from 'react';
import { defaults, generateJob, uniqueNames, validateForm, type BookForm } from './job';
import { loadTemplates } from './templates';
import { loadRuntime, runtimeCatalog, runtimeTargets, type RuntimeCatalog, type RuntimeTarget } from './runtime';
import { InfoPages, type InfoPage } from './InfoPages';
import { DesignPanel } from './DesignPanel';

export default function App() {
  const currentPage = (): InfoPage => location.hash === '#contents' ? 'contents' : location.hash === '#safety' ? 'safety' : 'job';
  const [page, setPage] = useState<InfoPage>(currentPage);
  useEffect(() => { const change = () => { setPage(currentPage()); window.scrollTo(0, 0); }; window.addEventListener('hashchange', change); return () => window.removeEventListener('hashchange', change); }, []);
  const [form, setForm] = useState<BookForm>(structuredClone(defaults));
  const [scale, setScale] = useState('150');
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [errors, setErrors] = useState<string[]>([]);
  const [success, setSuccess] = useState('');
  const [catalog, setCatalog] = useState<RuntimeCatalog>();
  const [catalogError, setCatalogError] = useState('');
  const [stage, setStage] = useState('');
  useEffect(() => { let live = true; runtimeCatalog(import.meta.env.BASE_URL).then(value => { if (live) setCatalog(value); }).catch(error => { if (live) setCatalogError(error.message); }); return () => { live = false; }; }, []);
  const errorRef = useRef<HTMLDivElement>(null);
  const names = uniqueNames(files);
  function field<K extends keyof BookForm>(key: K, value: BookForm[K]) { setForm(prev => ({ ...prev, [key]: value })); setSuccess(''); }
  function addFiles(list: FileList | File[]) { setFiles(prev => [...prev, ...Array.from(list)]); setSuccess(''); }
  function removeFile(index: number) { setFiles(prev => prev.filter((_, i) => i !== index)); setSuccess(''); }
  function formatFileSize(bytes: number) { return bytes < 1024 * 1024 ? `${(bytes / 1024).toLocaleString('ja', { maximumFractionDigits: 1 })} KB` : `${(bytes / 1024 / 1024).toLocaleString('ja', { maximumFractionDigits: 1 })} MB`; }
  async function submit(event: FormEvent) {
    event.preventDefault(); setSuccess(''); const issues = validateForm(form); setErrors(issues);
    if (issues.length) { requestAnimationFrame(() => errorRef.current?.focus()); return; }
    setBusy(true); setProgress(0);
    try {
      let runtime;
      if (form.runtimeTarget !== 'none') {
        if (!catalog) throw new Error(catalogError || '実行環境一覧の読み込みを待ってください。');
        runtime = await loadRuntime(form.runtimeTarget, catalog, import.meta.env.BASE_URL, setStage);
      }
      setStage('ZIPを生成中');
      const result = await generateJob(form, files.map(file => ({ name: file.name, data: file, size: file.size })), await loadTemplates(), setProgress, runtime);
      const url = URL.createObjectURL(new Blob([result.data as BlobPart], { type: 'application/zip' }));
      const a = document.createElement('a'); a.href = url; a.download = result.filename; document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000); setSuccess(`${result.filename} を生成しました。ZIPをAgentに渡し、下記の指示を依頼してください。`);
    } catch (error) { setErrors([error instanceof Error ? error.message : 'ZIPの生成に失敗しました。']); }
    finally { setBusy(false); }
  }
  const toggles = (group: 'research' | 'figures' | 'outputs', labels: Record<string, string>) => Object.entries(labels).map(([key, label]) => (
    <label className="check" key={key}><input type="checkbox" checked={Boolean((form[group] as Record<string, boolean>)[key])} disabled={key === 'canonical_markdown'} onChange={e => field(group, { ...form[group], [key]: e.target.checked })} />{label}</label>
  ));
  return <main>
    <header><div className="wordmark">PORTABLE PUBLISHING <span>v0.2</span></div><h1>Publishing Job Generator</h1><p>書籍の企画と資料を、AI Agentに渡せる出版ジョブにまとめます。</p></header>
    <nav aria-label="ページ"><a href="#job" aria-current={page === 'job' ? 'page' : undefined}>ジョブ作成</a><a href="#contents" aria-current={page === 'contents' ? 'page' : undefined}>同梱物・ライセンス</a><a href="#safety" aria-current={page === 'safety' ? 'page' : undefined}>安全性・データの扱い</a></nav>
    <InfoPages page={page} />
    <form onSubmit={submit} noValidate hidden={page !== 'job'}>
      <fieldset disabled={busy} className="form-body">
        <section><div className="section-heading"><span>01</span><h2>書籍の企画</h2></div>
          <label>Book title <em>必須</em><input value={form.title} onChange={e => field('title', e.target.value)} placeholder="書籍のタイトル" required /></label>
          <label>Book description / goal <em>必須</em><textarea value={form.description} onChange={e => field('description', e.target.value)} placeholder="例：生成AIを臨床医向けに解説する、300ページ程度の専門書。何を伝え、読者が何をできるようになるか。" rows={4} required /></label>
          <label>Target readers <em>必須</em><textarea value={form.targetReaders} onChange={e => field('targetReaders', e.target.value)} placeholder="対象読者と前提知識" rows={2} required /></label>
          <div className="row"><label>Language<input value={form.language} onChange={e => field('language', e.target.value)} list="languages" required /><datalist id="languages"><option value="ja">Japanese</option><option value="en">English</option><option value="zh">Chinese</option><option value="ko">Korean</option></datalist><small>言語コードまたは言語名（初期値：日本語 / ja）</small></label>
          <label>Target scale<select value={scale} onChange={e => { setScale(e.target.value); if (e.target.value !== 'custom') field('targetPages', Number(e.target.value)); }}><option value="50">Short · 約50ページ</option><option value="150">Medium · 約150ページ</option><option value="300">Long · 約300ページ</option><option value="400">Very long · 約400ページ以上</option><option value="custom">Custom</option></select>{scale === 'custom' && <input aria-label="希望ページ数" type="number" min={1} max={10000} value={form.targetPages || ''} onChange={e => field('targetPages', Number(e.target.value))} />}<small>ページ数はAgentへの分量の目安です。</small></label></div>
        </section>
        <section><div className="section-heading"><span>02</span><h2>資料と追加指示</h2></div>
          <label>Reference URLs<textarea value={form.urls} onChange={e => field('urls', e.target.value)} placeholder="https://example.org/article\n1行に1つのURL" rows={3} /><small>ここではURLを取得しません。資料の調査はAgentが行います。</small></label>
          <div className={`dropzone ${dragging ? 'dragging' : ''}`} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); if (!busy) addFiles(e.dataTransfer.files); }}>
            <strong>参考資料をここにドロップ</strong><p>PDF / Markdown / DOCX / TXT / CSV / JSON / HTML ほか</p><label className="secondary file-picker">ファイルを選択<input type="file" multiple aria-label="参考資料を選択" onChange={e => { if (e.target.files) addFiles(e.target.files); e.target.value = ''; }} /></label>
          </div>
          <div className="attachment-heading"><strong>添付ファイル</strong><span aria-live="polite">{files.length}件 ・ {formatFileSize(files.reduce((total, file) => total + file.size, 0))}</span>{files.length > 0 && <button type="button" className="remove-all" onClick={() => { setFiles([]); setSuccess(''); }}>すべて削除</button>}</div>
          {files.length > 0 ? <ul className="files">{files.map((file, i) => <li key={`${file.name}-${i}`}><span className="file-name"><strong>{file.name}</strong><small>{file.type || 'ファイル'} ・ {formatFileSize(file.size)}{names[i] !== file.name && ` ・ ZIP内：${names[i]}`}</small></span><button type="button" className="remove" aria-label={`${file.name}を削除`} onClick={() => removeFile(i)}>削除</button></li>)}</ul> : <p className="empty-files">まだファイルは添付されていません。</p>}
          <p className="privacy">ファイルはブラウザ内でのみ処理し、生成するPublishing Job ZIPに含めます。サーバーには送信しません。</p>
          <label>Additional user instructions<textarea value={form.instructions} onChange={e => field('instructions', e.target.value)} placeholder="文体、難易度、扱う・扱わないテーマ、引用・調査方針、図表、デザインなど。原文をそのままTASK.mdへ保存します。" rows={5} /></label>
        </section>
        <section><div className="section-heading"><span>03</span><h2>調査と図表の方針</h2></div><div className="row"><div><h3>Research</h3>{toggles('research', { allow_web_research: '追加Web調査を許可', prefer_primary_sources: '一次資料・信頼できる資料を優先', keep_provenance: '出典と調査履歴を保存', require_supplied_coverage: '関連する提供資料をすべて本文に反映' })}<label>Citation style<select value={form.citationStyle} onChange={e => field('citationStyle', e.target.value as BookForm['citationStyle'])}><option value="numeric">番号式 [1]</option><option value="author-year">著者・年 (Smith 2024)</option><option value="note">脚注式</option></select></label></div><div><h3>Figures</h3>{toggles('figures', { tables: '必要に応じて表を作成', diagrams: '必要に応じて技術図を作成', charts: '必要に応じてグラフを作成', generative_images: '利用可能なら生成画像ツールを使用' })}</div></div><small>科学・技術図は、表・Mermaid・Graphviz・SVG・プログラムによる描画を優先します。</small></section>
        <section><div className="section-heading"><span>04</span><h2>希望する出力</h2></div><div className="outputs"><div><h3>Canonical source</h3>{toggles('outputs', { canonical_markdown: 'Markdown project（必須）' })}<small>章別原稿・メタデータ・文献・図版。<br />再編集するための正本です。</small></div><div><h3>Interchange</h3>{toggles('outputs', { docx: 'DOCX', semantic_html: 'Semantic HTML' })}<small>Word編集やDTPへの受け渡し。</small></div><div><h3>Publication</h3>{toggles('outputs', { pdf: 'PDF', static_site: 'Static website', epub: 'EPUB' })}<small>読者向けの完成出版物。</small></div></div></section>
        <DesignPanel value={form.design} onChange={value => field('design', value)} />
        <section><div className="section-heading"><span>06</span><h2>Agentが実行する環境</h2></div>
          <label>OS / CPU<select value={form.runtimeTarget} onChange={e => field('runtimeTarget', e.target.value as RuntimeTarget)}>{runtimeTargets.map(target => <option key={target.id} value={target.id}>{target.label}</option>)}<option value="none">同梱なし · 既存の実行環境を使用</option></select></label>
          {form.runtimeTarget !== 'none' ? <><p>Python・Pandoc・Typst・日本語フォントを同梱します。Agentが実行するマシンのOSとCPUを選んでください。</p><small>インストールや追加ダウンロードは不要です。対応ソース・ライセンス通知もZIPに含めます。Linuxはglibc 2.17以降が対象です。</small>{catalog && <small>同梱データ：約{Math.ceil((catalog.shared.bytes + (catalog.platforms.find(p => p.id === form.runtimeTarget)?.pack.bytes || 0)) / 1024 / 1024)} MB（ダウンロードZIPは圧縮されます）</small>}{!catalog && <p role="status">{catalogError || '実行環境一覧を読み込み中…'}</p>}</> : <small>Agent側にPython・Pandoc・Typstが必要です。</small>}
        </section>
      </fieldset>
      {errors.length > 0 && <div className="error" role="alert" tabIndex={-1} ref={errorRef}>{errors.map(error => <p key={error}>{error}</p>)}</div>}
      <p className="download-info">ダウンロード前に <a href="#contents">同梱物・ライセンス</a> と <a href="#safety">安全性・データの扱い</a> を確認できます。</p>
      <div className="generate"><div><strong>出版ジョブをダウンロード</strong><p>Agentの実行は、この画面では行いません。</p>{busy && <small role="status">{stage}</small>}</div><button type="submit" disabled={busy}>{busy ? (stage === 'ZIPを生成中' ? `ZIPを生成中… ${progress}%` : '実行環境を準備中…') : 'Generate Publishing Job'}</button></div>
      {success && <div className="success" role="status"><p>{success}</p><code>/goal AGENTS.mdを読み、bookorder goal が STATUS: COMPLETE を表示するまで出版ジョブを最後まで実行してください。</code><small>Codexでは /goal で1回指示するだけです。他のAgentでは同じ文をそのまま依頼してください。途中の「続けて」は不要です。</small></div>}
    </form>
    <footer>ZIPを展開 → Codex / Claude Code / Gemini CLI等で開く → /goal で1回指示 → BookOrderが全工程を管理 → publish/result.zipを受け取る</footer>
  </main>;
}

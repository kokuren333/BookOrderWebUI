import { useEffect, useRef, useState, type FormEvent } from 'react';
import { defaults, generateJob, uniqueNames, validateForm, type BookForm } from './job';
import { loadTemplates } from './templates';
import { loadRuntime, runtimeCatalog, runtimeTargets, type RuntimeCatalog, type RuntimeTarget } from './runtime';
import { InfoPages, type InfoPage } from './InfoPages';
import { PublicationPanel, TierOverride } from './PublicationPanel';
import { ArchitectureSection, CitationControls, FileRoles, UiModeSwitch } from './ArchitecturePanel';
import { inferUsage, type FileUsage } from './architecture';

export default function App() {
  const currentPage = (): InfoPage => location.hash === '#contents' ? 'contents' : location.hash === '#safety' ? 'safety' : 'job';
  const [page, setPage] = useState<InfoPage>(currentPage);
  useEffect(() => { const change = () => { setPage(currentPage()); window.scrollTo(0, 0); }; window.addEventListener('hashchange', change); return () => window.removeEventListener('hashchange', change); }, []);
  const [form, setForm] = useState<BookForm>(structuredClone(defaults));
  const [scale, setScale] = useState('150');
  const [files, setFiles] = useState<File[]>([]);
  const [usages, setUsages] = useState<FileUsage[]>([]);  // per-file role metadata, parallel to files (estimated until edited)
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
  // Snapshot first: an input's FileList is live and is emptied when the input is reset below, before React runs the updater.
  function addFiles(list: FileList | File[]) { const selected = Array.from(list); if (!selected.length) return; setFiles(prev => [...prev, ...selected]); setUsages(prev => [...prev, ...selected.map(file => inferUsage(file.name, file.type))]); setSuccess(''); }
  function removeFile(index: number) { setFiles(prev => prev.filter((_, i) => i !== index)); setUsages(prev => prev.filter((_, i) => i !== index)); setSuccess(''); }
  function setUsage(index: number, usage: FileUsage) { setUsages(prev => prev.map((value, i) => i === index ? usage : value)); setSuccess(''); }
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
      const result = await generateJob(form, files.map((file, i) => ({ name: file.name, data: file, size: file.size, type: file.type, usage: usages[i] })), await loadTemplates(), setProgress, runtime);
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
        <UiModeSwitch mode={form.uiMode} onChange={mode => field('uiMode', mode)} />
        <section><div className="section-heading"><span>01</span><h2>本の企画</h2></div>
          <label>Book title <em>必須</em><input value={form.title} onChange={e => field('title', e.target.value)} placeholder="書籍のタイトル" required /></label>
          <label>Book description / goal <em>必須</em><textarea value={form.description} onChange={e => field('description', e.target.value)} placeholder="例：生成AIを臨床医向けに解説する、300ページ程度の専門書。何を伝え、読者が何をできるようになるか。" rows={4} required /></label>
          <label>Target readers <em>必須</em><textarea value={form.targetReaders} onChange={e => field('targetReaders', e.target.value)} placeholder="対象読者と前提知識" rows={2} required /></label>
          <div className="row"><label>Language<input value={form.language} onChange={e => field('language', e.target.value)} list="languages" required /><datalist id="languages"><option value="ja">Japanese</option><option value="en">English</option><option value="zh">Chinese</option><option value="ko">Korean</option></datalist><small>言語コードまたは言語名（初期値：日本語 / ja）</small></label>
          <label>Target scale<select value={scale} onChange={e => { setScale(e.target.value); if (e.target.value !== 'custom') field('targetPages', Number(e.target.value)); }}><option value="50">Short · 約50ページ</option><option value="150">Medium · 約150ページ</option><option value="300">Long · 約300ページ</option><option value="400">Very long · 約400ページ以上</option><option value="custom">Custom</option></select>{scale === 'custom' && <input aria-label="希望ページ数" type="number" min={1} max={10000} value={form.targetPages || ''} onChange={e => field('targetPages', Number(e.target.value))} />}<small>本の規模はここで決めます。ページ数はAgentへの分量の目安で、分量ティアはここから自動で決まります。</small></label></div>
          <TierOverride publication={form.publication} targetPages={form.targetPages} onChange={value => field('publication', value)} />
        </section>
        <section><div className="section-heading"><span>02</span><h2>資料と指示</h2></div>
          <label>Reference URLs<textarea value={form.urls} onChange={e => field('urls', e.target.value)} placeholder="https://example.org/article\n1行に1つのURL" rows={3} /><small>ここではURLを取得しません。資料の調査はAgentが行います。</small></label>
          <div className={`dropzone ${dragging ? 'dragging' : ''}`} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); if (!busy) addFiles(e.dataTransfer.files); }}>
            <strong>参考資料をここにドロップ</strong><p>PDF / Markdown / DOCX / TXT / CSV / JSON / HTML ほか</p><input className="file-picker" type="file" multiple aria-label="参考資料を選択" onChange={e => { if (e.target.files) addFiles(e.target.files); e.target.value = ''; }} />
          </div>
          <div className="attachment-heading"><strong>添付ファイル</strong><span aria-live="polite">{files.length}件 ・ {formatFileSize(files.reduce((total, file) => total + file.size, 0))}</span>{files.length > 0 && <button type="button" className="remove-all" onClick={() => { setFiles([]); setUsages([]); setSuccess(''); }}>すべて削除</button>}</div>
          {files.length > 0 ? <><FileRoles files={files} usages={usages} names={names} uiMode={form.uiMode} onChange={setUsage} onRemove={removeFile} />
            <small>資料はすべて同じ「ソース」ではありません。根拠資料（引用可）・背景資料（参考資料として掲載、事実の根拠にはしない）・レイアウト参考（内容としては読まない）・素材・再作図元などの役割を選べます。「推定」はファイル名からの推定で、未指定の役割はAgentがコーパス分析で見直します。</small></>
            : <p className="empty-files">まだファイルは添付されていません。</p>}
          <p className="privacy">ファイルはブラウザ内でのみ処理し、生成するPublishing Job ZIPに含めます。サーバーには送信しません。</p>
          <label>Additional user instructions — 本全体への優先指示<textarea value={form.instructions} onChange={e => field('instructions', e.target.value)} placeholder="文体・語り口、説明の濃さ、難易度、章構成、扱う／扱わないテーマ、重点を置く論点、取り上げる事例、図表で示す内容、「教科書的にしない」「章末まとめは付けない」など、この本固有の希望を書いてください。" rows={6} /><small>この欄は本全体に対する優先指示です。入力内容は原文のまま保存され、調査・構成・執筆・編集・デザイン・最終確認の各工程でAgentへ毎回そのまま渡されます。文体、説明の濃さ、扱う／扱わない内容、構成、事例などは、BookOrderの既定方針（章末まとめ・反論の併記・教科書的な補助要素など）よりこの指示を優先します。</small><small>ただし、この画面で選んだ規模・出力・判型・レイアウト・デザインの設定と、引用・事実性・安全性・ビルドの成立に関する必須条件は上書きしません。矛盾する場合は黙って無視せず、最終レポートに記録します。</small></label>
        </section>
        <ArchitectureSection value={form.architecture} uiMode={form.uiMode} intentText={`${form.instructions}\n${form.description}`} onChange={value => field('architecture', value)} />
        <section hidden={form.uiMode === 'quick'}><div className="section-heading"><span>04</span><h2>調査・引用・参考文献</h2></div><div className="row"><div><h3>Research</h3>{toggles('research', { allow_web_research: '追加Web調査を許可', prefer_primary_sources: '一次資料・信頼できる資料を優先', keep_provenance: '出典と調査履歴を保存', require_supplied_coverage: '関連する提供資料をすべて本文に反映' })}</div><div><h3>Visual content</h3>{toggles('figures', { tables: '必要に応じて表を作成', diagrams: '必要に応じて技術図を作成', charts: '必要に応じてグラフを作成', generative_images: '利用可能なら生成画像ツールを使用' })}</div></div><h3>Citations &amp; bibliography</h3><CitationControls inText={form.citationStyle} value={form.bibliography} onInText={value => field('citationStyle', value)} onChange={value => field('bibliography', value)} /><small>ここでは「作ってよいか」だけを決めます。配置（段抜き）と見た目は「06 出版形式とデザイン」で設定します。科学・技術図は、表・Mermaid・Graphviz・SVG・プログラムによる描画を優先します。</small></section>
        <section><div className="section-heading"><span>05</span><h2>希望する出力</h2></div><div className="outputs"><div><h3>Canonical source</h3>{toggles('outputs', { canonical_markdown: 'Markdown project（必須）' })}<small>章別原稿・メタデータ・文献・図版。<br />再編集するための正本です。</small></div><div><h3>Interchange</h3>{toggles('outputs', { docx: 'DOCX', semantic_html: 'Semantic HTML' })}<small>Word編集やDTPへの受け渡し。</small></div><div><h3>Publication</h3>{toggles('outputs', { pdf: 'PDF', static_site: 'Static website', epub: 'EPUB' })}<small>読者向けの完成出版物。</small></div></div></section>
        <div hidden={form.uiMode === 'quick'}><PublicationPanel publication={form.publication} design={form.design} targetPages={form.targetPages} outputs={form.outputs}
          onChange={next => { setForm(prev => ({ ...prev, ...(next.publication ? { publication: next.publication } : {}), ...(next.design ? { design: next.design } : {}) })); setSuccess(''); }} /></div>
        {form.uiMode === 'quick' && <p className="quick-mode-note">判型・デザイン・引用形式・調査方針は既定値を使います（Advanced publishing で変更できます）。</p>}
        <section><div className="section-heading"><span>07</span><h2>Agentが実行する環境</h2></div>
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

import { useState } from 'react';
// Intent-driven publication architecture in the WebUI:
//   ArchitectureSection  — structure mode (AUTO / GUIDED / FIXED), publication type, block / exercise / visual / evidence policy
//   FileRoles            — per-file role, authority, citation, intended chapter/section, asset flags and free instruction
//   CitationControls     — in-text citation form separate from bibliography style, numbering and grouping
// Quick mode shows only what is needed to run (roles are estimated and editable, the design is AUTO); Advanced mode
// exposes every setting behind progressive disclosure. Vocabulary: src/architecture.ts (shared JSON with the job).
import {
  applyBulk, applyQuickUse, ARCHETYPES, URL_ROLES, ASSET_ROLES, AUTHORITY, BLOCK_IDS, BLOCKS, CITATIONS, detectSignals, EXERCISE_POLICIES, isImage, QUICK_USES, quickUseOf,
  signalText, SOURCE_ROLES, STRUCTURE_MODES, VISUAL_DENSITIES, VISUAL_TYPES,
  type ArchitectureOptions, type BlockState, type CitationOptions, type FileUsage, type StructureMode, type UiMode,
} from './architecture';

export function UiModeSwitch({ mode, onChange }: { mode: UiMode; onChange: (mode: UiMode) => void }) {
  return <div className="ui-mode"><div className="segmented" role="tablist" aria-label="入力モード">
    {(['quick', 'advanced'] as UiMode[]).map(id => <button type="button" role="tab" key={id} aria-selected={mode === id} className={mode === id ? 'active' : ''}
      onClick={() => onChange(id)}>{id === 'quick' ? 'Quick' : 'Advanced publishing'}</button>)}</div>
    <small>{mode === 'quick' ? 'Quick：テーマ・意図・資料・分量・出力だけで作成できます。構成・図表・引用はAgentが意図から設計し、資料の役割は推定します（下で修正できます）。'
      : 'Advanced：出版物タイプ、ブロック方針、図表方針、資料の役割、根拠方針、引用・参考文献、レイアウト参考までを指定できます。'}</small></div>;
}

function Multi({ label, options, value, onChange }: { label: string; options: [string, string][]; value: string[]; onChange: (v: string[]) => void }) {
  return <fieldset className="multi"><legend>{label}</legend><div className="chips">{options.map(([id, text]) =>
    <label className="check chip" key={id}><input type="checkbox" checked={value.includes(id)} onChange={e => onChange(e.target.checked ? [...value, id] : value.filter(x => x !== id))} />{text}</label>)}</div></fieldset>;
}

export function ArchitectureSection({ value, uiMode, intentText, onChange }: { value: ArchitectureOptions; uiMode: UiMode; intentText: string; onChange: (v: ArchitectureOptions) => void }) {
  const set = <K extends keyof ArchitectureOptions>(key: K, v: ArchitectureOptions[K]) => onChange({ ...value, [key]: v });
  const signals = detectSignals(intentText);
  const archetype = value.archetype !== 'auto' ? ARCHETYPES[value.archetype] : undefined;
  const setBlock = (block: string, state: BlockState | '') => { const blocks = { ...value.blocks }; if (state) blocks[block] = state; else delete blocks[block]; set('blocks', blocks); };
  return <section className="architecture"><div className="section-heading"><span>03</span><h2>出版物の設計</h2></div>
    <p className="lead-note">BookOrderは「固定テンプレートへ本文を流し込む」のではなく、意図・目的・資料の役割から、章ごとの構成・ブロック・図表・引用を設計します。
      まとめ・演習・コラムなどは全章に機械的に入れず、必要な章にだけ使います。</p>
    <div className="signals" aria-live="polite"><strong>指示から読み取った明示的な希望</strong>{signals.length
      ? <ul>{signals.map(s => <li key={s.id}>「{s.quote}」 → {signalText(s.effect)}</li>)}</ul>
      : <small>「章末問題はいらない」「ケースを多く」「図表を多く」「固すぎない」などを書くと、構成方針に必ず反映されます。</small>}</div>
    {uiMode === 'quick' ? <p className="quick-mode-note"><strong>構成モード：{STRUCTURE_MODES[value.mode].label}</strong> — {STRUCTURE_MODES[value.mode].description_ja}</p> : <>
      <div className="field-block"><span className="label">Structure mode — 構成モード</span><div className="segmented" role="group" aria-label="構成モード">{(Object.keys(STRUCTURE_MODES) as StructureMode[]).map(id =>
        <button type="button" key={id} className={value.mode === id ? 'active' : ''} aria-pressed={value.mode === id} onClick={() => set('mode', id)}>{STRUCTURE_MODES[id].label}</button>)}</div>
        <small>{STRUCTURE_MODES[value.mode].description_ja}</small></div>
      <div className="row">
        <label>Publication type — 出版物タイプ<select value={value.archetype} onChange={e => set('archetype', e.target.value)}>
          <option value="auto">{value.mode === 'guided' ? '選択してください' : '自動（意図から推定）'}</option>{Object.entries(ARCHETYPES).map(([id, a]) => <option key={id} value={id}>{a.label} · {a.en}</option>)}</select>
          {archetype && <small>既定で重視：{archetype.preferred_blocks.map(b => BLOCKS[b]?.label ?? b).join('・')}／控える：{archetype.discouraged_blocks.map(b => BLOCKS[b]?.label ?? b).join('・') || 'なし'}</small>}</label>
        <label>Secondary type — 副タイプ（複合型）<select value={value.secondaryArchetype} onChange={e => set('secondaryArchetype', e.target.value)}>
          <option value="">なし</option>{Object.entries(ARCHETYPES).map(([id, a]) => <option key={id} value={id}>{a.label} · {a.en}</option>)}</select>
          <small>例：主＝実務ガイド、副＝入門教科書</small></label>
      </div>
      <label>出版物タイプの補足（自由記述）<input value={value.archetypeNote} onChange={e => set('archetypeNote', e.target.value)} placeholder="例：新人看護師が病棟で手元に置く実務書。基礎知識の章だけは教科書的に。" /></label>
      <div className="row">
        <label>Exercise policy — 問題・演習<select value={value.exercisePolicy} onChange={e => set('exercisePolicy', e.target.value)}>
          <option value="auto">自動（出版物タイプと意図から）</option>{Object.entries(EXERCISE_POLICIES).map(([id, text]) => <option key={id} value={id}>{id} — {text}</option>)}</select>
          <small>問題を入れる場合は必ず解答・解説が付きます。</small></label>
        <label>Visual density — 図表の密度<select value={value.visualDensity} onChange={e => set('visualDensity', e.target.value)}>
          <option value="auto">自動</option>{VISUAL_DENSITIES.map(id => <option key={id} value={id}>{id}</option>)}</select></label>
      </div>
      <details><summary>Block policy — ブロックごとの方針（未指定は出版物タイプに従う）</summary>
        <div className="block-grid">{BLOCK_IDS.map(id => <label key={id} className="block-row"><span>{BLOCKS[id].label}<code>{id}</code></span>
          <select value={value.blocks[id] ?? ''} aria-label={`${BLOCKS[id].label}の方針`} onChange={e => setBlock(id, e.target.value as BlockState | '')}>
            <option value="">自動</option><option value="preferred">重視</option><option value="discouraged">控える</option><option value="forbidden">使わない</option></select></label>)}</div>
        <small>「使わない」は全工程で禁止として扱われ、エージェントが再追加できません。GUIDEDでは「重視」も制約になります。</small></details>
      <details><summary>Visual policy — 図表の種類</summary>
        <Multi label="使いたい図表タイプ" options={Object.entries(VISUAL_TYPES).map(([id, t]) => [id, t.label])} value={value.visualPreferred} onChange={v => set('visualPreferred', v)} />
        <Multi label="避けたい図表タイプ" options={Object.entries(VISUAL_TYPES).map(([id, t]) => [id, t.label])} value={value.visualAvoid} onChange={v => set('visualAvoid', v)} />
        <small>図は装飾ではなく、章の計画時に「何を見せるべきか」から決めます。同じ種類の図ばかりにならないようQAで確認します。</small></details>
      <details><summary>Chapter architecture · Evidence policy · Layout strategy</summary>
        <label>章構成の方針（自由記述）<textarea rows={3} value={value.chapterArchitecture} onChange={e => set('chapterArchitecture', e.target.value)} placeholder="例：第1章は導入と全体像、第2章は時系列と業務フロー、第6章は急変時アルゴリズムと報告例、第7章は比較表とチェックリスト。" /></label>
        <div className="row"><label>Evidence priority — 根拠の厳密さ<select value={value.evidencePriority} onChange={e => set('evidencePriority', e.target.value)}>
          <option value="auto">自動</option>{['low', 'medium', 'high', 'strict'].map(id => <option key={id} value={id}>{id}</option>)}</select></label>
          <label>語り口・トーン<input value={value.tone} onChange={e => set('tone', e.target.value)} placeholder="例：固すぎない、先輩が隣で教える口調" /></label></div>
        <Multi label="事実・推奨の根拠として優先する資料" options={Object.entries(AUTHORITY).filter(([id]) => id !== 'unknown').map(([id, a]) => [id, a.label])} value={value.preferredAuthority} onChange={v => set('preferredAuthority', v)} />
        <label>根拠方針（自由記述）<input value={value.evidenceNote} onChange={e => set('evidenceNote', e.target.value)} placeholder="例：医学的推奨はガイドライン・行政資料・査読論文を優先。現場の困りごとの紹介には経験記事も可。" /></label>
        <label>レイアウト方針（自由記述）<input value={value.layoutStrategy} onChange={e => set('layoutStrategy', e.target.value)} placeholder="例：見開きで完結する構成、手順は左ページに大きく" /></label>
      </details>
    </>}
  </section>;
}

/** Shared by files and URLs: the role select with its 「推定」 marker and the role's meaning. */
export function RoleSelect({ usage, name, roles, labels, onChange }: { usage: FileUsage; name: string; roles?: readonly string[]; labels?: Record<string, string>; onChange: (role: string) => void }) {
  const role = SOURCE_ROLES[usage.role];
  return <div className="role-line">
    <label className="compact">役割{usage.roleOrigin === 'inferred' && <span className="badge" title="名前・アドレスからの推定です。変更できます。">推定</span>}
      <select value={usage.role} aria-label={`${name}の役割`} onChange={e => onChange(e.target.value)}>
        {(roles ?? Object.keys(SOURCE_ROLES)).map(id => <option key={id} value={id}>{labels?.[id] ?? SOURCE_ROLES[id].label}（{id}）</option>)}</select></label>
    <small className="role-help">{role?.description_ja}</small>
  </div>;
}

/** Shared by files, URLs and the bulk editor: authority, citation, chapter, intended usage and notes. */
export function SourceUsageFields({ usage, set, notesLabel = '自由記述 / notes', notesPlaceholder }: { usage: FileUsage; set: (patch: Partial<FileUsage>) => void; notesLabel?: string; notesPlaceholder?: string }) {
  return <>
    <div className="row">
      <label>Authority — 資料の種類・権威性<select value={usage.authority} onChange={e => set({ authority: e.target.value })}>{Object.entries(AUTHORITY).map(([id, a]) => <option key={id} value={id}>{a.label}</option>)}</select></label>
      <label>本文での引用<select value={usage.citationAllowed} onChange={e => set({ citationAllowed: e.target.value as FileUsage['citationAllowed'] })}>
        <option value="auto">役割に従う</option><option value="yes">引用可</option><option value="no">引用しない</option></select></label>
    </div>
    <div className="row">
      <label>使う章（例：第2章）<input value={usage.intendedChapter} onChange={e => set({ intendedChapter: e.target.value })} /></label>
      <label>用途（intended usage）<input value={usage.intendedUsage} onChange={e => set({ intendedUsage: e.target.value })} placeholder="例：第3章の数値の根拠" /></label>
    </div>
    <label>{notesLabel}<textarea rows={2} value={usage.notes} onChange={e => set({ notes: e.target.value })} placeholder={notesPlaceholder} /></label>
  </>;
}

const URL_ROLE_LABEL: Record<string, string> = { evidence: '根拠・引用資料', background: '執筆時の参考', further_reading: '読者向け参考資料', structure_reference: '構成参考', layout_reference: 'レイアウト参考', visual_reference: '図解参考' };

/** Pasted URLs expanded into cards: estimated roles, per-URL settings, and bulk editing of selected URLs. */
export function UrlRoles({ urls, usageOf, uiMode, onChange }: { urls: string[]; usageOf: (url: string) => FileUsage; uiMode: UiMode;
  onChange: (next: Record<string, FileUsage>) => void }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [bulk, setBulk] = useState<{ role: string; authority: string; citationAllowed: string; intendedChapter: string; intendedUsage: string }>({ role: '', authority: '', citationAllowed: '', intendedChapter: '', intendedUsage: '' });
  if (!urls.length) return null;
  const current = Object.fromEntries(urls.map(url => [url, usageOf(url)])) as Record<string, FileUsage>;
  const live = selected.filter(url => urls.includes(url));
  const applyToSelected = () => {
    const patch: Partial<FileUsage> = {};
    if (bulk.role) patch.role = bulk.role;
    if (bulk.authority) patch.authority = bulk.authority;
    if (bulk.citationAllowed) patch.citationAllowed = bulk.citationAllowed as FileUsage['citationAllowed'];
    if (bulk.intendedChapter) patch.intendedChapter = bulk.intendedChapter;
    if (bulk.intendedUsage) patch.intendedUsage = bulk.intendedUsage;
    if (Object.keys(patch).length && live.length) onChange(applyBulk(current, live, patch));
  };
  const estimated = urls.filter(url => current[url].roleOrigin === 'inferred').length;
  return <div className="url-roles">
    <div className="attachment-heading"><strong>URL（{urls.length}件）</strong><span>{estimated ? `${estimated}件は推定のまま` : 'すべて指定済み'}</span>
      <label className="check chip"><input type="checkbox" aria-label="すべてのURLを選択" checked={live.length === urls.length} onChange={e => setSelected(e.target.checked ? [...urls] : [])} />すべて選択</label></div>
    {live.length > 0 && <div className="bulk-edit" role="group" aria-label="選択したURLを一括編集">
      <strong>{live.length}件を一括編集</strong>
      <select aria-label="一括：役割" value={bulk.role} onChange={e => setBulk({ ...bulk, role: e.target.value })}><option value="">役割（変更しない）</option>{URL_ROLES.map(id => <option key={id} value={id}>{URL_ROLE_LABEL[id]}</option>)}</select>
      <select aria-label="一括：Authority" value={bulk.authority} onChange={e => setBulk({ ...bulk, authority: e.target.value })}><option value="">Authority（変更しない）</option>{Object.entries(AUTHORITY).map(([id, a]) => <option key={id} value={id}>{a.label}</option>)}</select>
      <select aria-label="一括：本文での引用" value={bulk.citationAllowed} onChange={e => setBulk({ ...bulk, citationAllowed: e.target.value })}><option value="">引用（変更しない）</option><option value="auto">役割に従う</option><option value="yes">引用可</option><option value="no">引用しない</option></select>
      <input aria-label="一括：使う章" placeholder="使う章" value={bulk.intendedChapter} onChange={e => setBulk({ ...bulk, intendedChapter: e.target.value })} />
      <input aria-label="一括：用途" placeholder="用途" value={bulk.intendedUsage} onChange={e => setBulk({ ...bulk, intendedUsage: e.target.value })} />
      <button type="button" className="secondary" onClick={applyToSelected}>選択したURLに適用</button></div>}
    <ul className="files file-roles url-cards">{urls.map((url, i) => {
      const u = current[url]; const set = (patch: Partial<FileUsage>) => onChange({ ...current, [url]: { ...u, ...patch, roleOrigin: 'user' } });
      return <li key={url} className="url-card"><div className="file-row">
        <label className="check url-select"><input type="checkbox" aria-label={`${url}を選択`} checked={live.includes(url)} onChange={e => setSelected(e.target.checked ? [...live, url] : live.filter(x => x !== url))} />
          <span className="file-name"><strong>{url}</strong><small>URL {i + 1} ・ Authority：{AUTHORITY[u.authority]?.label}{u.citationAllowed !== 'auto' && ` ・ ${u.citationAllowed === 'yes' ? '引用可' : '引用しない'}`}{u.intendedChapter && ` ・ ${u.intendedChapter}`}</small></span></label></div>
        <RoleSelect usage={u} name={url} roles={URL_ROLES} labels={URL_ROLE_LABEL} onChange={role => set({ role })} />
        {uiMode === 'advanced' && <details className="file-details"><summary>詳細設定（Authority・引用・章・用途・自由記述）</summary>
          <SourceUsageFields usage={u} set={set} notesPlaceholder="例：数値はこのページを根拠にする／雰囲気だけ参考にする" /></details>}
      </li>;
    })}</ul>
  </div>;
}

export function FileRoles({ files, usages, names, uiMode, onChange, onRemove }: { files: File[]; usages: FileUsage[]; names: string[]; uiMode: UiMode;
  onChange: (index: number, usage: FileUsage) => void; onRemove: (index: number) => void }) {
  const size = (bytes: number) => bytes < 1024 * 1024 ? `${(bytes / 1024).toLocaleString('ja', { maximumFractionDigits: 1 })} KB` : `${(bytes / 1024 / 1024).toLocaleString('ja', { maximumFractionDigits: 1 })} MB`;
  return <ul className="files file-roles">{files.map((file, i) => {
    const u = usages[i]; const set = (patch: Partial<FileUsage>) => onChange(i, { ...u, ...patch, roleOrigin: 'user' });
    const visual = isImage(file.name) || /pdf$/i.test(file.name);
    const role = SOURCE_ROLES[u.role];
    return <li key={`${file.name}-${i}`}><div className="file-row"><span className="file-name"><strong>{file.name}</strong><small>{file.type || 'ファイル'} ・ {size(file.size)}{names[i] !== file.name && ` ・ ZIP内：${names[i]}`}</small></span>
      <button type="button" className="remove" aria-label={`${file.name}を削除`} onClick={() => onRemove(i)}>削除</button></div>
      <RoleSelect usage={u} name={file.name} onChange={value => set({ role: value, assetRole: SOURCE_ROLES[value].content ? (value === 'redraw_source' ? 'redraw_source' : '') : (u.assetRole || (value === 'asset' ? 'inline_figure' : value)) })} />
      {visual && <div className="quick-uses" role="radiogroup" aria-label={`${file.name}の使い方`}>{Object.entries(QUICK_USES).map(([id, q]) =>
        <label key={id} className="check chip"><input type="radio" name={`use-${i}`} checked={quickUseOf(u) === id} onChange={() => onChange(i, applyQuickUse(u, id))} />{q.label}</label>)}</div>}
      {uiMode === 'advanced' && <details className="file-details"><summary>詳細設定（用途・章・権威性・加工可否・自由指示）</summary>
        <div className="row">
          <label>表示名 / label<input value={u.label} onChange={e => set({ label: e.target.value })} /></label>
          <label>Asset role<select value={u.assetRole} onChange={e => set({ assetRole: e.target.value })}><option value="">（素材ではない）</option>
            {Object.entries(ASSET_ROLES).map(([id, a]) => <option key={id} value={id}>{a.label}（{id}）</option>)}</select></label>
        </div>
        <SourceUsageFields usage={u} set={set} notesLabel="このファイルへの指示（自由記述）" notesPlaceholder="例：そのまま貼らず、情報構造だけ再作図する／表紙には使用しない／色味と余白だけ参考にする" />
        <div className="row">
          <label>使う節・場所<input value={u.intendedSection} onChange={e => set({ intendedSection: e.target.value })} placeholder="例：病棟業務の流れを説明する場所" /></label>
          <label>優先度<select value={u.priority} onChange={e => set({ priority: e.target.value as FileUsage['priority'] })}><option value="low">low</option><option value="normal">normal</option><option value="high">high</option></select></label>
        </div>
        <label>キャプション<input value={u.caption} onChange={e => set({ caption: e.target.value })} /></label>
        <div className="flags">{([['cropAllowed', 'トリミング可'], ['redrawAllowed', '再作図可'], ['transformAllowed', '色・サイズ等の加工可'], ['useVerbatim', 'そのまま使用']] as const).map(([key, text]) =>
          <label className="check" key={key}><input type="checkbox" checked={u[key]} onChange={e => set({ [key]: e.target.checked } as Partial<FileUsage>)} />{text}</label>)}</div>
      </details>}
    </li>;
  })}</ul>;
}

export function CitationControls({ inText, value, onInText, onChange }: { inText: CitationOptions['inText']; value: Omit<CitationOptions, 'inText'>;
  onInText: (v: CitationOptions['inText']) => void; onChange: (v: Omit<CitationOptions, 'inText'>) => void }) {
  const set = <K extends keyof typeof value>(key: K, v: (typeof value)[K]) => onChange({ ...value, [key]: v });
  const groups = CITATIONS.groups as Record<string, { ja: string }>;
  return <div className="citation-controls">
    <div className="row">
      <label>In-text citation — 本文中の参照<select value={inText} onChange={e => onInText(e.target.value as CitationOptions['inText'])}>
        {Object.entries(CITATIONS.in_text_styles).map(([id, text]) => <option key={id} value={id}>{text}</option>)}</select></label>
      {inText === 'note' ? <label>Footnote style — 脚注の内容<select value={value.footnoteStyle} onChange={e => set('footnoteStyle', e.target.value as CitationOptions['footnoteStyle'])}>
        {Object.entries(CITATIONS.footnote_styles).map(([id, text]) => <option key={id} value={id}>{text}</option>)}</select></label>
        : <label>Bibliography style — 巻末の書式<select value={value.bibliographyStyle} onChange={e => set('bibliographyStyle', e.target.value as CitationOptions['bibliographyStyle'])}>
          <option value="auto">自動</option><option value="standard">標準（著者. 書名. 発行者, 年）</option><option value="author_date">著者・年（著者 (年). 書名）</option></select></label>}
    </div>
    <div className="row">
      <label>Bibliography numbering — 巻末の番号<select value={value.numbering} onChange={e => set('numbering', e.target.value as CitationOptions['numbering'])}>
        {Object.entries(CITATIONS.bibliography_numbering).map(([id, text]) => <option key={id} value={id}>{text}</option>)}</select>
        <small>本文が脚注式・著者年式でも、巻末一覧に [1], [2] を付けられます。</small></label>
      <label>番号の振り方<select value={value.scope} onChange={e => set('scope', e.target.value as CitationOptions['scope'])}>
        {Object.entries(CITATIONS.numbering_scope).map(([id, text]) => <option key={id} value={id}>{text}</option>)}</select></label>
    </div>
    <fieldset className="multi"><legend>Bibliography grouping — 巻末リストを分ける</legend><div className="chips">{Object.entries(groups).map(([id, g]) =>
      <label className="check chip" key={id}><input type="checkbox" checked={value.groups[id as keyof typeof value.groups]} onChange={e => set('groups', { ...value.groups, [id]: e.target.checked })} />{g.ja}</label>)}</div>
      <small>引用文献（本文で引用した根拠資料）と参考資料（内容の参考にした背景資料・経験記事）は別リストになります。</small></fieldset>
  </div>;
}

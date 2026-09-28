import { useState } from 'react';
import type { DesignOptions } from './design';
import { themePage } from './design-presets';
import {
  applyLayoutPreset, genreStylePreset, issueText, LAYOUT_PRESETS, LIMITS, PAGE_SIZES, previewLayout, profileDescription,
  publicationPayload, publicationPresets, SPAN_POLICIES, STYLE_PRESETS, WRITING_MODES,
  type LayoutIssue, type LayoutPreview, type PageSize, type PublicationOptions, type SpanPolicy, type StyleControlName,
} from './publication';

// Tier and genre lists (and their descriptions) come from the resolver's own data files, not from a UI copy.
const tierFiles = import.meta.glob('../job-template/profiles/tiers/*.yaml', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>;
const genreFiles = import.meta.glob('../job-template/profiles/genres/*.yaml', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>;
const entries = (files: Record<string, string>) => Object.entries(files).map(([path, text]) => [path.replace(/^.*\/(.+)\.yaml$/, '$1'), profileDescription(text)] as const);
const TIER_ORDER = ['short', 'standard', 'long', 'monograph'];
export const TIERS = entries(tierFiles).sort((a, b) => TIER_ORDER.indexOf(a[0]) - TIER_ORDER.indexOf(b[0]));
export const GENRES = entries(genreFiles);
const DESIGN_SIZES = ['A5', 'B5', 'A4', 'Letter'];

type Props = { value: PublicationOptions; design: DesignOptions; onChange: (value: PublicationOptions) => void; onDesignChange: (value: DesignOptions) => void; initialMode?: 'basic' | 'advanced' };

export function PublicationPanel({ value, design, onChange, onDesignChange, initialMode = 'basic' }: Props) {
  const [mode, setMode] = useState<'basic' | 'advanced'>(initialMode);
  const themeMode = value.layoutPreset === 'theme';
  // In theme mode the geometry is the Design Spec's (exactly what the job used before this panel existed).
  const effective = themeMode ? applyLayoutPreset(value, 'theme', { size: design.pageSize, margin: themePage(design.theme).margin }) : value;
  const preview = previewLayout(effective);
  const payload = publicationPayload(value);
  const modified = !themeMode && value.layoutPreset !== 'custom' && Boolean(payload.layout_spec);
  const fieldIssues = (prefix: string) => preview.issues.filter(issue => issue.field.startsWith(prefix));

  /** Geometry edits: theme mode becomes Custom (starting from the theme's values) except a plain Design Spec page size. */
  function layout(patch: Partial<PublicationOptions>) {
    let next = { ...effective, ...patch };
    if (themeMode) {
      if (Object.keys(patch).length === 1 && patch.pageSize && DESIGN_SIZES.includes(patch.pageSize)) { onDesignChange({ ...design, pageSize: patch.pageSize }); return; }
      next = { ...next, layoutPreset: 'custom' };
    }
    if (next.columns === 1) next = { ...next, figureSpan: next.figureSpan === 'full' ? 'column' : next.figureSpan, tableSpan: next.tableSpan === 'full' ? 'column' : next.tableSpan };
    onChange(next);
  }
  const set = (patch: Partial<PublicationOptions>) => onChange({ ...value, ...patch });
  const num = (label: string, current: number, apply: (n: number) => void, issues: LayoutIssue[], extra?: { min?: number; max?: number; step?: number }) =>
    <label>{label}<input type="number" inputMode="decimal" min={extra?.min} max={extra?.max} step={extra?.step ?? 0.5} value={Number.isFinite(current) ? current : ''}
      aria-invalid={issues.length > 0} onChange={event => apply(Number(event.target.value))} />{issues.map(issue => <small className="field-error" key={issue.code + issue.field}>{issueText(issue, preview)}</small>)}</label>;
  const autoStyle = value.genre !== 'auto' ? genreStylePreset(value.genre) : undefined;

  return <section className="publication"><div className="section-heading"><span>05</span><h2>出版形式 · Publication format</h2></div>
    <p>判型・段組み・余白・スタイルを選ぶと、BookOrderの既存resolverが <code>plan/profile.resolved.yaml</code>・<code>plan/layout-spec.yaml</code>・<code>plan/style-bible.yaml</code> を生成し、Typst PDFに反映します。何も変更しなければ従来どおりのテーマ既定で組版します。</p>
    <div className="mode-switch" role="tablist" aria-label="設定レベル">
      <button type="button" role="tab" aria-selected={mode === 'basic'} className={mode === 'basic' ? 'active' : ''} onClick={() => setMode('basic')}>Basic</button>
      <button type="button" role="tab" aria-selected={mode === 'advanced'} className={mode === 'advanced' ? 'active' : ''} onClick={() => setMode('advanced')}>Advanced</button>
    </div>
    <div className="publication-grid">
      <div className="publication-form">
        {mode === 'basic' ? <>
          <div className="row">
            <label>Book scale / tier<select value={value.tier} onChange={event => set({ tier: event.target.value })}>
              <option value="auto">Automatic · Target scaleから決定</option>{TIERS.map(([id]) => <option key={id} value={id}>{id}</option>)}</select>
              <small>{value.tier === 'auto' ? 'BookOrderが希望ページ数から tier を決めます（従来動作）。' : TIERS.find(([id]) => id === value.tier)?.[1]}</small></label>
            <label>Genre<select value={value.genre} onChange={event => set({ genre: event.target.value })}>
              <option value="auto">Automatic · general</option>{GENRES.map(([id]) => <option key={id} value={id}>{id}</option>)}</select>
              <small>{value.genre === 'auto' ? 'ジャンル補正なし（従来動作）。' : GENRES.find(([id]) => id === value.genre)?.[1]}</small></label>
          </div>
          <fieldset className="preset-list"><legend>Layout preset</legend>
            {[['theme', { label: 'Theme default', description: `デザインテーマの判型（${design.pageSize}・1段組み）。従来と同じ出力です。` }] as const,
              ...Object.entries(LAYOUT_PRESETS), ['custom', { label: 'Custom', description: '判型・段組み・余白を直接指定します。' }] as const].map(([id, preset]) =>
              <label key={id} className={`preset ${value.layoutPreset === id ? 'selected' : ''}`}><input type="radio" name="layout-preset" value={id} checked={value.layoutPreset === id}
                onChange={() => onChange(id === 'custom' ? { ...effective, layoutPreset: 'custom' } : applyLayoutPreset(value, id, themePage(design.theme)))} />
                <span><strong>{preset.label}{value.layoutPreset === id && modified ? '（変更あり）' : ''}</strong><small>{preset.description}</small></span></label>)}
            <small>プリセットは新しい組版モードではなく、LayoutSpec の値（判型・段数・段間・余白・段抜き方針）への変換です。</small>
          </fieldset>
          <div className="row">
            <label>Page size<select value={effective.pageSize} onChange={event => layout({ pageSize: event.target.value as PageSize })}>
              {[...Object.keys(PAGE_SIZES), 'custom'].map(size => <option key={size} value={size}>{size === 'custom' ? 'Custom' : `${size} · ${PAGE_SIZES[size][0]} × ${PAGE_SIZES[size][1]} mm`}</option>)}</select>
              <small>{effective.pageSize === 'custom' ? 'カスタム寸法（縦長の仕上がりサイズ）' : `${preview.widthMm} × ${preview.heightMm} mm${publicationPresets.page_size_notes[effective.pageSize as 'B5'] ? ' — ' + publicationPresets.page_size_notes[effective.pageSize as 'B5'] : ''}`}</small></label>
            <div><span className="label">Columns</span><div className="segmented" role="radiogroup" aria-label="Columns">
              {[1, 2].map(n => <button type="button" role="radio" aria-checked={effective.columns === n} key={n} className={effective.columns === n ? 'active' : ''} onClick={() => layout({ columns: n as 1 | 2 })}>{n} column{n > 1 ? 's' : ''}</button>)}</div>
              {effective.columns === 2 && <small>Column width: <b>{preview.columnWidthMm} mm</b> · Gutter: <b>{preview.gutterMm} mm</b> · Body width: <b>{preview.bodyWidthMm} mm</b></small>}
              {fieldIssues('body.').map(issue => <small className="field-error" key={issue.code}>{issueText(issue, preview)}</small>)}</div>
          </div>
          {effective.pageSize === 'custom' && <div className="row">
            {num('Width · mm', effective.customWidthMm, n => layout({ customWidthMm: n }), fieldIssues('page.width'), { min: LIMITS.custom_page_min_mm, max: LIMITS.custom_page_max_mm })}
            {num('Height · mm', effective.customHeightMm, n => layout({ customHeightMm: n }), fieldIssues('page.height'), { min: LIMITS.custom_page_min_mm, max: LIMITS.custom_page_max_mm })}</div>}
          {effective.columns === 2 && <div className="row">
            <label>Figures<select value={effective.figureSpan} onChange={event => layout({ figureSpan: event.target.value as SpanPolicy })}>
              {(['auto', 'column', 'full'] as SpanPolicy[]).map(id => <option key={id} value={id}>{SPAN_POLICIES[id].label}</option>)}</select><small>{SPAN_POLICIES[effective.figureSpan].description}</small></label>
            <label>Tables<select value={effective.tableSpan} onChange={event => layout({ tableSpan: event.target.value as SpanPolicy })}>
              {(['auto', 'column', 'full'] as SpanPolicy[]).map(id => <option key={id} value={id}>{id === 'column' ? 'Single column where possible' : SPAN_POLICIES[id].label}</option>)}</select><small>個々の図表を何段抜きにするかは組版時に決まります（ここでは方針のみ）。</small></label>
          </div>}
          <div className="row">
            <label>Style preset<select value={value.stylePreset} onChange={event => set({ stylePreset: event.target.value })}>
              <option value="auto">Automatic · Genreに従う{autoStyle ? `（${STYLE_PRESETS[autoStyle].label}）` : ''}</option>
              {Object.entries(STYLE_PRESETS).map(([id, preset]) => <option key={id} value={id}>{preset.label}</option>)}</select>
              <small>StyleBible の genre template を選びます。細かなtokenは Advanced のコントロールで調整します。</small></label>
            <div><span className="label">Writing mode</span><div className="segmented" role="radiogroup" aria-label="Writing mode">
              {(Object.entries(WRITING_MODES) as [keyof typeof WRITING_MODES, (typeof WRITING_MODES)['horizontal-tb']][]).map(([id, item]) =>
                <button type="button" role="radio" key={id} aria-checked={effective.writingMode === id} disabled={!item.typst} className={effective.writingMode === id ? 'active' : ''}
                  title={item.reason} onClick={() => layout({ writingMode: id })}>{item.label}</button>)}</div>
              <small>Vertical: {WRITING_MODES['vertical-rl'].reason} 縦書きを横書きに置き換えて出力することはありません。</small></div>
          </div>
        </> : <>
          <h3>Margins（mm・製本を考慮した inner / outer）</h3>
          <div className="row">{num('Top · 天', effective.margins.top, n => layout({ margins: { ...effective.margins, top: n } }), fieldIssues('page.margin_top'))}
            {num('Bottom · 地', effective.margins.bottom, n => layout({ margins: { ...effective.margins, bottom: n } }), fieldIssues('page.margin_bottom'))}</div>
          <div className="row">{num('Inner · ノド', effective.margins.inner, n => layout({ margins: { ...effective.margins, inner: n } }), fieldIssues('page.margin_inner'))}
            {num('Outer · 小口', effective.margins.outer, n => layout({ margins: { ...effective.margins, outer: n } }), fieldIssues('page.margin_outer'))}</div>
          <div className="row">{num('Gutter · 段間 mm', effective.gutterMm, n => layout({ gutterMm: n }), fieldIssues('body.gutter'), { min: 0, max: 50 })}
            <label>Orientation<select value={effective.orientation} disabled={effective.pageSize === 'custom'} onChange={event => layout({ orientation: event.target.value as 'portrait' })}><option value="portrait">Portrait</option><option value="landscape">Landscape</option></select>
              <small>{effective.columns === 1 ? '段間は2段組みのときだけ使われます。' : `2段組み：1段 ${preview.columnWidthMm} mm（最小 ${LIMITS.min_column_width_mm} mm）、段間 ${LIMITS.min_gutter_mm}–${LIMITS.max_gutter_mm} mm。`}</small></label></div>
          <h3>StyleBible controls</h3>
          <div className="style-controls">{(Object.entries(publicationPresets.style_controls) as [StyleControlName, { label: string; options: Record<string, { label: string }> }][]).map(([name, control]) =>
            <label key={name}>{control.label}<select value={value.styleControls[name] ?? 'default'} onChange={event => set({ styleControls: { ...value.styleControls, [name]: event.target.value } })}>
              <option value="default">Preset default</option>{Object.entries(control.options).map(([id, option]) => <option key={id} value={id}>{option.label}</option>)}</select></label>)}</div>
          <small>各コントロールは StyleBible の既存フィールド（tone・spacing・typography・visual_grammar・table・chapter_opener）への変換です。低レベルtokenは plan/style-bible.yaml で編集できます。</small>
        </>}
        {preview.issues.length > 0 && <div className="layout-issues" role="alert"><strong>出版形式の設定を確認してください</strong>{preview.issues.map(issue => <p key={issue.code + issue.field}>{issueText(issue, preview)}</p>)}<small>最終判定は BookOrder（<code>bookorder publication</code> / 組版時の LayoutSpec 検証）が行います。</small></div>}
      </div>
      <aside className="publication-summary" aria-label="Resolved layout summary">
        <LayoutSummary preview={preview} value={value} themeMode={themeMode} modified={modified} autoStyle={autoStyle} />
        <SchematicPreview preview={preview} />
      </aside>
    </div>
    <details><summary>WebUIで現在設定できること・できないこと</summary>
      <div className="row"><div><h3>対応</h3><ul className="capabilities"><li>横書き（horizontal-tb）</li><li>1段組み・2段組み（Typst page columns）</li><li>図・表・囲みの段抜き（2段組み時に本文全幅へ）</li><li>A4 / A5 / B5 / B6 / Letter / カスタム判型</li><li>天・地・ノド・小口の余白と段間</li><li>PublicationProfile の tier / genre</li><li>StyleBible プリセットと高レベルコントロール</li></ul></div>
        <div><h3>未対応</h3><ul className="capabilities"><li>Typstによる本当の縦書き組版（選択できません）</li><li>3段以上の段組み</li><li>雑誌のような自由配置レイアウト</li><li>個々の図表の段抜きをWebUIで指定すること（方針のみ。個別指定は assets-plan の geometry）</li><li>HTML / EPUB / DOCX への段組み反映（1段で出力し、報告書に degraded と記録）</li></ul></div></div>
    </details>
  </section>;
}

function LayoutSummary({ preview, value, themeMode, modified, autoStyle }: { preview: LayoutPreview; value: PublicationOptions; themeMode: boolean; modified: boolean; autoStyle?: string }) {
  const style = value.stylePreset !== 'auto' ? STYLE_PRESETS[value.stylePreset]?.label : autoStyle ? `${STYLE_PRESETS[autoStyle].label}（genre既定）` : 'Theme / general';
  const policy = (kind: 'figure' | 'table') => preview.columns < 2 || !preview.spanPolicy ? '—（1段組み）' : SPAN_POLICIES[preview.spanPolicy[kind]].label;
  return <div className="summary-card">
    <h3>BOOK FORMAT</h3>
    <p className="summary-size"><b>{preview.pageSize === 'custom' ? 'Custom' : preview.pageSize}</b> {preview.widthMm} × {preview.heightMm} mm</p>
    <dl>
      <dt>Layout</dt><dd>{themeMode ? 'Theme default' : value.layoutPreset === 'custom' ? 'Custom' : LAYOUT_PRESETS[value.layoutPreset].label + (modified ? '（変更あり）' : '')}</dd>
      <dt>Columns</dt><dd>{preview.columns} column{preview.columns > 1 ? 's' : ''}</dd>
      {preview.columns > 1 && <><dt>Column width</dt><dd>{preview.columnWidthMm} mm</dd><dt>Gutter</dt><dd>{preview.gutterMm} mm</dd></>}
      <dt>Body</dt><dd>{preview.bodyWidthMm} × {preview.bodyHeightMm} mm</dd>
      <dt>Margins</dt><dd>Top {preview.margins.top} · Bottom {preview.margins.bottom} · Inner {preview.margins.inner} · Outer {preview.margins.outer} mm</dd>
      <dt>Writing</dt><dd>{WRITING_MODES[preview.writingMode].label}</dd>
      <dt>Tier</dt><dd>{value.tier === 'auto' ? 'Automatic' : value.tier}</dd>
      <dt>Genre</dt><dd>{value.genre === 'auto' ? 'general' : value.genre}</dd>
      <dt>Style</dt><dd>{style}</dd>
      <dt>Figure span</dt><dd>{policy('figure')}</dd>
      <dt>Table span</dt><dd>{policy('table')}</dd>
    </dl>
    <small>値は共有プリセット（schemas/publication-presets.json）から計算した見込みです。ジョブ実行時に LayoutSpec resolver が同じ規則で確定・検証します。</small>
  </div>;
}

/** CSS schematic of the page. Not a layout engine: Typst output is the authority. */
export function SchematicPreview({ preview }: { preview: LayoutPreview }) {
  const w = preview.widthMm, h = preview.heightMm;
  if (!(w > 0 && h > 0)) return null;
  const pct = (value: number, total: number) => `${Math.max(0, (value / total) * 100)}%`;
  const m = preview.margins; const ok = preview.bodyWidthMm > 0 && preview.bodyHeightMm > 0;
  return <figure className="schematic" aria-label="schematic page preview">
    <div className="schematic-page" style={{ aspectRatio: `${w} / ${h}` }}>
      {ok && <div className="schematic-body" style={{ top: pct(m.top, h), bottom: pct(m.bottom, h), left: pct(m.inner, w), right: pct(m.outer, w) }}>
        <div className="schematic-opener">Chapter opener</div>
        <div className="schematic-columns" style={{ columnGap: pct(preview.columns > 1 ? preview.gutterMm : 0, preview.bodyWidthMm) }}>
          {Array.from({ length: preview.columns }, (_, i) => <div key={i} className="schematic-column">{Array.from({ length: 5 }, (_, j) => <span key={j} />)}</div>)}
        </div>
        {preview.columns > 1 && <div className="schematic-span">full-width span</div>}
        <div className="schematic-columns" style={{ columnGap: pct(preview.columns > 1 ? preview.gutterMm : 0, preview.bodyWidthMm) }}>
          {Array.from({ length: preview.columns }, (_, i) => <div key={i} className="schematic-column">{Array.from({ length: 4 }, (_, j) => <span key={j} />)}</div>)}
        </div>
      </div>}
    </div>
    <figcaption>Schematic preview — 比率・余白・段・段間の模式図です（右ページ想定：左がノド）。正確な組版は Typst の出力が正です。</figcaption>
  </figure>;
}

// "05 Publication & design": one place for everything about how the book looks.
//   Basic    — publication preset, genre, layout, page size, columns, theme. Enough to generate a job.
//   Advanced — Geometry / Typography / Visual grammar / Expert. Every concept has a single control.
// Internally the values still go to separate models: PublicationOptions (profile, LayoutSpec and StyleBible requests
// in project.json) and DesignOptions (book.design.yaml). See src/publication.ts for the resolution order.
import { useState } from 'react';
import { switchTheme, themeNames, type DesignOptions } from './design';
import { designDefaults, themePage, themeSpec } from './design-presets';
import { ExpertControls, ThemeSamples, themePreviewUrl, TypographyControls, VisualGrammarControls } from './DesignPanel';
import {
  applyLayoutPreset, applyPublicationPreset, autoTier, pdfAccent, DESIGN_PAGE_SIZES, effectivePublication, genreStylePreset, issueText, LAYOUT_PRESETS, LIMITS,
  PAGE_SIZES, presetDeviations, previewLayout, profileDescription, PUBLICATION_PRESETS, requestPayload, SPAN_POLICIES, STYLE_PRESETS, WRITING_MODES,
  type LayoutIssue, type LayoutPreview, type Orientation, type PageSize, type PublicationOptions, type SpanPolicy,
} from './publication';

// Tier and genre lists (and their descriptions) come from the resolver's own data files, not from a UI copy.
const tierFiles = import.meta.glob('../job-template/profiles/tiers/*.yaml', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>;
const styleTemplates = import.meta.glob('../job-template/styles/genres/*.yaml', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>;
/** palette.accent of a StyleBible genre template (the files are small YAML; only this one key is read). */
const templateAccent = (template: string) => /^palette:\s*\r?\n(?:[ \t]+.*\r?\n)*?[ \t]+accent:\s*"?(#[0-9A-Fa-f]{6})/m.exec(styleTemplates[`../job-template/styles/genres/${template}.yaml`] ?? '')?.[1];
const genreFiles = import.meta.glob('../job-template/profiles/genres/*.yaml', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>;
const entries = (files: Record<string, string>) => Object.entries(files).map(([path, text]) => [path.replace(/^.*\/(.+)\.yaml$/, '$1'), profileDescription(text)] as const);
const TIER_ORDER = ['short', 'standard', 'long', 'monograph'];
export const TIERS = entries(tierFiles).sort((a, b) => TIER_ORDER.indexOf(a[0]) - TIER_ORDER.indexOf(b[0]));
export const GENRES = entries(genreFiles);

type Tab = 'basic' | 'geometry' | 'typography' | 'grammar' | 'expert';
type Change = { publication?: PublicationOptions; design?: DesignOptions };
type Props = { publication: PublicationOptions; design: DesignOptions; targetPages: number; outputs: Record<string, boolean>; onChange: (next: Change) => void; initialTab?: Tab };
const OUTPUT_LABELS: Record<string, string> = { canonical_markdown: 'Markdown', docx: 'DOCX', semantic_html: 'HTML', pdf: 'PDF', static_site: 'Website', epub: 'EPUB' };

/** Tier override for section 01 (the scale section): automatic unless the user overrides it. */
export function TierOverride({ publication, targetPages, onChange }: { publication: PublicationOptions; targetPages: number; onChange: (value: PublicationOptions) => void }) {
  return <details className="inline-advanced"><summary>Advanced · 分量ティア（tier）{publication.tier === 'auto' ? `：自動 → ${autoTier(targetPages)}` : `：${publication.tier}（手動）`}</summary>
    <label>Book tier<select value={publication.tier} onChange={event => onChange({ ...publication, tier: event.target.value })}>
      <option value="auto">Automatic · Target scale（{targetPages}ページ）から → {autoTier(targetPages)}</option>{TIERS.map(([id]) => <option key={id} value={id}>{id}</option>)}</select>
      <small>{publication.tier === 'auto' ? '通常は自動のままにしてください。BookOrderは希望ページ数から章数・本文量・図表密度の基準（PublicationProfile）を決めます。' : TIERS.find(([id]) => id === publication.tier)?.[1]}</small></label>
  </details>;
}

export function PublicationPanel({ publication, design, targetPages, outputs, onChange, initialTab = 'basic' }: Props) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const page = themePage(design.theme);
  const themeMode = publication.layoutPreset === 'theme';
  const effective = effectivePublication(publication, page);
  const preview = previewLayout(publication, page);
  const payload = requestPayload(publication, design, themeSpec(design.theme), page);
  const layoutModified = !themeMode && publication.layoutPreset !== 'custom' && Boolean(payload.layout_spec);
  const deviations = presetDeviations(publication, design.theme);
  const fieldIssues = (prefix: string) => preview.issues.filter(issue => issue.field.startsWith(prefix));
  const setPublication = (next: PublicationOptions) => onChange({ publication: next });
  const setDesign = (next: DesignOptions) => onChange({ design: next });
  const themed = (theme: string) => switchTheme(design, designDefaults(design.theme), designDefaults(theme));
  const setTheme = (theme: string) => onChange({ design: themed(theme) });

  /** Geometry edits. In theme mode a Design Spec page size or an orientation stays a theme-mode override (legacy path,
   *  book.design.yaml); any other geometry edit starts a Custom layout from the current effective values. */
  function layout(patch: Partial<PublicationOptions>) {
    let next: PublicationOptions;
    const keys = Object.keys(patch);
    const legacyPage = keys.length === 1 && ((patch.pageSize && (patch.pageSize === 'theme' || DESIGN_PAGE_SIZES.includes(patch.pageSize))) || patch.orientation);
    if (themeMode && legacyPage) next = { ...publication, ...patch };
    else next = { ...(themeMode ? { ...effective, layoutPreset: 'custom' } : publication), ...patch };
    if (next.pageSize === 'theme' && !themeMode) next = { ...next, pageSize: effective.pageSize };
    if (next.orientation === 'theme' && !themeMode) next = { ...next, orientation: effective.orientation };
    if (next.columns === 1) next = { ...next, figureSpan: next.figureSpan === 'full' ? 'column' : next.figureSpan, tableSpan: next.tableSpan === 'full' ? 'column' : next.tableSpan };
    setPublication(next);
  }
  const num = (label: string, current: number, apply: (n: number) => void, issues: LayoutIssue[], extra?: { min?: number; max?: number; step?: number }) =>
    <label>{label}<input type="number" inputMode="decimal" min={extra?.min} max={extra?.max} step={extra?.step ?? 0.5} value={Number.isFinite(current) ? current : ''}
      aria-invalid={issues.length > 0} onChange={event => apply(Number(event.target.value))} />{issues.map(issue => <small className="field-error" key={issue.code + issue.field}>{issueText(issue, preview)}</small>)}</label>;
  const tabs: [Tab, string][] = [['basic', 'Basic'], ['geometry', 'Geometry'], ['typography', 'Typography'], ['grammar', 'Visual grammar'], ['expert', 'Expert']];

  return <section className="publication"><div className="section-heading"><span>05</span><h2>出版形式とデザイン · Publication &amp; design</h2></div>
    <p>ふつうは <b>Basic</b> だけで十分です。おすすめの出版スタイルを選ぶと、ジャンル・レイアウト・テーマがまとめて入ります。細かく調整したいときだけ Advanced の各タブを開いてください。</p>
    <div className="mode-switch" role="tablist" aria-label="設定レベル">{tabs.map(([id, label], i) =>
      <button type="button" role="tab" key={id} aria-selected={tab === id} className={`${tab === id ? 'active' : ''} ${i === 1 ? 'first-advanced' : ''}`} onClick={() => setTab(id)}>{i ? <><small>Advanced</small>{label}</> : label}</button>)}</div>
    <div className="publication-grid">
      <div className="publication-form">
        {tab === 'basic' && <>
          <fieldset className="preset-list"><legend>出版スタイル · Publication preset</legend>
            {[...Object.entries(PUBLICATION_PRESETS), ['none', { label: '個別に設定', description: 'プリセットを使わず、下の項目を個別に選びます（初期状態＝テーマ既定）。' }] as const].map(([id, preset]) =>
              <label key={id} className={`preset ${publication.publicationPreset === id ? 'selected' : ''}`}><input type="radio" name="publication-preset" value={id} checked={publication.publicationPreset === id}
                onChange={() => {
                  if (id === 'none') { setPublication({ ...publication, publicationPreset: 'none' }); return; }
                  const applied = applyPublicationPreset(publication, id);
                  onChange({ publication: applied.publication, design: applied.theme ? themed(applied.theme) : undefined });
                }} />
                <span><strong>{preset.label}{publication.publicationPreset === id && deviations.length ? '（変更あり）' : ''}</strong><small>{preset.description}</small></span></label>)}
            <small>プリセットは初期値を一括で入れるだけです。下の項目を変えると「変更あり」になり、変えた項目が優先されます。</small>
          </fieldset>
          <p className="roles"><b>Genre</b> = 内容の種類（章構成・図表密度）　<b>Layout</b> = 判型・段組み・余白　<b>Theme</b> = 書体・色・誌面表現</p>
          <div className="row">
            <label>Genre<select value={publication.genre} onChange={event => setPublication({ ...publication, genre: event.target.value })}>
              <option value="auto">Automatic · general</option>{GENRES.map(([id]) => <option key={id} value={id}>{id}</option>)}</select>
              <small>{publication.genre === 'auto' ? 'ジャンル補正なし。' : GENRES.find(([id]) => id === publication.genre)?.[1]}</small></label>
            <label>Theme<select value={design.theme} onChange={event => setTheme(event.target.value)}>{Object.entries(themeNames).map(([id, label]) => <option value={id} key={id}>{label}</option>)}</select>
              <small>書体・色・部品の初期値を切り替えます。個別に変更した値と、判型・段組みの設定は保持します。</small></label>
          </div>
          <div className="row">
            <label>Layout<select value={publication.layoutPreset} onChange={event => { const id = event.target.value; setPublication(id === 'custom' ? { ...effective, layoutPreset: 'custom' } : applyLayoutPreset(publication, id, page)); }}>
              <option value="theme">Theme default（{page.size}・1段組み）</option>{Object.entries(LAYOUT_PRESETS).map(([id, preset]) => <option key={id} value={id}>{preset.label}</option>)}<option value="custom">Custom</option></select>
              <small>{themeMode ? 'テーマの判型・余白を使います（従来と同じ）。' : publication.layoutPreset === 'custom' ? '判型・段組み・余白を直接指定しています（Geometry タブ）。' : LAYOUT_PRESETS[publication.layoutPreset].description + (layoutModified ? '（変更あり）' : '')}</small></label>
            <label>Page size<select value={publication.pageSize === 'theme' ? 'theme' : effective.pageSize} onChange={event => layout({ pageSize: event.target.value as PageSize | 'theme' })}>
              {themeMode && <option value="theme">Theme default · {page.size}</option>}
              {[...Object.keys(PAGE_SIZES), 'custom'].map(size => <option key={size} value={size}>{size === 'custom' ? 'Custom…' : `${size} · ${PAGE_SIZES[size][0]} × ${PAGE_SIZES[size][1]} mm`}</option>)}</select>
              <small>{effective.pageSize === 'custom' ? '寸法は Geometry タブで指定します。' : `${preview.widthMm} × ${preview.heightMm} mm${publicationPresets_note(effective.pageSize as string)}`}</small></label>
          </div>
          <div><span className="label">Columns</span><div className="segmented" role="radiogroup" aria-label="Columns">
            {[1, 2].map(n => <button type="button" role="radio" aria-checked={effective.columns === n} key={n} className={effective.columns === n ? 'active' : ''} onClick={() => layout({ columns: n as 1 | 2 })}>{n} column{n > 1 ? 's' : ''}</button>)}</div>
            {effective.columns === 2 && <small>Column width: <b>{preview.columnWidthMm} mm</b> · Gutter: <b>{preview.gutterMm} mm</b> · Body width: <b>{preview.bodyWidthMm} mm</b></small>}
            {fieldIssues('body.').map(issue => <small className="field-error" key={issue.code}>{issueText(issue, preview)}</small>)}</div>
          <ThemeSamples />
        </>}
        {tab === 'geometry' && <>
          {themeMode && <p className="note">いまはテーマ既定のレイアウトです。判型・向き以外を変更すると Custom レイアウトになります。</p>}
          {effective.pageSize === 'custom' && <div className="row">
            {num('Width · mm', effective.customWidthMm, n => layout({ customWidthMm: n }), fieldIssues('page.width'), { min: LIMITS.custom_page_min_mm, max: LIMITS.custom_page_max_mm })}
            {num('Height · mm', effective.customHeightMm, n => layout({ customHeightMm: n }), fieldIssues('page.height'), { min: LIMITS.custom_page_min_mm, max: LIMITS.custom_page_max_mm })}</div>}
          <div className="row">
            <label>Orientation<select value={publication.orientation} disabled={effective.pageSize === 'custom'} onChange={event => layout({ orientation: event.target.value as Orientation | 'theme' })}>
              {themeMode && <option value="theme">Theme default · {page.orientation ?? 'portrait'}</option>}<option value="portrait">Portrait</option><option value="landscape">Landscape</option></select>
              <small>{effective.pageSize === 'custom' ? 'カスタム判型は幅・高さで向きを決めます。' : '判型の向き（この1か所だけで設定します）。'}</small></label>
            {num('Gutter · 段間 mm', effective.gutterMm, n => layout({ gutterMm: n }), fieldIssues('body.gutter'), { min: 0, max: 50 })}
          </div>
          <h3>Margins（mm・製本を考慮した inner / outer）</h3>
          <div className="row">{num('Top · 天', effective.margins.top, n => layout({ margins: { ...effective.margins, top: n } }), fieldIssues('page.margin_top'))}
            {num('Bottom · 地', effective.margins.bottom, n => layout({ margins: { ...effective.margins, bottom: n } }), fieldIssues('page.margin_bottom'))}</div>
          <div className="row">{num('Inner · ノド', effective.margins.inner, n => layout({ margins: { ...effective.margins, inner: n } }), fieldIssues('page.margin_inner'))}
            {num('Outer · 小口', effective.margins.outer, n => layout({ margins: { ...effective.margins, outer: n } }), fieldIssues('page.margin_outer'))}</div>
          {effective.columns === 2 ? <div className="row">
            <label>Figure span<select value={effective.figureSpan} onChange={event => layout({ figureSpan: event.target.value as SpanPolicy })}>
              {(['auto', 'column', 'full'] as SpanPolicy[]).map(id => <option key={id} value={id}>{SPAN_POLICIES[id].label}</option>)}</select><small>{SPAN_POLICIES[effective.figureSpan].description}</small></label>
            <label>Table span<select value={effective.tableSpan} onChange={event => layout({ tableSpan: event.target.value as SpanPolicy })}>
              {(['auto', 'column', 'full'] as SpanPolicy[]).map(id => <option key={id} value={id}>{id === 'column' ? 'Single column where possible' : SPAN_POLICIES[id].label}</option>)}</select><small>個々の図表の段抜きは組版時に決まります（ここでは方針のみ）。</small></label>
          </div> : <small className="note">図・表の段抜き方針は2段組みのときに設定できます。</small>}
          <div><span className="label">Writing mode</span><div className="segmented" role="radiogroup" aria-label="Writing mode">
            {(Object.entries(WRITING_MODES) as [keyof typeof WRITING_MODES, (typeof WRITING_MODES)['horizontal-tb']][]).map(([id, item]) =>
              <button type="button" role="radio" key={id} aria-checked={effective.writingMode === id} disabled={!item.typst} className={effective.writingMode === id ? 'active' : ''}
                title={item.reason} onClick={() => layout({ writingMode: id })}>{item.label}</button>)}</div>
            <small>Vertical: {WRITING_MODES['vertical-rl'].reason} 縦書きを横書きに置き換えて出力することはありません。</small></div>
        </>}
        {tab === 'typography' && <TypographyControls value={design} onChange={setDesign} />}
        {tab === 'grammar' && <VisualGrammarControls value={design} onChange={setDesign} publication={publication} onPublication={setPublication} />}
        {tab === 'expert' && <ExpertControls value={design} onChange={setDesign} publication={publication} onPublication={setPublication} />}
        {preview.issues.length > 0 && <div className="layout-issues" role="alert"><strong>出版形式の設定を確認してください</strong>{preview.issues.map(issue => <p key={issue.code + issue.field}>{issueText(issue, preview)}</p>)}<small>最終判定は BookOrder（<code>bookorder publication</code> / 組版時の LayoutSpec 検証）が行います。</small></div>}
        <details><summary>設定の優先順位と、現在できること・できないこと</summary>
          <ol className="precedence"><li><b>レイアウト</b>：テーマの判型・余白 → レイアウトプリセット → Geometry で変更した値（後ろほど優先）。</li>
            <li><b>分量</b>：Target scale から tier を自動決定 → 01 の Advanced で指定した tier。</li>
            <li><b>PDFの見た目</b>：テーマ → PDF style preset（未指定なら Genre）→ Visual grammar で変更した値 → アクセント色の明示指定。</li>
            <li><b>自由記述</b>：02 の追加指示と Art direction は補足です。構造化設定と矛盾する場合は構造化設定が優先されます。</li></ol>
          <div className="row"><div><h3>対応</h3><ul className="capabilities"><li>横書き（horizontal-tb）</li><li>1段組み・2段組み（Typst page columns）</li><li>図・表・囲みの段抜き（2段組み時に本文全幅へ）</li><li>A4 / A5 / B5 / B6 / Letter / カスタム判型</li><li>天・地・ノド・小口の余白と段間</li></ul></div>
            <div><h3>未対応</h3><ul className="capabilities"><li>Typstによる本当の縦書き組版（選択できません）</li><li>3段以上の段組み・雑誌のような自由配置</li><li>個々の図表の段抜き指定（方針のみ）</li><li>HTML / EPUB / DOCX への段組み反映（1段で出力）</li><li>StyleBible の誌面表現を完全に反映するTypstテーマは Modern Technical のみ（他テーマは色などの一部）</li></ul></div></div>
        </details>
      </div>
      <aside className="publication-summary" aria-label="Resolved format summary">
        <FormatSummary preview={preview} publication={publication} design={design} themeMode={themeMode} layoutModified={layoutModified} deviations={deviations} targetPages={targetPages} outputs={outputs} />
        <SchematicPreview preview={preview} />
        {themePreviewUrl(design.theme) && <figure className="theme-thumb"><img src={themePreviewUrl(design.theme)} alt={`${themeNames[design.theme]}の誌面サンプル`} /><figcaption>Theme sample · {themeNames[design.theme]}（判型・段組みは上の模式図が現在の設定です）</figcaption></figure>}
      </aside>
    </div>
  </section>;
}
function publicationPresets_note(size: string) {
  const notes: Record<string, string> = { B5: ' — ISO B5。JIS B5（182×257）は Custom', B6: ' — ISO B6。JIS B6（128×182）は Custom' };
  return notes[size] ?? '';
}

function FormatSummary({ preview, publication, design, themeMode, layoutModified, deviations, targetPages, outputs }: { preview: LayoutPreview; publication: PublicationOptions; design: DesignOptions; themeMode: boolean; layoutModified: boolean; deviations: string[]; targetPages: number; outputs: Record<string, boolean> }) {
  const auto = publication.genre !== 'auto' ? genreStylePreset(publication.genre) : undefined;
  const style = publication.stylePreset !== 'auto' ? STYLE_PRESETS[publication.stylePreset]?.label : auto ? `${STYLE_PRESETS[auto].label}（Genreから自動）` : 'Theme / general';
  const policy = (kind: 'figure' | 'table') => preview.columns < 2 || !preview.spanPolicy ? '—' : SPAN_POLICIES[preview.spanPolicy[kind]].label;
  const bundle = PUBLICATION_PRESETS[publication.publicationPreset];
  const accent = pdfAccent(publication, design, themeSpec(design.theme), templateAccent);
  return <div className="summary-card">
    <h3>BOOK FORMAT</h3>
    <p className="summary-size"><b>{preview.pageSize === 'custom' ? 'Custom' : preview.pageSize}</b> {preview.widthMm} × {preview.heightMm} mm{preview.orientation === 'landscape' ? '（横）' : ''}</p>
    <dl>
      <dt>Preset</dt><dd>{bundle ? bundle.label + (deviations.length ? `（変更: ${deviations.join(', ')}）` : '') : '個別設定'}</dd>
      <dt>Layout</dt><dd>{themeMode ? 'Theme default' : publication.layoutPreset === 'custom' ? 'Custom' : LAYOUT_PRESETS[publication.layoutPreset].label + (layoutModified ? '（変更あり）' : '')}</dd>
      <dt>Columns</dt><dd>{preview.columns}{preview.columns > 1 ? ` · 1段 ${preview.columnWidthMm} mm · 段間 ${preview.gutterMm} mm` : ''}</dd>
      <dt>Body</dt><dd>{preview.bodyWidthMm} × {preview.bodyHeightMm} mm</dd>
      <dt>Margins</dt><dd>天 {preview.margins.top} · 地 {preview.margins.bottom} · ノド {preview.margins.inner} · 小口 {preview.margins.outer} mm</dd>
      <dt>Spans</dt><dd>図 {policy('figure')} · 表 {policy('table')}</dd>
      <dt>Theme</dt><dd>{themeNames[design.theme]}</dd>
      <dt>Accent</dt><dd><span className="swatch" style={{ background: accent }} />PDF {accent.toUpperCase()}{accent.toLowerCase() !== design.accent.toLowerCase() ? <> · <span className="swatch" style={{ background: design.accent }} />Web {design.accent.toUpperCase()}</> : ''}</dd>
      <dt>Type</dt><dd>{design.bodyJapanese} {design.bodySize}pt / 見出し {design.headingJapanese}</dd>
      <dt>Genre</dt><dd>{publication.genre === 'auto' ? 'general' : publication.genre}</dd>
      <dt>Tier</dt><dd>{publication.tier === 'auto' ? `${autoTier(targetPages)}（${targetPages}ページから自動）` : `${publication.tier}（手動）`}</dd>
      <dt>PDF style</dt><dd>{style}</dd>
      <dt>Outputs</dt><dd>{Object.entries(outputs).filter(([, on]) => on).map(([key]) => OUTPUT_LABELS[key] ?? key).join(' · ')}</dd>
    </dl>
    <small>判型・段組みの値は共有プリセット（schemas/publication-presets.json）から計算した見込みです。ジョブ実行時に BookOrder の resolver が同じ規則で確定・検証します。</small>
  </div>;
}

/** CSS schematic of the page. Not a layout engine: Typst output is the authority. */
export function SchematicPreview({ preview }: { preview: LayoutPreview }) {
  const w = preview.widthMm, h = preview.heightMm;
  if (!(w > 0 && h > 0)) return null;
  const pct = (value: number, total: number) => `${Math.max(0, (value / total) * 100)}%`;
  const m = preview.margins; const ok = preview.bodyWidthMm > 0 && preview.bodyHeightMm > 0;
  const gap = { columnGap: pct(preview.columns > 1 ? preview.gutterMm : 0, preview.bodyWidthMm) };
  return <figure className="schematic" aria-label="schematic page preview">
    <div className="schematic-page" style={{ aspectRatio: `${w} / ${h}` }}>
      {ok && <div className="schematic-body" style={{ top: pct(m.top, h), bottom: pct(m.bottom, h), left: pct(m.inner, w), right: pct(m.outer, w) }}>
        <div className="schematic-opener">Chapter opener</div>
        <div className="schematic-columns" style={gap}>{Array.from({ length: preview.columns }, (_, i) => <div key={i} className="schematic-column">{Array.from({ length: 5 }, (_, j) => <span key={j} />)}</div>)}</div>
        {preview.columns > 1 && <div className="schematic-span">full-width span</div>}
        <div className="schematic-columns" style={gap}>{Array.from({ length: preview.columns }, (_, i) => <div key={i} className="schematic-column">{Array.from({ length: 4 }, (_, j) => <span key={j} />)}</div>)}</div>
      </div>}
    </div>
    <figcaption>Schematic preview — 比率・余白・段・段間の模式図です（右ページ想定：左がノド）。正確な組版は Typst の出力が正です。</figcaption>
  </figure>;
}

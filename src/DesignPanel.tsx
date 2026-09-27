import { themeNames, type DesignOptions } from './design';
import { designDefaults } from './design-presets';
import { themePreviews } from './templates';

export function DesignPanel({ value, onChange }: { value: DesignOptions; onChange: (value: DesignOptions) => void }) {
  const update = <K extends keyof DesignOptions>(key: K, next: DesignOptions[K]) => onChange({ ...value, [key]: next });
  const font = (label: string, key: 'bodyJapanese' | 'bodyLatin' | 'headingJapanese' | 'headingLatin' | 'codeFont' | 'captionFont' | 'footnoteFont') => <label>{label}<input list="design-fonts" value={value[key]} onChange={event => update(key, event.target.value)} /></label>;
  const size = (label: string, key: 'bodySize' | 'codeSize' | 'captionSize' | 'footnoteSize') => <label>{label}<input type="number" min={5} max={40} step={0.5} value={value[key]} onChange={event => update(key, Number(event.target.value))} /></label>;
  return <section><div className="section-heading"><span>05</span><h2>書籍のデザイン</h2></div>
    <p>内容と独立したDesign Specとして保存し、PDF・Web・EPUB・DOCXで共有します。</p>
    <details><summary>テーマの誌面サンプルを見る</summary><div className="theme-samples">{Object.entries(themeNames).map(([id, label]) => <figure key={id}><img src={themePreviews[`../job-template/themes/${id}/preview.png`]} alt={`${label}のPDF誌面`} loading="lazy" /><figcaption>{label}</figcaption></figure>)}</div><small>同じ原稿から生成したPDFの例です。実行環境のフォントによって見た目は変わります。</small></details>
    <div className="row"><label>Theme<select value={value.theme} onChange={event => onChange({ ...designDefaults(event.target.value), customCss: value.customCss, artDirection: value.artDirection })}>{Object.entries(themeNames).map(([id, label]) => <option value={id} key={id}>{label}</option>)}</select><small>テーマ変更で書体・余白・誌面部品の初期設定を切り替えます。</small></label>
      <label>Page size<select value={value.pageSize} onChange={event => update('pageSize', event.target.value)}>{['A5', 'B5', 'A4', 'Letter'].map(size => <option key={size}>{size}</option>)}</select></label></div>
    <div className="row">{font('Body · 日本語', 'bodyJapanese')}{font('Heading · 日本語', 'headingJapanese')}</div>
    <div className="row">{font('Code', 'codeFont')}<label>Density<select value={value.density} onChange={event => update('density', event.target.value)}><option value="compact">Compact</option><option value="standard">Standard</option><option value="spacious">Spacious</option></select></label></div>
    <div className="row"><label>Accent color<input type="color" value={value.accent} onChange={event => update('accent', event.target.value)} /></label><label>Chapter style<select value={value.chapterStyle} onChange={event => update('chapterStyle', event.target.value)}><option value="editorial">Editorial</option><option value="academic">Academic</option><option value="minimal">Minimal</option></select></label></div>
    <div className="row"><label>Figures<select value={value.figureStyle} onChange={event => update('figureStyle', event.target.value)}><option value="technical">Technical</option><option value="monochrome">Monochrome</option></select></label><label>Tables<select value={value.tableStyle} onChange={event => update('tableStyle', event.target.value)}><option value="minimal-horizontal">Minimal horizontal</option><option value="grid">Grid</option><option value="striped">Striped</option></select></label></div>
    <label>Callouts<select value={value.calloutStyle} onChange={event => update('calloutStyle', event.target.value)}><option value="border">Border</option><option value="card">Card</option><option value="plain">Plain</option></select></label>
    <datalist id="design-fonts">{['Noto Serif CJK JP', 'Noto Sans JP', 'Source Serif 4', 'Inter', 'JetBrains Mono', 'Noto Sans CJK JP', 'Noto Serif JP', 'Yu Mincho', 'Yu Gothic', 'Hiragino Mincho ProN', 'Hiragino Sans', 'Courier New'].map(font => <option key={font} value={font} />)}</datalist>
    <small>Noto Serif CJK JP・Noto Sans JP・Source Serif 4・Inter・JetBrains Mono は実行環境に同梱されます（SIL OFL）。その他の候補はAgentのマシンに存在するとは限りません。実行環境の一覧は <code>bookorder fonts</code> で取得し、PDFでの代替先はdesign-report.jsonに記録します。追加フォントは利用・埋め込み・再配布条件を確認してください。</small>
    <details><summary>Advanced · Typography / CSS</summary>
      <div className="row">{font('Body · Latin', 'bodyLatin')}{font('Heading · Latin', 'headingLatin')}</div>
      <div className="row">{size('Body size · pt', 'bodySize')}{size('Code size · pt', 'codeSize')}</div>
      <div className="row">{font('Caption font', 'captionFont')}{size('Caption size · pt', 'captionSize')}</div>
      <div className="row">{font('Footnote font', 'footnoteFont')}{size('Footnote size · pt', 'footnoteSize')}</div>
      <div className="row"><label>Body weight<select value={value.bodyWeight} onChange={event => update('bodyWeight', Number(event.target.value))}><option value={400}>400</option><option value={500}>500</option></select></label><label>Heading weight<select value={value.headingWeight} onChange={event => update('headingWeight', Number(event.target.value))}><option value={600}>600</option><option value={700}>700</option><option value={800}>800</option></select></label></div>
      <label>Orientation<select value={value.orientation} onChange={event => update('orientation', event.target.value)}><option value="portrait">Portrait</option><option value="landscape">Landscape</option></select></label>
      <label>custom.css<textarea rows={6} value={value.customCss} onChange={event => update('customCss', event.target.value)} placeholder="例：.warning { border-left-width: 4px; }" /><small>Web・HTML・EPUBのテーマCSSの最後に読み込みます。Typst PDFには適用しません。CSS内の外部URLは閲覧時の通信を発生させる場合があります。</small></label>
    </details>
    <label>Additional art direction<textarea rows={4} value={value.artDirection} onChange={event => update('artDirection', event.target.value)} placeholder="本文は明朝、見出しは太めのゴシック。重要事項だけ囲み記事にし、章扉は大胆すぎず編集的に。" /><small>Agentは可能な限りDesign Specを更新し、表現できない部分だけCSS / Typstの追加設定を使います。</small></label>
  </section>;
}

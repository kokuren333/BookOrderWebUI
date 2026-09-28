// Design Spec controls (book.design.yaml) used inside the "Publication & design" panel.
// Each concept has exactly one control. Where a Design Spec value also has a StyleBible counterpart (density,
// chapter opener, accent) the Design Spec value is the authority and the StyleBible request is derived from it
// (publication.designStyleLinks) — there is no second control for the same thing.
import type { ReactNode } from 'react';
import { themeNames, type DesignOptions } from './design';
import { themePreviews } from './templates';
import { publicationPresets, STYLE_PRESETS, genreStylePreset, type PublicationOptions, type StyleControlName } from './publication';

type Design = { value: DesignOptions; onChange: (value: DesignOptions) => void };
const FONTS = ['Noto Serif CJK JP', 'Noto Sans JP', 'Source Serif 4', 'Inter', 'JetBrains Mono', 'Noto Sans CJK JP', 'Noto Serif JP', 'Yu Mincho', 'Yu Gothic', 'Hiragino Mincho ProN', 'Hiragino Sans', 'Courier New'];
const CONTROLS = publicationPresets.style_controls as Record<StyleControlName, { label: string; options: Record<string, { label: string }> }>;

export function themePreviewUrl(theme: string): string | undefined { return themePreviews[`../job-template/themes/${theme}/preview.png`]; }

export function ThemeSamples() {
  return <details><summary>テーマの誌面サンプルを見る</summary><div className="theme-samples">{Object.entries(themeNames).map(([id, label]) => <figure key={id}><img src={themePreviewUrl(id)} alt={`${label}のPDF誌面`} loading="lazy" /><figcaption>{label}</figcaption></figure>)}</div><small>同じ原稿から生成したPDFの例です。実行環境のフォントによって見た目は変わります。</small></details>;
}

export function TypographyControls({ value, onChange }: Design) {
  const update = <K extends keyof DesignOptions>(key: K, next: DesignOptions[K]) => onChange({ ...value, [key]: next });
  const font = (label: string, key: 'bodyJapanese' | 'bodyLatin' | 'headingJapanese' | 'headingLatin' | 'codeFont' | 'captionFont' | 'footnoteFont') => <label>{label}<input list="design-fonts" value={value[key]} onChange={event => update(key, event.target.value)} /></label>;
  const size = (label: string, key: 'bodySize' | 'codeSize' | 'captionSize' | 'footnoteSize') => <label>{label}<input type="number" min={5} max={40} step={0.5} value={value[key]} onChange={event => update(key, Number(event.target.value))} /></label>;
  return <>
    <div className="row">{font('Body · 日本語', 'bodyJapanese')}{font('Body · Latin', 'bodyLatin')}</div>
    <div className="row">{font('Heading · 日本語', 'headingJapanese')}{font('Heading · Latin', 'headingLatin')}</div>
    <div className="row">{font('Code', 'codeFont')}{font('Caption font', 'captionFont')}</div>
    <div className="row">{font('Footnote font', 'footnoteFont')}{size('Body size · pt', 'bodySize')}</div>
    <div className="row">{size('Code size · pt', 'codeSize')}{size('Caption size · pt', 'captionSize')}</div>
    <div className="row">{size('Footnote size · pt', 'footnoteSize')}<label>Body weight<select value={value.bodyWeight} onChange={event => update('bodyWeight', Number(event.target.value))}><option value={400}>400</option><option value={500}>500</option></select></label></div>
    <label>Heading weight<select value={value.headingWeight} onChange={event => update('headingWeight', Number(event.target.value))}><option value={600}>600</option><option value={700}>700</option><option value={800}>800</option></select></label>
    <datalist id="design-fonts">{FONTS.map(name => <option key={name} value={name} />)}</datalist>
    <small>Noto Serif CJK JP・Noto Sans JP・Source Serif 4・Inter・JetBrains Mono は実行環境に同梱されます（SIL OFL）。その他の候補はAgentのマシンに存在するとは限りません。実行環境の一覧は <code>bookorder fonts</code> で取得し、PDFでの代替先はdesign-report.jsonに記録します。見出し・図表ラベルなど他の文字サイズは、ここで指定した大きさから自動で算出されます。</small>
  </>;
}

type Grammar = Design & { publication: PublicationOptions; onPublication: (value: PublicationOptions) => void };
export function VisualGrammarControls({ value, onChange, publication, onPublication }: Grammar) {
  const update = <K extends keyof DesignOptions>(key: K, next: DesignOptions[K]) => onChange({ ...value, [key]: next });
  const control = (name: StyleControlName) => <select value={publication.styleControls[name] ?? 'default'} onChange={event => onPublication({ ...publication, styleControls: { ...publication.styleControls, [name]: event.target.value } })}>
    <option value="default">Style preset default</option>{Object.entries(CONTROLS[name].options).map(([id, option]) => <option key={id} value={id}>{option.label}</option>)}</select>;
  const auto = publication.genre !== 'auto' ? genreStylePreset(publication.genre) : undefined;
  return <>
    {value.theme !== 'modern-technical' && <p className="note">現在のテーマ（{themeNames[value.theme]}）のPDFが使う StyleBible は配色・図解の描き方・表の数値揃えなど一部だけです。「(PDF)」の付いた項目や、見出し・線・余白・囲みの StyleBible 表現が PDF に効くのは Modern Technical テーマです。</p>}
    <label>PDF style preset (StyleBible)<select value={publication.stylePreset} onChange={event => onPublication({ ...publication, stylePreset: event.target.value })}>
      <option value="auto">Automatic · Genreに従う{auto ? `（${STYLE_PRESETS[auto].label}）` : '（theme / general）'}</option>
      {Object.entries(STYLE_PRESETS).map(([id, preset]) => <option key={id} value={id}>{preset.label}</option>)}</select>
      <small>PDFの図表・囲み・見出しの意味的な扱い（StyleBible）の出発点です。テーマ（書体・色）とは独立しています。</small></label>
    <div className="row">
      <label>Density<select value={value.density} onChange={event => update('density', event.target.value)}><option value="compact">Compact</option><option value="standard">Standard</option><option value="spacious">Spacious</option></select><small>全出力の行間・余白感。テーマ既定から変えるとPDFのStyleBible密度にも反映します。</small></label>
      <label>Accent color<input type="color" value={value.accent} onChange={event => update('accent', event.target.value)} /><small>テーマ既定から変えると、PDFスタイルプリセットの色より優先します。</small></label>
    </div>
    <div className="row">
      <label>Chapter opener<select value={value.chapterStyle} onChange={event => update('chapterStyle', event.target.value)}><option value="editorial">Editorial</option><option value="academic">Academic</option><option value="minimal">Minimal</option></select><small>章扉。テーマ既定から変えるとPDFのStyleBibleにも同じ値を渡します。</small></label>
      <label>Figures<select value={value.figureStyle} onChange={event => update('figureStyle', event.target.value)}><option value="technical">Technical</option><option value="monochrome">Monochrome</option></select><small>図版の配色。作るかどうかは「03」、配置は Geometry で設定します。</small></label>
    </div>
    <Group title="Tables">
      <label>Rules<select value={value.tableStyle} onChange={event => update('tableStyle', event.target.value)}><option value="minimal-horizontal">Minimal horizontal</option><option value="grid">Grid</option><option value="striped">Striped</option></select></label>
      <label>Row density (PDF){control('table_density')}</label>
    </Group>
    <Group title="Callouts">
      <label>Frame<select value={value.calloutStyle} onChange={event => update('calloutStyle', event.target.value)}><option value="border">Border</option><option value="card">Card</option><option value="plain">Plain</option></select></label>
      <label>Emphasis (PDF){control('callout_intensity')}</label>
    </Group>
  </>;
}
function Group({ title, children }: { title: string; children: ReactNode }) {
  return <fieldset className="control-group"><legend>{title}</legend><div className="row">{children}</div></fieldset>;
}

export function ExpertControls({ value, onChange, publication, onPublication }: Grammar) {
  return <>
    <label>Visual tone (StyleBible)<select value={publication.styleControls.visual_tone ?? 'default'} onChange={event => onPublication({ ...publication, styleControls: { ...publication.styleControls, visual_tone: event.target.value } })}>
      <option value="default">Style preset default</option>{Object.entries(CONTROLS.visual_tone.options).map(([id, option]) => <option key={id} value={id}>{option.label}</option>)}</select>
      <small>低レベルのStyleBible tokenは、ジョブ内の plan/style-bible.yaml（project.json style_bible）で編集できます。</small></label>
    <label>Art direction<textarea rows={4} value={value.artDirection} onChange={event => onChange({ ...value, artDirection: event.target.value })} placeholder="本文は明朝、見出しは太めのゴシック。重要事項だけ囲み記事にし、章扉は大胆すぎず編集的に。" /><small>StyleBibleの tone に記録される誌面の方向性です。上の構造化設定と矛盾する場合は構造化設定が優先されます。</small></label>
    <label>custom.css<textarea rows={6} value={value.customCss} onChange={event => onChange({ ...value, customCss: event.target.value })} placeholder="例：.warning { border-left-width: 4px; }" /><small>Web・HTML・EPUBのテーマCSSの最後に読み込みます。Typst PDFには適用しません。CSS内の外部URLは閲覧時の通信を発生させる場合があります。</small></label>
  </>;
}

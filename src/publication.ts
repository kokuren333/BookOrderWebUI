// Publication & design settings frontend model.
//
// Resolution order (later wins), mirrored by the job's resolvers:
//   Layout (LayoutSpec):  theme page/margins (Design Spec)  <  layout preset  <  explicit geometry edits (layout_spec patch)
//   Scale (Profile):      target scale (book.target_pages) -> automatic tier  <  explicit tier override
//   PDF appearance:       theme tokens (Design Spec)  <  style template (style_preset, else genre)  <  profile art direction
//                         <  style_controls (incl. values derived from explicit Visual grammar edits)  <  style_bible (explicit accent)
//   Free-text instructions supplement the structured settings; structured settings are authoritative.
// A "publication preset" only fills genre + layout preset + style preset + theme at once; it writes nothing of its own.
//
// The WebUI is an input frontend for the job's existing resolvers (PublicationProfile, LayoutSpec, StyleBible).
// It never becomes the source of truth: `publicationPayload` only writes the project.json request fields those
// resolvers already read (`profile`, `layout_preset`, `layout_spec`, `style_preset`, `style_controls`).
// Presets, page sizes and limits come from job-template/schemas/publication-presets.json, the same file the Python
// resolvers load. `previewLayout` mirrors layout_spec.summary()/geometry_issues() for the live summary and early
// warnings; `bookorder publication` / the orchestrator remain the final authority (a parity test keeps them equal).
import presets from '../job-template/schemas/publication-presets.json' with { type: 'json' };
import type { DesignOptions } from './design.ts';

export type PageSize = 'A4' | 'A5' | 'B5' | 'B6' | 'Letter' | 'custom';
export type SpanPolicy = 'auto' | 'column' | 'full';
export type WritingMode = 'horizontal-tb' | 'vertical-rl';
export type Orientation = 'portrait' | 'landscape';
export type StyleControlName = keyof typeof presets.style_controls;
export interface Margins { top: number; bottom: number; inner: number; outer: number }
export interface PublicationOptions {
  tier: string;            // 'auto' = from target scale (resolver compatibility rule)
  genre: string;           // 'auto' = general
  publicationPreset: string; // 'none' or a publication_presets id (UI bundle: genre + layout + style + theme)
  layoutPreset: string;    // 'theme' = Design Spec defaults (unchanged behaviour), a preset id, or 'custom'
  // The single authority for page size and orientation. 'theme' = follow the selected theme's Design Spec page.
  pageSize: PageSize | 'theme'; customWidthMm: number; customHeightMm: number; orientation: Orientation | 'theme';
  columns: 1 | 2; gutterMm: number; margins: Margins; writingMode: WritingMode;
  figureSpan: SpanPolicy; tableSpan: SpanPolicy;
  stylePreset: string;     // 'auto' = follow genre
  styleControls: Partial<Record<StyleControlName, string>>;
}
export interface LayoutIssue { code: string; field: string; message: string }
export interface LayoutPreview {
  source: 'theme' | 'preset' | 'custom'; pageSize: string; orientation: string; widthMm: number; heightMm: number;
  columns: number; gutterMm: number; bodyWidthMm: number; bodyHeightMm: number; columnWidthMm: number;
  margins: Margins; writingMode: WritingMode; spanPolicy: { figure: SpanPolicy; table: SpanPolicy } | null;
  issues: LayoutIssue[];
}

export const publicationPresets = presets;
export const LIMITS = presets.limits;
export const PAGE_SIZES = presets.page_sizes as unknown as Record<string, [number, number]>;
export const LAYOUT_PRESETS = presets.layout_presets as Record<string, { label: string; description: string; layout: PresetLayout }>;
export const PUBLICATION_PRESETS = presets.publication_presets as Record<string, { label: string; description: string; genre: string | null; layout: string; style: string | null; theme: string }>;
export const TIER_RULE = presets.tier_from_pages as unknown as { bounds: [number, string][]; above: string; default: string };
export const DESIGN_PAGE_SIZES = ['A5', 'B5', 'A4', 'Letter'];  // sizes the Design Spec schema accepts
export const STYLE_PRESETS = presets.style_presets as Record<string, { label: string; template: string }>;
export const SPAN_POLICIES = presets.span_policies as Record<SpanPolicy, { label: string; description: string }>;
export const WRITING_MODES = presets.writing_modes as Record<WritingMode, { label: string; typst: boolean; reason?: string }>;
interface PresetLayout {
  page_size: string; orientation: string; writing_mode: string;
  page: { margin_top_mm: number; margin_bottom_mm: number; margin_inner_mm: number; margin_outer_mm: number; width_mm?: number; height_mm?: number };
  body: { columns: number; gutter_mm: number }; span_policy?: { figure: SpanPolicy; table: SpanPolicy };
}

// LayoutSpec defaults when project.json asks for nothing (layout_spec.defaults): 1 column, 6 mm gutter.
const DEFAULT_GUTTER = 6;
export const defaultPublication: PublicationOptions = {
  tier: 'auto', genre: 'auto', publicationPreset: 'none', layoutPreset: 'theme',
  pageSize: 'theme', customWidthMm: 182, customHeightMm: 257, orientation: 'theme',
  columns: 1, gutterMm: DEFAULT_GUTTER, margins: { top: 18, bottom: 20, inner: 20, outer: 17 }, writingMode: 'horizontal-tb',
  figureSpan: 'column', tableSpan: 'column', stylePreset: 'auto', styleControls: {},
};

const mm = (value: string | number | undefined, fallback: number) => {
  const match = /^\s*([0-9.]+)\s*(mm|cm|pt|in)?\s*$/.exec(String(value ?? ''));
  if (!match) return fallback;
  const unit = (match[2] ?? 'mm') as 'mm' | 'cm' | 'pt' | 'in';
  return Math.round(parseFloat(match[1]) * { mm: 1, cm: 10, pt: 25.4 / 72, in: 25.4 }[unit] * 1000) / 1000;
};
const round2 = (value: number) => Math.round(value * 100) / 100;

/** Options that reproduce a preset exactly (what selecting it in the UI does). */
export function applyLayoutPreset(current: PublicationOptions, id: string, themePage?: ThemePage): PublicationOptions {
  if (id === 'custom') return { ...current, layoutPreset: 'custom' };
  if (id === 'theme') {
    const page = themePage ?? DEFAULT_THEME_PAGE;
    return { ...current, layoutPreset: 'theme', pageSize: 'theme', orientation: 'theme', columns: 1, gutterMm: DEFAULT_GUTTER,
      margins: themeMargins(page), writingMode: 'horizontal-tb', figureSpan: 'column', tableSpan: 'column' };
  }
  const layout = LAYOUT_PRESETS[id].layout;
  return { ...current, layoutPreset: id, pageSize: layout.page_size as PageSize, orientation: layout.orientation as 'portrait',
    columns: layout.body.columns as 1 | 2, gutterMm: layout.body.gutter_mm, writingMode: layout.writing_mode as WritingMode,
    margins: { top: layout.page.margin_top_mm, bottom: layout.page.margin_bottom_mm, inner: layout.page.margin_inner_mm, outer: layout.page.margin_outer_mm },
    figureSpan: layout.span_policy?.figure ?? 'column', tableSpan: layout.span_policy?.table ?? 'column' };
}
export interface ThemePage { size: string; orientation?: string; margin: Record<string, string | undefined> }
/** The parts of a theme's theme.yaml (Design Spec defaults) the linked settings compare against. */
export interface ThemeSpec { page: ThemePage; layout: { density: string }; components: { chapter_opener: string }; colors: { accent: string } }
export const DEFAULT_THEME_PAGE: ThemePage = { size: 'A5', orientation: 'portrait', margin: { top: '18mm', bottom: '20mm', inner: '20mm', outer: '17mm' } };

/** Actual page size / orientation: an explicit choice, else the theme's page ('theme' sentinel). */
export function resolvePage(options: PublicationOptions, themePage: ThemePage = DEFAULT_THEME_PAGE): { size: PageSize; orientation: Orientation } {
  return { size: (options.pageSize === 'theme' ? themePage.size : options.pageSize) as PageSize,
    orientation: (options.orientation === 'theme' ? (themePage.orientation ?? 'portrait') : options.orientation) as Orientation };
}
/** Options with every theme-derived value filled in: in theme mode the geometry is the Design Spec's (layout_spec.defaults). */
export function effectivePublication(options: PublicationOptions, themePage: ThemePage = DEFAULT_THEME_PAGE): PublicationOptions {
  const page = resolvePage(options, themePage);
  if (options.layoutPreset !== 'theme') return { ...options, pageSize: page.size, orientation: page.orientation };
  return { ...options, pageSize: page.size, orientation: page.orientation, columns: 1, gutterMm: DEFAULT_GUTTER, margins: themeMargins(themePage),
    writingMode: 'horizontal-tb', figureSpan: 'column', tableSpan: 'column' };
}
/** Page written to the Design Spec (book.design.yaml). Its schema only knows A5/B5/A4/Letter; B6 and custom sizes live in
 *  the LayoutSpec request and the Design Spec keeps the theme's page for the legacy CSS/HTML consumers. */
export function designPage(options: PublicationOptions, themePage: ThemePage = DEFAULT_THEME_PAGE): { size: string; orientation: Orientation } {
  const page = resolvePage(options, themePage);
  return { size: DESIGN_PAGE_SIZES.includes(page.size) ? page.size : themePage.size, orientation: page.orientation };
}
/** Tier the PublicationProfile resolver derives from book.target_pages when no tier is requested (shared rule). */
export function autoTier(pages: number): string {
  if (!pages) return TIER_RULE.default;
  return TIER_RULE.bounds.find(([bound]) => pages <= bound)?.[1] ?? TIER_RULE.above;
}
/** Selecting a publication preset fills genre, layout preset and style preset; the caller switches the theme. */
export function applyPublicationPreset(current: PublicationOptions, id: string): { publication: PublicationOptions; theme?: string } {
  const bundle = PUBLICATION_PRESETS[id];
  if (!bundle) return { publication: { ...current, publicationPreset: 'none' } };
  const publication = { ...applyLayoutPreset(current, bundle.layout), publicationPreset: id, genre: bundle.genre ?? 'auto', stylePreset: bundle.style ?? 'auto' };
  return { publication, theme: bundle.theme };
}
/** Which parts of a publication preset the user has since changed (empty = preset as selected). */
export function presetDeviations(options: PublicationOptions, theme: string): string[] {
  const bundle = PUBLICATION_PRESETS[options.publicationPreset];
  if (!bundle) return [];
  const out: string[] = [];
  if ((bundle.genre ?? 'auto') !== options.genre) out.push('genre');
  if (bundle.layout !== options.layoutPreset || publicationPayload(options).layout_spec) out.push('layout');
  if ((bundle.style ?? 'auto') !== options.stylePreset) out.push('style');
  if (bundle.theme !== theme) out.push('theme');
  return out;
}

/** Visual-grammar settings with one control in the UI but two consumers: the Design Spec value is the authority and,
 *  only when the user changed it from the theme default, the matching StyleBible request is derived so the PDF agrees. */
export const DENSITY_TO_VISUAL_DENSITY: Record<string, string> = { compact: 'compact', standard: 'balanced', spacious: 'airy' };
export function designStyleLinks(design: Pick<DesignOptions, 'density' | 'chapterStyle' | 'accent'>, theme?: ThemeSpec) {
  const controls: Record<string, string> = {}; const styleBible: Record<string, unknown> = {};
  if (!theme) return { controls, styleBible };
  if (design.density !== theme.layout.density && DENSITY_TO_VISUAL_DENSITY[design.density]) controls.visual_density = DENSITY_TO_VISUAL_DENSITY[design.density];
  if (design.chapterStyle !== theme.components.chapter_opener) controls.chapter_opener = design.chapterStyle;
  if (design.accent.toLowerCase() !== theme.colors.accent.toLowerCase()) styleBible.palette = { accent: design.accent.toUpperCase() };
  return { controls, styleBible };
}
/** Accent the PDF will use (StyleBible palette): an explicit accent, else the style template's palette accent, else the
 *  theme's. `templateAccent` looks up styles/genres/<template>.yaml. HTML/EPUB always use the Design Spec accent. */
export function pdfAccent(options: PublicationOptions, design: Pick<DesignOptions, 'accent'>, theme: ThemeSpec | undefined, templateAccent: (template: string) => string | undefined): string {
  if (theme && design.accent.toLowerCase() !== theme.colors.accent.toLowerCase()) return design.accent;
  const template = options.stylePreset !== 'auto' ? STYLE_PRESETS[options.stylePreset]?.template : options.genre !== 'auto' ? options.genre : undefined;
  return (template && templateAccent(template)) || design.accent;
}
/** Every project.json request field the WebUI writes: publication payload plus the derived visual-grammar links. */
export function requestPayload(options: PublicationOptions, design?: Pick<DesignOptions, 'density' | 'chapterStyle' | 'accent'>, theme?: ThemeSpec, themePage?: ThemePage) {
  const payload = publicationPayload(options, themePage ?? theme?.page);
  if (!design) return payload;
  const links = designStyleLinks(design, theme);
  const controls = { ...links.controls, ...((payload.style_controls as Record<string, string>) ?? {}) };
  if (Object.keys(controls).length) payload.style_controls = controls;
  if (Object.keys(links.styleBible).length) payload.style_bible = links.styleBible;
  return payload;
}
export function themeMargins(page: ThemePage): Margins {
  return { top: mm(page.margin.top, 20), bottom: mm(page.margin.bottom, 20), inner: mm(page.margin.inner, 20), outer: mm(page.margin.outer, 17) };
}

export function pageDimensions(size: string, orientation: string, customWidth?: number, customHeight?: number): [number, number] {
  if (size === 'custom') return [Number(customWidth), Number(customHeight)];
  const [w, h] = PAGE_SIZES[size] ?? PAGE_SIZES.A5;
  return orientation === 'landscape' ? [h, w] : [w, h];
}

/** The LayoutSpec request fields (layout_spec patch) the options describe, relative to a base preset. */
function layoutRequest(options: PublicationOptions) {  // options must be effective (no 'theme' sentinels)
  const [width, height] = pageDimensions(options.pageSize as string, options.orientation as string, options.customWidthMm, options.customHeightMm);
  const full: Record<string, unknown> = {
    page_size: options.pageSize, orientation: options.orientation, writing_mode: options.writingMode,
    page: { margin_top_mm: options.margins.top, margin_bottom_mm: options.margins.bottom, margin_inner_mm: options.margins.inner, margin_outer_mm: options.margins.outer,
      ...(options.pageSize === 'custom' ? { width_mm: width, height_mm: height } : {}) },
    body: { columns: options.columns, gutter_mm: options.gutterMm },
    span_policy: { figure: options.figureSpan, table: options.tableSpan },
  };
  if (options.layoutPreset === 'custom') return full;
  const base = LAYOUT_PRESETS[options.layoutPreset].layout as unknown as Record<string, unknown>;
  return diff(full, { ...base, span_policy: (base.span_policy as object) ?? { figure: 'column', table: 'column' } }) ?? {};
}
function diff(value: Record<string, unknown>, base: Record<string, unknown>): Record<string, unknown> | undefined {
  const out: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value)) {
    const other = base?.[key];
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      const nested = diff(item as Record<string, unknown>, (other ?? {}) as Record<string, unknown>);
      if (nested) out[key] = nested;
    } else if (item !== other) out[key] = item;
  }
  return Object.keys(out).length ? out : undefined;
}

/** project.json fields for the resolvers. Untouched defaults produce {} so existing jobs build exactly as before. */
export function publicationPayload(input: PublicationOptions, themePage?: ThemePage) {
  const options = effectivePublication(input, themePage);
  const payload: Record<string, unknown> = {};
  const profile: Record<string, string> = {};
  if (options.tier !== 'auto') profile.tier = options.tier;
  if (options.genre !== 'auto') profile.genre = options.genre;
  if (Object.keys(profile).length) payload.profile = profile;
  if (input.layoutPreset !== 'theme') {
    if (options.layoutPreset !== 'custom') payload.layout_preset = options.layoutPreset;
    const patch = layoutRequest(options);
    if (Object.keys(patch).length) payload.layout_spec = patch;
  }
  if (options.stylePreset !== 'auto') payload.style_preset = options.stylePreset;
  const controls = Object.fromEntries(Object.entries(options.styleControls).filter(([, value]) => value && value !== 'default'));
  if (Object.keys(controls).length) payload.style_controls = controls;
  return payload;
}

/** Live summary + early warnings. Mirrors layout_spec.summary() and geometry_issues(); BookOrder re-validates. */
export function previewLayout(input: PublicationOptions, themePage?: ThemePage): LayoutPreview {
  const options = effectivePublication(input, themePage);
  const [widthMm, heightMm] = pageDimensions(options.pageSize as string, options.orientation as string, options.customWidthMm, options.customHeightMm);
  const m = options.margins; const columns = options.columns; const gutter = options.gutterMm;
  const bodyWidth = widthMm - m.inner - m.outer; const bodyHeight = heightMm - m.top - m.bottom;
  const columnWidth = (bodyWidth - (columns > 1 ? gutter * (columns - 1) : 0)) / columns;
  const issues: LayoutIssue[] = [];
  const add = (code: string, field: string, message: string) => issues.push({ code, field, message });
  const L = LIMITS;
  if (options.pageSize === 'custom') {
    for (const [key, value] of [['width_mm', widthMm], ['height_mm', heightMm]] as const)
      if (!Number.isFinite(value) || value < L.custom_page_min_mm || value > L.custom_page_max_mm) add('custom_page_invalid', `page.${key}`, `LayoutSpec custom page ${key} ${value}mm must be between ${L.custom_page_min_mm} and ${L.custom_page_max_mm}mm`);
  }
  for (const [key, value] of Object.entries(m))
    if (!Number.isFinite(value) || value < L.margin_min_mm || value > L.margin_max_mm) add('margin_out_of_range', `page.margin_${key}_mm`, `margin ${key} must be ${L.margin_min_mm}–${L.margin_max_mm} mm`);
  if (bodyWidth <= 0) add('margins_exceed_page', 'page.margin_inner_mm', `LayoutSpec inner+outer margins (${m.inner + m.outer}mm) exceed the page width (${widthMm}mm)`);
  if (bodyHeight <= 0) add('margins_exceed_page', 'page.margin_top_mm', `LayoutSpec top+bottom margins (${m.top + m.bottom}mm) exceed the page height (${heightMm}mm)`);
  if (bodyWidth < L.min_body_width_mm) add('body_width_insufficient', 'page.margin_outer_mm', `LayoutSpec margins leave less than ${L.min_body_width_mm}mm body width (${round2(bodyWidth)}mm)`);
  if (bodyHeight < L.min_body_height_mm) add('body_height_insufficient', 'page.margin_bottom_mm', `LayoutSpec margins leave less than ${L.min_body_height_mm}mm body height (${round2(bodyHeight)}mm)`);
  if (columns > 1) {
    if (gutter * (columns - 1) >= bodyWidth) add('gutter_consumes_body', 'body.gutter_mm', 'LayoutSpec gutters consume the entire body width');
    else if (gutter < L.min_gutter_mm) add('gutter_too_small', 'body.gutter_mm', `LayoutSpec gutter ${gutter}mm is below ${L.min_gutter_mm}mm; columns would touch`);
    else if (gutter > L.max_gutter_mm) add('gutter_too_large', 'body.gutter_mm', `LayoutSpec gutter ${gutter}mm exceeds ${L.max_gutter_mm}mm`);
    if (bodyWidth > 0 && columnWidth > 0 && columnWidth < L.min_column_width_mm) add('column_too_narrow', 'body.columns', `LayoutSpec ${columns}-column body leaves ${columnWidth.toFixed(1)}mm per column (minimum ${L.min_column_width_mm}mm); the page is too narrow for ${columns} columns`);
  }
  const spanPolicy = options.layoutPreset === 'theme' ? null : { figure: options.figureSpan, table: options.tableSpan };
  if (spanPolicy && columns === 1) for (const kind of ['figure', 'table'] as const)
    if (spanPolicy[kind] === 'full') add('span_policy_single_column', `span_policy.${kind}`, `LayoutSpec span_policy.${kind}=full needs two columns; a one-column body has no column span`);
  if (!WRITING_MODES[options.writingMode]?.typst) add('vertical_unsupported', 'writing_mode', 'Current Typst renderer does not support vertical writing (writing_mode vertical-rl); choose horizontal-tb');
  return { source: options.layoutPreset === 'theme' ? 'theme' : options.layoutPreset === 'custom' ? 'custom' : 'preset',
    pageSize: options.pageSize as string, orientation: options.orientation as string, widthMm, heightMm, columns, gutterMm: columns > 1 ? gutter : 0,
    bodyWidthMm: round2(bodyWidth), bodyHeightMm: round2(bodyHeight), columnWidthMm: round2(columnWidth), margins: { ...m },
    writingMode: options.writingMode, spanPolicy, issues };
}

/** User-facing (Japanese) text for resolver issue codes, keyed by the same codes Python emits. */
export function issueText(issue: LayoutIssue, preview?: LayoutPreview): string {
  const p = preview;
  switch (issue.code) {
    case 'custom_page_invalid': return `カスタム判型の幅・高さは ${LIMITS.custom_page_min_mm}〜${LIMITS.custom_page_max_mm} mm で指定してください。`;
    case 'margin_out_of_range': return `余白は ${LIMITS.margin_min_mm}〜${LIMITS.margin_max_mm} mm で指定してください。`;
    case 'margins_exceed_page': return issue.field.includes('top') ? '天・地の余白の合計がページの高さを超えています。' : 'ノド・小口の余白の合計がページの幅を超えています。';
    case 'body_width_insufficient': return `余白が大きすぎて版面の幅が ${LIMITS.min_body_width_mm} mm 未満${p ? `（${p.bodyWidthMm} mm）` : ''}になります。ノドまたは小口の余白を減らしてください。`;
    case 'body_height_insufficient': return `余白が大きすぎて版面の高さが ${LIMITS.min_body_height_mm} mm 未満${p ? `（${p.bodyHeightMm} mm）` : ''}になります。天または地の余白を減らしてください。`;
    case 'gutter_consumes_body': return '段間（ガター）が版面の幅をすべて使ってしまいます。';
    case 'gutter_too_small': return `段間が ${LIMITS.min_gutter_mm} mm 未満だと段同士が接して読めません。`;
    case 'gutter_too_large': return `段間は ${LIMITS.max_gutter_mm} mm 以下にしてください。`;
    case 'column_too_narrow': return `この判型・余白では2段組みの1段が ${p ? p.columnWidthMm : '?'} mm になり、最小 ${LIMITS.min_column_width_mm} mm を下回ります。ページが2段組みには狭すぎます（判型を大きくする、余白や段間を減らす、または1段組みにしてください）。`;
    case 'span_policy_single_column': return '「全幅優先」の段抜き方針は2段組みでのみ使えます。';
    case 'vertical_unsupported': return '現在のTypstレンダラーは縦書きに対応していません。横書きを選んでください（横書きへ自動変換はしません）。';
    default: return issue.message;
  }
}

/** Genre → StyleBible preset the resolver uses when no preset is chosen (reverse of style_presets.template). */
export function genreStylePreset(genre: string): string | undefined {
  return Object.entries(STYLE_PRESETS).find(([, preset]) => preset.template === genre)?.[0];
}

/** A tier/genre description from the first comment line(s) of profiles/<kind>/<name>.yaml. */
export function profileDescription(yaml: string): string {
  const lines: string[] = [];
  for (const line of yaml.split(/\r?\n/)) { if (!line.startsWith('#')) break; lines.push(line.replace(/^#\s?/, '')); }
  return lines.join(' ').replace(/^(Length tier|Genre template):\s*/, '');
}

// Design Spec (book.design.yaml) options: typography, colour and component treatments of the selected theme.
// Page size and orientation are NOT here: PublicationOptions is their single authority and the Design Spec page is
// derived from it when the job is written (publication.designPage).
export interface DesignOptions {
  theme: string; density: string; accent: string;
  bodyJapanese: string; bodyLatin: string; bodySize: number; bodyWeight: number;
  headingJapanese: string; headingLatin: string; headingWeight: number;
  codeFont: string; codeSize: number; captionFont: string; captionSize: number; footnoteFont: string; footnoteSize: number;
  chapterStyle: string; figureStyle: string; tableStyle: string; calloutStyle: string; customCss: string; artDirection: string;
}
export const themeNames: Record<string, string> = { 'modern-technical': 'Modern Technical', 'academic-jp': 'Academic JP', 'medical-textbook': 'Medical Textbook', 'minimal-monochrome': 'Minimal Monochrome', 'business-reference': 'Business Reference' };
export const defaultDesign: DesignOptions = {
  theme: 'modern-technical', density: 'standard', accent: '#0891B2',
  bodyJapanese: 'Noto Serif CJK JP', bodyLatin: 'Source Serif 4', bodySize: 9.5, bodyWeight: 400,
  headingJapanese: 'Noto Sans JP', headingLatin: 'Inter', headingWeight: 700,
  codeFont: 'JetBrains Mono', codeSize: 8.3, captionFont: 'Noto Sans JP', captionSize: 7.8,
  footnoteFont: 'Noto Serif CJK JP', footnoteSize: 7.3, chapterStyle: 'editorial', figureStyle: 'technical', tableStyle: 'minimal-horizontal', calloutStyle: 'border', customCss: '', artDirection: '',
};

export function designSpec(design: DesignOptions, page: { size: string; orientation: string } = { size: 'A5', orientation: 'portrait' }) {
  return { $schema: 'schemas/design.schema.json', theme: design.theme, art_direction: design.artDirection,
    page: { size: page.size, orientation: page.orientation }, layout: { density: design.density }, colors: { accent: design.accent },
    typography: { body: { japanese: design.bodyJapanese, latin: design.bodyLatin, size: `${design.bodySize}pt`, weight: design.bodyWeight },
      heading: { japanese: design.headingJapanese, latin: design.headingLatin, weight: design.headingWeight }, code: { latin: design.codeFont, size: `${design.codeSize}pt` },
      caption: { family: design.captionFont, size: `${design.captionSize}pt` }, footnote: { family: design.footnoteFont, size: `${design.footnoteSize}pt` } },
    components: { chapter_opener: design.chapterStyle, table: design.tableStyle, callout: design.calloutStyle }, figures: { style: design.figureStyle } };
}

/** Switching theme: values the user left at the old theme's defaults take the new theme's defaults; values the user
 *  changed (accent, fonts, density, components…) and the free-text/CSS fields are kept. Explicit always beats theme. */
export function switchTheme(current: DesignOptions, currentDefaults: DesignOptions, nextDefaults: DesignOptions): DesignOptions {
  const next = { ...nextDefaults, customCss: current.customCss, artDirection: current.artDirection } as Record<string, unknown>;
  for (const key of Object.keys(nextDefaults) as (keyof DesignOptions)[]) {
    if (key === 'theme' || key === 'customCss' || key === 'artDirection') continue;
    if (current[key] !== currentDefaults[key]) next[key] = current[key];
  }
  return next as unknown as DesignOptions;
}

/** Design Spec defaults of a theme from its parsed theme.yaml (pure; the browser reads the files via design-presets). */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function designFromTheme(theme: string, t: any): DesignOptions {
  return { theme, density: t.layout.density, accent: t.colors.accent,
    bodyJapanese: t.typography.body.japanese, bodyLatin: t.typography.body.latin, bodySize: parseFloat(t.typography.body.size), bodyWeight: t.typography.body.weight,
    headingJapanese: t.typography.heading.japanese, headingLatin: t.typography.heading.latin, headingWeight: t.typography.heading.weight,
    codeFont: t.typography.code.latin, codeSize: parseFloat(t.typography.code.size), captionFont: t.typography.caption.japanese, captionSize: parseFloat(t.typography.caption.size),
    footnoteFont: t.typography.footnote.japanese, footnoteSize: parseFloat(t.typography.footnote.size), chapterStyle: t.components.chapter_opener,
    figureStyle: t.figures.style, tableStyle: t.components.table, calloutStyle: t.components.callout, customCss: '', artDirection: '' };
}

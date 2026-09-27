export interface DesignOptions {
  theme: string; pageSize: string; orientation: string; density: string; accent: string;
  bodyJapanese: string; bodyLatin: string; bodySize: number; bodyWeight: number;
  headingJapanese: string; headingLatin: string; headingWeight: number;
  codeFont: string; codeSize: number; captionFont: string; captionSize: number; footnoteFont: string; footnoteSize: number;
  chapterStyle: string; figureStyle: string; tableStyle: string; calloutStyle: string; customCss: string; artDirection: string;
}
export const themeNames: Record<string, string> = { 'modern-technical': 'Modern Technical', 'academic-jp': 'Academic JP', 'medical-textbook': 'Medical Textbook', 'minimal-monochrome': 'Minimal Monochrome', 'business-reference': 'Business Reference' };
export const defaultDesign: DesignOptions = {
  theme: 'modern-technical', pageSize: 'A5', orientation: 'portrait', density: 'standard', accent: '#0891B2',
  bodyJapanese: 'Noto Serif CJK JP', bodyLatin: 'Source Serif 4', bodySize: 9.5, bodyWeight: 400,
  headingJapanese: 'Noto Sans JP', headingLatin: 'Inter', headingWeight: 700,
  codeFont: 'JetBrains Mono', codeSize: 8.3, captionFont: 'Noto Sans JP', captionSize: 7.8,
  footnoteFont: 'Noto Serif CJK JP', footnoteSize: 7.3, chapterStyle: 'editorial', figureStyle: 'technical', tableStyle: 'minimal-horizontal', calloutStyle: 'border', customCss: '', artDirection: '',
};

export function designSpec(design: DesignOptions) {
  return { $schema: 'schemas/design.schema.json', theme: design.theme, art_direction: design.artDirection,
    page: { size: design.pageSize, orientation: design.orientation }, layout: { density: design.density }, colors: { accent: design.accent },
    typography: { body: { japanese: design.bodyJapanese, latin: design.bodyLatin, size: `${design.bodySize}pt`, weight: design.bodyWeight },
      heading: { japanese: design.headingJapanese, latin: design.headingLatin, weight: design.headingWeight }, code: { latin: design.codeFont, size: `${design.codeSize}pt` },
      caption: { family: design.captionFont, size: `${design.captionSize}pt` }, footnote: { family: design.footnoteFont, size: `${design.footnoteSize}pt` } },
    components: { chapter_opener: design.chapterStyle, table: design.tableStyle, callout: design.calloutStyle }, figures: { style: design.figureStyle } };
}

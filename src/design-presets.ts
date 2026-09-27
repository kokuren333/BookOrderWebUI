import type { DesignOptions } from './design';
const specs = import.meta.glob('../job-template/themes/*/theme.yaml', { eager: true, query: '?raw', import: 'default' });
export function designDefaults(theme = 'modern-technical'): DesignOptions {
  const spec = JSON.parse(specs[`../job-template/themes/${theme}/theme.yaml`] as string);
  return { theme, pageSize: spec.page.size, orientation: spec.page.orientation, density: spec.layout.density, accent: spec.colors.accent,
    bodyJapanese: spec.typography.body.japanese, bodyLatin: spec.typography.body.latin, bodySize: parseFloat(spec.typography.body.size), bodyWeight: spec.typography.body.weight,
    headingJapanese: spec.typography.heading.japanese, headingLatin: spec.typography.heading.latin, headingWeight: spec.typography.heading.weight,
    codeFont: spec.typography.code.latin, codeSize: parseFloat(spec.typography.code.size), captionFont: spec.typography.caption.japanese, captionSize: parseFloat(spec.typography.caption.size),
    footnoteFont: spec.typography.footnote.japanese, footnoteSize: parseFloat(spec.typography.footnote.size), chapterStyle: spec.components.chapter_opener,
    figureStyle: spec.figures.style, tableStyle: spec.components.table, calloutStyle: spec.components.callout, customCss: '', artDirection: '' };
}

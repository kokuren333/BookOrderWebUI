import { designFromTheme, type DesignOptions } from './design';
import type { ThemePage, ThemeSpec } from './publication';
const specs = import.meta.glob('../job-template/themes/*/theme.yaml', { eager: true, query: '?raw', import: 'default' });
const spec = (theme: string) => JSON.parse(specs[`../job-template/themes/${theme}/theme.yaml`] as string);

/** Design Spec defaults of a theme (theme.yaml). Page size/orientation stay with PublicationOptions. */
export function designDefaults(theme = 'modern-technical'): DesignOptions { return designFromTheme(theme, spec(theme)); }
/** A theme's page settings — the Design Spec defaults LayoutSpec starts from when nothing is requested. */
export function themePage(theme = 'modern-technical'): ThemePage {
  const t = spec(theme);
  return { size: t.page.size, orientation: t.page.orientation, margin: t.page.margin };
}
/** The theme.yaml values the linked visual-grammar settings compare against. */
export function themeSpec(theme = 'modern-technical'): ThemeSpec {
  const t = spec(theme);
  return { page: themePage(theme), layout: { density: t.layout.density }, components: { chapter_opener: t.components.chapter_opener }, colors: { accent: t.colors.accent } };
}

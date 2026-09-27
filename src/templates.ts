const entries = import.meta.glob(['../job-template/**/*', '!../job-template/**/*.png'], { eager: true, query: '?raw', import: 'default' });
export const templates = Object.fromEntries(Object.entries(entries).map(([path, value]) => [path.replace('../job-template/', ''), value as string]));
export const themePreviews = import.meta.glob('../job-template/themes/*/preview.png', { eager: true, query: '?url', import: 'default' }) as Record<string, string>;
export async function loadTemplates(): Promise<Record<string, string | Uint8Array>> {
  const output: Record<string, string | Uint8Array> = { ...templates };
  await Promise.all(Object.entries(themePreviews).map(async ([path, url]) => {
    const response = await fetch(url);
    if (!response.ok) throw new Error('テーマプレビューの読み込みに失敗しました');
    output[path.replace('../job-template/', '')] = new Uint8Array(await response.arrayBuffer());
  }));
  return output;
}

// Test helper: drive the real WebUI modules (src/job.ts, src/publication.ts) from Python tests.
//   node --experimental-strip-types tests/webui_cli.ts zip '<json>' out.zip   -> job ZIP exactly as the WebUI generates it
//   node --experimental-strip-types tests/webui_cli.ts preview '<json-list>'  -> previewLayout() for each case (parity)
// <json>: {"preset": "<layout preset id | theme | custom>", "publication": {...PublicationOptions overrides}, "form": {...}}
import { readdir, readFile, writeFile } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { defaults, generateJob, projectData, templateTheme, validateForm } from '../src/job.ts';
import { applyLayoutPreset, applyPublicationPreset, defaultPublication, previewLayout, publicationPayload, type PublicationOptions } from '../src/publication.ts';
import { designFromTheme, defaultDesign, type DesignOptions } from '../src/design.ts';

async function templateFiles(dir = 'job-template'): Promise<Record<string, string | Uint8Array>> {
  const output: Record<string, string | Uint8Array> = {};
  async function scan(path: string) {
    for (const entry of await readdir(path, { withFileTypes: true })) {
      const full = join(path, entry.name);
      if (entry.isDirectory()) await scan(full);
      else output[relative(dir, full).replaceAll('\\', '/')] = entry.name.endsWith('.png') ? new Uint8Array(await readFile(full)) : await readFile(full, 'utf8');
    }
  }
  await scan(dir); return output;
}
let presetTheme: string | undefined;
export function options(spec: { publicationPreset?: string; preset?: string; publication?: Partial<PublicationOptions> }): PublicationOptions {
  let value = structuredClone(defaultPublication);
  if (spec.publicationPreset) { const applied = applyPublicationPreset(value, spec.publicationPreset); value = applied.publication; presetTheme = applied.theme; }
  if (spec.preset && spec.preset !== 'theme') value = applyLayoutPreset(value, spec.preset);
  return { ...value, ...(spec.publication ?? {}) } as PublicationOptions;
}
/** Theme defaults as the WebUI's theme selector applies them (theme.yaml), plus explicit Design Spec edits. */
async function design(spec: { theme?: string; design?: Partial<DesignOptions> }, fallback?: string): Promise<DesignOptions> {
  const theme = spec.theme ?? fallback;
  const base = theme ? designFromTheme(theme, JSON.parse(await readFile(`job-template/themes/${theme}/theme.yaml`, 'utf8'))) : structuredClone(defaultDesign);
  return { ...base, ...(spec.design ?? {}) };
}
const [command, arg, out] = process.argv.slice(2);
if (command === 'zip') {
  const spec = JSON.parse(arg);
  const form = { ...structuredClone(defaults), runtimeTarget: 'none' as const, title: 'WebUI publication test', description: 'P1-UI payload', targetReaders: 'Editors',
    ...(spec.form ?? {}), publication: options(spec) };
  form.design = await design(spec, presetTheme);
  const errors = validateForm(form);
  if (errors.length) { console.log(JSON.stringify({ ok: false, errors })); process.exit(2); }
  const templates = await templateFiles();
  const result = await generateJob(form, [], templates);
  await writeFile(out, result.data);
  console.log(JSON.stringify({ ok: true, payload: publicationPayload(form.publication), project: projectData(form, [], [], templateTheme(templates, form.design.theme)) }));
} else if (command === 'preview') {
  console.log(JSON.stringify((JSON.parse(arg) as { preset?: string; publication?: Partial<PublicationOptions> }[]).map(spec => {
    const value = options(spec);
    return { payload: publicationPayload(value), preview: previewLayout(value) };
  })));
} else { console.error('usage: webui_cli.ts zip|preview ...'); process.exit(1); }

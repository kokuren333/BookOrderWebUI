import { readFile, readdir, writeFile, mkdir } from 'node:fs/promises';
import { relative, join } from 'node:path';
import { defaults, generateJob } from '../src/job.ts';
import { loadRuntime, runtimeCatalog } from '../src/runtime.ts';
const templates = {};
async function scan(dir) {
  for (const item of await readdir(dir, { withFileTypes: true })) {
    const full = join(dir, item.name);
    if (item.isDirectory()) await scan(full);
    else templates[relative('job-template', full).replaceAll('\\', '/')] = item.name.endsWith('.png') ? new Uint8Array(await readFile(full)) : await readFile(full, 'utf8');
  }
}
await scan('job-template');
const fetcher = async url => new Response(await readFile('public/' + url));
const catalog = await runtimeCatalog('', fetcher);
const runtime = await loadRuntime('windows-x64', catalog, '', console.log, fetcher);
const form = { ...structuredClone(defaults), title: 'Test Technical Book', description: 'AI Agent architectureを解説する技術書', targetReaders: 'Software engineers', targetPages: 50, urls: 'https://pandoc.org/MANUAL.html\nhttps://typst.app/docs/', outputs: { ...defaults.outputs, epub: true } };
const files = await Promise.all(['reference-1.pdf', 'reference-2.pdf', 'notes.md'].map(async name => { const data = new Uint8Array(await readFile('tests/fixtures/' + name)); return { name, data, size: data.length }; }));
const job = await generateJob(form, files, templates, undefined, runtime);
await mkdir('.test-output', { recursive: true });
await writeFile('.test-output/portable-job.zip', job.data);
console.log('Portable fixture ZIP:', job.data.length, 'bytes');

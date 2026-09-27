import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
const root = new URL('../public/runtimes/', import.meta.url);
const catalog = JSON.parse(await readFile(new URL('catalog.json', root), 'utf8').catch(() => { throw new Error('Runtime assets are missing. Run npm run prepare:runtimes before building.'); }));
if (catalog.format_version !== '1' || catalog.platforms.length !== 5) throw new Error('Incomplete runtime catalogue');
for (const pack of [catalog.shared, ...catalog.platforms.map(p => p.pack)]) {
  const whole = createHash('sha256'); let bytes = 0;
  for (const part of pack.parts) {
    if (!/^[a-z0-9-]+\.\d{3}\.bin$/.test(part.file)) throw new Error('Invalid asset path');
    const data = await readFile(new URL(part.file, root));
    if (data.length !== part.bytes || createHash('sha256').update(data).digest('hex') !== part.sha256) throw new Error(`Corrupt runtime asset: ${part.file}`);
    bytes += data.length; whole.update(data);
  }
  if (bytes !== pack.bytes || whole.digest('hex') !== pack.sha256) throw new Error('Runtime pack mismatch');
}
console.log('All runtime assets verified (five platforms and corresponding source pack).');

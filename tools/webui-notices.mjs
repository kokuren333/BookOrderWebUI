import { readFile, readdir, writeFile } from 'node:fs/promises';
const packages = ['react', 'react-dom', 'scheduler', 'jszip', 'lie', 'immediate', 'pako', 'readable-stream', 'core-util-is', 'inherits', 'isarray', 'process-nextick-args', 'safe-buffer', 'string_decoder', 'util-deprecate', 'setimmediate', 'vite'];
let notices = 'WebUI third-party notices\nJSZip is used under its MIT license option. These notices concern the WebUI; job runtime notices are inside each bundled job.\n';
for (const name of packages) {
  const dir = `node_modules/${name}`;
  const pkg = JSON.parse(await readFile(`${dir}/package.json`, 'utf8'));
  const files = (await readdir(dir)).filter(file => /^(license|copying|notice)(\.|$)/i.test(file));
  if (!files.length) {
    for (const file of (await readdir(dir)).filter(file => /^readme/i.test(file))) {
      if (/permission is hereby granted/i.test(await readFile(`${dir}/${file}`, 'utf8'))) files.push(file);
    }
  }
  if (!files.length) throw new Error(`No license notice found for ${name}`);
  notices += `\n\n========== ${name} ${pkg.version} (${pkg.license}) ==========\n`;
  for (const file of files) notices += `\n${file}\n${await readFile(`${dir}/${file}`, 'utf8')}\n`;
}
await writeFile('public/webui-licenses.txt', notices);
console.log('WebUI third-party notices prepared.');

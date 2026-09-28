// Test harness: bundle the real WebUI (src/main.tsx) into one script WITHOUT vite, for headless interaction tests
// on machines where vite's native esbuild/rollup binaries are unavailable. Not used by the product build.
// Usage: node tools/ui-bundle.cjs <out-dir>   -> <out-dir>/index.html + app.js
const ts = require('typescript');
const fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '..');
const OUT = path.resolve(process.argv[2] || path.join(ROOT, '.test-output/ui-bundle'));
const mods = {}; const ids = {}; let next = 0;
const walk = dir => fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]);
function templatesModule() {
  const files = walk(path.join(ROOT, 'job-template')).filter(f => !f.endsWith('.png') && !f.includes('__pycache__') && !f.endsWith('.pyc'));
  const map = Object.fromEntries(files.map(f => ['../job-template/' + path.relative(path.join(ROOT, 'job-template'), f).split(path.sep).join('/'), fs.readFileSync(f, 'utf8')]));
  const previews = Object.fromEntries(fs.readdirSync(path.join(ROOT, 'job-template/themes')).map(t => [`../job-template/themes/${t}/preview.png`,
    'data:image/png;base64,' + fs.readFileSync(path.join(ROOT, 'job-template/themes', t, 'preview.png')).toString('base64')]));
  return `const entries = ${JSON.stringify(map)};
export const templates = Object.fromEntries(Object.entries(entries).map(([p, v]) => [p.replace('../job-template/', ''), v]));
export const themePreviews = ${JSON.stringify(previews)};
export async function loadTemplates() { return { ...templates }; }`;
}
function load(file) {
  if (ids[file] !== undefined) return ids[file];
  const id = ids[file] = next++;
  let code = fs.readFileSync(file, 'utf8');
  if (file.endsWith('.json')) code = 'module.exports = ' + code;
  else if (/\.tsx?$/.test(file)) {
    if (file.endsWith(path.join('src', 'templates.ts'))) code = templatesModule();
    code = code.replace(/import\.meta\.env\.BASE_URL/g, '"/"').replace(/import\.meta\.glob\(/g, 'globalThis.__glob(');
    code = ts.transpileModule(code, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  } else if (file.endsWith('.css')) code = '';
  code = code.replace(/process\.env\.NODE_ENV/g, '"production"');
  const deps = {};
  code.replace(/require\((['"])([^'"]+)\1\)/g, (m, q, spec) => {
    let target;
    if (spec.startsWith('.')) {
      const base = path.resolve(path.dirname(file), spec);
      target = [base, base + '.ts', base + '.tsx', base + '.js', base + '.json', base + '/index.js'].find(f => fs.existsSync(f) && fs.statSync(f).isFile());
    } else if (spec === 'jszip') target = path.join(ROOT, 'node_modules/jszip/dist/jszip.min.js');
    else if (require('module').builtinModules.includes(spec)) target = null;
    else target = require.resolve(spec, { paths: [ROOT] });
    if (target === undefined) throw new Error(`cannot resolve ${spec} from ${file}`);
    deps[spec] = target === null ? -1 : load(target); return m;
  });
  mods[id] = { code, deps };
  return id;
}
const entry = load(path.join(ROOT, 'src/main.tsx'));
const glob = {};  // import.meta.glob targets outside src/templates.ts: theme and profile data files
for (const t of fs.readdirSync(path.join(ROOT, 'job-template/themes'))) glob[`../job-template/themes/${t}/theme.yaml`] = fs.readFileSync(path.join(ROOT, 'job-template/themes', t, 'theme.yaml'), 'utf8');
for (const k of ['tiers', 'genres']) for (const f of fs.readdirSync(path.join(ROOT, 'job-template/profiles', k))) glob[`../job-template/profiles/${k}/${f}`] = fs.readFileSync(path.join(ROOT, 'job-template/profiles', k, f), 'utf8');
for (const f of fs.readdirSync(path.join(ROOT, 'job-template/styles/genres'))) glob[`../job-template/styles/genres/${f}`] = fs.readFileSync(path.join(ROOT, 'job-template/styles/genres', f), 'utf8');
let out = `globalThis.__GLOB=${JSON.stringify(glob)};globalThis.__glob=p=>{const r={};const re=new RegExp('^'+String(p).replace(/[.]/g,'\\\\.').replace(/\\*/g,'[^/]+')+'$');for(const k in __GLOB)if(re.test(k))r[k]=__GLOB[k];return r};
var process={env:{NODE_ENV:'production'}};const __m={},__c={};function __r(i){if(i<0)return{};if(__c[i])return __c[i].exports;const m=__c[i]={exports:{}};__m[i](m,m.exports);return m.exports}\n`;
for (const [id, m] of Object.entries(mods)) out += `__m[${id}]=function(module,exports){const require=s=>__r(${JSON.stringify(m.deps)}[s]);\n${m.code}\n};\n`;
out += `__r(${entry});`;
fs.mkdirSync(OUT, { recursive: true });
fs.writeFileSync(path.join(OUT, 'app.js'), out);
fs.writeFileSync(path.join(OUT, 'index.html'), `<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>${fs.readFileSync(path.join(ROOT, 'src/style.css'), 'utf8')}</style><body><div id="root"></div><script src="app.js"></script></body></html>`);
console.log(`bundled ${Object.keys(mods).length} modules -> ${OUT}`);

"""Prepare pinned, offline runtime packs for static hosting. Never run from the browser.

Archives remain compressed in job ZIPs; launchers unpack them locally. GPL source
archives and original notices travel with every job and completed result ZIP.
"""
from pathlib import Path
import concurrent.futures
import hashlib
import io
import json
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import time
import urllib.error
import tomllib
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".tools/runtime-cache"
OUT = ROOT / "public/runtimes"
LOCK = ROOT / "tools/runtime-lock.json"
PANDOC = "3.11"
TYPST = "0.15.1"
PBS = "20260924"
PYTHON = "3.12.14"
NOTO_COMMIT = "f8d157532fbfaeda587e826d4cd5b21a49186f7c"
FONT_ARCHIVES = [  # (family, pinned release URL, SHA-256, font members, licence members)
    ("noto-sans-jp", "https://github.com/notofonts/noto-cjk/releases/download/Sans2.004/16_NotoSansJP.zip",
     "2bbdd2c20f30670b39ca735c96d75f1fdabdb348103e43b820cf17701fd22b18", ["NotoSansJP-Regular.otf", "NotoSansJP-Bold.otf"], ["LICENSE"]),
    ("source-serif-4", "https://github.com/adobe-fonts/source-serif/releases/download/4.005R/source-serif-4.005_Desktop.zip",
     "549fdb8f9a682bd06944298621404969f6de77c2e422ff3b8244a1dcd6a0c425",
     [f"source-serif-4.005_Desktop/OTF/SourceSerif4-{w}.otf" for w in ("Regular", "It", "Semibold", "Bold")], ["source-serif-4.005_Desktop/LICENSE.md"]),
    ("inter", "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip",
     "9883fdd4a49d4fb66bd8177ba6625ef9a64aa45899767dde3d36aa425756b11e",
     [f"extras/ttf/Inter-{w}.ttf" for w in ("Regular", "Italic", "Medium", "SemiBold", "Bold")], ["LICENSE.txt"]),
    ("jetbrains-mono", "https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip",
     "6f6376c6ed2960ea8a963cd7387ec9d76e3f629125bc33d1fdcd7eb7012f7bbf",
     [f"fonts/ttf/JetBrainsMono-{w}.ttf" for w in ("Regular", "Italic", "Bold")], ["OFL.txt"]),
]
TARGETS = {
    "windows-x64": ("Windows · x64", "windows-x86_64.zip", "x86_64-pc-windows-msvc.zip", None),
    "macos-arm64": ("macOS · Apple Silicon", "arm64-macOS.zip", "aarch64-apple-darwin.tar.xz", "aarch64-apple-darwin"),
    "macos-x64": ("macOS · Intel", "x86_64-macOS.zip", "x86_64-apple-darwin.tar.xz", "x86_64-apple-darwin"),
    "linux-x64": ("Linux · x64 (glibc)", "linux-amd64.tar.gz", "x86_64-unknown-linux-musl.tar.xz", "x86_64-unknown-linux-gnu"),
    "linux-arm64": ("Linux · ARM64 (glibc)", "linux-arm64.tar.gz", "aarch64-unknown-linux-musl.tar.xz", "aarch64-unknown-linux-gnu"),
}
pins = json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.exists() else {}
for mutable_url in ('https://hackage.haskell.org/packages/', 'https://api.github.com/repos/notofonts/noto-cjk/commits/main'):
    pins.pop(mutable_url, None)
GHC_PACKAGES = set('base array binary bytestring containers deepseq directory exceptions filepath ghc ghc-boot-th integer-gmp mtl os-string parsec pretty process stm template-haskell text time transformers unix Win32 ghc-bignum ghc-prim ghc-internal'.split())
PANDOC_PACKAGES = {'pandoc', 'pandoc-cli', 'pandoc-server', 'pandoc-lua-engine'}

def consonants(name):
    return re.sub('[aeiouAEIOU]', '', name)

def unit_matches(name, candidates):
    pattern = re.compile('^' + re.escape(name).replace('_', '.*') + '$')
    return {candidate for candidate in candidates if pattern.match(candidate) or pattern.match(consonants(candidate))}

def supplied_unit(name):
    return name.endswith('-ghc') or bool(unit_matches(name, GHC_PACKAGES | PANDOC_PACKAGES))


def fetch(url, expected=None):
    key = hashlib.sha256(url.encode()).hexdigest()
    path = CACHE / key
    trusted = expected or pins.get(url)
    if path.exists():
        cached = path.read_bytes()
        if not trusted or hashlib.sha256(cached).hexdigest() == trusted:
            return cached
        path.unlink()
    if not path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "PortablePublishingJob/0.1"})
        last = None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=600) as response:
                    data = response.read()
                digest = hashlib.sha256(data).hexdigest()
                if trusted and trusted != digest:
                    raise ValueError(f"Checksum mismatch: {url}")
                path.write_bytes(data)
                break
            except Exception as exc: last = exc
            if attempt < 4:
                delay = min(15 * (2 ** attempt), 120)
                print(f"Download failed; retrying in {delay}s ({attempt + 2}/5): {url}: {last}", flush=True)
                time.sleep(delay)
        else:
            if sys.platform == 'win32' and isinstance(last, urllib.error.URLError) and isinstance(last.reason, ssl.SSLCertVerificationError):
                # Use Windows' trust store, without disabling certificate checks.
                escaped_url = url.replace("'", "''"); escaped_path = str(path).replace("'", "''")
                subprocess.run(['powershell.exe', '-NoProfile', '-Command', f"$ErrorActionPreference='Stop'; Invoke-WebRequest -Uri '{escaped_url}' -OutFile '{escaped_path}' -TimeoutSec 120"], check=True)
            else: raise RuntimeError(f"Download failed: {url}: {last}")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if trusted and trusted != digest: raise ValueError(f"Checksum mismatch: {url}")
    pins[url] = digest
    return data


def archive_files(data, name):
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return [(info.filename, archive.read(info), info.external_attr >> 16) for info in archive.infolist() if not info.is_dir()]
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        return [(info.name, archive.extractfile(info).read(), info.mode) for info in archive.getmembers() if info.isfile()]


def add_notices(pack, data, archive_name, prefix):
    found = 0
    for path, content, _ in archive_files(data, archive_name):
        if re.search(r"(^|/)(license[^/]*|copying[^/]*|copyright[^/]*|notice[^/]*|authors[^/]*)$", path, re.I):
            pack[f"third-party/licenses/{prefix}/{path}"] = content; found += 1
    return found


def source(pack, url, name, expected=None):
    data = fetch(url, expected)
    pack[f"third-party/sources/{name}"] = data
    add_notices(pack, data, name, name.replace(".tar.gz", "").replace(".tar.xz", "").replace(".zip", ""))
    return {"url": url, "path": "third-party/sources/" + name, "sha256": hashlib.sha256(data).hexdigest()}


def pandoc_dependencies(binary, candidates):
    # GHC's embedded unit IDs carry actual linked package versions. Long package
    # names may be abbreviated with _; retain ALL matching source packages.
    units = set(re.findall(rb"(?<![A-Za-z0-9_-])([A-Za-z][A-Za-z0-9_-]*)-([0-9]+(?:\.[0-9]+)+)-(?:[a-f0-9]{4,64}|inplace)(?=[\x00\s/])", binary))
    packages = set(); unresolved = []
    for raw_name, raw_version in units:
        name, version = raw_name.decode(), raw_version.decode()
        if supplied_unit(name): continue
        if name in ("base", "array", "binary", "bytestring", "containers", "deepseq", "directory", "exceptions", "filepath", "ghc", "ghc-boot-th", "integer-gmp", "mtl", "os-string", "parsec", "pretty", "process", "stm", "template-haskell", "text", "time", "transformers", "unix", "Win32", "ghc-bignum", "ghc-prim", "ghc-internal"):
            continue  # supplied in the matching GHC source archive
        matches = {(candidate, version) for candidate in unit_matches(name, candidates)}
        if not matches: unresolved.append((name, version))
        packages.update(matches)
    if unresolved: raise ValueError(f"Unresolved abbreviated Pandoc unit IDs: {unresolved}")
    if len(packages) < 80: raise ValueError("Pandoc dependency inventory unexpectedly incomplete")
    return packages, sorted((a.decode(), b.decode()) for a, b in units)


def write_pack(name, files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for path, data in sorted(files.items()): archive.writestr(path, data)
    data = buffer.getvalue()
    parts = []
    # Below common static-host per-file limits. Shared sources are fetched once.
    for i, offset in enumerate(range(0, len(data), 8 * 1024 * 1024)):
        chunk = data[offset:offset + 8 * 1024 * 1024]
        filename = f"{name}.{i:03}.bin"
        (OUT / filename).write_bytes(chunk)
        parts.append({"file": filename, "bytes": len(chunk), "sha256": hashlib.sha256(chunk).hexdigest()})
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "parts": parts}


def main():
    CACHE.mkdir(parents=True, exist_ok=True); OUT.mkdir(parents=True, exist_ok=True)
    shared = {}; source_manifest = []; platforms = []; all_packages = set(); unit_inventory = {}
    candidates = set(json.loads((ROOT / "tools/pandoc-source-candidates.json").read_text(encoding="utf-8")))
    for target, (label, pandoc_suffix, typst_suffix, python_triple) in TARGETS.items():
        print("Preparing", target, flush=True)
        files = {}; artifacts = []
        specs = [
            ("pandoc", f"https://github.com/jgm/pandoc/releases/download/{PANDOC}/pandoc-{PANDOC}-{pandoc_suffix}", "pandoc-" + pandoc_suffix),
            ("typst", f"https://github.com/typst/typst/releases/download/v{TYPST}/typst-{typst_suffix}", "typst-" + typst_suffix),
            ("python", f"https://github.com/astral-sh/python-build-standalone/releases/download/{PBS}/cpython-{PYTHON}%2B{PBS}-{python_triple}-install_only.tar.gz" if python_triple else "https://www.python.org/ftp/python/3.14.7/python-3.14.7-embed-amd64.zip", "python.tar.gz" if python_triple else "python.zip"),
        ]
        for component, url, name in specs:
            data = fetch(url)
            files["runtime/archives/" + name] = data
            notices = add_notices(shared, data, name, target + "/" + component)
            artifacts.append({"component": component, "path": "runtime/archives/" + name, "sha256": hashlib.sha256(data).hexdigest(), "url": url, "license_notices": notices})
            if component == "pandoc":
                binaries = [(path, content) for path, content, _ in archive_files(data, name) if Path(path).name in ("pandoc", "pandoc.exe")]
                if len(binaries) != 1: raise ValueError("Expected exactly one Pandoc executable")
                deps, units = pandoc_dependencies(binaries[0][1], candidates)
                all_packages.update(deps); unit_inventory[target] = units
        manifest = {"format": "portable-publishing-runtime", "format_version": "1", "target": target,
                    "versions": {"python": PYTHON if python_triple else "3.14.7", "pandoc": PANDOC, "typst": TYPST},
                    "artifacts": artifacts, "source_manifest": "third-party/source-manifest.json"}
        files["runtime/manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
        platforms.append({"id": target, "label": label, "pack": write_pack(target, files)})
    source_manifest.append(source(shared, f"https://codeload.github.com/jgm/pandoc/tar.gz/refs/tags/{PANDOC}", f"pandoc-{PANDOC}.tar.gz"))
    shared["third-party/pandoc-linked-units.json"] = json.dumps(unit_inventory, indent=2).encode()
    def get_package(spec):
        name, version = spec
        url = f"https://hackage-content.haskell.org/package/{name}-{version}/{name}-{version}.tar.gz"
        try: return spec, url, fetch(url)
        except RuntimeError:
            # A truncated unit name can match unrelated packages. Fail unless
            # at least one exact version candidate for each unit was acquired.
            return spec, url, None
    available = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for (name, version), url, data in pool.map(get_package, sorted(all_packages)):
            if data is None: continue
            archive_name = f"{name}-{version}.tar.gz"
            shared["third-party/sources/" + archive_name] = data
            add_notices(shared, data, archive_name, "haskell/" + name + "-" + version)
            source_manifest.append({"url": url, "path": "third-party/sources/" + archive_name, "sha256": hashlib.sha256(data).hexdigest()})
            available.add((name, version))
    # Every observable linked unit must resolve to at least one archived source.
    for target, units in unit_inventory.items():
        for name, version in units:
            if supplied_unit(name): continue
            if name.startswith(("pandoc", "ghc")) or name in ("base", "array", "binary", "bytestring", "containers", "deepseq", "directory", "exceptions", "filepath", "integer-gmp", "mtl", "os-string", "parsec", "pretty", "process", "stm", "template-haskell", "text", "time", "transformers", "unix", "Win32"): continue
            if not any(v == version and n in unit_matches(name, {x[0] for x in available}) for n, v in available): raise ValueError(f"Missing linked source: {target}: {name}-{version}")
    print("Linked Haskell package sources:", len(available), flush=True)
    ghcs = set()
    for units in unit_inventory.values():
        ghcs.update(version for name, version in units if name in ('ghc-boot-th', consonants('ghc-boot-th')))
    if not ghcs: ghcs = {"9.10.3"}
    for version in sorted(ghcs):
        source_manifest.append(source(shared, f"https://downloads.haskell.org/~ghc/{version}/ghc-{version}-src.tar.xz", f"ghc-{version}-src.tar.xz"))
    # Native library sources that may be statically linked by the official builds.
    for version in ("1.2.13", "1.3.1", "1.3.2"):
        source_manifest.append(source(shared, f"https://zlib.net/fossils/zlib-{version}.tar.gz", f"zlib-{version}.tar.gz"))
    source_manifest.append(source(shared, "https://gmplib.org/download/gmp/gmp-6.3.0.tar.xz", "gmp-6.3.0.tar.xz"))
    source_manifest.append(source(shared, f"https://codeload.github.com/astral-sh/python-build-standalone/tar.gz/refs/tags/{PBS}", f"python-build-standalone-{PBS}.tar.gz"))
    # CLI LICENSE/NOTICE alone do not cover the linked Rust crates' notices.
    typst_url = f'https://codeload.github.com/typst/typst/tar.gz/refs/tags/v{TYPST}'
    source_manifest.append(source(shared, typst_url, f'typst-{TYPST}.tar.gz'))
    typst_files = archive_files(fetch(typst_url), '.tar.gz')
    cargo_lock = tomllib.loads(next(data for path, data, _ in typst_files if path.endswith('/Cargo.lock')).decode())
    crates = [(item['name'], item['version'], item['checksum']) for item in cargo_lock['package'] if item.get('source', '').startswith('registry+')]
    for item in cargo_lock['package']:
        if item.get('source', '').startswith('git+') and not (item['name'] == 'typst-dev-assets' and item['source'] == 'git+https://github.com/typst/typst-dev-assets?tag=v0.15.1#53c12796fc6c62e12af8788ab80ebed686d5eedb'):
            raise ValueError('Unaccounted git dependency in Typst lock')
    # typst-dev-assets is used by tests/docs and CLI dev-dependencies only;
    # it is not linked into any distributed CLI executable.
    def get_crate(item):
        name, version, digest = item
        return item, fetch(f'https://static.crates.io/crates/{name}/{name}-{version}.crate', digest)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for (name, version, digest), data in pool.map(get_crate, crates):
            filename = f'{name}-{version}.crate'
            shared['third-party/sources/' + filename] = data
            add_notices(shared, data, filename, 'rust/' + name + '-' + version)
            source_manifest.append({'url': f'https://static.crates.io/crates/{name}/{filename}', 'path': 'third-party/sources/' + filename, 'sha256': digest})
    print('Typst dependency source/notice archives:', len(crates), flush=True)
    downloads = json.loads(fetch(f"https://raw.githubusercontent.com/astral-sh/python-build-standalone/{PBS}/pythonbuild/downloads.json"))
    for name in ("cpython-3.12", "bdb"):
        item = downloads[name]
        filename = Path(urllib.request.urlparse(item["url"]).path).name if hasattr(urllib.request, "urlparse") else item["url"].split("/")[-1]
        source_manifest.append(source(shared, item["url"], filename, item["sha256"]))
    # Complete upstream Python notices include transitive library attribution.
    shared["third-party/licenses/python-build-standalone/python-licenses.rst"] = fetch(f"https://raw.githubusercontent.com/astral-sh/python-build-standalone/{PBS}/python-licenses.rst")
    shared["third-party/licenses/pandoc/COPYRIGHT"] = fetch(f"https://raw.githubusercontent.com/jgm/pandoc/{PANDOC}/COPYRIGHT")
    shared["third-party/licenses/pandoc/GPL-2.0.md"] = fetch(f"https://raw.githubusercontent.com/jgm/pandoc/{PANDOC}/COPYING.md")
    for name in ("LICENSE", "NOTICE"):
        shared["third-party/licenses/typst/" + name] = fetch(f"https://raw.githubusercontent.com/typst/typst/v{TYPST}/{name}")
    # A pinned Git commit covers font binaries, attribution and license together.
    noto = NOTO_COMMIT
    for weight in ("Regular", "Bold"):
        shared[f"runtime/fonts/NotoSerifCJKjp-{weight}.otf"] = fetch(f"https://raw.githubusercontent.com/notofonts/noto-cjk/{noto}/Serif/OTF/Japanese/NotoSerifCJKjp-{weight}.otf")
    for name in ("LICENSE", "README-third_party.md"):
        shared["third-party/licenses/noto-serif-cjk/" + name] = fetch(f"https://raw.githubusercontent.com/notofonts/noto-cjk/{noto}/Serif/{name}")
    # Additional OFL-1.1 fonts from pinned upstream release archives (SHA-256 verified). Only the needed weights
    # are extracted; each family keeps its licence under third-party/licenses/<family>/.
    for family, url, digest, members, licences in FONT_ARCHIVES:
        files = {path: content for path, content, _ in archive_files(fetch(url, digest), url)}
        for member in members:
            shared["runtime/fonts/" + Path(member).name] = files[member]
        for licence in licences:
            shared[f"third-party/licenses/{family}/" + Path(licence).name] = files[licence]
    shared["third-party/README.md"] = (ROOT / "tools/runtime-redistribution.md").read_bytes()
    inventory = [{'path': path, 'sha256': hashlib.sha256(data).hexdigest()} for path, data in sorted(shared.items()) if not path.startswith('third-party/sources/')]
    shared["third-party/source-manifest.json"] = (json.dumps({"sources": source_manifest, 'bundled_files': inventory}, indent=2) + "\n").encode()
    common = write_pack("shared", shared)
    (OUT / "catalog.json").write_text(json.dumps({"format_version": "1", "shared": common, "platforms": platforms}, indent=2) + "\n", encoding="utf-8")
    LOCK.write_text(json.dumps(dict(sorted(pins.items())), indent=2) + "\n", encoding="utf-8")
    print("Ready:", OUT, "shared bytes:", common["bytes"], flush=True)


if __name__ == "__main__": main()

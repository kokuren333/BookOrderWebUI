"""Initialize and run only the locally bundled publishing tools; never install/download."""
from pathlib import Path
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def contained(path):
    candidate = (ROOT / path).resolve()
    if not candidate.is_relative_to(ROOT): raise ValueError(f"Path escapes job: {path}")
    return candidate


_VERIFIED = {}
_CACHE = ROOT / "runtime/.verified.json"


def checksum(path, expected):
    """SHA-256 check; unchanged files (same size and mtime as a previous successful check) are not re-hashed,
    so the frequent `bookorder goal` calls of a long publication stay fast."""
    if not _VERIFIED and _CACHE.is_file():
        try: _VERIFIED.update(json.loads(_CACHE.read_text(encoding="utf-8")))
        except ValueError: pass
    stat = path.stat(); key = path.relative_to(ROOT).as_posix()
    if _VERIFIED.get(key) == [stat.st_size, stat.st_mtime_ns, expected]: return
    with path.open("rb") as stream: digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != expected: raise ValueError(f"Runtime/source checksum mismatch: {path.relative_to(ROOT)}")
    _VERIFIED[key] = [stat.st_size, stat.st_mtime_ns, expected]


def extract(archive_path, destination):
    destination.mkdir(parents=True, exist_ok=True)
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as archive:
            for name in archive.namelist():
                target = (destination / name).resolve()
                if not target.is_relative_to(destination.resolve()) or "\\" in name or ":" in name:
                    raise ValueError(f"Unsafe archive member: {name}")
            archive.extractall(destination)
    else:
        with tarfile.open(archive_path, "r:*") as archive: archive.extractall(destination, filter="data")


def initialize():
    manifest = json.loads((ROOT / "runtime/manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "portable-publishing-runtime" or manifest.get("format_version") != "1":
        raise ValueError("Unsupported runtime manifest")
    machine = platform.machine().lower()
    architecture = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(machine, machine)
    system = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(platform.system())
    target = f"{system}-{architecture}"
    if manifest["target"] != target: raise RuntimeError(f"Job runtime is {manifest['target']}; this machine is {target}. Download the matching job.")
    if system == 'macos' and int(platform.mac_ver()[0].split('.')[0]) < 15:
        raise RuntimeError('Bundled Pandoc requires macOS 15 or later.')
    artifacts = manifest.get("artifacts", [])
    if {item["component"] for item in artifacts} != {"python", "pandoc", "typst"} or len(artifacts) != 3:
        raise ValueError("Incomplete runtime artifact list")
    sources = json.loads(contained(manifest["source_manifest"]).read_text(encoding="utf-8"))
    if not sources.get("sources"): raise ValueError("Corresponding source inventory is missing")
    for item in sources["sources"] + sources.get('bundled_files', []): checksum(contained(item["path"]), item["sha256"])
    for item in artifacts:
        path = contained(item["path"]); checksum(path, item["sha256"])
        if item["component"] == "python": continue  # launcher has initialized Python
        name = item["component"]
        destination = ROOT / "runtime/tools" / name
        marker = destination / ".archive-sha256"
        if not marker.is_file() or marker.read_text().strip() != item["sha256"]:
            extract(path, destination)
            marker.write_text(item["sha256"], encoding="ascii")
        filename = name + (".exe" if system == "windows" else "")
        matches = [p for p in destination.rglob(filename) if p.is_file()]
        if len(matches) != 1: raise ValueError(f"Expected exactly one {filename}, found {len(matches)}")
        if system != "windows": matches[0].chmod(matches[0].stat().st_mode | 0o111)
        os.environ[name.upper()] = str(matches[0])
    try: _CACHE.write_text(json.dumps(_VERIFIED), encoding="utf-8")
    except OSError: pass
    os.environ["TYPST_FONT_PATHS"] = str(ROOT / "runtime/fonts")
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    return manifest


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "check"
    actions = {"check": ["check_env.py"], "validate": ["validate.py"], "source-check": ["validate.py", "--source-only"],
               "build": ["build.py"], "package": ["package.py"], "goal": ["cli.py", "goal"], "status": ["cli.py", "status"]}
    if action not in (*actions, "all"): raise ValueError("Use goal, status, check, source-check, validate, build, package, or all")
    manifest = initialize()
    print(f"Portable runtime ready: {manifest['target']} (no system installation)", flush=True)
    sequences = [["validate.py", "--source-only"], ["build.py"], ["validate.py"], ["package.py"]] if action == "all" else [actions[action]]
    for script, *args in sequences:
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args], cwd=ROOT, env=os.environ)
        if result.returncode: return result.returncode
    return 0


if __name__ == "__main__":
    try: sys.exit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr); sys.exit(1)

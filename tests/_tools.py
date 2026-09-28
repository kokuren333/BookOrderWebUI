"""Test environment: locate Pandoc/Typst (PANDOC/TYPST env vars, then PATH, then the maintainer copies in .tools/)
and make child Python processes write UTF-8, as the job launchers (run.cmd, run.sh, bookorder) do. Without it a
captured job script on Japanese Windows prints with cp932 and fails on characters such as "–".

Importing this module sets PANDOC/TYPST in os.environ when they are found, so child processes (job scripts) see them.
`.tools/` holds the pinned portable executables (e.g. .tools/pandoc-3.11/pandoc.exe, .tools/typst-*/typst.exe).
"""
import os
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parent.parent


def locate(name):
    configured = os.environ.get(name.upper())
    if configured and Path(configured).is_file(): return configured
    found = shutil.which(name)
    if found: return found
    executable = name + (".exe" if os.name == "nt" else "")
    candidates = sorted(p for p in (REPO / ".tools").glob(f"*/{executable}") if p.is_file()) if (REPO / ".tools").is_dir() else []
    return str(candidates[0]) if candidates else None


os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"
for _stream in (sys.stdout, sys.stderr):  # a redirected cp932 console must not crash a passing test
    try: _stream.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError): pass

MISSING = []
for _name in ("pandoc", "typst"):
    _path = locate(_name)
    if _path: os.environ[_name.upper()] = _path
    else: MISSING.append(_name)

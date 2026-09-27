"""Report prerequisites without installing anything."""
import json
import sys
import shutil
from common import ROOT, tool, run, read_project, version_tuple, report


def main():
    project = read_project()
    required = {"python": sys.version_info >= (3, 10)}
    versions = {"python": sys.version.split()[0]}
    for name, minimum in (("pandoc", (3, 6, 0)), ("typst", (0, 13, 0))):
        try:
            version = run([tool(name), "--version"]).splitlines()[0]
            versions[name] = version
            ok = version_tuple(version) >= minimum
        except RuntimeError as exc:
            versions[name] = str(exc); ok = False
        diagrams_need_raster = any((ROOT / 'source/assets/diagrams').glob('*.yaml')) and any(project['outputs'].get(key) for key in ('docx', 'epub'))
        if name == "pandoc" or project["outputs"].get("pdf") or diagrams_need_raster: required[name] = ok
    result = {"ok": all(required.values()), "required": required, "versions": versions,
              "optional": {name: shutil.which(name) for name in ("node", "quarto", "dot", "epubcheck")}}
    report("environment-report.json", result)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    try: sys.exit(main())
    except Exception as exc: print(str(exc), file=sys.stderr); sys.exit(1)

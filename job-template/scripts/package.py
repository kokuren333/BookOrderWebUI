"""Create a reproducible editable project ZIP only after a fresh final validation."""
import json
import sys
import zipfile
from common import ROOT, fingerprint
from validate import validate


def publication_gates():
    """The orchestrator's publication gates; a structurally valid build of a short or unaudited book is refused."""
    import orchestrator
    project, state = orchestrator.load_state()
    gates = orchestrator.completion_gates(orchestrator.Context(project, state), include_package=False)
    failing = [g for g in gates if not g["passed"]]
    if failing:
        raise RuntimeError("Publication gates failed; the publication is incomplete: " + "; ".join(f"{g['id']}. {g['name']} ({g['detail']})" for g in failing))


def package():
    from common import read_project
    if not read_project()["book"].get("preview"): publication_gates()
    result = validate()
    if not result["ok"] or result["phase"] != "final":
        raise RuntimeError("Packaging requires a successful build and fresh final validation: " + "; ".join(result["errors"]))
    for review in ("editorial-review.md", "layout-review.md"):
        path = ROOT / "reports" / review
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            raise RuntimeError(f"Missing human/agent QA record: reports/{review}. Inspect the outputs and record actual checks.")
    target = ROOT / "publish/result.zip"
    temporary = ROOT / "publish/.result.tmp"
    folders = ("source", "input", "interchange", "publish", "reports", "scripts", "skills", "config", "templates", "third-party", "themes", "schemas", "docs")
    files = [ROOT / name for name in ("project.json", "TASK.md", "README.md", "AGENTS.md", "run.cmd", "run.sh", "bookorder.cmd", "bookorder", "book.design.yaml", "custom.css", "custom.typ") if (ROOT / name).is_file()]
    # Keep original runtime archives/fonts/licenses, not unpacked executable caches.
    for folder in ("runtime/archives", "runtime/fonts"):
        files += [p for p in (ROOT / folder).rglob("*") if p.is_file()]
    files += [p for p in (ROOT / "runtime").glob("*") if p.is_file()]
    files += [p for folder in folders for p in (ROOT / folder).rglob("*") if p.is_file()]
    # The editorial review links to these decisions, which must travel with the result ZIP.
    files += [p for p in (ROOT / "plan/prose-audit.yaml", ROOT / "plan/prose-editing.yaml") if p.is_file()]
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            if path in (target, temporary) or "__pycache__" in path.parts or path.suffix in (".pyc", ".tmp") or path.name == ".DS_Store": continue
            archive.write(path, "publishing-job/" + path.relative_to(ROOT).as_posix(), compress_type=zipfile.ZIP_STORED if path.suffix in ('.zip', '.gz', '.xz', '.crate') else zipfile.ZIP_DEFLATED)
    temporary.replace(target)
    print(f"Completed project: {target}")


if __name__ == "__main__":
    try: package()
    except Exception as exc: print(str(exc), file=sys.stderr); sys.exit(1)

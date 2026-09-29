"""Discover the job's editorial guides without assuming a flat skills directory."""
from pathlib import Path

from common import ROOT

CATEGORIES = frozenset({"authoring", "research", "editorial", "design", "quality", "planning"})
EXCLUDED = frozenset({"node_modules", "build", "dist", "fixtures", "tests", "__pycache__"})


def discover(root=None):
    base = Path(root) if root is not None else ROOT / "skills"
    found = {}
    for path in sorted(base.rglob("*.md")):
        relative = path.relative_to(base)
        if len(relative.parts) < 2 or relative.parts[0] not in CATEGORIES or EXCLUDED.intersection(relative.parts):
            continue
        if path.name.lower() == "readme.md":
            continue
        identifier = path.stem
        if identifier in found:
            raise ValueError(f"Duplicate skill id {identifier!r}: {found[identifier]} and {path}")
        found[identifier] = "skills/" + relative.as_posix()
    return found


def resolve(*identifiers, root=None):
    found = discover(root)
    missing = [identifier for identifier in identifiers if identifier not in found]
    if missing:
        raise ValueError("Missing skills: " + ", ".join(missing))
    return [found[identifier] for identifier in identifiers]

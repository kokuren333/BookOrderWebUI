"""PDF renderer interface: adapters consume Book IR + normalized design tokens."""
from typing import Protocol
from pathlib import Path

class PdfRenderer(Protocol):
    def render(self, ir: dict, tokens: dict, output: Path) -> None: ...

def renderer(name):
    # New adapters register here; no backend-specific values enter IR/schema.
    if name == 'typst':
        from .typst import TypstRenderer
        return TypstRenderer()
    raise ValueError(f'PDF backend not installed: {name}')

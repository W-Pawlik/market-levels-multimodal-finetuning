"""Containment and Windows path checks with distinct artifact policies."""
from __future__ import annotations

from pathlib import Path


def require_short_path(path: Path) -> None:
    """Fail before writing, including on Windows without long-path support."""
    if len(str(path.resolve()).encode("utf-16-le")) // 2 >= 260:
        raise ValueError(f"Ścieżka wymaga skrócenia (<260 UTF-16): {path}")


def child(root: Path, name: str, *, message: str = "Ścieżka wychodzi poza katalog pilotażu") -> Path:
    path = (root/name).resolve()
    if root.resolve() not in path.parents:
        raise ValueError(message)
    return path


def _batch_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value.strip() or Path(value).is_absolute():
        raise ValueError("Manifest wymaga względnych ścieżek plików")
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Ścieżka pliku wychodzi poza katalog partii")
    return path


def _child(root: Path, relative: str) -> Path:
    """Use the manifest-specific error without changing containment semantics."""
    return child(root, relative, message="Ścieżka manifestu wychodzi poza partię")

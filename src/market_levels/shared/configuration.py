"""Read flat experiment JSON or explicit top-level file references."""
from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath
from typing import Any

from .integrity import SourceLedger


def _read(path: Path, ledger: SourceLedger | None = None) -> tuple[Any, tuple[Path, ...], bool]:
    path = Path(path)
    files: dict[Path, Any] = {}

    def read_file(source: Path) -> Any:
        resolved = source.resolve()
        if resolved not in files:
            if ledger is not None:
                ledger.track(source)
            files[resolved] = json.loads(source.read_text(encoding="utf-8-sig"))
        return files[resolved]

    document = read_file(path)
    if not isinstance(document, dict):
        return document, tuple(files), False
    result = dict(document)
    composed = False
    for key, value in document.items():
        if not isinstance(value, dict) or "$file" not in value:
            continue
        if set(value) - {"$file", "$section"}:
            raise ValueError(f"{key}: odwołanie dopuszcza wyłącznie $file i $section")
        name = value["$file"]
        if not isinstance(name, str) or not name.strip() or Path(name).anchor or PureWindowsPath(name).anchor:
            raise ValueError(f"{key}.$file wymaga niepustej ścieżki względnej")
        source = path.parent / name
        if source.resolve() == path.resolve():
            raise ValueError(f"{key}: plik wejściowy nie może być własnym fragmentem")
        selected = read_file(source)
        if "$section" in value:
            section = value["$section"]
            if not isinstance(section, str) or not section or not isinstance(selected, dict) or section not in selected:
                raise ValueError(f"{key}.$section nie wskazuje istniejącej sekcji pliku {name}")
            selected = selected[section]
        if isinstance(selected, dict) and "$file" in selected:
            raise ValueError(f"{key}: fragment musi zawierać dane, bez kolejnych odwołań $file")
        result[key] = selected
        composed = True
    return result, tuple(files), composed


def read_configuration(path: Path, *, ledger: SourceLedger | None = None) -> Any:
    """Assemble values without changing defaults, CLI overrides or domain validation."""
    return _read(path, ledger)[0]


def configuration_sources(path: Path) -> tuple[Path, ...]:
    """List the root and each referenced file once, in first-read order."""
    return _read(path)[1]


def track_configuration(path: Path, ledger: SourceLedger) -> None:
    """Pin every configuration input to the existing source-integrity ledger."""
    _read(path, ledger)


def configuration_snapshot(path: Path) -> bytes:
    """Keep flat JSON bytes; expand references into a self-contained run snapshot."""
    document, _, composed = _read(path)
    raw = Path(path).read_bytes()
    if not composed:
        return raw
    text = json.dumps(document, ensure_ascii=False, indent=2)
    if raw.endswith((b"\n", b"\r")):
        text += "\n"
    if b"\r\n" in raw:
        text = text.replace("\n", "\r\n")
    return (b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b"") + text.encode("utf-8")

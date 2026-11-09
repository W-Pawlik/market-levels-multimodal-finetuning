"""Existing UTF-8 report writer and BOM-aware JSON object reader."""
from __future__ import annotations

import json
from pathlib import Path


def write_json(path: Path, document: dict) -> None:
    """Zapisz raport lub manifest jako UTF-8, z dotychczasowym formatowaniem."""
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError(f'Oczekiwano obiektu JSON: {path}')
    return value

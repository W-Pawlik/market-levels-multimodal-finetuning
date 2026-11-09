"""Sealed directory inventories and exact file-integrity verification."""
from __future__ import annotations

import json
from pathlib import Path

from .json_io import write_json
from .integrity import sha256_file as sha256
from .paths import child


def seal(stage: Path, payload: dict) -> None:
    files = {p.relative_to(stage).as_posix(): sha256(p) for p in sorted(stage.rglob("*")) if p.is_file()}
    write_json(stage/"manifest.json", dict(payload, files=files))
    (stage/"manifest.sha256").write_text(sha256(stage/"manifest.json")+"\n", encoding="ascii")


def verify_files(output: Path) -> dict:
    manifest_path = output/"manifest.json"
    if (output/"manifest.sha256").read_text(encoding="ascii").strip() != sha256(manifest_path):
        raise ValueError("Niezgodny hash manifestu")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
    if actual != set(manifest["files"]) | {"manifest.json", "manifest.sha256"}:
        raise ValueError("Niezgodny inwentarz plików")
    for name, digest in manifest["files"].items():
        if sha256(child(output, name)) != digest:
            raise ValueError(f"Niezgodny hash pliku: {name}")
    return manifest

"""SHA-256 of file bytes and read-only source integrity tracking."""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Hash a file incrementally, retaining its exact bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(128 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SourceLedger:
    """Byte hashes of inputs before reading and after analysis; never writes them."""
    def __init__(self):
        self.files: dict[str, str] = {}

    def track(self, path: Path) -> Path:
        path = Path(path).resolve()
        key = str(path)
        digest = sha256_file(path)
        if key in self.files and self.files[key] != digest:
            raise ValueError(f"Źródło zmieniło się podczas analizy: {path}")
        self.files[key] = digest
        return path

    def verify(self) -> dict:
        changed = [p for p, digest in self.files.items() if sha256_file(Path(p)) != digest]
        if changed:
            raise ValueError(f"Zmienione źródła: {changed}")
        return {"unchanged": True, "file_count": len(self.files), "sha256": dict(self.files)}

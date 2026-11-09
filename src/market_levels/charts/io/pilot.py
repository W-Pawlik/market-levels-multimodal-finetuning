"""Verify and read the existing 32-example pilot artifact format."""
from __future__ import annotations

import json
from pathlib import Path

from ...data_processing.io.candles import read_candles_csv
from ...core.ohlc.identity import canonical_hash
from ...shared.integrity import sha256_file as sha256
from ...shared.paths import child


def read_pilot(pilot: Path) -> tuple[list, dict]:
    """Zweryfikuj każdy CSV/PNG/JSON i manifest przed obliczeniami."""
    manifest_path = pilot/"manifest.json"
    ledger = {str(manifest_path.resolve()): sha256(manifest_path)}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest["images"]
    if manifest["actual_count"] != 32 or len(records) != 32:
        raise ValueError("Etap 3.4 wymaga wszystkich 32 przykładów istniejącego pilotażu")
    if len({r["id"] for r in records}) != 32 or len({r["png"] for r in records}) != 32:
        raise ValueError("Powtórzone identyfikatory/pliki pilotażu")
    loaded = []
    for record in records:
        png, csv = child(pilot, record["png"]), child(pilot, record["window_csv"])
        sidecar = png.with_suffix(".json")
        if json.loads(sidecar.read_text(encoding="utf-8")) != record:
            raise ValueError(f"Niezgodny JSON: {sidecar}")
        for path, key in ((png, "png_sha256"), (csv, "window_csv_sha256")):
            if sha256(path) != record[key]:
                raise ValueError(f"Niezgodny SHA-256: {path}")
        for path in (png, csv, sidecar):
            ledger[str(path.resolve())] = sha256(path)
        candles = read_candles_csv(csv, source="labeling-pilot")
        if canonical_hash(candles) != record["ohlc_sha256"]:
            raise ValueError(f"Niezgodny OHLC: {csv}")
        loaded.append((record, candles))
    return loaded, ledger

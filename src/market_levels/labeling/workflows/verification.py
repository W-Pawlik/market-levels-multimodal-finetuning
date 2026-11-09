"""labeling / workflows / verification."""
from __future__ import annotations

import json
from pathlib import Path

from ..domain.models import VERSION
from ..domain.algorithm import label_window
from ...shared.integrity import sha256_file as sha256
from ...shared.paths import child
from ...charts.io.pilot import read_pilot
from ..io.overlays import render_levels
from ..reporting.pilot import summarize


def verify_labeling(output: Path, pilot: Path, *, re_render: bool = False) -> None:
    """Kontrola hashy, pochodzenia i ponownego obliczenia całej diagnostyki."""
    import tempfile
    manifest = json.loads((output/"manifest.json").read_text(encoding="utf-8"))
    if manifest["algorithm_version"] != VERSION or manifest["overlay_is_vlm_input"] is not False:
        raise ValueError("Niezgodna wersja lub przeznaczenie wyników")
    expected_files = {"summary.json", "RAPORT.md", "SOURCE_INTEGRITY.json"}
    expected_files.update(f"{folder}/{i:03d}.{suffix}" for i in range(32)
                          for folder, suffix in (("labels", "json"), ("diagnostics", "json"), ("overlays", "png")))
    actual_files = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
    if set(manifest["files"]) != expected_files or actual_files != expected_files | {"manifest.json"}:
        raise ValueError("Niekompletna lista plików lub hashy")
    for name, digest in manifest["files"].items():
        if sha256(child(output, name)) != digest:
            raise ValueError(f"Niezgodny hash wyniku: {name}")
    loaded, ledger = read_pilot(pilot)
    if manifest["count"] != 32 or len(manifest["images"]) != 32:
        raise ValueError("Niekompletny wynik")
    integrity = json.loads((output/"SOURCE_INTEGRITY.json").read_text(encoding="utf-8"))
    # W przeniesionym handoff ścieżki absolutne mogą się zmienić; porównujemy zawartość.
    if sorted(ledger.values()) != sorted(integrity["files"].values()) or not integrity["unchanged"]:
        raise ValueError("Źródłowy pilotaż zmienił się")
    results = []
    with tempfile.TemporaryDirectory(prefix="sr-verify-") as temporary:
        for i, ((record, candles), image) in enumerate(zip(loaded, manifest["images"])):
            if (image["label"], image["diagnostic"], image["overlay"]) != (f"labels/{i:03d}.json", f"diagnostics/{i:03d}.json", f"overlays/{i:03d}.png"):
                raise ValueError("Powtórzone lub niezgodne pliki w manifeście")
            result = label_window(candles)
            results.append((record, result))
            if (image["id"], image["source_png_sha256"], image["source_csv_sha256"], image["ohlc_sha256"]) != (record["id"], record["png_sha256"], record["window_csv_sha256"], record["ohlc_sha256"]):
                raise ValueError("Niezgodne pochodzenie")
            if child(output, image["label"]).read_text(encoding="utf-8") != result.target_json():
                raise ValueError("Niezgodna etykieta")
            expected = dict(result.diagnostics(), source_metadata=record, overlay_is_vlm_input=False)
            if json.loads(child(output, image["diagnostic"]).read_text(encoding="utf-8")) != expected:
                raise ValueError("Niezgodna diagnostyka")
            if re_render:
                path = Path(temporary)/f"{i:03d}.png"
                render_levels(candles, result, path)
                if sha256(path) != sha256(child(output, image["overlay"])):
                    raise ValueError("Niezgodny odtworzony PNG; sprawdź wersje renderera i fonty")
    if json.loads((output/"summary.json").read_text(encoding="utf-8")) != json.loads(json.dumps(summarize(results))):
        raise ValueError("Niezgodne podsumowanie")

"""data_processing / synthetic / workflows / generation."""
from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path

from ...io.candles import read_candles_csv, write_candles_csv
from ....shared.json_io import write_json
from ....shared.publication import publication_workspace, publish_directory
from ..domain.generation.models import GENERATOR_VERSION
from ..domain.generation.seeds import example_seed
from ..domain.generation.dispatch import generate_example
from ..domain.parameters import V2_VERSION
from ....core.ohlc.identity import canonical_hash
from ..domain.quality import compare_statistics, validate_synthetic
from ..config.generation import SyntheticSettings
from ..io.profiles import prepare_profiles


def run(settings: SyntheticSettings) -> Path:
    """Zapisz całą partię lub pozostaw poprzednie wyniki bez zmian."""
    profiles = prepare_profiles(settings)
    identity = {"configuration": settings.document(), "profiles": profiles,
                "generator_version": V2_VERSION if settings.generator_version == "v2" else GENERATOR_VERSION,
                "python": platform.python_version(),
                "implementation": platform.python_implementation()}
    # Katalog wyjściowy nie zmienia tożsamości danych ani identyfikatora partii.
    identity["configuration"].pop("output")
    run_id = hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False).encode()).hexdigest()[:24]
    output = Path(settings.output)
    final = output / ("diagnostics" if settings.diagnostic else "candidates") / run_id
    if final.exists():
        raise FileExistsError(f"Partia już istnieje (odmowa nadpisania): {final}")
    # Kontrola duplikatów także względem wcześniejszych partii w tym katalogu.
    seen_hashes = set()
    for mode in ("diagnostics", "candidates"):
        for path in (output / mode).glob("*/manifest.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            seen_hashes.update(entry["ohlc_sha256"] for entry in manifest["examples"])
    output.mkdir(parents=True, exist_ok=True)
    seen_seeds = set()
    entries = []
    with publication_workspace(output, prefix=".synthetic-") as temporary:
        stage = temporary / "batch"
        stage.mkdir()
        for symbol in settings.symbols:
            directory = stage / symbol
            directory.mkdir()
            for index in range(settings.count):
                seed = example_seed(settings.seed, symbol, index)
                if seed in seen_seeds:
                    raise ValueError("Kolizja seedów: przerwano całą partię")
                seen_seeds.add(seed)
                example = generate_example(symbol, seed, profiles[symbol], settings)
                metadata = dict(example.metadata)
                digest = metadata["ohlc_sha256"]
                if digest in seen_hashes:
                    raise ValueError("Duplikat OHLC: przerwano całą partię bez zapisu przykładów")
                seen_hashes.add(digest)
                example_id = f"{symbol}_{index:06d}_{seed:064x}"
                relative_csv = Path(symbol) / f"{example_id}.csv"
                write_candles_csv(stage / relative_csv, example.candles)
                restored = read_candles_csv(stage / relative_csv, source=example.candles[0].source_archive)
                if restored != example.candles or canonical_hash(restored) != digest:
                    raise ValueError("Błąd kontroli ponownego odczytu CSV")
                validate_synthetic(restored, metadata["regimes"], seed)
                metadata.update(id=example_id, csv=relative_csv.as_posix(), roundtrip_valid=True)
                if profiles[symbol]["status"] == "approved":
                    metadata["reference_comparison"] = compare_statistics(
                        metadata["statistics"], profiles[symbol]["statistics"])
                relative_json = relative_csv.with_suffix(".json")
                write_json(stage / relative_json, metadata)
                entries.append({"id": example_id, "symbol": symbol, "seed": seed,
                                "csv": relative_csv.as_posix(), "metadata": relative_json.as_posix(),
                                "ohlc_sha256": digest, "statistics": metadata["statistics"],
                                "regime_shares": metadata["regime_shares"]})
        manifest = {"run_id": run_id, "status": "diagnostic" if settings.diagnostic else "candidate",
                    "origin": "synthetic", "identity": identity, "examples": entries,
                    "accepted_count": len(entries), "rejected_count": 0,
                    "failure_policy": "fail-fast: błąd odrzuca całą partię; brak cichego ponawiania losowań",
                    "dataset_split": None, "visual_review": "pending_chart_renderer"}
        write_json(stage / "manifest.json", manifest)
        # Jedyny moment publikacji przykładów: rename kompletnego katalogu na tym samym dysku.
        final.parent.mkdir(parents=True, exist_ok=True)
        publish_directory(stage, final)
    return final

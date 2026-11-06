"""Generowanie i atomowe zatwierdzanie kompletnych partii syntetycznych."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform

from ..storage import read_candles_csv, write_candles_csv, write_json
from ..staging import publication_workspace, publish_directory
from ..synthetic.calibration import diagnostic_profile, load_profile, validate_generator_profile
from ..synthetic.generator import GENERATOR_VERSION, example_seed
from ..synthetic.dispatch import generate_example
from ..synthetic.profile_v2 import diagnostic_profile_v2, regime_configuration
from ..synthetic.v2_parameters import V2_VERSION
from ..synthetic.quality import canonical_hash, compare_statistics, validate_synthetic
from ..synthetic.regimes import feasible_sequences
from ..synthetic.settings import SyntheticSettings


def prepare_profiles(settings: SyntheticSettings) -> dict[str, dict]:
    """Walidacja pełnego wejścia także dla dry-run, bez tworzenia katalogów."""
    settings.validate()
    resolved_output = Path(settings.output).resolve()
    protected = {Path("data/processed").resolve(), Path(__file__).resolve().parents[4] / "data/processed"}
    if any(resolved_output == path or path in resolved_output.parents for path in protected):
        raise ValueError("Dane syntetyczne nie mogą być zapisywane w data/processed")
    feasible_sequences(settings)
    profiles = {}
    for symbol in settings.symbols:
        if symbol in settings.profiles:
            profile = load_profile(Path(settings.profiles[symbol]), symbol=symbol)
        elif settings.diagnostic:
            profile = (diagnostic_profile_v2(symbol, settings) if settings.generator_version == "v2"
                       else diagnostic_profile(symbol))
        else:
            raise ValueError(f"{symbol}: brak profilu kalibracyjnego; do prób użyj --diagnostic")
        validate_generator_profile(profile, symbol=symbol, generator_version=settings.generator_version)
        if (profile.get("calibration", {}).get("method") == "volatility_refinement_v1"
                and profile["calibration"]["variant"] != settings.v2_variant):
            raise ValueError("Profil refinement nie odpowiada wybranemu wariantowi v2")
        if settings.generator_version == "v2" and profile["regime_configuration"] != regime_configuration(settings):
            raise ValueError("Konfiguracja reżimów nie odpowiada profilowi v2")
        if not settings.diagnostic and profile["status"] != "approved":
            raise ValueError(f"{symbol}: niezatwierdzony profil; wymagany --diagnostic")
        profiles[symbol] = profile
    return profiles


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

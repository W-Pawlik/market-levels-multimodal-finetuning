"""datasets / config."""
from __future__ import annotations

from pathlib import Path

from ..data_processing.synthetic.config.generation import load_synthetic_settings
from ..shared.configuration import read_configuration
from ..shared.integrity import SourceLedger


SYMBOLS = ("BTCUSDT", "ETHUSDT")


SPLITS = ("train", "validation", "test")


SELECTION_METHOD = "chronological_equal_count_strata_seeded_v1"


def load_plan_config(config: Path, *, ledger: SourceLedger | None = None) -> dict:
    doc = read_configuration(config, ledger=ledger)
    options = doc["dataset_build"]
    if set(options) != {"targets", "selection_seed", "synthetic_master_seed", "profiles", "synthetic_history_root"}:
        raise ValueError("Nieobsługiwane/brakujące ustawienia dataset_build")
    if doc["candles_per_chart"] != 120 or doc["interval"] != "4h" or tuple(doc["symbols"]) != SYMBOLS:
        raise ValueError("Wymagane 120 świec 4h i BTCUSDT/ETHUSDT")
    if set(options["targets"]) != set(SPLITS):
        raise ValueError("Wymagane trzy splity liczebności")
    for name, targets in options["targets"].items():
        if set(targets) != {"real", "synthetic"}:
            raise ValueError("Wymagane liczebności real/synthetic")
        for source, by_symbol in targets.items():
            if set(by_symbol) != set(SYMBOLS) or any(type(v) is not int or v < 0 for v in by_symbol.values()):
                raise ValueError("Niepoprawne liczebności na instrument")
            if source == "synthetic" and name != "train" and any(by_symbol.values()):
                raise ValueError("Syntetyki mogą występować wyłącznie w train")
    total = sum(v for targets in options["targets"].values() for group in targets.values() for v in group.values())
    if not total:
        raise ValueError("Plan musi zawierać przykłady")
    for key in ("selection_seed", "synthetic_master_seed"):
        if type(options[key]) is not int or options[key] < 0:
            raise ValueError("Seed musi być nieujemną liczbą całkowitą")
    if set(options["profiles"]) != set(SYMBOLS) or not isinstance(options["synthetic_history_root"], str):
        raise ValueError("Wymagane jawne profile i katalog historii syntetyków")
    return doc


def synthetic_settings(config: Path, symbol: str, *, output: Path):
    """Production settings only. The existing approval gate remains authoritative."""
    options = load_plan_config(config)["dataset_build"]
    if symbol not in SYMBOLS:
        raise ValueError("Niepoprawny symbol")
    return load_synthetic_settings(config, generator_version="v2", v2_variant="full",
        profiles={symbol: options["profiles"][symbol]}, symbols=(symbol,),
        count=options["targets"]["train"]["synthetic"][symbol],
        seed=options["synthetic_master_seed"], diagnostic=False, output=output,
        experiment_id="dataset-3.5-v1")

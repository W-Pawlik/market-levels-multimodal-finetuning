"""Read-only real-data preflight and guarded synthetic generation contract."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from ..charts.diversity import SourceLedger
from ..data_processing.storage import read_candles_csv
from ..data_processing.windows import candidates, coverage, select_training, validate_selection
from ..data_processing.synthetic.calibration import load_profile, profile_hash
from ..data_processing.synthetic.generator import example_seed
from ..data_processing.synthetic.profile_v2 import regime_configuration
from ..data_processing.synthetic.settings import load_synthetic_settings
from ..data_processing.synthetic.training_period import load_chronological_split
from ..data_processing.pipelines.synthetic import prepare_profiles

SYMBOLS = ("BTCUSDT", "ETHUSDT")
SPLITS = ("train", "validation", "test")
SELECTION_METHOD = "chronological_equal_count_strata_seeded_v1"


def load_plan_config(config: Path) -> dict:
    doc = json.loads(config.read_text(encoding="utf-8-sig"))
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


def require_production_ready(config: Path) -> None:
    """No generation. Raises on any unapproved profile via existing pipeline."""
    for symbol in SYMBOLS:
        prepare_profiles(synthetic_settings(config, symbol, output=Path("data/synthetic/dataset35")))


def inspect_synthetic(config: Path, ledger: SourceLedger) -> dict:
    doc = load_plan_config(config)
    options = doc["dataset_build"]
    split = load_chronological_split(config)
    profiles, planned = {}, []
    for symbol in SYMBOLS:
        path = ledger.track(Path(options["profiles"][symbol]))
        profile = load_profile(path, symbol=symbol)
        settings = synthetic_settings(config, symbol, output=Path("data/synthetic/dataset35"))
        if (profile["version"] != 2 or profile["estimation_kind"] != "training"
                or profile["calibration"]["method"] != "volatility_refinement_v1"
                or profile["calibration"]["variant"] != "full"
                or profile["regime_configuration"] != regime_configuration(settings)
                or profile["source"]["chronological_split"] != split.document()):
            raise ValueError("Niezgodny profil V2-full-refined / konfiguracja / chronologia")
        split.require_training(*(datetime.fromisoformat(profile["period"][k]) for k in ("allowed_start", "allowed_end")))
        profiles[symbol] = {"path": str(path), "file_sha256": ledger.files[str(path)],
                            "profile_id": profile_hash(profile), "status": profile["status"],
                            "generator_version": profile["generator_version"],
                            "variant": "V2-full-refined", "parameters": profile["v2_parameters"],
                            "configuration": settings.document()}
        planned += [{"symbol": symbol, "split": "train", "index": i,
                     "master_seed": settings.seed, "seed": example_seed(settings.seed, symbol, i),
                     "profile_id": profile_hash(profile)} for i in range(settings.count)]
    history_root = Path(options["synthetic_history_root"])
    if not history_root.is_dir():
        raise FileNotFoundError(f"Brak historii do kontroli kolizji seedów: {history_root}")
    previous_seeds, masters, manifests = set(), set(), 0
    def reserved_seeds(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if 'seed' in key:
                    if type(item) is int:
                        masters.add(item)
                    elif isinstance(item, list):
                        masters.update(v for v in item if type(v) is int)
                reserved_seeds(item)
        elif isinstance(value, list):
            for item in value:
                reserved_seeds(item)
    reserved_seeds({k: v for k, v in doc.items() if k != 'dataset_build'})
    for symbol in SYMBOLS:
        reserved_seeds(load_profile(Path(options["profiles"][symbol]), symbol=symbol))
    for manifest_path in sorted(history_root.rglob("manifest.json")):
        if any(part.startswith(".") for part in manifest_path.relative_to(history_root).parts):
            continue
        manifest = json.loads(ledger.track(manifest_path).read_text(encoding="utf-8-sig"))
        if "identity" not in manifest or "examples" not in manifest:
            continue
        manifests += 1
        masters.add(manifest["identity"]["configuration"]["seed"])
        previous_seeds.update(e["seed"] for e in manifest["examples"])
    # Published datasets live separately from old generator batches. They also reserve seeds.
    for manifest_path in sorted((history_root.parent/'datasets').glob('*/manifest.json')):
        manifest = json.loads(ledger.track(manifest_path).read_text(encoding='utf-8'))
        if manifest.get('kind') != 'production_dataset':
            continue
        manifests += 1
        snapshot = json.loads(ledger.track(manifest_path.parent/'config.json').read_text(encoding='utf-8'))
        masters.add(snapshot['dataset_build']['synthetic_master_seed'])
    seeds = [p["seed"] for p in planned]
    if options["synthetic_master_seed"] in masters or len(set(seeds)) != len(seeds) or set(seeds) & previous_seeds:
        raise ValueError("Kolizja seedów planu z historią lub wewnątrz planu")
    try:
        require_production_ready(config)
        ready, block = True, None
    except ValueError as error:
        if any(p["status"] != "approved" for p in profiles.values()):
            ready, block = False, str(error)
        else:
            raise
    return {"profiles": profiles, "planned_examples": planned,
            "production_ready": ready, "production_block": block,
            "history_manifests": manifests, "history_seeds": len(previous_seeds),
            "reserved_master_seeds": sorted(masters),
            "collision_scope": str(history_root.resolve()), "seed_collisions": 0,
            "note": "Kontrola lokalnej historii; powtórzyć przed produkcją. Brak generacji i zmiany statusów."}


def build_plan(config: Path, real_csv: dict[str, Path]) -> dict:
    ledger = SourceLedger()
    ledger.track(config)
    doc = load_plan_config(config)
    split = load_chronological_split(config)
    options = doc["dataset_build"]
    strides = {s: doc[s+"_stride_candles"] for s in SPLITS}
    groups, chosen, problems, sources = {}, [], [], {}
    for symbol in SYMBOLS:
        path = Path(real_csv[symbol])
        if not path.is_file():
            problems.append(f"Brak CSV {symbol}: {path}")
            continue
        path = ledger.track(path)
        if not path.name.startswith(symbol+"_4h_"):
            raise ValueError("Nazwa CSV nie odpowiada symbolowi/interwałowi")
        sources[symbol] = {"path": str(path), "sha256": ledger.files[str(path)]}
        candles = read_candles_csv(path, source=str(path))
        pool, audit = candidates(candles, symbol, split, strides)
        groups[symbol] = {}
        for name in SPLITS:
            target = options["targets"][name]["real"][symbol]
            available = pool[name]
            if len(available) < target:
                selected = []
                problems.append(f"{symbol}/{name}: {len(available)} < {target}; bez zmiany liczebności/przesunięcia")
            else:
                selected = (select_training(available, target, options["selection_seed"])
                            if name == "train" else available[:target])
            chosen += selected
            groups[symbol][name] = dict(audit[name], target=target, selected=coverage(selected),
                                        candidates_coverage=coverage(available),
                                        unselected_ids=[w.document()["id"] for w in available if w not in selected])
    validate_selection(chosen, split)
    synthetic = inspect_synthetic(config, ledger)
    # Binding real provenance: profiles calibrated on the same pinned source files.
    for symbol, source in sources.items():
        profile = load_profile(Path(options["profiles"][symbol]), symbol=symbol)
        if profile["source"]["sha256"] != source["sha256"]:
            raise ValueError("Źródło profilu nie odpowiada CSV preflightu")
    real_total = sum(v for t in options["targets"].values() for v in t["real"].values())
    synthetic_total = sum(v for t in options["targets"].values() for v in t["synthetic"].values())
    return {"schema_version": 1, "status": "plan_only_not_dataset", "targets": options["targets"],
            "totals": {"real": real_total, "synthetic": synthetic_total, "total": real_total+synthetic_total,
                       "real_share": real_total/(real_total+synthetic_total)},
            "real_feasible": not problems, "problems": problems, "groups": groups,
            "chronological_split": split.document(), "selection_method": SELECTION_METHOD,
            "selection_seed": options["selection_seed"],
            "selection_description": "Chronologiczni kandydaci train podzieleni na N kolejnych warstw o prawie równej liczbie; jeden indeks z każdej przez lokalny Random(seed). Bez etykiet i cech cenowych. Validation/test: pierwsze planowane okna chronologicznie.",
            "real_sources": sources, "selected_real": [w.document() for w in chosen],
            "synthetic": synthetic, "source_integrity": ledger.verify(),
            "audit_only": True, "dependence_note": "Train może nakładać się w czasie. BTC i ETH z tego samego okresu nie są niezależnymi obserwacjami rynku."}

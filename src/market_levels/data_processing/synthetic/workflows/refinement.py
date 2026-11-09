"""data_processing / synthetic / workflows / refinement."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

from ...io.candles import read_candles_csv
from ..domain.profiles.v1 import profile_hash
from ..domain.calibration.features import calibration_features
from ..domain.diagnostics import aggregate_windows
from ..domain.generation.seeds import example_seed
from ..domain.generation.v2 import generate_example_v2
from ..domain.profiles.v2 import regime_configuration
from ..domain.profiles.validation import validate_profile_v2
from ...windows.domain.selection import select_real_windows
from ..config.generation import SyntheticSettings
from ....core.time.periods import ChronologicalSplit
from ..config.refinement import (
    METHOD,
    REFINEMENT_VARIANTS,
    VOLATILITY_KEYS,
    CRITERION,
    SELECTION_RULE,
    RefinementSettings,
)
from ..domain.calibration.objectives import refinement_objective, _trial_score
from ..domain.calibration.candidates import _candidate_parameters


def refine_v2_volatility(real_csv: Path, source_profile_path: Path, *, symbol: str, variant: str,
                          start: datetime, end: datetime, split: ChronologicalSplit,
                          settings: SyntheticSettings, search: RefinementSettings,
                          expected_source_sha256: str | None = None) -> dict:
    split.require_training(start, end)
    search.validate()
    settings.validate()
    if variant not in REFINEMENT_VARIANTS or settings.generator_version != "v2":
        raise ValueError("Refinement wymaga v2 i wariantu full albo bridge_volatility")
    raw_source = Path(source_profile_path).read_bytes()
    file_hash = hashlib.sha256(raw_source).hexdigest()
    if expected_source_sha256 is not None and expected_source_sha256.lower() != file_hash:
        raise ValueError("SHA-256 pliku profilu źródłowego nie odpowiada oczekiwanej wartości")
    source = json.loads(raw_source.decode("utf-8-sig"))
    if source.get("calibration", {}).get("method") == METHOD:
        raise ValueError("Ta iteracja wymaga oryginalnego profilu v2, nie kolejnego refinement")
    validate_profile_v2(source, symbol=symbol)
    if source["estimation_kind"] != "training" or source["source"]["chronological_split"] != split.document():
        raise ValueError("Wymagany empiryczny profil v2 z obecnego zatwierdzonego treningu")
    if source["regime_configuration"] != regime_configuration(settings):
        raise ValueError("Refinement nie może zmieniać konfiguracji reżimów")
    split.require_training(*(datetime.fromisoformat(source["period"][k]) for k in ("allowed_start", "allowed_end")))
    if not (datetime.fromisoformat(source["period"]["allowed_start"]) <= start < end
            <= datetime.fromisoformat(source["period"]["allowed_end"])):
        raise ValueError("Okres refinement wychodzi poza źródłowy okres kalibracji")
    candidates = _candidate_parameters(source, search)
    raw_csv = Path(real_csv).read_bytes()
    if hashlib.sha256(raw_csv).hexdigest() != source["source"]["sha256"]:
        raise ValueError("CSV nie odpowiada SHA-256 źródła oryginalnego profilu; nie zmieniono danych ani profilu")
    candles = read_candles_csv(Path(real_csv), source=str(real_csv))
    count = len(search.simulation_seeds)*search.examples_per_seed
    reference_windows, selection = select_real_windows(candles, symbol=symbol, start=start, end=end,
        count=count, seed=search.selection_seed, split=split)
    reference = calibration_features(aggregate_windows(reference_windows))
    # Cel wymaga określonych metryk; nie zastępujemy null arbitralnymi zerami.
    refinement_objective(reference, reference, search)
    profile = deepcopy(source)
    profile["status"] = "unapproved"
    profile.pop("approval", None)
    profile["calibration"] = {"method": METHOD, "phase": "evaluation", "status": "unapproved",
        "variant": variant, "source_profile": source, "source_profile_sha256": profile_hash(source),
        "source_profile_file_sha256": file_hash, "source_profile_path": str(Path(source_profile_path).resolve()),
        "search": asdict(search), "simulation_seeds": search.simulation_seeds,
        "requested_period": {"start": start.isoformat(), "end": end.isoformat()},
        "reference_selection": selection, "reference_features": reference,
        "changed_parameters": list(VOLATILITY_KEYS),
        "criterion": CRITERION,
        "profile_family": "refined", "selection_rule": SELECTION_RULE}
    trials = []
    baseline_features = None
    for parameters in candidates:
        candidate = deepcopy(profile)
        candidate["v2_parameters"] = parameters
        windows, by_seed = [], []
        for seed in search.simulation_seeds:
            config = replace(settings, diagnostic=True, seed=seed, count=search.examples_per_seed,
                             v2_variant=variant, experiment_id=METHOD+"-evaluation")
            seed_windows = [generate_example_v2(symbol, example_seed(seed, symbol, i), candidate, config,
                            calibration_evaluation=True).candles for i in range(search.examples_per_seed)]
            windows.extend(seed_windows)
            by_seed.append(calibration_features(aggregate_windows(seed_windows)))
        if baseline_features is None:
            baseline_features = by_seed
        loss, seed_scores = _trial_score(by_seed, reference, search, baseline_features)
        trials.append({"parameters": parameters, "loss": loss, "features_by_seed": by_seed,
                       "seed_objectives": seed_scores, "pooled_features": calibration_features(aggregate_windows(windows))})
    best = min(trials, key=lambda trial: trial["loss"])
    profile["v2_parameters"] = deepcopy(best["parameters"])
    profile["calibration"].update(phase="complete", trials=trials,
        baseline_features_by_seed=baseline_features, baseline_loss=trials[0]["loss"],
        selected_parameters=deepcopy(best["parameters"]), selected_loss=best["loss"],
        selection_reason="Najmniejszy wieloseedowy błąd z karą pogorszenia kontroli; remisy zachowują pierwszy punkt, w tym baseline.")
    for key in VOLATILITY_KEYS:
        profile["parameter_provenance"][key] = METHOD+"; training only; unapproved"
    validate_profile_v2(profile, symbol=symbol)
    return profile

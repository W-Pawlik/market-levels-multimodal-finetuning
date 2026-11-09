"""data_processing / synthetic / workflows / calibration."""
from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from dataclasses import replace
from itertools import product

from ....core.ohlc.model import Candle
from ..domain.quality import series_statistics
from ..domain.parameters import SYMBOLS, V2Parameters
from ...io.candles import read_candles_csv
from ..domain.diagnostics import aggregate_windows
from ..domain.generation.seeds import example_seed
from ..domain.generation.v2 import generate_example_v2
from ..domain.profiles.v2 import make_profile_v2
from ..domain.profiles.validation import validate_profile_v2
from ...windows.domain.selection import select_real_windows
from ..config.generation import SyntheticSettings
from ....core.time.periods import ChronologicalSplit, validate_period
from ..domain.profiles.v1 import PROFILE_VERSION, validate_profile
from ..config.calibration import CalibrationV2Settings
from ..domain.calibration.features import calibration_features, training_volatility_diagnostics
from ..domain.calibration.objectives import objective


def calibrate(candles: list[Candle], symbol: str, *, allowed_start: datetime | None,
              allowed_end: datetime | None, source: dict) -> dict:
    """Oszacuj profil wyłącznie z obserwacji we wskazanym domkniętym okresie."""
    validate_period(allowed_start, allowed_end)
    if symbol not in SYMBOLS or not isinstance(source, dict) or not source:
        raise ValueError("Wymagane instrument BTC/ETH i jawne źródło danych")
    selected = [c for c in candles if allowed_start <= c.timestamp <= allowed_end]
    if len(selected) < 3:
        raise ValueError("Kalibracja wymaga co najmniej trzech obserwacji")
    stats = series_statistics(selected)
    sigma = stats["log_returns"]["std"]
    if sigma <= 0:
        raise ValueError("Nie można kalibrować zerowej zmienności")
    profile = {"version": PROFILE_VERSION, "symbol": symbol, "status": "unapproved",
               "source": deepcopy(source),
               "period": {"allowed_start": allowed_start.isoformat(), "allowed_end": allowed_end.isoformat(),
                          "observed_start": selected[0].timestamp.isoformat(),
                          "observed_end": selected[-1].timestamp.isoformat(), "bounds": "inclusive"},
               "observations": len(selected),
               "skipped_noncontiguous_transitions": stats["skipped_noncontiguous_transitions"],
               "statistics": stats,
               "generator_parameters": {"sigma_4h": sigma, "initial_price_range": [
                   stats["close_prices"]["quantiles"]["0.05"], stats["close_prices"]["quantiles"]["0.95"]]},
               "parameter_status": "sigma i ceny oszacowane; reżimy pozostają projektowe"}
    validate_profile(profile)
    return profile


def calibrate_csv(path: Path, symbol: str, *, allowed_start: datetime | None,
                  allowed_end: datetime | None) -> dict:
    """Ręczna kalibracja; brak granic zatrzymuje proces jeszcze przed odczytem."""
    validate_period(allowed_start, allowed_end)
    path = Path(path)
    return calibrate(read_candles_csv(path, source=str(path)), symbol,
                     allowed_start=allowed_start, allowed_end=allowed_end,
                     source={"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                             "description": "OHLC użytkownika; symbol zadeklarowany przez wywołującego"})


def calibrate_v2_csv(path: Path, symbol: str, *, start: datetime, end: datetime,
                     split: ChronologicalSplit, settings: SyntheticSettings,
                     search: CalibrationV2Settings) -> dict:
    split.require_training(start, end)
    settings.validate()
    search.validate()
    if settings.generator_version != "v2":
        raise ValueError("Kalibracja v2 wymaga ustawień v2")
    path = Path(path)
    candles = read_candles_csv(path, source=str(path))
    base = calibrate(candles, symbol, allowed_start=start, allowed_end=end,
                     source={"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                             "chronological_split": split.document(), "description": "OHLC użytkownika; trening v2"})
    profile = make_profile_v2(base, settings, diagnostic=False)
    count = len(search.simulation_seeds) * search.examples_per_seed
    reference_windows, selection = select_real_windows(candles, symbol=symbol, start=start, end=end,
        count=count, seed=search.selection_seed, split=split)
    reference = calibration_features(aggregate_windows(reference_windows))
    current = V2Parameters(**profile["v2_parameters"])
    trials, cache = [], {}

    def evaluate(parameters):
        key = tuple(parameters.document().values())
        if key not in cache:
            candidate = deepcopy(profile)
            candidate["v2_parameters"] = parameters.document()
            simulated = []
            per_seed = []
            for seed in search.simulation_seeds:
                config = replace(settings, diagnostic=True, seed=seed, count=search.examples_per_seed,
                                 v2_variant="full", experiment_id="v2-calibration")
                windows = [generate_example_v2(symbol, example_seed(seed, symbol, i), candidate, config).candles
                           for i in range(search.examples_per_seed)]
                simulated.extend(windows)
                per_seed.append(calibration_features(aggregate_windows(windows)))
            features = calibration_features(aggregate_windows(simulated))
            loss, terms = objective(features, reference)
            cache[key] = {"parameters": parameters.document(), "loss": loss, "loss_terms": terms,
                          "features": features, "features_by_seed": per_seed}
            trials.append(cache[key])
        return cache[key]["loss"]

    evaluate(current)
    groups = (("volatility_phi", "volatility_stationary_std"),
              ("tail_probability", "tail_scale"), ("bridge_gamma",))
    history = []
    for round_index in range(search.rounds):
        for names in groups:
            candidates = [current] + [replace(current, **dict(zip(names, values)))
                                      for values in product(*(getattr(search, name) for name in names))]
            current = min(candidates, key=evaluate)
            history.append({"round": round_index + 1, "group": list(names),
                            "selected_parameters": current.document(), "loss": evaluate(current)})
    profile["v2_parameters"] = current.document()
    for name in current.document():
        profile["parameter_provenance"][name] = "bounded_joint_simulation_calibration; training only; unapproved"
    profile["calibration"] = {"method": "bounded_coordinate_grid_full_model_v1", "status": "unapproved",
        "search": deepcopy(search.__dict__), "simulation_seeds": search.simulation_seeds,
        "reference_selection": selection, "reference_features": reference,
        "training_volatility_diagnostics": training_volatility_diagnostics([c for c in candles if start <= c.timestamp <= end]),
        "trials": trials, "coordinate_history": history, "selected_parameters": current.document(),
        "selected_loss": evaluate(current),
        "criterion": "mean squared scaled errors; positive scales relative to reference (floor 1e-5), proportions/ac1 scale .25, exceedances .05, log1p kurtosis weight .25",
        "limitations": "bounded coordinate search, not global optimum; joint full-model fit; common random numbers on several calibration seeds; no independent validation"}
    validate_profile_v2(profile, symbol=symbol)
    return profile

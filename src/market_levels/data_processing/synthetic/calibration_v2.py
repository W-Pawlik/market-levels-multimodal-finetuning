"""Ograniczona kalibracja łącznego modelu na kilku seedach treningowych."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime
import hashlib
from itertools import product
import json
import math
from pathlib import Path

from ..storage import read_candles_csv
from .calibration import calibrate
from .comparison import aggregate_windows, lag1_absolute_correlation
from .generator import example_seed
from .generator_v2 import generate_example_v2
from .profile_v2 import make_profile_v2, validate_profile_v2
from .quality import distribution, series_observations
from .selection import select_real_windows
from .settings import SyntheticSettings, positive_int
from .training_period import ChronologicalSplit
from .v2_parameters import V2Parameters


@dataclass(frozen=True)
class CalibrationV2Settings:
    simulation_seeds: list[int] = field(default_factory=lambda: [73001, 73002, 73003])
    selection_seed: int = 73004
    examples_per_seed: int = 4
    rounds: int = 2
    bridge_gamma: list[float] = field(default_factory=lambda: [1.0, 1.4, 1.8, 2.2])
    tail_probability: list[float] = field(default_factory=lambda: [0.02, 0.05, 0.1])
    tail_scale: list[float] = field(default_factory=lambda: [2.0, 3.0, 4.0])
    volatility_phi: list[float] = field(default_factory=lambda: [0.8, 0.95, 0.99])
    volatility_stationary_std: list[float] = field(default_factory=lambda: [0.0, 0.3, 0.6])

    def validate(self) -> None:
        if (not isinstance(self.simulation_seeds, list) or len(self.simulation_seeds) < 2
                or any(type(s) is not int or s < 0 for s in self.simulation_seeds)
                or len(set(self.simulation_seeds)) != len(self.simulation_seeds)):
            raise ValueError("Kalibracja wymaga co najmniej dwóch różnych nieujemnych seedów")
        if type(self.selection_seed) is not int or self.selection_seed < 0:
            raise ValueError("Niepoprawny seed wyboru okien kalibracyjnych")
        positive_int(self.examples_per_seed, "examples_per_seed")
        if type(self.rounds) is not int or not 1 <= self.rounds <= 3:
            raise ValueError("Ograniczona kalibracja obsługuje 1..3 rundy")
        for name in V2Parameters.__dataclass_fields__:
            values = getattr(self, name)
            if not isinstance(values, list) or not values or len(values) > 10:
                raise ValueError(f"{name}: wymagana siatka 1..10 wartości")
            for value in values:
                replace(V2Parameters(), **{name: value}).validate()


def load_calibration_v2_settings(path: Path) -> CalibrationV2Settings:
    options = json.loads(Path(path).read_text(encoding="utf-8-sig")).get("synthetic_v2_calibration", {})
    if not isinstance(options, dict) or set(options) - set(CalibrationV2Settings.__dataclass_fields__):
        raise ValueError("Nieobsługiwane ustawienia synthetic_v2_calibration")
    result = CalibrationV2Settings(**options)
    result.validate()
    return result


def calibration_features(stats: dict) -> dict:
    pooled, window = stats["pooled_observations"], stats["window_distributions"]
    result = {"return_std": pooled["log_returns"]["std"],
              "abs_q95": pooled["absolute_log_returns"]["quantiles"]["0.95"],
              "abs_q99": pooled["absolute_log_returns"]["quantiles"]["0.99"],
              "range_mean": pooled["relative_range"]["mean"],
              "range_q95": pooled["relative_range"]["quantiles"]["0.95"],
              "body_fraction": pooled["body_fraction"]["mean"],
              "upper_wick": pooled["upper_wick_fraction"]["mean"],
              "lower_wick": pooled["lower_wick_fraction"]["mean"],
              "window_std_mean": window["return_std"]["mean"],
              "window_std_std": window["return_std"]["std"],
              "abs_ac1": stats["absolute_return_lag1"]["value"]}
    for key in ("pearson_kurtosis", "exceedance_abs_2sigma", "exceedance_abs_3sigma"):
        result[key] = stats["return_diagnostics"][key]
    return result


def objective(observed: dict, reference: dict) -> tuple[float, dict]:
    """Wspólny wielometryczny błąd; brak progów automatycznego zatwierdzenia."""
    terms = {}
    for name, target in reference.items():
        value = observed[name]
        if target is None or value is None:
            continue
        if name == "pearson_kurtosis":
            error = 0.25 * (math.log1p(value) - math.log1p(target))
        elif name in ("body_fraction", "upper_wick", "lower_wick", "abs_ac1"):
            error = (value - target) / 0.25
        elif name.startswith("exceedance"):
            error = (value - target) / 0.05
        else:
            error = (value - target) / max(abs(target), 1e-5)
        terms[name] = error * error
    return math.fsum(terms.values()) / len(terms), terms


def training_volatility_diagnostics(candles: list) -> dict:
    """Ruchome std z 24 zwrotów, bez przechodzenia przez luki; krok 1 świeca."""
    from ...core.candles import CANDLE_DELTA
    runs = []
    for candle in candles:
        if not runs or candle.timestamp - runs[-1][-1].timestamp != CANDLE_DELTA:
            runs.append([])
        runs[-1].append(candle)
    rolling, returns = [], []
    for run in runs:
        if len(run) < 2:
            continue
        r = series_observations(run)["log_returns"]
        returns.append(r)
        rolling.extend(distribution(r[i:i+24])["std"] for i in range(len(r)-23))
    return {"rolling_return_count": 24, "rolling_stride_candles": 1,
            "rolling_std": distribution(rolling) if rolling else None,
            "absolute_return_lag1": lag1_absolute_correlation(returns)}


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

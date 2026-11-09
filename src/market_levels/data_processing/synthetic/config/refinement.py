"""data_processing / synthetic / config / refinement."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from ....core.numeric.validation import finite_number, positive_int
from ..domain.parameters import V2Parameters


METHOD = "volatility_refinement_v1"


REFINEMENT_VARIANTS = ("full", "bridge_volatility")


VOLATILITY_KEYS = ("volatility_phi", "volatility_stationary_std")


PRIORITY = ("abs_ac1", "window_std_mean", "window_std_std")


METRIC_KINDS = {"abs_ac1": "absolute", "window_std_mean": "relative", "window_std_std": "relative",
                "abs_q95": "relative", "abs_q99": "relative", "range_mean": "relative",
                "body_fraction": "absolute", "upper_wick": "absolute", "lower_wick": "absolute"}


FROZEN_FIELDS = ("symbol", "source", "period", "observations", "skipped_noncontiguous_transitions",
                 "statistics", "generator_parameters", "regime_configuration", "estimation_kind")


CRITERION = "per-seed weighted normalized squared errors + control deterioration guard; mean/worst-seed blend"


SELECTION_RULE = "minimum_loss_then_input_order; baseline included first"


@dataclass(frozen=True)
class RefinementSettings:
    volatility_phi: list[float] = field(default_factory=lambda: [.65, .75, .85, .90, .94, .97, .99])
    volatility_stationary_std: list[float] = field(default_factory=lambda: [.25, .35, .45, .55, .65])
    simulation_seeds: list[int] = field(default_factory=lambda: [73001, 73002, 73003])
    diagnostic_seeds: list[int] = field(default_factory=lambda: [20261105, 20261115, 20261125, 20261205, 20261215])
    selection_seed: int = 73004
    examples_per_seed: int = 12
    max_candidates: int = 64
    max_simulated_windows: int = 2304
    tolerances: dict[str, float] = field(default_factory=lambda: dict(
        abs_ac1=.05, window_std_mean=.10, window_std_std=.20, abs_q95=.15,
        abs_q99=.15, range_mean=.10, body_fraction=.03, upper_wick=.03, lower_wick=.03))
    weights: dict[str, float] = field(default_factory=lambda: {key: 3.0 if key in PRIORITY else 1.0 for key in METRIC_KINDS})
    guard_penalty: float = 4.0
    worst_seed_weight: float = .25
    relative_floor: float = 1e-8
    practical_equivalence_fraction: float = .10

    def validate(self) -> None:
        for name, minimum in (("simulation_seeds", 3), ("diagnostic_seeds", 2)):
            values = getattr(self, name)
            if (not isinstance(values, list) or len(values) < minimum
                    or any(type(s) is not int or s < 0 for s in values) or len(set(values)) != len(values)):
                raise ValueError(f"{name}: wymagane co najmniej {minimum} różne nieujemne seedy")
        if set(self.simulation_seeds) & set(self.diagnostic_seeds):
            raise ValueError("Seedy kalibracyjne i diagnostyczne muszą być rozłączne")
        if type(self.selection_seed) is not int or self.selection_seed < 0:
            raise ValueError("Niepoprawny seed selekcji refinement")
        for name in ("examples_per_seed", "max_candidates", "max_simulated_windows"):
            positive_int(getattr(self, name), name)
        for name in VOLATILITY_KEYS:
            values = getattr(self, name)
            if not isinstance(values, list) or not values or len(values) > 20 or len(set(values)) != len(values):
                raise ValueError(f"{name}: wymagana niepusta siatka maksymalnie 20 różnych wartości")
            for value in values:
                replace(V2Parameters(), **{name: value}).validate()
        for name in ("tolerances", "weights"):
            values = getattr(self, name)
            if not isinstance(values, dict) or set(values) != set(METRIC_KINDS):
                raise ValueError(f"{name}: wymagany komplet metryk refinement")
            for key, value in values.items():
                finite_number(value, key, positive=True)
        for name in ("guard_penalty", "relative_floor", "practical_equivalence_fraction"):
            finite_number(getattr(self, name), name, positive=True)
        if not 0 <= finite_number(self.worst_seed_weight, "worst_seed_weight") <= 1:
            raise ValueError("worst_seed_weight musi mieścić się w [0,1]")


def load_refinement_settings(path: Path) -> RefinementSettings:
    options = json.loads(Path(path).read_text(encoding="utf-8-sig")).get("volatility_refinement_v1", {})
    if not isinstance(options, dict) or set(options) - set(RefinementSettings.__dataclass_fields__):
        raise ValueError("Nieobsługiwane ustawienia volatility_refinement_v1")
    settings = RefinementSettings(**options)
    settings.validate()
    return settings

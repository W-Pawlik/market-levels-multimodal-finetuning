"""data_processing / synthetic / config / calibration."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from ....core.numeric.validation import positive_int
from ..domain.parameters import V2Parameters
from ....shared.configuration import read_configuration


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
    options = read_configuration(path).get("synthetic_v2_calibration", {})
    if not isinstance(options, dict) or set(options) - set(CalibrationV2Settings.__dataclass_fields__):
        raise ValueError("Nieobsługiwane ustawienia synthetic_v2_calibration")
    result = CalibrationV2Settings(**options)
    result.validate()
    return result

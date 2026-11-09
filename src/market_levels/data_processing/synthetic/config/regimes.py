"""data_processing / synthetic / config / regimes."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.parameters import KINDS
from ....core.numeric.validation import positive_int, finite_number


@dataclass(frozen=True)
class RegimeSettings:
    """Wartości projektowe, wymagające późniejszej oceny empirycznej."""

    minimum_lengths: dict[str, int] = field(default_factory=lambda: dict(
        uptrend=24, downtrend=24, consolidation=24, breakout=8))
    maximum_lengths: dict[str, int] = field(default_factory=lambda: dict(
        uptrend=120, downtrend=120, consolidation=120, breakout=24))
    initial_weights: dict[str, float] = field(default_factory=lambda: dict(
        uptrend=1.0, downtrend=1.0, consolidation=2.0, breakout=0.0))
    transitions: dict[str, dict[str, float]] = field(default_factory=lambda: {
        "uptrend": dict(downtrend=1.0, consolidation=2.0),
        "downtrend": dict(uptrend=1.0, consolidation=2.0),
        "consolidation": dict(uptrend=1.0, downtrend=1.0, breakout=3.0),
        "breakout": dict(uptrend=1.0, downtrend=1.0, consolidation=1.0),
    })
    trend_drift_sigma: tuple[float, float] = (0.08, 0.25)
    breakout_drift_sigma: tuple[float, float] = (0.4, 0.9)
    trend_volatility: tuple[float, float] = (0.8, 1.2)
    consolidation_volatility: tuple[float, float] = (0.45, 0.8)
    breakout_volatility: tuple[float, float] = (1.2, 1.8)
    mean_reversion: tuple[float, float] = (0.05, 0.2)

    def validate(self) -> None:
        for mapping in (self.minimum_lengths, self.maximum_lengths, self.initial_weights):
            if not isinstance(mapping, dict) or set(mapping) != set(KINDS):
                raise ValueError("Mapy długości/wag muszą obejmować dokładnie cztery reżimy")
        for kind in KINDS:
            lo = positive_int(self.minimum_lengths[kind], "minimum_lengths")
            hi = positive_int(self.maximum_lengths[kind], "maximum_lengths")
            if lo > hi or hi > 120:
                raise ValueError("Długości reżimów: wymagane minimum <= maksimum <= 120")
            weight = finite_number(self.initial_weights[kind], "initial_weights")
            if weight < 0 or (kind == "breakout" and weight != 0):
                raise ValueError("Wagi nieujemne; wybicie wymaga poprzedzającej konsolidacji")
        if not isinstance(self.transitions, dict) or set(self.transitions) != set(KINDS):
            raise ValueError("transitions musi opisywać cztery reżimy")
        for previous, weights in self.transitions.items():
            if not isinstance(weights, dict):
                raise ValueError("Wiersz transitions musi być mapą wag")
            for kind, weight in weights.items():
                if kind not in KINDS or finite_number(weight, "transition weight") < 0:
                    raise ValueError("Niepoprawne przejście reżimu")
                if weight > 0 and (kind == previous or (kind == "breakout" and previous != "consolidation")):
                    raise ValueError("Powtórzenie reżimu lub wybicie bez konsolidacji jest niedozwolone")
        for name in ("trend_drift_sigma", "breakout_drift_sigma", "trend_volatility",
                     "consolidation_volatility", "breakout_volatility", "mean_reversion"):
            values = getattr(self, name)
            if not isinstance(values, (tuple, list)) or len(values) != 2:
                raise ValueError(f"{name}: wymagany zakres [min, max]")
            lo, hi = (finite_number(v, name, positive=True) for v in values)
            if lo > hi or (name == "mean_reversion" and hi > 1):
                raise ValueError(f"{name}: niepoprawny zakres")
        if self.maximum_lengths["breakout"] >= min(
                self.maximum_lengths[k] for k in KINDS if k != "breakout"):
            raise ValueError("Wybicie musi mieć krótszą maksymalną długość od pozostałych faz")

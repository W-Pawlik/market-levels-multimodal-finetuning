"""Jawne parametry eksperymentu i roboczego planowania reżimów."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path

SYMBOLS = ("BTCUSDT", "ETHUSDT")
KINDS = ("uptrend", "downtrend", "consolidation", "breakout")


def positive_int(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name}: wymagana dodatnia liczba całkowita")
    return value


def finite_number(value: object, name: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name}: wymagana skończona liczba")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name}: liczba poza zakresem float") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name}: wymagana skończona liczba")
    if positive and number <= 0:
        raise ValueError(f"{name}: wymagana wartość dodatnia")
    return number


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


@dataclass(frozen=True)
class SyntheticSettings:
    candles: int = 120
    internal_steps: int = 12
    min_regimes: int = 1
    max_regimes: int = 3
    seed: int = 20261103
    symbols: tuple[str, ...] = SYMBOLS
    count: int = 5
    profiles: dict[str, str] = field(default_factory=dict)
    output: Path = Path("data/synthetic")
    diagnostic: bool = False
    regimes: RegimeSettings = field(default_factory=RegimeSettings)

    def validate(self) -> None:
        if type(self.candles) is not int or self.candles != 120:
            raise ValueError("Zatwierdzono dokładnie 120 świec")
        if type(self.internal_steps) is not int or self.internal_steps != 12:
            raise ValueError("Zatwierdzono dokładnie 12 kroków wewnętrznych")
        if (type(self.min_regimes) is not int or type(self.max_regimes) is not int
                or not 1 <= self.min_regimes <= self.max_regimes <= 3):
            raise ValueError("Liczba reżimów musi mieścić się w 1..3")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed musi być nieujemną liczbą całkowitą")
        positive_int(self.count, "count (liczba przykładów na instrument)")
        if (not isinstance(self.symbols, (tuple, list)) or not self.symbols
                or any(s not in SYMBOLS for s in self.symbols) or len(set(self.symbols)) != len(self.symbols)):
            raise ValueError("symbols: unikalna lista BTCUSDT/ETHUSDT")
        if type(self.diagnostic) is not bool:
            raise ValueError("diagnostic wymaga true/false")
        if not isinstance(self.profiles, dict) or any(
                k not in SYMBOLS or not isinstance(v, str) or not v.strip() for k, v in self.profiles.items()):
            raise ValueError("profiles: mapa symbol -> ścieżka JSON")
        if not str(self.output).strip():
            raise ValueError("output wymaga ścieżki")
        self.regimes.validate()

    def document(self) -> dict:
        result = asdict(self)
        result["output"] = str(self.output)
        return result


def load_synthetic_settings(path: Path, **overrides: object) -> SyntheticSettings:
    """Wczytaj wyłącznie sekcję synthetic; CLI ma pierwszeństwo."""
    document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict) or not isinstance(document.get("synthetic"), dict):
        raise ValueError("Konfiguracja wymaga obiektu synthetic")
    options = dict(document["synthetic"])
    options.update({k: v for k, v in overrides.items() if v is not None})
    allowed = set(SyntheticSettings.__dataclass_fields__)
    if set(options) - allowed:
        raise ValueError(f"Nieobsługiwane ustawienia synthetic: {sorted(set(options) - allowed)}")
    regime_options = options.pop("regimes", {})
    if not isinstance(regime_options, dict) or set(regime_options) - set(RegimeSettings.__dataclass_fields__):
        raise ValueError("Nieobsługiwane ustawienia regimes")
    options["regimes"] = RegimeSettings(**regime_options)
    if "output" in options:
        if not isinstance(options["output"], (str, Path)) or not str(options["output"]).strip():
            raise ValueError("output wymaga niepustej ścieżki")
        options["output"] = Path(options["output"])
    settings = SyntheticSettings(**options)
    settings.validate()
    return settings

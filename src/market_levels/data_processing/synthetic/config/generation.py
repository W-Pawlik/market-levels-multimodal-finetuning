"""data_processing / synthetic / config / generation."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..domain.parameters import SYMBOLS
from ....core.numeric.validation import positive_int
from .regimes import RegimeSettings
from ....shared.configuration import read_configuration


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
    generator_version: str = "v1"
    v2_variant: str = "full"
    experiment_id: str = "ohlc-v2-diagnostic"
    v2_parameters: dict = field(default_factory=dict)

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
        from ..domain.parameters import VARIANTS, V2Parameters
        if self.generator_version not in ("v1", "v2") or self.v2_variant not in VARIANTS:
            raise ValueError("Niepoprawna wersja generatora lub wariant v2")
        if self.generator_version == "v1" and self.v2_variant != "full":
            raise ValueError("Wariant v2 wymaga generator_version=v2")
        if not isinstance(self.experiment_id, str) or not self.experiment_id.strip():
            raise ValueError("experiment_id wymaga niepustego tekstu")
        if not isinstance(self.v2_parameters, dict) or set(self.v2_parameters) - set(V2Parameters.__dataclass_fields__):
            raise ValueError("Niepoprawne lub nieobsługiwane parametry v2")
        V2Parameters(**self.v2_parameters).validate()

    def document(self) -> dict:
        result = asdict(self)
        result["output"] = str(self.output)
        if self.generator_version == "v1":
            # Zachowanie historycznych metadanych i identyfikatora partii v1.
            for key in ("generator_version", "v2_variant", "experiment_id", "v2_parameters"):
                result.pop(key)
        return result


def load_synthetic_settings(path: Path, **overrides: object) -> SyntheticSettings:
    """Wczytaj wyłącznie sekcję synthetic; CLI ma pierwszeństwo."""
    document = read_configuration(path)
    if not isinstance(document, dict) or not isinstance(document.get("synthetic"), dict):
        raise ValueError("Konfiguracja wymaga obiektu synthetic")
    options = dict(document["synthetic"])
    options.update({k: v for k, v in overrides.items() if v is not None})
    if options.get("generator_version", "v1") == "v2":
        v2 = document.get("synthetic_v2", {})
        if not isinstance(v2, dict) or set(v2) - {"profiles", "variant", "experiment_id", "parameters"}:
            raise ValueError("Nieobsługiwane ustawienia synthetic_v2")
        for target, key, default in (("profiles", "profiles", {}), ("v2_variant", "variant", "full"),
                                     ("experiment_id", "experiment_id", "ohlc-v2-diagnostic"),
                                     ("v2_parameters", "parameters", {})):
            options[target] = overrides[target] if overrides.get(target) is not None else v2.get(key, default)
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

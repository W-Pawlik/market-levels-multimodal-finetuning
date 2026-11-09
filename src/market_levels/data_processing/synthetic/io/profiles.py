"""Profile persistence and unchanged production approval gates."""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..domain.profiles.v1 import diagnostic_profile
from ..domain.profiles.validation import validate_generator_profile
from ..domain.profiles.v2 import diagnostic_profile_v2, regime_configuration
from ..domain.generation.regimes import feasible_sequences
from ..config.generation import SyntheticSettings
from ....shared.json_io import write_json
from ....shared.publication import publication_workspace


def prepare_profiles(settings: SyntheticSettings) -> dict[str, dict]:
    """Walidacja pełnego wejścia także dla dry-run, bez tworzenia katalogów."""
    settings.validate()
    resolved_output = Path(settings.output).resolve()
    protected = {Path("data/processed").resolve(), Path(__file__).resolve().parents[5] / "data/processed"}
    if any(resolved_output == path or path in resolved_output.parents for path in protected):
        raise ValueError("Dane syntetyczne nie mogą być zapisywane w data/processed")
    feasible_sequences(settings)
    profiles = {}
    for symbol in settings.symbols:
        if symbol in settings.profiles:
            profile = load_profile(Path(settings.profiles[symbol]), symbol=symbol)
        elif settings.diagnostic:
            profile = (diagnostic_profile_v2(symbol, settings) if settings.generator_version == "v2"
                       else diagnostic_profile(symbol))
        else:
            raise ValueError(f"{symbol}: brak profilu kalibracyjnego; do prób użyj --diagnostic")
        validate_generator_profile(profile, symbol=symbol, generator_version=settings.generator_version)
        if (profile.get("calibration", {}).get("method") == "volatility_refinement_v1"
                and profile["calibration"]["variant"] != settings.v2_variant):
            raise ValueError("Profil refinement nie odpowiada wybranemu wariantowi v2")
        if settings.generator_version == "v2" and profile["regime_configuration"] != regime_configuration(settings):
            raise ValueError("Konfiguracja reżimów nie odpowiada profilowi v2")
        if not settings.diagnostic and profile["status"] != "approved":
            raise ValueError(f"{symbol}: niezatwierdzony profil; wymagany --diagnostic")
        profiles[symbol] = profile
    return profiles


def save_profile(path: Path, profile: dict) -> None:
    """Opublikuj kompletny profil atomowo i bez nadpisywania istniejącego."""
    validate_generator_profile(profile)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with publication_workspace(path.parent, prefix=".profile-") as temporary:
        staged = temporary / "profile.json"
        write_json(staged, profile)
        # Hard link na tym samym systemie plików: kompletny plik albo FileExistsError.
        os.link(staged, path)


def load_profile(path: Path, *, symbol: str | None = None) -> dict:
    profile = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    validate_generator_profile(profile, symbol=symbol)
    return profile

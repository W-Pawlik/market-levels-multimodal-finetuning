"""data_processing / synthetic / domain / profiles / v1."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime

from ..parameters import SYMBOLS
from .....core.numeric.validation import finite_number, positive_int
from .....core.time.periods import validate_period


PROFILE_VERSION = 1


def profile_hash(profile: dict) -> str:
    return hashlib.sha256(json.dumps(profile, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def diagnostic_profile(symbol: str) -> dict:
    """Jawnie robocze liczby, bez odczytu plików danych historycznych."""
    if symbol not in SYMBOLS:
        raise ValueError("Nieobsługiwany symbol")
    return {"version": PROFILE_VERSION, "symbol": symbol, "status": "diagnostic",
            "source": {"description": "ręczne wartości robocze; bez kalibracji na rynku"},
            "period": None, "observations": 0, "skipped_noncontiguous_transitions": 0,
            "statistics": None,
            "generator_parameters": {"sigma_4h": 0.012 if symbol == "BTCUSDT" else 0.016,
                                     "initial_price_range": [20000.0, 70000.0] if symbol == "BTCUSDT"
                                     else [1000.0, 4000.0]},
            "parameter_status": "diagnostic; niezatwierdzone do zbioru treningowego"}


def approve_profile(profile: dict, *, training_start: datetime, training_end: datetime,
                    split_id: str, reviewed_by: str) -> dict:
    """Zapisz jawną decyzję autora po zatwierdzeniu podziału i przeglądzie profilu."""
    validate_profile(profile)
    validate_period(training_start, training_end)
    if profile["status"] != "unapproved" or not split_id.strip() or not reviewed_by.strip():
        raise ValueError("Zatwierdzenie wymaga profilu unapproved, identyfikatora podziału i autora decyzji")
    period = profile["period"]
    if not (training_start <= datetime.fromisoformat(period["allowed_start"])
            < datetime.fromisoformat(period["allowed_end"]) <= training_end):
        raise ValueError("Kalibracja wychodzi poza zatwierdzony okres treningowy")
    result = deepcopy(profile)
    result.update(status="approved", approval={"training_start": training_start.isoformat(),
                  "training_end": training_end.isoformat(), "split_id": split_id, "reviewed_by": reviewed_by})
    validate_profile(result)
    return result


def validate_profile(profile: dict, *, symbol: str | None = None) -> None:
    """Odrzuć niekompletne, niefinitywne lub sprzeczne profile."""
    try:
        if (not isinstance(profile, dict) or type(profile["version"]) is not int
                or profile["version"] != PROFILE_VERSION or profile["symbol"] not in SYMBOLS
                or (symbol is not None and profile["symbol"] != symbol)):
            raise ValueError("Nieobsługiwana wersja lub instrument profilu")
        if profile["status"] not in ("diagnostic", "unapproved", "approved"):
            raise ValueError("Niepoprawny status profilu")
        params = profile["generator_parameters"]
        finite_number(params["sigma_4h"], "sigma_4h", positive=True)
        prices = params["initial_price_range"]
        if not isinstance(prices, (list, tuple)) or len(prices) != 2:
            raise ValueError("Wymagany zakres cen")
        low, high = [finite_number(p, "initial_price", positive=True) for p in prices]
        if low > high or not isinstance(profile["source"], dict) or not profile["source"]:
            raise ValueError("Niepoprawny zakres cen lub źródło")
        if profile["status"] == "diagnostic":
            if profile["observations"] != 0 or profile["period"] is not None or profile["statistics"] is not None:
                raise ValueError("Profil diagnostyczny nie może udawać kalibracji")
        else:
            period = profile["period"]
            start, end = [datetime.fromisoformat(period[k]) for k in ("allowed_start", "allowed_end")]
            validate_period(start, end)
            observed_start, observed_end = [datetime.fromisoformat(period[k]) for k in ("observed_start", "observed_end")]
            validate_period(observed_start, observed_end)
            if not start <= observed_start < observed_end <= end or period["bounds"] != "inclusive":
                raise ValueError("Obserwacje spoza dozwolonego okresu")
            count = positive_int(profile["observations"], "observations")
            skipped = profile["skipped_noncontiguous_transitions"]
            if type(skipped) is not int or not 0 <= skipped < count - 1:
                raise ValueError("Niepoprawna liczba pominiętych przejść")
            stats = profile["statistics"]
            for key in ("log_returns", "absolute_log_returns", "close_prices", "relative_range",
                        "relative_body", "body_fraction", "upper_wick_fraction", "lower_wick_fraction"):
                dist = stats[key]
                expected = count - 1 - skipped if key in ("log_returns", "absolute_log_returns") else count
                if dist["count"] != expected:
                    raise ValueError("Niezgodna liczba obserwacji statystyk")
                for name in ("mean", "std", "min", "max"):
                    finite_number(dist[name], name)
                if dist["std"] < 0 or dist["min"] > dist["max"]:
                    raise ValueError("Niepoprawne statystyki")
                for q in ("0.01", "0.05", "0.5", "0.95", "0.99"):
                    finite_number(dist["quantiles"][q], "quantile")
            if params["sigma_4h"] != stats["log_returns"]["std"]:
                raise ValueError("sigma_4h musi odpowiadać kalibracji")
            if profile["status"] == "approved":
                approval = profile["approval"]
                a, b = [datetime.fromisoformat(approval[k]) for k in ("training_start", "training_end")]
                validate_period(a, b)
                if not a <= start < end <= b or not approval["split_id"].strip() or not approval["reviewed_by"].strip():
                    raise ValueError("Brak poprawnego zatwierdzenia podziału treningowego")
        profile_hash(profile)  # Także pozostałe pola JSON nie mogą zawierać NaN/Infinity.
    except (KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError(f"Niekompletny lub niepoprawny profil: {exc}") from exc

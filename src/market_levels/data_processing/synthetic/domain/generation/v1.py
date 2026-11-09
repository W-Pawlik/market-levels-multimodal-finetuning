"""data_processing / synthetic / domain / generation / v1."""
from __future__ import annotations

import math
import platform
import random
from decimal import Decimal

from .....core.ohlc.model import CANDLE_DELTA, Candle
from ..profiles.v1 import profile_hash, validate_profile
from .....core.ohlc.identity import canonical_hash
from ..quality import series_statistics, validate_synthetic
from .regimes import plan_regimes
from ...config.generation import SyntheticSettings
from .models import GENERATOR_VERSION, SIMULATION_START, SyntheticExample


def generate_example(symbol: str, seed: int, profile: dict, settings: SyntheticSettings) -> SyntheticExample:
    """Odtwórz przykład wyłącznie z seeda, profilu, ustawień i wersji środowiska."""
    settings.validate()
    validate_profile(profile, symbol=symbol)
    if type(seed) is not int or seed < 0:
        raise ValueError("seed musi być nieujemną liczbą całkowitą")
    if not settings.diagnostic and profile["status"] != "approved":
        raise ValueError("Generowanie kandydatów wymaga zatwierdzonego profilu treningowego; użyj --diagnostic")
    rng = random.Random(seed)
    params = profile["generator_parameters"]
    # Jednostajnie w skali logarytmicznej, nie faworyzując dużych cen.
    log_price = rng.uniform(*(math.log(p) for p in params["initial_price_range"]))
    regimes = plan_regimes(rng, settings, params["sigma_4h"])
    source = f"synthetic:{GENERATOR_VERSION}:{symbol}:{seed}"
    candles = []
    price = math.exp(log_price)
    steps = settings.internal_steps
    try:
        for regime in regimes:
            regime["center_log_price"] = log_price
            for _ in range(regime["length"]):
                opening = price
                path = [opening]
                for _ in range(steps):
                    drift = regime["mu"] - regime["mean_reversion"] * (log_price - regime["center_log_price"])
                    log_price += drift / steps + regime["sigma"] / math.sqrt(steps) * rng.gauss(0, 1)
                    price = math.exp(log_price)
                    if not math.isfinite(price) or price <= 0:
                        raise ValueError("Niepoprawny wynik symulacji ceny")
                    path.append(price)
                # Konwersja przez str bez kwantyzacji: równe floaty dają równe Decimal.
                values = [Decimal(str(v)) for v in (opening, max(path), min(path), price)]
                candles.append(Candle(SIMULATION_START + len(candles) * CANDLE_DELTA, *values, source))
    except OverflowError as exc:
        raise ValueError("Przekroczenie zakresu liczbowego symulacji") from exc
    validation = validate_synthetic(candles, regimes, seed)
    metadata = {"symbol": symbol, "seed": seed, "origin": "synthetic",
                "status": "diagnostic" if settings.diagnostic else "candidate",
                "generator_version": GENERATOR_VERSION,
                "runtime": {"python": platform.python_version(), "implementation": platform.python_implementation()},
                "profile_sha256": profile_hash(profile), "calibration_profile": profile,
                "configuration": settings.document(), "regimes": regimes,
                "internal_steps_per_candle": steps, "total_internal_steps": len(candles) * steps,
                "timestamp_role": "simulation_index; nie są to daty rzeczywistych notowań ani podziału danych",
                "validation": validation, "ohlc_sha256": canonical_hash(candles),
                "statistics": series_statistics(candles),
                "regime_shares": {kind: sum(r["length"] for r in regimes if r["kind"] == kind) / len(candles)
                                  for kind in ("uptrend", "downtrend", "consolidation", "breakout")}}
    return SyntheticExample(candles, metadata)

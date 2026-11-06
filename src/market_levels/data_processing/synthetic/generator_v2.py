"""Wersja 2: Close 4h, most i stacjonarna zmienność mają osobne RNG."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import math
import platform
import random

from ...core.candles import CANDLE_DELTA, Candle
from .calibration import profile_hash
from .generator import SIMULATION_START, SyntheticExample
from .profile_v2 import regime_configuration, validate_profile_v2
from .quality import canonical_hash, series_statistics, validate_synthetic
from .regimes import plan_regimes
from .settings import KINDS, SyntheticSettings
from .stochastic_processes import (brownian_bridge, mixture_value, stream_seed,
                                   volatility_multiplier, volatility_states)
from .v2_parameters import V2_VERSION, V2Parameters, mechanisms, effective_parameters

STREAMS = ("regimes", "close", "tail_selector", "intracandle", "volatility", "example")


def generate_example_v2(symbol: str, seed: int, profile: dict, settings: SyntheticSettings, *,
                        calibration_evaluation: bool = False) -> SyntheticExample:
    settings.validate()
    if settings.generator_version != "v2":
        raise ValueError("Generator v2 wymaga jawnych ustawień v2")
    validate_profile_v2(profile, symbol=symbol, allow_evaluation=calibration_evaluation)
    if (profile["calibration"]["method"] == "volatility_refinement_v1"
            and profile["calibration"]["variant"] != settings.v2_variant):
        raise ValueError("Profil refinement jest przypisany do innego wariantu mechanizmów")
    if regime_configuration(settings) != profile["regime_configuration"]:
        raise ValueError("Konfiguracja reżimów różni się od zapisanej w profilu v2")
    if not settings.diagnostic and profile["status"] != "approved":
        raise ValueError("Niezatwierdzony profil v2 wymaga --diagnostic")
    seeds = {name: stream_seed(seed, name) for name in STREAMS}
    rng = {name: random.Random(value) for name, value in seeds.items()}
    active = mechanisms(settings.v2_variant)
    params = V2Parameters(**profile["v2_parameters"])
    base = profile["generator_parameters"]
    log_price = rng["example"].uniform(*(math.log(p) for p in base["initial_price_range"]))
    regimes = plan_regimes(rng["regimes"], settings, base["sigma_4h"])
    states = (volatility_states(rng["volatility"], 120, params.volatility_phi, params.volatility_stationary_std)
              if active["volatility"] else [0.0] * 120)
    candles, trace = [], []
    source = f"synthetic:{V2_VERSION}:{symbol}:{seed}"
    try:
        price = math.exp(log_price)
        for regime in regimes:
            regime["center_log_price"] = log_price
            for _ in range(regime["length"]):
                index = len(candles)
                opening, opening_log = price, log_price
                multiplier = volatility_multiplier(states[index], params.volatility_stationary_std) if active["volatility"] else 1.0
                sigma = regime["sigma"] * multiplier
                epsilon = rng["close"].gauss(0, 1)
                innovation = (mixture_value(epsilon, rng["tail_selector"].random(), params.tail_probability, params.tail_scale)
                              if active["tails"] else epsilon)
                drift = regime["mu"] - regime["mean_reversion"] * (opening_log - regime["center_log_price"])
                # Jeden zwrot 4h, nie suma dwunastu ciężkoogonowych zaburzeń.
                log_price = opening_log + drift + sigma * innovation
                gamma = params.bridge_gamma if active["bridge"] else 1.0
                log_path = brownian_bridge(rng["intracandle"], opening_log, log_price, sigma, gamma)
                path = [math.exp(value) for value in log_path]
                # Otwarcie bierze dokładną poprzednią cenę, Close dokładny exp zaplanowanego końca.
                path[0] = opening
                price = path[-1]
                if any(not math.isfinite(value) or value <= 0 for value in path):
                    raise ValueError("Niedodatnia lub niefinitywna cena v2")
                values = [Decimal(str(v)) for v in (opening, max(path), min(path), price)]
                candles.append(Candle(SIMULATION_START + index * CANDLE_DELTA, *values, source))
                trace.append({"index": index, "h": states[index], "sigma_4h": sigma, "multiplier": multiplier})
    except OverflowError as exc:
        raise ValueError("Przepełnienie numeryczne v2; ścieżki nie są obcinane") from exc
    validation = validate_synthetic(candles, regimes, seed)
    metadata = {"symbol": symbol, "seed": seed, "origin": "synthetic",
                "status": "diagnostic" if settings.diagnostic else "candidate",
                "generator_version": V2_VERSION, "profile_version": 2,
                "v2_variant": settings.v2_variant, "experiment_id": settings.experiment_id,
                "mechanisms": active, "configured_parameters": params.document(),
                "effective_parameters": effective_parameters(params, settings.v2_variant), "rng_stream_seeds": seeds,
                "runtime": {"python": platform.python_version(), "implementation": platform.python_implementation()},
                "profile_sha256": profile_hash(profile), "calibration_profile": deepcopy(profile),
                "configuration": settings.document(), "regimes": regimes,
                "internal_steps_per_candle": 12, "total_internal_steps": 1440,
                "timestamp_role": "simulation_index; nie są to daty rzeczywistych notowań ani podziału danych",
                "volatility_trace": trace, "validation": validation, "ohlc_sha256": canonical_hash(candles),
                "statistics": series_statistics(candles),
                "regime_shares": {kind: sum(r["length"] for r in regimes if r["kind"] == kind) / 120 for kind in KINDS}}
    return SyntheticExample(candles, metadata)

"""Ważone sekwencje reżimów z ograniczeniami długości i przejść."""
from __future__ import annotations

from itertools import product
import random

from .settings import KINDS, SyntheticSettings


def feasible_sequences(settings: SyntheticSettings) -> dict[int, list[tuple[tuple[str, ...], float]]]:
    """Rozważ tylko wykonalne sekwencje; wagi to iloczyn wag przejść."""
    settings.validate()
    options = settings.regimes
    feasible = {}
    for count in range(settings.min_regimes, settings.max_regimes + 1):
        choices = []
        for sequence in product(KINDS, repeat=count):
            weight = options.initial_weights[sequence[0]]
            for a, b in zip(sequence, sequence[1:]):
                weight *= options.transitions[a].get(b, 0)
            if (weight > 0 and sum(options.minimum_lengths[k] for k in sequence) <= settings.candles
                    <= sum(options.maximum_lengths[k] for k in sequence)):
                choices.append((sequence, weight))
        if choices:
            feasible[count] = choices
    if not feasible:
        raise ValueError("Brak wykonalnego planu reżimów dla podanych długości i przejść")
    return feasible


def plan_regimes(rng: random.Random, settings: SyntheticSettings, sigma_4h: float) -> list[dict]:
    """Losuj liczbę faz jednostajnie z wykonalnych, następnie ważoną sekwencję."""
    feasible = feasible_sequences(settings)
    choices = feasible[rng.choice(list(feasible))]
    sequence = rng.choices([s for s, _ in choices], weights=[w for _, w in choices], k=1)[0]
    options = settings.regimes
    remaining = settings.candles
    cursor = 0
    result = []
    for index, kind in enumerate(sequence):
        rest = sequence[index + 1:]
        low = max(options.minimum_lengths[kind], remaining - sum(options.maximum_lengths[k] for k in rest))
        high = min(options.maximum_lengths[kind], remaining - sum(options.minimum_lengths[k] for k in rest))
        length = rng.randint(low, high)
        if kind in ("uptrend", "downtrend"):
            mu = sigma_4h * rng.uniform(*options.trend_drift_sigma) * (1 if kind == "uptrend" else -1)
            sigma = sigma_4h * rng.uniform(*options.trend_volatility)
        elif kind == "breakout":
            mu = sigma_4h * rng.uniform(*options.breakout_drift_sigma) * rng.choice((-1, 1))
            sigma = sigma_4h * rng.uniform(*options.breakout_volatility)
        else:
            mu = 0.0
            sigma = sigma_4h * rng.uniform(*options.consolidation_volatility)
        reversion = rng.uniform(*options.mean_reversion) if kind == "consolidation" else 0.0
        result.append({"kind": kind, "start": cursor, "end_exclusive": cursor + length,
                       "length": length, "mu": mu, "sigma": sigma, "mean_reversion": reversion})
        cursor += length
        remaining -= length
    return result

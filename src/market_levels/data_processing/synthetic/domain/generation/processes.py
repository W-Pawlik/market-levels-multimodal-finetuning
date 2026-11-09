"""data_processing / synthetic / domain / generation / processes."""
from __future__ import annotations

import hashlib
import math
import random

from .....core.numeric.validation import finite_number


def stream_seed(seed: int, name: str) -> int:
    if type(seed) is not int or seed < 0 or not isinstance(name, str) or not name:
        raise ValueError("Strumień wymaga nieujemnego seeda i nazwy")
    return int.from_bytes(hashlib.sha256(f"ohlc-v2:{seed}:{name}".encode()).digest(), "big")


def normal_mixture(rng: random.Random, probability: float, tail_scale: float) -> float:
    """Mieszanka o E[Z]=0 i Var(Z)=1; Bernoulli i epsilon są niezależne."""
    return mixture_value(rng.gauss(0, 1), rng.random(), probability, tail_scale)


def mixture_value(epsilon: float, uniform: float, probability: float, tail_scale: float) -> float:
    """Oddzielne wejścia ułatwiają wspólne losowania w wariantach kontrolnych."""
    p = finite_number(probability, "tail_probability")
    k = finite_number(tail_scale, "tail_scale", positive=True)
    if not 0 <= p < 1 or k <= 1:
        raise ValueError("Mieszanka wymaga 0 <= p < 1 i k > 1")
    finite_number(epsilon, "epsilon")
    if not 0 <= finite_number(uniform, "uniform") < 1:
        raise ValueError("Wybór składowej wymaga 0 <= uniform < 1")
    scale = k if uniform < p else 1.0
    normalization = math.sqrt((1 - p) + p * k * k)
    if not math.isfinite(normalization):
        raise ValueError("Nieskończona wariancja mieszanki")
    return scale * epsilon / normalization


def volatility_states(rng: random.Random, count: int, phi: float,
                      stationary_std: float) -> list[float]:
    """Stacjonarne AR(1) h, z inicjalizacją N(0, stationary_std²)."""
    phi = finite_number(phi, "volatility_phi")
    sd = finite_number(stationary_std, "volatility_stationary_std")
    if type(count) is not int or count <= 0 or not 0 <= phi < 1 or sd < 0:
        raise ValueError("AR(1) wymaga count>0, 0<=phi<1, std>=0")
    innovation_std = sd * math.sqrt(1 - phi * phi)
    state = rng.gauss(0, sd)
    states = [state]
    for _ in range(count - 1):
        state = phi * state + rng.gauss(0, innovation_std)
        if not math.isfinite(state):
            raise ValueError("Niefinitywny stan zmienności")
        states.append(state)
    return states


def volatility_multiplier(state: float, stationary_std: float) -> float:
    """exp(h-v) daje E[multiplier²]=1, gdy h~N(0,v), v=std²."""
    state = finite_number(state, "volatility_state")
    sd = finite_number(stationary_std, "volatility_stationary_std")
    if sd < 0:
        raise ValueError("Odchylenie stanu zmienności nie może być ujemne")
    try:
        result = math.exp(state - sd * sd)
    except OverflowError as exc:
        raise ValueError("Przepełnienie skali zmienności") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError("Niepoprawna skala zmienności")
    return result


def brownian_bridge(rng: random.Random, opening: float, closing: float,
                    sigma: float, gamma: float) -> list[float]:
    """13 log-cen: 12 kroków, dokładne końce, Var(B_t)=t(1-t)."""
    for name, value in (("opening", opening), ("closing", closing), ("sigma", sigma), ("gamma", gamma)):
        finite_number(value, name)
    if sigma <= 0 or gamma <= 0:
        raise ValueError("Most wymaga dodatnich sigma i gamma")
    motion = [0.0]
    for _ in range(12):
        motion.append(motion[-1] + rng.gauss(0, 1) / math.sqrt(12))
    path = [opening + (k / 12) * (closing - opening)
            + gamma * sigma * (motion[k] - (k / 12) * motion[-1]) for k in range(13)]
    path[0], path[-1] = opening, closing
    if any(not math.isfinite(value) for value in path):
        raise ValueError("Niefinitywna ścieżka mostu")
    return path

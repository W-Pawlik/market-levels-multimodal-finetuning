"""Parametry v2; wartości początkowe są wyłącznie diagnostyczne."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .settings import finite_number

VARIANT_MECHANISMS = {
    "base": (False, False, False),
    "bridge": (True, False, False),
    "tails": (False, True, False),
    "volatility": (False, False, True),
    "full": (True, True, True),
    "bridge_volatility": (True, False, True),
}
VARIANTS = tuple(VARIANT_MECHANISMS)
V2_VERSION = "2.0.0"


@dataclass(frozen=True)
class V2Parameters:
    bridge_gamma: float = 1.5
    tail_probability: float = 0.05
    tail_scale: float = 3.0
    volatility_phi: float = 0.95
    volatility_stationary_std: float = 0.35

    def validate(self) -> None:
        for name, value in asdict(self).items():
            finite_number(value, name)
        if not 0 < self.bridge_gamma <= 5:
            raise ValueError("bridge_gamma: wymagane 0 < gamma <= 5 (obsługiwany zakres diagnostyczny)")
        if not 0 <= self.tail_probability <= 0.25 or not 1 < self.tail_scale <= 10:
            raise ValueError("Mieszanka: wymagane 0 <= p <= 0.25 i 1 < k <= 10")
        if not 0 <= self.volatility_phi <= 0.995 or not 0 <= self.volatility_stationary_std <= 1:
            raise ValueError("AR(1): wymagane 0 <= phi <= 0.995 i 0 <= stationary_std <= 1")

    def document(self) -> dict:
        return asdict(self)


def mechanisms(variant: str) -> dict[str, bool]:
    if variant not in VARIANTS:
        raise ValueError("Nieznany wariant v2")
    return dict(zip(("bridge", "tails", "volatility"), VARIANT_MECHANISMS[variant]))


def effective_parameters(parameters: V2Parameters, variant: str) -> dict:
    active = mechanisms(variant)
    result = parameters.document()
    if not active["bridge"]:
        result["bridge_gamma"] = 1.0
    if not active["tails"]:
        result["tail_probability"] = 0.0
    if not active["volatility"]:
        result.update(volatility_phi=0.0, volatility_stationary_std=0.0)
    return result

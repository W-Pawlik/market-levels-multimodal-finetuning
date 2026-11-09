"""Validate windows before renderable diagnostic computations."""
from __future__ import annotations

import math

from ...core.ohlc.model import Candle
from ...core.ohlc.validation import validate_values


def validate_window(candles: list[Candle]) -> None:
    if len(candles) != 120:
        raise ValueError("Renderer wymaga dokładnie 120 świec")
    if validate_values(candles)["missing_total"]:
        raise ValueError("Okno z luką nie może być renderowane; brak interpolacji")
    if any(not math.isfinite(float(getattr(c, k))) or float(getattr(c, k)) <= 0
           for c in candles for k in ("open", "high", "low", "close")):
        raise ValueError("Ceny poza zakresem reprezentacji renderera")

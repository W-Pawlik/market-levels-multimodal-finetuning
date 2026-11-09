"""Strict finite-number and positive-integer validation."""
from __future__ import annotations

import math


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

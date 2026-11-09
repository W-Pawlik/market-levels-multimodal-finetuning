"""Exact level, response, reference and matched-pair values."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Levels:
    supports: tuple[Decimal, ...]
    resistances: tuple[Decimal, ...]


@dataclass(frozen=True)
class Response:
    raw: str
    levels: Levels | None
    error: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class Reference:
    id: str
    symbol: str
    split: str
    levels: Levels
    atr: Decimal


@dataclass(frozen=True)
class Match:
    predicted_index: int
    reference_index: int
    predicted: Decimal
    reference: Decimal
    absolute_error: Decimal
    atr_error: Decimal | None
    atr_error_reason: str | None

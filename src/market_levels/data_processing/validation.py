"""Walidacja cen, granic świec oraz ciągłości szeregu OHLC."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from ..core.candles import CANDLE_DELTA, Candle, DataValidationError


def _positive_decimal(s: str, label: str) -> Decimal:
    try:
        x = Decimal(s)
    except InvalidOperation as exc:
        raise DataValidationError(f"Nieliczbowa wartość {label}: {s!r}") from exc
    if not x.is_finite() or x <= 0:
        raise DataValidationError(f"{label} musi być dodatnie i skończone: {s!r}")
    return x


def check_series(candles: list[Candle]) -> dict:
    """Waliduje serię, zgłasza luki, nigdy ich nie uzupełnia."""
    if not candles:
        raise DataValidationError("Brak świec")
    sorted_candles = sorted(candles, key=lambda x: x.timestamp)
    gaps = []
    for previous, current in zip(sorted_candles, sorted_candles[1:]):
        diff = current.timestamp - previous.timestamp
        if diff == timedelta(0):
            raise DataValidationError(f"Zduplikowany czas świecy: {current.timestamp.isoformat()}")
        if diff < CANDLE_DELTA or diff % CANDLE_DELTA:
            raise DataValidationError(f"Nieregularny odstęp czasowy: {previous.timestamp} → {current.timestamp}")
        if diff > CANDLE_DELTA:
            gaps.append({"after": previous.timestamp.isoformat(),
                         "before": current.timestamp.isoformat(),
                         "missing_candles": int(diff / CANDLE_DELTA) - 1})
    return {"count": len(sorted_candles),
            "start": sorted_candles[0].timestamp.isoformat(),
            "end": sorted_candles[-1].timestamp.isoformat(),
            "gaps": gaps,
            "missing_total": sum(g["missing_candles"] for g in gaps)}


def validate_candle_timestamp(stamp: datetime, archive: str, row_number: int) -> None:
    """Sprawdź granicę świecy 4h, zachowując komunikat i kolejność walidacji."""
    if (stamp.minute, stamp.second, stamp.microsecond) != (0, 0, 0) or stamp.hour % 4:
        raise DataValidationError(f"{archive}, wiersz {row_number}: świeca nie rozpoczyna się na granicy 4h ({stamp})")


def validate_ohlc(o: Decimal, h: Decimal, l: Decimal, c: Decimal,
                  archive: str, row_number: int) -> None:
    """Sprawdź relacje cen po ich konwersji na dodatnie wartości Decimal."""
    if h < max(o, c) or l > min(o, c) or l > h:
        raise DataValidationError(f"{archive}, wiersz {row_number}: niepoprawne relacje OHLC")

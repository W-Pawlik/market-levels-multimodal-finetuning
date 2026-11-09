"""Price, UTC, OHLC and chronological series validation."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from datetime import timedelta, datetime

from .model import DataValidationError, CANDLE_DELTA, Candle


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


def validate_values(candles: list[Candle]) -> dict:
    """Sprawdź wartości, UTC, kolejność i wspólny kontrakt szeregu."""
    for index, candle in enumerate(candles):
        stamp = candle.timestamp
        if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
            raise DataValidationError("Wymagany czas UTC")
        validate_candle_timestamp(stamp, candle.source_archive, index)
        for name in ("open", "high", "low", "close"):
            _positive_decimal(str(getattr(candle, name)), name)
        validate_ohlc(candle.open, candle.high, candle.low, candle.close, candle.source_archive, index)
    report = check_series(candles)
    if any(b.timestamp <= a.timestamp for a, b in zip(candles, candles[1:])):
        raise DataValidationError("Świece muszą być uporządkowane chronologicznie")
    return report

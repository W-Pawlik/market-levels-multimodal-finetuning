"""Source-independent OHLC candles and validation errors."""
from __future__ import annotations

from datetime import timezone, timedelta, datetime
from dataclasses import dataclass
from decimal import Decimal


UTC = timezone.utc


CANDLE_DELTA = timedelta(hours=4)


class DataValidationError(ValueError):
    """Niepoprawne, uszkodzone lub niespójne dane wejściowe."""


@dataclass(frozen=True)
class Candle:
    """Świeca z cenami Decimal, czasem UTC i zachowanym pochodzeniem."""
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    source_archive: str

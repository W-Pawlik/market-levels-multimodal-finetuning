"""Model OHLC i wspólne kontrakty walidacji, niezależne od źródła danych."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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

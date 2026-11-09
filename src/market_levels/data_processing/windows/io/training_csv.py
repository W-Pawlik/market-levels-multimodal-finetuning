"""Read training OHLC only, stopping at the first later timestamp."""
from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from ....core.ohlc.model import Candle
from ....core.ohlc.validation import validate_values


def read_training_csv(path: Path, start: datetime, end: datetime) -> list[Candle]:
    """Parse only training OHLC; first later timestamp is a stop sentinel.

    Whole-file byte hashes are integrity checks, not analytical access. CSV is
    chronological: a strictly increasing training prefix is required.
    """
    result = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["open_time_utc", "open", "high", "low", "close"]:
            raise ValueError("Niepoprawny nagłówek CSV")
        previous = None
        for row in reader:
            stamp = datetime.fromisoformat(row["open_time_utc"])
            if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
                raise ValueError("Wymagany UTC")
            if previous is not None and stamp <= previous:
                raise ValueError("Niechronologiczny CSV treningu")
            previous = stamp
            if stamp > end:
                break
            if stamp < start:
                continue
            result.append(Candle(stamp, *(Decimal(row[k]) for k in ("open", "high", "low", "close")), str(path)))
    validate_values(result)
    if result[0].timestamp != start or result[-1].timestamp != end:
        raise ValueError("Niepełne pokrycie granic treningu")
    return result

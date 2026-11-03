"""Zapis dotychczasowych formatów CSV OHLC i dokumentów JSON."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from ..core.candles import Candle
from .validation import _positive_decimal, validate_candle_timestamp, validate_ohlc


def write_candles_csv(path: Path, candles: list[Candle]) -> None:
    """Zapisz świece chronologicznie, bez zmiany precyzji cen ani nagłówka."""
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("open_time_utc", "open", "high", "low", "close"))
        for candle in sorted(candles, key=lambda x: x.timestamp):
            writer.writerow((candle.timestamp.isoformat(), str(candle.open), str(candle.high),
                             str(candle.low), str(candle.close)))


def write_json(path: Path, document: dict) -> None:
    """Zapisz raport lub manifest jako UTF-8, z dotychczasowym formatowaniem."""
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


def read_candles_csv(path: Path, *, source: str) -> list[Candle]:
    """Odczytaj wspólny format CSV, bez utraty precyzji Decimal."""
    candles = []
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["open_time_utc", "open", "high", "low", "close"]:
            raise ValueError("Niepoprawny nagłówek CSV OHLC")
        for number, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Niepoprawna liczba pól CSV, wiersz {number}")
            stamp = datetime.fromisoformat(row["open_time_utc"])
            if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
                raise ValueError("CSV wymaga czasu UTC")
            validate_candle_timestamp(stamp, source, number)
            values = [_positive_decimal(row[k], k) for k in ("open", "high", "low", "close")]
            validate_ohlc(*values, source, number)
            candles.append(Candle(stamp, *values, source))
    return candles

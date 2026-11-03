"""Zapis dotychczasowych formatów CSV OHLC i dokumentów JSON."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ..core.candles import Candle


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

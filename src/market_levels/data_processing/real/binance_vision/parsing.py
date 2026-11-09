"""Dekodowanie formatu Binance, bezpieczny odczyt ZIP i kontrola okresu archiwum."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from io import TextIOWrapper
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from ....core.ohlc.model import UTC, Candle, DataValidationError
from ....core.ohlc.validation import _positive_decimal, validate_ohlc


COLUMNS = ("open_time", "open", "high", "low", "close", "volume", "close_time",
           "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume",
           "taker_buy_quote_asset_volume", "ignore")


def decode_binance_timestamp(value: str) -> datetime:
    """Dekodowanie czasu spot (ms do 2024, µs od 2025), bez float."""
    try:
        n = int(value)
    except (ValueError, TypeError) as exc:
        raise DataValidationError(f"Niepoprawny znacznik czasu: {value!r}") from exc
    if 10**12 <= n < 10**14:
        scale = 1000
    elif 10**15 <= n < 10**17:
        scale = 1_000_000
    else:
        raise DataValidationError(f"Nieoczekiwana jednostka czasu: {n}")
    seconds, fraction = divmod(n, scale)
    try:
        return (datetime.fromtimestamp(seconds, tz=UTC) +
                timedelta(microseconds=fraction * (1_000_000 // scale)))
    except (OverflowError, OSError, ValueError) as exc:
        raise DataValidationError(f"Znacznik poza zakresem: {n}") from exc


def parse_candle(row: list[str], archive: str, row_number: int) -> Candle:
    if len(row) != len(COLUMNS):
        raise DataValidationError(f"{archive}, wiersz {row_number}: oczekiwano 12 kolumn, jest {len(row)}")
    stamp = decode_binance_timestamp(row[0])
    if (stamp.minute, stamp.second, stamp.microsecond) != (0, 0, 0) or stamp.hour % 4:
        raise DataValidationError(f"{archive}, wiersz {row_number}: świeca nie rozpoczyna się na granicy 4h ({stamp})")
    o, h, l, c = (_positive_decimal(row[i], COLUMNS[i]) for i in range(1, 5))
    validate_ohlc(o, h, l, c, archive, row_number)
    return Candle(stamp, o, h, l, c, archive)


def read_spot_klines_zip(path: Path) -> list[Candle]:
    path = Path(path)
    try:
        with ZipFile(path) as bundle:
            csv_files = [m for m in bundle.infolist() if m.filename.endswith(".csv") and not m.is_dir()]
            if len(csv_files) != 1:
                raise DataValidationError(f"{path.name}: oczekiwano jednego pliku CSV, jest {len(csv_files)}")
            candles: list[Candle] = []
            with bundle.open(csv_files[0]) as content, TextIOWrapper(content, encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream)
                for index, row in enumerate(reader, start=1):
                    if not row:
                        continue
                    if index == 1 and row[0].strip().lower() in ("open time", "open_time"):
                        continue
                    try:
                        candles.append(parse_candle(row, path.name, index))
                    except DataValidationError as exc:
                        raise DataValidationError(str(exc)) from exc
    except (BadZipFile, OSError, UnicodeDecodeError) as exc:
        raise DataValidationError(f"Nie można odczytać archiwum {path}: {exc}") from exc
    if not candles:
        raise DataValidationError(f"Puste archiwum: {path}")
    return candles


def verify_archive_period(candles: list[Candle], period: str) -> None:
    """period: YYYY-MM albo YYYY-MM-DD; chroni przed pomyleniem archiwów."""
    if len(period) not in (7, 10):
        raise DataValidationError(f"Nieobsługiwany okres: {period}")
    for candle in candles:
        if not candle.timestamp.isoformat().startswith(period):
            raise DataValidationError(f"Świeca {candle.timestamp} nie pasuje do archiwum {period}")

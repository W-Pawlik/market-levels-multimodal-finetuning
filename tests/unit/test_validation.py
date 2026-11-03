import csv
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from market_levels.core.candles import DataValidationError
from market_levels.data_processing.validation import check_series
from market_levels.data_processing.real.binance_vision.parsing import (
    decode_binance_timestamp, read_spot_klines_zip, verify_archive_period,
)
from market_levels.core.periods import iter_months
from market_levels.data_processing.real.binance_vision.archives import _expected_sha256
from market_levels.data_processing.real.binance_vision.client import _remote_url


def row(stamp, high="112", low="91"):
    return [str(stamp), "100", high, low, "110", "1", "0", "2", "3", "4", "5", "0"]


class ParsingTests(unittest.TestCase):
    def test_milliseconds_2024_and_microseconds_2025(self):
        a = decode_binance_timestamp("1735689600000")
        b = decode_binance_timestamp("1735689600000000")
        self.assertEqual(a, datetime(2025, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(b, a)

    def test_zip_validity_and_gaps(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "BTCUSDT-4h-2025-01.zip"
            with ZipFile(path, "w") as z:
                from io import StringIO
                out = StringIO()
                writer = csv.writer(out)
                writer.writerow(row(1735689600000000))  # 00:00
                writer.writerow(row(1735718400000000))  # 08:00 — brakuje 04:00
                z.writestr("BTCUSDT-4h-2025-01.csv", out.getvalue())
            data = read_spot_klines_zip(path)
            verify_archive_period(data, "2025-01")
            report = check_series(data)
            self.assertEqual(report["count"], 2)
            self.assertEqual(report["missing_total"], 1)
            with self.assertRaises(DataValidationError):
                verify_archive_period(data, "2024-12")

    def test_bad_ohlc_rejected(self):
        from market_levels.data_processing.real.binance_vision.parsing import parse_candle
        with self.assertRaises(DataValidationError):
            parse_candle(row(1735689600000000, high="105"), "file.zip", 1)

    def test_duplicate_rejected(self):
        from market_levels.data_processing.real.binance_vision.parsing import parse_candle
        candle = parse_candle(row(1735689600000000), "file.zip", 1)
        with self.assertRaises(DataValidationError):
            check_series([candle, candle])

    def test_period_and_checksum_format(self):
        self.assertEqual(len(list(iter_months("2026-09", "2026-10"))), 2)
        self.assertIn("/spot/monthly/klines/BTCUSDT/4h/", _remote_url("BTCUSDT", "2026-10"))
        with tempfile.TemporaryDirectory() as folder:
            name = "BTCUSDT-4h-2024-01.zip"
            p = Path(folder) / (name + ".CHECKSUM")
            p.write_text("a" * 64 + "  " + name + "\n")
            self.assertEqual(_expected_sha256(p, name), "a" * 64)
            with self.assertRaises(Exception):
                _expected_sha256(p, "other.zip")

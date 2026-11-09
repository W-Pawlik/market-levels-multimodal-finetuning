from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_levels.core.ohlc.model import Candle, DataValidationError
from market_levels.core.time.calendar import _days_in_month, _last_closed_month, iter_months
from market_levels.data_processing.real.binance_vision import archives, client, parsing
from market_levels.core.ohlc.validation import check_series


class ValidationContracts(unittest.TestCase):
    def test_invalid_records_and_validation_order(self):
        row = ["1704067200000", "100", "112", "91", "110"] + ["0"] * 7
        for index, value, message in (
            (0, "bad", "Niepoprawny znacznik czasu"),
            (0, "1704067200001", "granicy 4h"),
            (1, "NaN", "dodatnie i skończone"),
            (2, "Infinity", "dodatnie i skończone"),
            (3, "0", "dodatnie i skończone"),
            (4, "bad", "Nieliczbowa wartość close"),
            (2, "105", "niepoprawne relacje OHLC"),
        ):
            with self.subTest(index=index, value=value):
                invalid = row.copy()
                invalid[index] = value
                with self.assertRaisesRegex(DataValidationError, message):
                    parsing.parse_candle(invalid, "fixture.zip", 3)
        with self.assertRaisesRegex(DataValidationError, "oczekiwano 12 kolumn"):
            parsing.parse_candle(row[:-1], "fixture.zip", 1)
        candle = parsing.parse_candle(row, "fixture.zip", 1)
        self.assertEqual(candle.open, Decimal("100"))
        self.assertEqual(candle.source_archive, "fixture.zip")

    def test_timestamp_precision_and_invalid_units(self):
        self.assertEqual(parsing.decode_binance_timestamp("1735689600123456"),
                         datetime(2025, 1, 1, microsecond=123456, tzinfo=timezone.utc))
        for stamp in ("1", "-1", "100000000000000", None):
            with self.subTest(stamp=stamp), self.assertRaises(DataValidationError):
                parsing.decode_binance_timestamp(stamp)

    def test_empty_and_irregular_series(self):
        with self.assertRaisesRegex(DataValidationError, "Brak świec"):
            check_series([])
        stamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
        def candle(time):
            return Candle(time, *(Decimal("1"),) * 4, "fixture.zip")
        with self.assertRaisesRegex(DataValidationError, "Nieregularny odstęp"):
            check_series([candle(stamp), candle(stamp + timedelta(hours=5))])
        report = check_series([candle(stamp + timedelta(hours=8)), candle(stamp)])
        self.assertEqual(report["missing_total"], 1)

    def test_calendar_boundaries(self):
        self.assertEqual(list(iter_months("2023-12", "2024-02")),
                         [date(2023, 12, 1), date(2024, 1, 1), date(2024, 2, 1)])
        self.assertEqual(len(list(_days_in_month(date(2024, 2, 1)))), 29)
        self.assertEqual(_last_closed_month(date(2024, 1, 15)), date(2023, 12, 1))
        for start, end in (("2024-13", "2024-01"), ("2024-02", "2024-01"), ("bad", "2024-01")):
            with self.subTest(start=start), self.assertRaises(ValueError):
                list(iter_months(start, end))

    def test_checksum_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "archive.zip"
            file.write_bytes(b"abc")
            self.assertEqual(archives._sha256_file(file),
                             "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
            checksum = file.with_suffix(".CHECKSUM")
            checksum.write_text("A" * 64 + " *archive.zip\n", encoding="utf-8")
            self.assertEqual(archives._expected_sha256(checksum, file.name), "a" * 64)
            for content in ("", "bad", "a" * 64 + " other.zip", ("a" * 64 + " archive.zip\n") * 2):
                checksum.write_text(content, encoding="utf-8")
                with self.assertRaises(client.DownloadError):
                    archives._expected_sha256(checksum, file.name)


class FallbackContracts(unittest.TestCase):
    def test_daily_fallback_only_for_last_closed_month(self):
        with patch.object(archives, "date") as clock, patch.object(archives, "acquire_archive") as acquire:
            clock.today.return_value = date(2024, 3, 10)
            acquire.side_effect = [client.DownloadError("404: fixture")] + [(Path("daily.zip"), {})] * 29
            result = archives.acquire_month("BTCUSDT", date(2024, 2, 1), Path("raw"), False)
            self.assertEqual(len(result), 29)
            self.assertEqual(acquire.call_args_list[1].args[1:3], ("2024-02-01", "daily"))
            self.assertEqual(acquire.call_args_list[-1].args[1:3], ("2024-02-29", "daily"))

    def test_fallback_restrictions_and_offline_missing_file(self):
        cases = (
            (date(2024, 1, 1), False, True, "404: fixture", False),
            (date(2024, 2, 1), False, False, "404: fixture", False),
            (date(2024, 2, 1), True, True, "Błędna suma SHA-256", False),
            (date(2024, 2, 1), False, True, "HTTP 500", False),
            (date(2024, 2, 1), True, True, "Brak pliku w trybie offline: fixture", True),
        )
        for month, offline, enabled, error, fallback in cases:
            with self.subTest(error=error, month=month), patch.object(archives, "date") as clock, patch.object(archives, "acquire_archive") as acquire:
                clock.today.return_value = date(2024, 3, 10)
                acquire.side_effect = [client.DownloadError(error)] + [(Path("daily.zip"), {})] * 29
                if fallback:
                    self.assertEqual(len(archives.acquire_month("BTCUSDT", month, Path("raw"), offline, enabled)), 29)
                else:
                    with self.assertRaisesRegex(client.DownloadError, error):
                        archives.acquire_month("BTCUSDT", month, Path("raw"), offline, enabled)
                    self.assertEqual(acquire.call_count, 1)

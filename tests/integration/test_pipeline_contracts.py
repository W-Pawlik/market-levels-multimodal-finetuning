import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from market_levels.core.candles import DataValidationError
from market_levels.data_processing.pipelines.download import run
from market_levels.data_processing.real.binance_vision import archives, client, parsing


PROJECT = Path(__file__).resolve().parents[2]
BASELINE = PROJECT / "tests/fixtures/pipeline_baseline.json"


def make_archive(root):
    path = root / "raw/BTCUSDT/4h/monthly/BTCUSDT-4h-2024-01.zip"
    path.parent.mkdir(parents=True)
    with ZipFile(path, "w") as bundle:
        bundle.writestr(path.stem + ".csv",
                        "1704081600000,100,112,91,110,1,0,2,3,4,5,0\n"
                        "1704110400000,100,112,91,110,1,0,2,3,4,5,0\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(path.name + ".CHECKSUM").write_text(digest + "  " + path.name + "\n")
    return path, digest


class PipelineContracts(unittest.TestCase):
    def test_outputs_match_original_implementation(self):
        expected = json.loads(BASELINE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder, patch.object(client, "urlopen", side_effect=AssertionError("Network forbidden")):
            root = Path(folder)
            _, digest = make_archive(root)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                run("2024-01", "2024-01", root, True, False, False, ("BTCUSDT",))
            self.assertEqual(stdout.getvalue(), expected.pop("stdout"))
            for relative, baseline in expected.items():
                path = root / relative
                if path.suffix == ".csv":
                    # CSV must preserve the original csv.writer CRLF, including on Windows.
                    self.assertEqual(path.read_bytes(), baseline.replace("\n", "\r\n").encode("utf-8"))
                    continue
                actual = json.loads(path.read_text(encoding="utf-8"))
                if "created_at_utc" in actual:
                    from datetime import datetime
                    self.assertIsNotNone(datetime.fromisoformat(actual.pop("created_at_utc")).utcoffset())
                # Normalize only paths; assert the actual archive digest separately.
                def normalize(value):
                    if isinstance(value, dict):
                        return {k: normalize(v) for k, v in value.items()}
                    if isinstance(value, list):
                        return [normalize(v) for v in value]
                    if isinstance(value, str) and value.startswith(str(root)):
                        return "<OUTPUT>/" + Path(value).relative_to(root).as_posix()
                    return value
                def baseline_paths(value):
                    if isinstance(value, dict):
                        return {k: baseline_paths(v) for k, v in value.items()}
                    if isinstance(value, list):
                        return [baseline_paths(v) for v in value]
                    if isinstance(value, str) and value.startswith("<OUTPUT>"):
                        return value.replace("\\", "/")
                    return value
                if "sources" in actual:
                    entry = actual["sources"]["BTCUSDT"][0]
                    self.assertEqual(entry["sha256"], digest)
                    baseline["sources"]["BTCUSDT"][0]["sha256"] = digest
                self.assertEqual(normalize(actual), baseline_paths(baseline))
                # Retain JSON serialization too, including field order, indentation and UTF-8.
                self.assertEqual(path.read_bytes(), json.dumps(
                    json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False, indent=2).replace("\n", os.linesep).encode("utf-8"))

    def test_strict_gaps_writes_report_before_raising(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            make_archive(root)
            with self.assertRaisesRegex(DataValidationError, "184 brakujących świec; raport zapisany"):
                run("2024-01", "2024-01", root, True, True, False, ("BTCUSDT",))
            self.assertTrue((root / "processed/BTCUSDT_4h_2024-01_2024-01.csv").exists())
            self.assertTrue((root / "reports/BTCUSDT_2024-01_2024-01.json").exists())
            self.assertFalse((root / "reports/manifest_2024-01_2024-01.json").exists())

    def test_archive_reuse_and_checksum_failure_offline(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(client, "urlopen", side_effect=AssertionError("Network forbidden")):
            root = Path(folder)
            path, digest = make_archive(root)
            before = path.read_bytes()
            for offline in (True, False):
                result, metadata = archives.acquire_archive("BTCUSDT", "2024-01", "monthly", root / "raw", offline)
                self.assertEqual(result, path)
                self.assertEqual(metadata["sha256"], digest)
                self.assertEqual(path.read_bytes(), before)
            path.write_bytes(b"corrupted")
            with self.assertRaisesRegex(client.DownloadError, "Błędna suma SHA-256"):
                archives.acquire_archive("BTCUSDT", "2024-01", "monthly", root / "raw", True)
            self.assertEqual(path.read_bytes(), b"corrupted")

    def test_offline_missing_checksum_and_invalid_zip(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(client, "urlopen", side_effect=AssertionError("Network forbidden")):
            root = Path(folder)
            with self.assertRaisesRegex(client.DownloadError, "Brak pliku w trybie offline"):
                archives.acquire_archive("BTCUSDT", "2024-01", "monthly", root / "raw", True)
            path, _ = make_archive(root)
            path.write_bytes(b"not a zip")
            path.with_name(path.name + ".CHECKSUM").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name)
            with self.assertRaisesRegex(client.DownloadError, "Plik nie jest archiwum ZIP"):
                archives.acquire_archive("BTCUSDT", "2024-01", "monthly", root / "raw", True)

    def test_zip_header_bom_and_invalid_members(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.zip"
            for members in ({}, {"a.csv": "", "b.csv": ""}, {"a.csv": ""}):
                with ZipFile(path, "w") as bundle:
                    for name, content in members.items():
                        bundle.writestr(name, content)
                with self.assertRaises(DataValidationError):
                    parsing.read_spot_klines_zip(path)
            with ZipFile(path, "w") as bundle:
                bundle.writestr("nested/fixture.csv", "\ufeffopen_time,open,high,low,close\n1704067200000,100,112,91,110,1,0,2,3,4,5,0\n")
            self.assertEqual(len(parsing.read_spot_klines_zip(path)), 1)
            self.assertFalse((Path(folder) / "nested").exists())


class CliContracts(unittest.TestCase):
    def test_dry_run(self):
        expected = (
            "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/4h/BTCUSDT-4h-2020-01.zip\n"
            "https://data.binance.vision/data/spot/monthly/klines/ETHUSDT/4h/ETHUSDT-4h-2020-01.zip\n"
            "Archiwa miesięczne do pobrania: 2 (plus pliki CHECKSUM)\n"
        )
        for module in ("market_levels.cli.download",):
            with self.subTest(module=module), tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / "must-not-exist"
                result = subprocess.run([sys.executable, "-X", "utf8", "-m", module, "--start", "2020-01", "--end", "2020-01", "--dry-run", "--output", str(output)],
                                        cwd=PROJECT, capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)
                self.assertEqual(result.stderr, "")
                self.assertFalse(output.exists())

    def test_argument_defaults_and_flags(self):
        from market_levels.cli import download
        with patch.object(sys, "argv", ["download"]), patch.object(download, "run") as pipeline:
            download.main()
            pipeline.assert_called_once_with("2020-01", "2026-10", Path("data"), False, False, True, ("BTCUSDT", "ETHUSDT"))
        with patch.object(sys, "argv", ["download", "--start", "2024-01", "--end", "2024-02", "--output", "other", "--offline", "--strict-gaps", "--no-daily-fallback", "--symbols", "ETHUSDT"]), patch.object(download, "run") as pipeline:
            download.main()
            pipeline.assert_called_once_with("2024-01", "2024-02", Path("other"), True, True, False, ("ETHUSDT",))

    def test_offline_cli_error_status(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, "-X", "utf8", "-m", "market_levels.cli.download", "--start", "2020-01", "--end", "2020-01", "--offline", "--output", folder],
                                    cwd=PROJECT, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 1)
            self.assertIn("BŁĄD: Brak pliku w trybie offline", result.stderr)

"""Kalibracja CLI oraz raport z rzeczywistych plików i istniejącego generatora."""
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from market_levels.core.ohlc.model import UTC
from market_levels.data_processing.synthetic.workflows.generation import run
from market_levels.data_processing.synthetic.workflows.comparison import build_comparison, save_comparison
from market_levels.data_processing.synthetic.reporting.comparison import comparison_summary
from market_levels.data_processing.io.candles import write_candles_csv
from market_levels.data_processing.synthetic.workflows.calibration import calibrate_csv
from market_levels.data_processing.synthetic.io.profiles import load_profile, save_profile
from market_levels.data_processing.synthetic.io.batches import load_synthetic_windows
from market_levels.data_processing.synthetic.config.generation import SyntheticSettings
from market_levels.data_processing.io.chronology import load_chronological_split
from support.comparison import CONFIG, real_fixture


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.csv = self.root / "real.csv"
        self.candles = real_fixture()
        write_candles_csv(self.csv, self.candles)
        self.split = load_chronological_split(CONFIG)
        self.start, self.end = self.split.periods["train"]
        self.profile_path = self.root / "profile.json"

    def cli(self, module, arguments):
        return subprocess.run([sys.executable, "-X", "utf8", "-m", f"market_levels.cli.{module}",
                               "--config", str(CONFIG), *arguments], capture_output=True, text=True, encoding="utf-8")

    def calibration_args(self, symbol="BTCUSDT"):
        return ["--symbol", symbol, "--input", str(self.csv), "--start", self.start.isoformat(),
                "--end", self.end.isoformat(), "--output", str(self.profile_path)]

    def batch(self):
        profile = calibrate_csv(self.csv, "BTCUSDT", allowed_start=self.start, allowed_end=self.end)
        save_profile(self.profile_path, profile)
        return run(SyntheticSettings(diagnostic=True, count=2, symbols=("BTCUSDT",),
            profiles={"BTCUSDT": str(self.profile_path)}, output=self.root / "synthetic")) / "manifest.json"

    def report(self, manifest):
        return build_comparison(symbol="BTCUSDT", real_csv=self.csv, synthetic_manifest=manifest,
            start=self.start, end=self.end, count=2, selection_seed=13, split=self.split)

    def test_calibration_cli_for_both_symbols_and_dry_run(self):
        for symbol in ("BTCUSDT", "ETHUSDT"):
            args = self.calibration_args(symbol)
            dry = self.cli("calibrate_synthetic", args + ["--dry-run"])
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertFalse(self.profile_path.exists())
            saved = self.cli("calibrate_synthetic", args)
            self.assertEqual(saved.returncode, 0, saved.stderr)
            profile = load_profile(self.profile_path, symbol=symbol)
            self.assertEqual(profile["status"], "unapproved")
            self.assertEqual(profile["source"]["chronological_split"], self.split.document())
            collision = self.cli("calibrate_synthetic", args)
            self.assertEqual(collision.returncode, 1)
            self.assertIn("odmowa nadpisania", collision.stderr)
            self.profile_path.unlink()

    def test_calibration_cli_rejects_bad_symbol_dates_and_leakage(self):
        for key, value in (("--symbol", "BAD"), ("--start", "2024-01-01T00:00:00+00:00"),
                           ("--end", "2024-01-01T00:00:00+00:00"), ("--start", "invalid"),
                           ("--start", "2020-01-01T00:00:00"), ("--start", "2020-01-01T01:00:00+00:00"),
                           ("--start", "2020-01-01T00:00:00+01:00")):
            args = self.calibration_args()
            args[args.index(key)+1] = value
            result = self.cli("calibrate_synthetic", args)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(self.profile_path.exists())

    def test_calibration_does_not_use_future_prices(self):
        future = real_fixture(10, datetime(2024, 1, 1, tzinfo=UTC))
        write_candles_csv(self.csv, self.candles + future)
        result = self.cli("calibrate_synthetic", self.calibration_args())
        self.assertEqual(result.returncode, 0, result.stderr)
        first = load_profile(self.profile_path)
        self.profile_path.unlink()
        changed = [replace(c, open=Decimal(10**12), high=Decimal(10**12+1), low=Decimal(10**12-1), close=Decimal(10**12)) for c in future]
        write_candles_csv(self.csv, self.candles + changed)
        result = self.cli("calibrate_synthetic", self.calibration_args())
        self.assertEqual(result.returncode, 0, result.stderr)
        second = load_profile(self.profile_path)
        self.assertEqual(first["generator_parameters"], second["generator_parameters"])
        self.assertEqual(first["statistics"], second["statistics"])
        self.assertNotEqual(first["source"]["sha256"], second["source"]["sha256"])

    def test_report_reproduction_provenance_json_and_no_overwrite(self):
        manifest = self.batch()
        report = self.report(manifest)
        self.assertEqual(report, self.report(manifest))
        # Domyślne kodowanie polskiego Windows także przy przekierowaniu stdout.
        comparison_summary(report).encode("cp1250")
        self.assertEqual(report["real"]["pooled_observations"]["log_returns"]["count"], 238)
        self.assertEqual(report["synthetic"]["pooled_observations"]["relative_range"]["count"], 240)
        self.assertEqual(report["synthetic_source"]["profile_status"], "unapproved")
        self.assertEqual(sum(report["synthetic_source"]["regimes"]["candle_counts"].values()), 240)
        self.assertEqual(report["synthetic_source"]["manifest"], str(manifest.resolve()))
        directory = save_comparison(self.root / "reports", report)
        self.assertEqual(json.loads((directory / "BTCUSDT_comparison.json").read_text(encoding="utf-8")), report)
        self.assertTrue((directory / "BTCUSDT_summary.md").exists())
        with self.assertRaises(FileExistsError):
            save_comparison(self.root / "reports", report)
        with patch('market_levels.data_processing.synthetic.workflows.comparison.write_json', side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                save_comparison(self.root / "failure", report)
        self.assertEqual(list((self.root / "failure").iterdir()), [])

    def test_comparison_cli_and_dry_run(self):
        manifest = self.batch()
        output = self.root / "cli-reports"
        args = ["--symbol", "BTCUSDT", "--real-csv", str(self.csv), "--synthetic-manifest", str(manifest),
                "--start", self.start.isoformat(), "--end", self.end.isoformat(), "--window-count", "2",
                "--selection-seed", "13", "--output", str(output)]
        result = self.cli("compare_synthetic", args + ["--dry-run"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(output.exists())
        result = self.cli("compare_synthetic", args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Raport JSON:", result.stdout)
        self.assertEqual(len(list(output.glob("*/*_comparison.json"))), 1)

    def test_both_symbols_via_unchanged_generation_cli(self):
        profiles = {}
        for symbol in ("BTCUSDT", "ETHUSDT"):
            output = self.root / f"{symbol}.json"
            args = self.calibration_args(symbol)
            args[-1] = str(output)
            result = self.cli("calibrate_synthetic", args)
            self.assertEqual(result.returncode, 0, result.stderr)
            profiles[symbol] = str(output)
        result = self.cli("generate_synthetic", ["--diagnostic", "--count", "1", "--seed", "20261105",
            "--symbols", "BTCUSDT", "ETHUSDT", "--profile", "BTCUSDT=" + profiles["BTCUSDT"],
            "--profile", "ETHUSDT=" + profiles["ETHUSDT"], "--output", str(self.root / "generated")])
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = next((self.root / "generated").glob("diagnostics/*/manifest.json"))
        for symbol in ("BTCUSDT", "ETHUSDT"):
            report = build_comparison(symbol=symbol, real_csv=self.csv, synthetic_manifest=manifest,
                start=self.start, end=self.end, count=1, selection_seed=12, split=self.split)
            self.assertEqual(report["synthetic_source"]["profile"]["symbol"], symbol)
            self.assertEqual(report["synthetic"]["window_count"], 1)

    def test_missing_csv_corrupt_manifest_wrong_symbol_and_count(self):
        manifest = self.batch()
        document = json.loads(manifest.read_text(encoding="utf-8"))
        for change in ({"run_id": "wrong"}, {"examples": []}, {"origin": "real"}):
            modified = dict(document, **change)
            manifest.write_text(json.dumps(modified), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.report(manifest)
        manifest.write_text(json.dumps(document), encoding="utf-8")
        for symbol, count in (("ETHUSDT", 2), ("BTCUSDT", 3)):
            with self.assertRaises(ValueError):
                load_synthetic_windows(manifest, symbol=symbol, count=count, split=self.split)
        (manifest.parent / document["examples"][0]["csv"]).unlink()
        with self.assertRaises(OSError):
            self.report(manifest)

    def test_corrupt_metadata_hash_statistics_and_unsafe_paths(self):
        manifest = self.batch()
        document = json.loads(manifest.read_text(encoding="utf-8"))
        metadata_path = manifest.parent / document["examples"][0]["metadata"]
        original = json.loads(metadata_path.read_text(encoding="utf-8"))
        for change in ({"profile_sha256": "wrong"}, {"symbol": "ETHUSDT"}, {"statistics": {}},
                       {"total_internal_steps": 12}):
            metadata_path.write_text(json.dumps(dict(original, **change)), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.report(manifest)
        metadata_path.write_text(json.dumps(original), encoding="utf-8")
        document["examples"][0]["csv"] = "../../outside.csv"
        manifest.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.report(manifest)

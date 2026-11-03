"""Pełny zapis, CLI i błędy niepozostawiające częściowych przykładów."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from market_levels.data_processing.pipelines.synthetic import prepare_profiles, run
from market_levels.data_processing.synthetic.calibration import approve_profile, save_profile
from market_levels.data_processing.synthetic.quality import compare_statistics
from market_levels.data_processing.synthetic.settings import SyntheticSettings, load_synthetic_settings
from unit.test_synthetic import sample_profile, sample_candles

PROJECT = Path(__file__).resolve().parents[2]


class SyntheticPipelineTests(unittest.TestCase):
    def test_batch_roundtrip_reproduction_and_collision(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings = SyntheticSettings(diagnostic=True, count=2, output=root / "one")
            first = run(settings)
            second = run(replace(settings, output=root / "two"))
            manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["accepted_count"], 4)
            self.assertEqual(manifest["rejected_count"], 0)
            self.assertEqual(manifest["status"], "diagnostic")
            self.assertIsNone(manifest["dataset_split"])
            self.assertEqual(first.name, second.name)
            for a in manifest["examples"]:
                self.assertEqual((first / a["csv"]).read_bytes(), (second / a["csv"]).read_bytes())
                metadata = json.loads((first / a["metadata"]).read_text(encoding="utf-8"))
                self.assertTrue(metadata["roundtrip_valid"])
                self.assertEqual(metadata["seed"], a["seed"])
            previous = {p.relative_to(first): p.read_bytes() for p in first.rglob("*") if p.is_file()}
            with self.assertRaises(FileExistsError):
                run(settings)
            self.assertEqual(previous, {p.relative_to(first): p.read_bytes() for p in first.rglob("*") if p.is_file()})

    def test_duplicate_detection_across_and_within_batches(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = SyntheticSettings(diagnostic=True, count=1, output=Path(folder))
            run(settings)
            with self.assertRaisesRegex(ValueError, "Duplikat"):
                run(replace(settings, count=2))
            self.assertEqual(len(list(Path(folder).glob("diagnostics/*/manifest.json"))), 1)
        with tempfile.TemporaryDirectory() as folder:
            settings = SyntheticSettings(diagnostic=True, count=2, output=Path(folder))
            with patch("market_levels.data_processing.pipelines.synthetic.example_seed", return_value=123):
                with self.assertRaisesRegex(ValueError, "Kolizja seedów"):
                    run(settings)
            self.assertEqual(list(Path(folder).rglob("*.csv")), [])

    def test_write_failure_leaves_no_partial_examples(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = SyntheticSettings(diagnostic=True, output=Path(folder))
            with patch("market_levels.data_processing.pipelines.synthetic.write_json", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    run(settings)
            self.assertEqual(list(Path(folder).rglob("*.csv")), [])
            self.assertEqual(list(Path(folder).rglob("*.json")), [])
            self.assertEqual(list(Path(folder).glob(".synthetic-*")), [])

    def test_processed_directory_is_protected(self):
        with self.assertRaisesRegex(ValueError, "data/processed"):
            prepare_profiles(SyntheticSettings(diagnostic=True, output=PROJECT / "data/processed/synthetic"))

    def test_candidates_require_approval_and_include_reference_comparison(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            profile_path = root / "profile.json"
            profile = sample_profile()
            save_profile(profile_path, profile)
            settings = SyntheticSettings(symbols=("BTCUSDT",), count=1, profiles={"BTCUSDT": str(profile_path)}, output=root / "out")
            with self.assertRaisesRegex(ValueError, "niezatwierdzony"):
                run(settings)
            self.assertFalse(settings.output.exists())
            candles = sample_candles()
            approved = approve_profile(profile, training_start=candles[0].timestamp,
                training_end=candles[-1].timestamp, split_id="test-only", reviewed_by="fixture")
            approved_path = root / "approved.json"
            save_profile(approved_path, approved)
            result = run(replace(settings, profiles={"BTCUSDT": str(approved_path)}))
            metadata_path = next(result.glob("BTCUSDT/*.json"))
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["status"], "candidate")
            self.assertEqual(metadata["reference_comparison"], compare_statistics(metadata["statistics"], profile["statistics"]))

    def cli(self, *arguments):
        return subprocess.run([sys.executable, "-X", "utf8", "-m", "market_levels.cli.generate_synthetic",
                               "--config", str(PROJECT / "configs/experiment.json"), *arguments],
                              capture_output=True, text=True, encoding="utf-8")

    def test_cli_overrides_and_dry_run_have_no_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "out"
            result = self.cli("--diagnostic", "--count", "1", "--symbols", "ETHUSDT", "--seed", "77",
                              "--output", str(output), "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("diagnostyczny", result.stderr)
            settings = json.loads(result.stdout)
            self.assertEqual(settings["count"], 1)
            self.assertEqual(settings["symbols"], ["ETHUSDT"])
            self.assertEqual(settings["seed"], 77)
            self.assertFalse(output.exists())
            result = self.cli("--diagnostic", "--count", "1", "--symbols", "ETHUSDT", "--output", str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(list(output.rglob("*.csv"))), 1)

    def test_cli_invalid_inputs_and_missing_approval_fail_cleanly(self):
        for arguments in (("--count", "0", "--diagnostic"), ("--seed", "-2", "--diagnostic"),
                          ("--no-diagnostic", "--dry-run"), ("--profile", "wrong", "--diagnostic")):
            result = self.cli(*arguments)
            self.assertEqual(result.returncode, 1)
            self.assertIn("BŁĄD:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_config_fields_are_active_and_unknown_options_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "config.json"
            options = SyntheticSettings(diagnostic=True, symbols=("ETHUSDT",), count=3, seed=44).document()
            path.write_text(json.dumps({"synthetic": options}), encoding="utf-8")
            settings = load_synthetic_settings(path)
            self.assertEqual(settings.count, 3)
            self.assertEqual(settings.seed, 44)
            self.assertIn("ETHUSDT", prepare_profiles(settings))
            options["unknown"] = True
            path.write_text(json.dumps({"synthetic": options}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_synthetic_settings(path)

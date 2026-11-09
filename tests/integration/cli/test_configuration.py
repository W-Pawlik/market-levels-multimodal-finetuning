import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from market_levels.cli import download
from market_levels.configuration import ConfigurationError, load_download_settings

from support.paths import PROJECT


CONFIG = json.loads((PROJECT / "configs/experiment.json").read_text(encoding="utf-8"))


class ConfigurationTests(unittest.TestCase):
    def write_config(self, folder, document):
        path = Path(folder) / "experiment.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_file_controls_pipeline_without_cli_overrides(self):
        document = copy.deepcopy(CONFIG)
        document.update(history_start_month="2024-02", history_end_month="2024-03", symbols=["ETHUSDT"])
        document["download"] = {"output": "custom-data", "offline": True,
                                "strict_gaps": True, "daily_fallback": False}
        with tempfile.TemporaryDirectory() as folder:
            config = self.write_config(folder, document)
            with patch.object(sys, "argv", ["download", "--config", str(config)]), patch.object(download, "run") as pipeline:
                download.main()
                pipeline.assert_called_once_with("2024-02", "2024-03", Path("custom-data"),
                                                 True, True, False, ("ETHUSDT",))

    def test_cli_overrides_config_in_both_boolean_directions(self):
        document = copy.deepcopy(CONFIG)
        document["download"] = {"offline": True, "strict_gaps": True, "daily_fallback": False}
        with tempfile.TemporaryDirectory() as folder:
            config = self.write_config(folder, document)
            args = ["download", "--config", str(config), "--start", "2024-01", "--end", "2024-02",
                    "--symbols", "BTCUSDT", "--output", "override", "--no-offline",
                    "--no-strict-gaps", "--daily-fallback"]
            with patch.object(sys, "argv", args), patch.object(download, "run") as pipeline:
                download.main()
                pipeline.assert_called_once_with("2024-01", "2024-02", Path("override"),
                                                 False, False, True, ("BTCUSDT",))

    def test_invalid_configs_fail_before_pipeline_or_output(self):
        changes = [
            {"source": "other"}, {"market": "futures"}, {"interval": "1h"},
            {"symbols": []}, {"symbols": ["OTHER"]}, {"symbols": "BTCUSDT"},
            {"symbols": [1]}, {"history_start_month": "bad"},
            {"history_start_month": "2027-01"}, {"history_end_month": None},
            {"download": []}, {"download": {"offline": "false"}},
            {"download": {"strict_gaps": 1}}, {"download": {"daily_fallback": None}},
            {"download": {"output": ""}}, {"download": {"output": 1}},
        ]
        with tempfile.TemporaryDirectory() as folder:
            for change in changes:
                document = copy.deepcopy(CONFIG)
                document.update(change)
                config = self.write_config(folder, document)
                with self.subTest(change=change), self.assertRaises(ConfigurationError):
                    load_download_settings(config)
            for content in ("[]", "null", "{invalid", ""):
                config.write_text(content, encoding="utf-8")
                with self.subTest(content=content), self.assertRaises(ConfigurationError):
                    load_download_settings(config)
            config.unlink()
            with self.assertRaises(ConfigurationError):
                load_download_settings(config)
            with patch.object(sys, "argv", ["download", "--config", str(config)]), patch.object(download, "run") as pipeline, contextlib.redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit) as error:
                    download.main()
                self.assertEqual(error.exception.code, 1)
                self.assertIn("BŁĄD:", stderr.getvalue())
                self.assertNotIn("Traceback", stderr.getvalue())
                pipeline.assert_not_called()

    def test_default_config_is_loaded_from_working_directory(self):
        document = copy.deepcopy(CONFIG)
        document.update(history_start_month="2024-02", history_end_month="2024-02", symbols=["ETHUSDT"])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "configs").mkdir()
            (root / "configs/experiment.json").write_text(json.dumps(document), encoding="utf-8")
            result = subprocess.run([sys.executable, "-X", "utf8", "-m", "market_levels.cli.download", "--dry-run"],
                                    cwd=root, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), [
                "https://data.binance.vision/data/spot/monthly/klines/ETHUSDT/4h/ETHUSDT-4h-2024-02.zip",
                "Archiwa miesięczne do pobrania: 1 (plus pliki CHECKSUM)",
            ])
            self.assertFalse((root / "data").exists())

    def test_config_drives_real_offline_pipeline(self):
        from support.archives import make_archive
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "output"
            make_archive(output)
            document = copy.deepcopy(CONFIG)
            document.update(history_start_month="2024-01", history_end_month="2024-01", symbols=["BTCUSDT"])
            document["download"] = {"output": str(output), "offline": True,
                                    "strict_gaps": False, "daily_fallback": False}
            config = self.write_config(root, document)
            with patch.object(sys, "argv", ["download", "--config", str(config)]), contextlib.redirect_stdout(io.StringIO()):
                download.main()
            report = json.loads((output / "reports/BTCUSDT_2024-01_2024-01.json").read_text(encoding="utf-8"))
            self.assertEqual(report["count"], 2)
            self.assertEqual(report["missing_total"], 184)
            self.assertTrue((output / "processed/BTCUSDT_4h_2024-01_2024-01.csv").exists())

    def test_download_section_optional_and_utf8_bom_supported(self):
        document = copy.deepcopy(CONFIG)
        del document["download"]
        with tempfile.TemporaryDirectory() as folder:
            path = self.write_config(folder, document)
            path.write_text(json.dumps(document), encoding="utf-8-sig")
            settings = load_download_settings(path)
            self.assertEqual(settings.output, Path("data"))
            self.assertFalse(settings.offline)
            self.assertFalse(settings.strict_gaps)
            self.assertTrue(settings.daily_fallback)

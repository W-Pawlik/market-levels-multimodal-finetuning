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


class OfflineIntegrationTests(unittest.TestCase):
    def test_offline_download_pipeline_and_edge_gaps(self):
        from market_levels.data_processing.pipelines.download import run
        import hashlib
        import json
        from io import StringIO
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive_dir = root / "raw" / "BTCUSDT" / "4h" / "monthly"
            archive_dir.mkdir(parents=True)
            name = "BTCUSDT-4h-2024-01.zip"
            zpath = archive_dir / name
            with ZipFile(zpath, "w") as z:
                out = StringIO()
                w = csv.writer(out)
                # 1 stycznia 2024 00:00 i 04:00 UTC
                w.writerow(row(1704067200000))
                w.writerow(row(1704081600000))
                z.writestr(name.replace(".zip", ".csv"), out.getvalue())
            checksum = hashlib.sha256(zpath.read_bytes()).hexdigest()
            (archive_dir / (name + ".CHECKSUM")).write_text(f"{checksum}  {name}\n")
            run("2024-01", "2024-01", root, True, False, False, ("BTCUSDT",))
            out = root / "processed" / "BTCUSDT_4h_2024-01_2024-01.csv"
            self.assertTrue(out.exists())
            self.assertEqual(len(out.read_text().splitlines()), 3)
            report = json.loads((root / "reports" / "BTCUSDT_2024-01_2024-01.json").read_text())
            self.assertEqual(report["count"], 2)
            self.assertGreater(report["missing_at_end"], 0)
            self.assertTrue((root / "reports" / "manifest_2024-01_2024-01.json").exists())

"""Original generator, label, metric and CSV outputs."""
import hashlib
from pathlib import Path
import platform
import tempfile
import unittest

from support.behavior import BASELINE, object_hash, reproduce
from market_levels.core.ohlc.identity import canonical_hash
from market_levels.labeling.domain.algorithm import label_window
from market_levels.charts.domain.metrics import window_metrics
from market_levels.data_processing.io.candles import write_candles_csv


class BehaviorBaselineTests(unittest.TestCase):
    @unittest.skipUnless(platform.python_version() == BASELINE['python'] and
        platform.python_implementation() == 'CPython', 'Reference requires CPython ' + BASELINE['python'])
    def test_generator_labels_metrics_and_csv_match_original_28_cases(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'candles.csv'
            for identity, expected in BASELINE['examples'].items():
                with self.subTest(identity=identity):
                    example = reproduce(identity)
                    result = label_window(example.candles)
                    self.assertEqual(canonical_hash(example.candles), expected['candles'])
                    self.assertEqual(object_hash(example.metadata), expected['metadata'])
                    self.assertEqual(result.target_json(), expected['labels'])
                    self.assertEqual(object_hash(result.diagnostics()), expected['diagnostics'])
                    self.assertEqual(window_metrics(example.candles), expected['metrics'])
                    write_candles_csv(path, example.candles)
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected['csv'])

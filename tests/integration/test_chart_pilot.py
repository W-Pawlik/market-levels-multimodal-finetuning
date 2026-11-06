"""Offline end-to-end audit: missing synthetics are reported, never regenerated."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_levels.charts.pilot import run_audit
from market_levels.data_processing.storage import write_candles_csv
from market_levels.data_processing.synthetic.quality import canonical_hash
from market_levels.data_processing.storage import read_candles_csv
from unit.test_charts import fixture


class PilotIntegrationTests(unittest.TestCase):
    def test_atomic_pilot_metadata_replay_missing_synthetics_and_unchanged_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = Path(__file__).resolve().parents[2]/'configs/experiment.json'
            candles = fixture(8766)  # full inclusive 2020–2023 train bounds
            source = root/'real.csv'
            write_candles_csv(source,candles)
            with source.open('a',encoding='utf8') as stream:
                stream.write('2024-01-01T00:00:00+00:00,NO_ACCESS,NO_ACCESS,NO_ACCESS,NO_ACCESS\n')
            before = source.read_bytes()
            with patch('market_levels.data_processing.synthetic.generator.generate_example',side_effect=AssertionError('Generation forbidden')), patch('market_levels.data_processing.synthetic.generator_v2.generate_example_v2',side_effect=AssertionError('Generation forbidden')):
                final = run_audit(synthetic_root=root/'missing',real_csv={'BTCUSDT':source,'ETHUSDT':source},
                                  config=config,output=root/'audit',selection_seed=42,per_group=6)
            report = json.loads((final/'AUDYT_ROZNORODNOSCI.json').read_text(encoding='utf8'))
            self.assertEqual(report['analyzed_count'],0)
            self.assertEqual(len(report['discovery']['missing_seeds']),5)
            self.assertEqual(report['pilot']['actual_count'],12)
            self.assertEqual(report['pilot']['requested_count'],24)
            self.assertFalse(report['data_access']['validation_test_ohlc_parsed'])
            self.assertTrue(report['source_integrity']['unchanged'])
            for item in report['pilot']['images']:
                self.assertEqual(item['selection_seed'],42)
                self.assertIsNone(item['variant'])
                png = final/'pilot'/item['png']
                self.assertEqual(hashlib.sha256(png.read_bytes()).hexdigest(),item['png_sha256'])
                copied = read_candles_csv(final/'pilot'/item['window_csv'],source='portable-window')
                self.assertEqual(canonical_hash(copied),item['ohlc_sha256'])
                indices = item['training_record_indices']
                self.assertEqual(canonical_hash(candles[indices[0]:indices[-1]+1]),item['ohlc_sha256'])
            self.assertEqual(source.read_bytes(),before)
            with self.assertRaises(FileExistsError):
                run_audit(synthetic_root=root/'missing',real_csv={},config=config,output=final)
            self.assertEqual(source.read_bytes(),before)


if __name__ == '__main__':
    unittest.main()

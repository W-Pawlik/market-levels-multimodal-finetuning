"""Audit summaries must stay descriptive and separate split/source groups."""
from copy import deepcopy
import unittest

from market_levels.datasets.audit import audit_dataset
from market_levels.datasets.production import json_line, synthetic_id
from market_levels.datasets.packaging import INSTRUCTION


class ProductionAuditTests(unittest.TestCase):
    def record(self, **overrides):
        row = {'id': 'a', 'symbol': 'BTCUSDT', 'source': 'real', 'split': 'train',
               'start_utc': '2020-01-01T00:00:00+00:00', 'ohlc_sha256': 'a',
               'support_count': 3, 'resistance_count': 0,
               'metrics': {'observed_motion': 'upward', 'log_return_std': .01, 'price_change': .1},
               'answer': {'supports': [100, 100.1, 90], 'resistances': []},
               'label_audit': {'atr': '1'}}
        row.update(overrides)
        return row

    def test_groups_missing_sides_limit_and_close_levels(self):
        rows = [self.record(), self.record(id='b', split='test', ohlc_sha256='b', support_count=0,
                                           resistance_count=0, answer={'supports': [], 'resistances': []})]
        before = deepcopy(rows)
        report = audit_dataset(rows)
        self.assertEqual(rows, before)
        self.assertEqual(report['groups']['train/real']['full_support_limit_share'], 1)
        self.assertEqual(report['groups']['test/real']['without_supports_share'], 1)
        self.assertEqual(report['close_level_examples'][0]['id'], 'a')
        self.assertEqual(report['exact_ohlc_duplicates'], 0)

    def test_synthetic_years_and_regimes_do_not_become_market_years(self):
        row = self.record(source='synthetic', start_utc=None, generator_metadata={'regimes': [
            {'kind': 'consolidation', 'length': 80}, {'kind': 'uptrend', 'length': 40}]})
        report = audit_dataset([row])
        self.assertEqual(report['groups']['train/synthetic']['real_years_by_start'], {})
        self.assertEqual(report['synthetic_regime_candles'], {'consolidation': 80, 'uptrend': 40})
        self.assertEqual(report['synthetic_transitions'], {'consolidation->uptrend': 1})

    def test_exact_serialization_and_stable_names(self):
        import json
        answer = '{"supports": [123.40], "resistances": []}\n'
        line = json_line('id', 'test', 'images/id.png', answer)
        self.assertIn('123.40', line)
        self.assertEqual(json.loads(line)['instruction'], INSTRUCTION)
        identity = synthetic_id('BTCUSDT', 1, 'a', 'b')
        self.assertEqual(identity, synthetic_id('BTCUSDT', 1, 'a', 'b'))
        self.assertNotEqual(identity, synthetic_id('BTCUSDT', 2, 'a', 'b'))

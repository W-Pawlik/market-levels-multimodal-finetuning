"""Chronology, gaps, deterministic selection and data leakage contracts."""
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from market_levels.shared.configuration import read_configuration
from market_levels.core.ohlc.model import Candle, CANDLE_DELTA, UTC
from market_levels.data_processing.io.chronology import load_chronological_split
from market_levels.data_processing.windows.domain.models import Window
from market_levels.data_processing.windows.domain.candidates import candidates, coverage, validate_selection
from market_levels.data_processing.windows.domain.selection import select_training
from market_levels.datasets.config import load_plan_config, synthetic_settings
from market_levels.datasets.workflows.planning import require_production_ready

from support.paths import PROJECT

CONFIG = PROJECT/'configs/experiment.json'


def series(start, count, offset=0):
    return [Candle(start+i*CANDLE_DELTA, Decimal(100+offset+i), Decimal(102+offset+i),
                   Decimal(99+offset+i), Decimal(101+offset+i), 'fixture') for i in range(count)]


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.split = load_chronological_split(CONFIG)
        self.strides = {'train': 60, 'validation': 120, 'test': 120}

    def test_gap_restarts_grid_and_rejects_short_tails(self):
        candles = series(datetime(2020, 1, 1, tzinfo=UTC), 400)
        del candles[150]
        pool, audit = candidates(candles, 'BTCUSDT', self.split, self.strides)
        self.assertEqual([w.indices[0] for w in pool['train']], [0, 150, 210, 270])
        self.assertEqual(audit['train']['gaps'][0]['missing_candles'], 1)
        self.assertEqual(audit['train']['ineligible_grid_starts'][0]['reason'], 'gap')
        validate_selection(pool['train'], self.split)

    def test_explicit_split_boundary_fixtures(self):
        # Actual 2023/24 and 2024/25 boundaries, independent of diagnostic pilot.
        for year in (2024, 2025):
            boundary = datetime(year, 1, 1, tzinfo=UTC)
            pool, _ = candidates(series(boundary-119*CANDLE_DELTA, 239, year), 'ETHUSDT', self.split, self.strides)
            target = 'validation' if year == 2024 else 'test'
            self.assertEqual(len(pool[target]), 1)
            self.assertEqual(pool[target][0].candles[0].timestamp, boundary)
            self.assertEqual(sum(map(len, pool.values())), 1)

    def test_inclusive_end_and_exact_window_length(self):
        start, end = self.split.periods['test']
        pool, _ = candidates(series(end-119*CANDLE_DELTA, 120), 'BTCUSDT', self.split, self.strides)
        self.assertEqual(pool['test'][0].candles[-1].timestamp, end)
        validate_selection(pool['test'], self.split)

    def test_selection_coverage_repeatability_seed_and_no_label_access(self):
        candles = series(datetime(2020, 1, 1, tzinfo=UTC), 8766)
        pool, _ = candidates(candles, 'BTCUSDT', self.split, self.strides)
        windows = pool['train']
        selected = select_training(windows, 129, 123)
        self.assertEqual(selected, select_training(list(reversed(windows)), 129, 123))
        self.assertNotEqual(selected, select_training(windows, 129, 124))
        self.assertEqual(len({w.indices for w in selected}), 129)
        self.assertEqual(set(coverage(selected)['years_by_window_start']), {'2020', '2021', '2022', '2023'})
        validate_selection(selected, self.split)  # train overlap is intentional

    def test_shortage_rejected_instead_of_adjusted(self):
        for count in (-1, 1, True):
            with self.assertRaises(ValueError):
                select_training([], count, 1)
        self.assertEqual(select_training([], 0, 1), [])

    def test_unsorted_duplicate_ohlc_and_non_utc_rejected(self):
        cs = series(datetime(2020, 1, 1, tzinfo=UTC), 120)
        for bad in ([cs[1], cs[0]]+cs[2:], [cs[0]]+cs, [replace(cs[0], high=Decimal(1))]+cs[1:],
                    [replace(cs[0], timestamp=cs[0].timestamp.replace(tzinfo=None))]+cs[1:]):
            with self.assertRaises(ValueError):
                candidates(bad, 'BTCUSDT', self.split, self.strides)

    def test_selection_boundary_and_gap_rejected(self):
        for cs in (series(datetime(2023, 12, 31, tzinfo=UTC), 120),
                   series(datetime(2020, 1, 1, tzinfo=UTC), 121)[1:60]+series(datetime(2020, 1, 1, tzinfo=UTC), 121)[61:]):
            with self.assertRaises(ValueError):
                validate_selection([Window('BTCUSDT', 'train', tuple(range(120)), tuple(cs))], self.split)

    def test_evaluation_overlap_and_cross_split_duplicate_rejected(self):
        cs = series(datetime(2024, 1, 1, tzinfo=UTC), 180)
        ws = [Window('BTCUSDT', 'validation', tuple(range(i, i+120)), tuple(cs[i:i+120])) for i in (0, 60)]
        with self.assertRaisesRegex(ValueError, 'Nakładające'):
            validate_selection(ws, self.split)
        base = series(datetime(2020, 1, 1, tzinfo=UTC), 120)
        duplicate = series(datetime(2024, 1, 1, tzinfo=UTC), 120)
        with self.assertRaisesRegex(ValueError, 'Duplikat'):
            validate_selection([Window('BTCUSDT', 'train', tuple(range(120)), tuple(base)),
                                Window('BTCUSDT', 'validation', tuple(range(120)), tuple(duplicate))], self.split)

    def test_invalid_symbol_stride_and_validation_selection(self):
        for symbol, strides in [('DOGE', self.strides), ('BTCUSDT', dict(self.strides, train=0)),
                                ('BTCUSDT', dict(self.strides, test=60))]:
            with self.assertRaises(ValueError):
                candidates([], symbol, self.split, strides)
        ws = [Window('BTCUSDT', 'test', tuple(range(120)), tuple(series(self.split.periods['test'][0], 120)))]
        with self.assertRaises(ValueError):
            select_training(ws, 1, 1)


class PlanConfigTests(unittest.TestCase):
    def test_approved_targets_and_production_settings(self):
        config = load_plan_config(CONFIG)
        self.assertEqual(config['dataset_build']['targets']['train']['real']['BTCUSDT'], 129)
        settings = synthetic_settings(CONFIG, 'BTCUSDT', output=Path('temp'))
        self.assertEqual((settings.generator_version, settings.v2_variant, settings.count, settings.diagnostic), ('v2', 'full', 220, False))

    def test_bad_targets_and_unknown_options_fail(self):
        for key in ('unknown', 'synthetic_test', 'negative', 'empty'):
            doc = read_configuration(CONFIG)
            if key == 'unknown':
                doc['dataset_build']['unknown'] = 1
            elif key == 'synthetic_test':
                doc['dataset_build']['targets']['test']['synthetic']['BTCUSDT'] = 1
            elif key == 'negative':
                doc['dataset_build']['targets']['train']['real']['BTCUSDT'] = -1
            else:
                for group in doc['dataset_build']['targets'].values():
                    for counts in group.values():
                        counts.update(BTCUSDT=0, ETHUSDT=0)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)/'config.json'
                path.write_text(json.dumps(doc), encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_plan_config(path)

    def test_counts_change_in_one_place(self):
        doc = read_configuration(CONFIG)
        doc['dataset_build']['targets']['train']['real']['BTCUSDT'] = 130
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'config.json'
            path.write_text(json.dumps(doc), encoding='utf-8')
            self.assertEqual(load_plan_config(path)['dataset_build']['targets']['train']['real']['BTCUSDT'], 130)

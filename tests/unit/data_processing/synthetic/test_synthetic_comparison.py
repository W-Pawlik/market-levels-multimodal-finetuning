"""Selekcja i agregacja bez luk, przecieku i sztucznych zwrotów na granicach."""
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from copy import deepcopy
import json
import math
from pathlib import Path
import unittest
import tempfile

from market_levels.shared.configuration import read_configuration
from market_levels.core.ohlc.model import Candle, CANDLE_DELTA, UTC
from market_levels.data_processing.synthetic.domain.diagnostics import aggregate_windows, lag1_absolute_correlation
from market_levels.core.numeric.statistics import distribution
from market_levels.data_processing.synthetic.domain.quality import series_statistics
from market_levels.data_processing.windows.domain.selection import select_real_windows
from market_levels.data_processing.io.chronology import load_chronological_split

from support.comparison import real_fixture

from support.paths import PROJECT

CONFIG = PROJECT / "configs/experiment.json"




class WindowSelectionTests(unittest.TestCase):
    def setUp(self):
        self.split = load_chronological_split(CONFIG)

    def select(self, candles, count=5, seed=41):
        return select_real_windows(candles, symbol="BTCUSDT", start=self.split.periods["train"][0],
            end=self.split.periods["train"][1], count=count, seed=seed, split=self.split)

    def test_gap_nonoverlap_reproduction_and_seed_effect(self):
        candles = real_fixture()
        del candles[296]
        windows, selection = self.select(candles)
        self.assertEqual((windows, selection), self.select(candles))
        self.assertNotEqual(selection, self.select(candles, seed=42)[1])
        self.assertEqual(len(selection["gaps"]), 1)
        self.assertEqual(selection["max_nonoverlapping_windows"], 6)
        stamps = []
        for window in windows:
            self.assertEqual(len(window), 120)
            self.assertTrue(all(b.timestamp - a.timestamp == CANDLE_DELTA for a, b in zip(window, window[1:])))
            stamps.extend(c.timestamp for c in window)
        self.assertEqual(len(set(stamps)), 600)
        for window, entry in zip(windows, selection["windows"]):
            self.assertEqual(window, [candles[i] for i in entry["csv_record_indices"]])

    def test_maximum_is_achievable_and_insufficient_count_errors(self):
        candles = real_fixture(480)
        self.assertEqual(len(self.select(candles, count=4)[0]), 4)
        with self.assertRaisesRegex(ValueError, "maksimum 4"):
            self.select(candles, count=5)

    def test_future_observations_do_not_change_selection(self):
        candles = real_fixture(480)
        future = real_fixture(150, datetime(2024, 1, 1, tzinfo=UTC))
        self.assertEqual(self.select(candles, count=3), self.select(candles + future, count=3))
        with self.assertRaisesRegex(ValueError, "treningu"):
            select_real_windows(candles + future, symbol="BTCUSDT", start=candles[0].timestamp,
                end=future[-1].timestamp, count=1, seed=1, split=self.split)

    def test_sixty_windows_and_realistic_gap_fit_without_greedy_failure(self):
        # Same rozmiary czasowe co oczekiwany trening, bez danych rynkowych.
        candles = real_fixture(8766)
        del candles[296]
        for seed in (0, 1, 20261106):
            windows, metadata = self.select(candles, count=60, seed=seed)
            self.assertEqual(len(windows), 60)
            self.assertEqual(metadata["max_nonoverlapping_windows"], 72)
            self.assertGreater(windows[-1][0].timestamp.year, 2020)

    def test_invalid_split_configuration_is_rejected(self):
        original = read_configuration(CONFIG)
        mutations = [lambda s: s.update(status="unapproved"),
                     lambda s: s.update(timestamp_role="close"),
                     lambda s: s["periods"]["validation"].update(start="2023-12-31T20:00:00+00:00"),
                     lambda s: s["periods"]["test"].update(end="2026-10-31T21:00:00+00:00"),
                     lambda s: s.update(unknown=True)]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            for mutation in mutations:
                document = deepcopy(original)
                mutation(document["chronological_split"])
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_chronological_split(path)


class ComparisonStatisticsTests(unittest.TestCase):
    def test_no_returns_or_correlation_pairs_between_independent_windows(self):
        first = real_fixture(120)
        a = [replace(c, open=Decimal(100), high=Decimal(101), low=Decimal(99), close=Decimal(100)) for c in first]
        b = [replace(c, open=Decimal(10000), high=Decimal(10100), low=Decimal(9900), close=Decimal(10000)) for c in first]
        stats = aggregate_windows([a, b])
        self.assertEqual(stats["pooled_observations"]["log_returns"]["count"], 238)
        self.assertEqual(stats["pooled_observations"]["log_returns"]["max"], 0)
        self.assertEqual(stats["absolute_return_lag1"]["pair_count"], 236)
        self.assertIsNone(stats["absolute_return_lag1"]["value"])
        self.assertEqual(stats["absolute_return_lag1"]["reason"], "zero_variance")

    def test_quantiles_are_computed_from_observations_not_window_quantiles(self):
        def make_window(returns):
            result = []
            log_price = 0.0
            for i, step in enumerate([0.0] + returns):
                log_price += step
                p = Decimal(str(math.exp(log_price)))
                result.append(Candle(datetime(2020, 1, 1, tzinfo=UTC) + i*CANDLE_DELTA, p, p, p, p, "test"))
            return result
        a, b = make_window([0.0] * 118 + [3.0]), make_window([1.0] * 119)
        stats = aggregate_windows([a, b])
        self.assertAlmostEqual(stats["pooled_observations"]["log_returns"]["quantiles"]["0.5"], 1)
        self.assertAlmostEqual((series_statistics(a)["log_returns"]["quantiles"]["0.5"] +
                               series_statistics(b)["log_returns"]["quantiles"]["0.5"]) / 2, 0.5)
        self.assertAlmostEqual(distribution([0, 10])["quantiles"]["0.05"], 0.5)

    def test_wicks_and_window_metrics_use_existing_definitions(self):
        window = real_fixture(120)
        actual = aggregate_windows([window])
        expected = series_statistics(window)
        self.assertEqual(actual["pooled_observations"]["upper_wick_fraction"], expected["upper_wick_fraction"])
        self.assertEqual(actual["pooled_observations"]["body_fraction"]["mean"], 0)
        self.assertAlmostEqual(actual["pooled_observations"]["upper_wick_fraction"]["mean"], 0.5)
        self.assertEqual(actual["window_distributions"]["return_std"]["mean"], expected["log_returns"]["std"])
        self.assertEqual(actual["window_distributions"]["close_change"]["mean"], expected["window_close_change"])

    def test_autocorrelation_known_cases_and_undefined_results(self):
        self.assertAlmostEqual(lag1_absolute_correlation([[1, -2, 3, -4]])["value"], 1)
        self.assertAlmostEqual(lag1_absolute_correlation([[1, -3, 1, -3]])["value"], -1)
        self.assertEqual(lag1_absolute_correlation([[1], [2]])["reason"], "insufficient_pairs")
        self.assertEqual(lag1_absolute_correlation([[1, 1, 1]])["reason"], "zero_variance")

    def test_invalid_windows_are_rejected(self):
        with self.assertRaises(ValueError):
            aggregate_windows([])
        with self.assertRaises(ValueError):
            aggregate_windows([real_fixture(119)])
        window = real_fixture(121)
        del window[30]
        with self.assertRaises(ValueError):
            aggregate_windows([window])

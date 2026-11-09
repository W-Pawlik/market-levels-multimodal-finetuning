"""Generator, planowanie, statystyki i ochrona granic kalibracji (offline)."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
import math
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from market_levels.core.ohlc.model import Candle, UTC, CANDLE_DELTA
from market_levels.data_processing.io.candles import write_candles_csv, read_candles_csv
from market_levels.data_processing.synthetic.domain.profiles.v1 import approve_profile, diagnostic_profile, validate_profile
from market_levels.data_processing.synthetic.workflows.calibration import calibrate, calibrate_csv
from market_levels.data_processing.synthetic.io.profiles import load_profile, save_profile
from market_levels.data_processing.synthetic.domain.generation.seeds import example_seed
from market_levels.data_processing.synthetic.domain.generation.v1 import generate_example
from market_levels.core.ohlc.identity import canonical_hash
from market_levels.data_processing.synthetic.domain.quality import series_statistics, validate_synthetic
from market_levels.core.ohlc.validation import validate_values
from market_levels.data_processing.synthetic.domain.generation.regimes import feasible_sequences, plan_regimes
from market_levels.data_processing.synthetic.config.regimes import RegimeSettings
from market_levels.data_processing.synthetic.config.generation import SyntheticSettings

from support.synthetic import sample_candles, sample_profile






class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.settings = SyntheticSettings(diagnostic=True)
        self.profile = diagnostic_profile("BTCUSDT")

    def generate(self, seed=42, settings=None):
        return generate_example("BTCUSDT", seed, self.profile, settings or self.settings)

    def test_reproduction_and_global_rng_independence(self):
        first = self.generate()
        random.seed(900)
        for _ in range(20):
            random.random()
        second = self.generate()
        self.assertEqual(first, second)
        self.assertNotEqual(first.candles, self.generate(43).candles)

    def test_seed_uniqueness_and_order_independence(self):
        seeds = [example_seed(123, symbol, i) for symbol in ("BTCUSDT", "ETHUSDT") for i in range(1000)]
        self.assertEqual(len(seeds), len(set(seeds)))
        self.assertEqual(example_seed(123, "BTCUSDT", 0), seeds[0])

    def test_ohlc_continuity_utc_and_provenance_for_both_symbols(self):
        for symbol in ("BTCUSDT", "ETHUSDT"):
            result = generate_example(symbol, 7, diagnostic_profile(symbol), self.settings)
            self.assertEqual(len(result.candles), 120)
            self.assertTrue(result.metadata["validation"]["valid"])
            self.assertEqual(result.metadata["total_internal_steps"], 1440)
            for a, b in zip(result.candles, result.candles[1:]):
                self.assertEqual(a.close, b.open)
                self.assertEqual(b.timestamp - a.timestamp, CANDLE_DELTA)
            self.assertIn("simulation_index", result.metadata["timestamp_role"])
            for c in result.candles:
                self.assertIsInstance(c.open, Decimal)
                self.assertEqual(c.timestamp.utcoffset(), timedelta(0))
                self.assertTrue(c.source_archive.startswith("synthetic:"))
                self.assertGreater(c.low, 0)
                self.assertLessEqual(c.low, min(c.open, c.close))
                self.assertGreaterEqual(c.high, max(c.open, c.close))

    def test_exact_steps_and_extrema_come_from_internal_path(self):
        # Naprzemienne +1/-1 ujawniają śródświecowe maksimum, którego nie ma w Open/Close.
        with patch('market_levels.data_processing.synthetic.domain.generation.v1.random.Random.gauss',
                   side_effect=[1.0, -1.0] * 720) as noise:
            result = self.generate(settings=replace(self.settings, min_regimes=1, max_regimes=1,
                regimes=replace(RegimeSettings(), initial_weights=dict(
                    uptrend=1.0, downtrend=0.0, consolidation=0.0, breakout=0.0))))
        self.assertEqual(noise.call_count, 1440)
        first = result.candles[0]
        regime = result.metadata["regimes"][0]
        expected_log_return = regime["mu"]
        self.assertAlmostEqual(math.log(float(first.close / first.open)), expected_log_return, places=12)
        self.assertGreater(first.high, max(first.open, first.close))

    def test_regime_direction_and_mean_reversion(self):
        # Bez szumu trend ma oczekiwany znak; konsolidacja tłumi uprzednie odchylenie.
        for kind, sign in (("uptrend", 1), ("downtrend", -1)):
            options = replace(RegimeSettings(), initial_weights={k: float(k == kind) for k in
                       ("uptrend", "downtrend", "consolidation", "breakout")})
            settings = replace(self.settings, min_regimes=1, max_regimes=1, regimes=options)
            with patch('market_levels.data_processing.synthetic.domain.generation.v1.random.Random.gauss', return_value=0):
                result = self.generate(settings=settings)
            self.assertGreater(sign * (result.candles[-1].close - result.candles[0].open), 0)
        options = replace(RegimeSettings(), initial_weights=dict(
            uptrend=0.0, downtrend=0.0, consolidation=1.0, breakout=0.0))
        settings = replace(self.settings, min_regimes=1, max_regimes=1, regimes=options)
        with patch('market_levels.data_processing.synthetic.domain.generation.v1.random.Random.gauss',
                   side_effect=[1.0] + [0.0] * 1439):
            result = self.generate(settings=settings)
        self.assertLess(result.candles[-1].close, result.candles[0].close)
        self.assertGreater(result.candles[-1].close, result.candles[0].open)

    def test_nonfinite_path_is_rejected(self):
        with patch('market_levels.data_processing.synthetic.domain.generation.v1.random.Random.gauss', return_value=math.inf):
            with self.assertRaises(ValueError):
                self.generate()

    def test_unapproved_profile_cannot_generate_candidate(self):
        with self.assertRaises(ValueError):
            self.generate(settings=replace(self.settings, diagnostic=False))


class RegimeTests(unittest.TestCase):
    def test_hundreds_of_plans_have_valid_lengths_and_transitions(self):
        settings = SyntheticSettings(diagnostic=True)
        sequences = set()
        counts = set()
        for seed in range(300):
            plan = plan_regimes(random.Random(seed), settings, 0.01)
            sequences.add(tuple(r["kind"] for r in plan))
            counts.add(len(plan))
            self.assertEqual(sum(r["length"] for r in plan), 120)
            cursor = 0
            previous = None
            for regime in plan:
                kind = regime["kind"]
                self.assertEqual(regime["start"], cursor)
                self.assertGreaterEqual(regime["length"], settings.regimes.minimum_lengths[kind])
                self.assertLessEqual(regime["length"], settings.regimes.maximum_lengths[kind])
                if kind == "breakout":
                    self.assertEqual(previous, "consolidation")
                cursor = regime["end_exclusive"]
                previous = kind
        self.assertEqual(counts, {1, 2, 3})
        self.assertGreater(len(sequences), 6)

    def test_transition_weights_and_lengths_are_active(self):
        options = replace(RegimeSettings(), initial_weights=dict(
            uptrend=0.0, downtrend=0.0, consolidation=1.0, breakout=0.0),
            transitions={"uptrend": {}, "downtrend": {}, "consolidation": {"breakout": 1.0}, "breakout": {}},
            minimum_lengths=dict(uptrend=24, downtrend=24, consolidation=24, breakout=17),
            maximum_lengths=dict(uptrend=120, downtrend=120, consolidation=120, breakout=17))
        settings = SyntheticSettings(min_regimes=2, max_regimes=2, regimes=options)
        plan = plan_regimes(random.Random(3), settings, 0.01)
        self.assertEqual([(r["kind"], r["length"]) for r in plan], [("consolidation", 103), ("breakout", 17)])

    def test_invalid_and_infeasible_settings(self):
        for change in (dict(candles=100), dict(internal_steps=0), dict(min_regimes=0), dict(max_regimes=4),
                       dict(seed=True), dict(count=0), dict(count=2.1), dict(symbols=[]), dict(diagnostic="yes")):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(SyntheticSettings(), **change).validate()
        options = replace(RegimeSettings(), initial_weights=dict(
            uptrend=0.0, downtrend=0.0, consolidation=0.0, breakout=0.0))
        with self.assertRaises(ValueError):
            feasible_sequences(SyntheticSettings(regimes=options))
        options = replace(RegimeSettings(), transitions={k: {"breakout": 1} for k in
                            ("uptrend", "downtrend", "consolidation", "breakout")})
        with self.assertRaises(ValueError):
            options.validate()
        options = replace(RegimeSettings(), mean_reversion=[0.1, 10 ** 400])
        with self.assertRaises(ValueError):
            options.validate()


class CalibrationTests(unittest.TestCase):
    def test_statistics_known_values_and_wick_proportions(self):
        candles = sample_candles()
        stats = series_statistics(candles)
        returns = [math.log(float(b.close / a.close)) for a, b in zip(candles, candles[1:])]
        self.assertAlmostEqual(stats["log_returns"]["mean"], sum(returns) / 5)
        self.assertEqual(stats["log_returns"]["count"], 5)
        self.assertEqual(stats["upper_wick_fraction"]["mean"], 0.5)
        self.assertEqual(stats["lower_wick_fraction"]["mean"], 0.5)

    def test_no_range_fails_before_file_read(self):
        with self.assertRaises(ValueError):
            calibrate_csv(Path("does-not-exist.csv"), "BTCUSDT", allowed_start=None, allowed_end=None)

    def test_only_allowed_observations_affect_calibration(self):
        candles = sample_candles()
        start, end = candles[1].timestamp, candles[4].timestamp
        first = calibrate(candles, "BTCUSDT", allowed_start=start, allowed_end=end, source={"fixture": True})
        changed = list(candles)
        changed[0] = replace(changed[0], close=Decimal("1e20"))
        changed[-1] = replace(changed[-1], close=Decimal("1e30"))
        second = calibrate(changed, "BTCUSDT", allowed_start=start, allowed_end=end, source={"fixture": True})
        self.assertEqual(first, second)
        self.assertEqual(first["observations"], 4)
        self.assertEqual(first["status"], "unapproved")

    def test_gap_transition_is_skipped_without_interpolation(self):
        candles = sample_candles()
        candles = candles[:2] + candles[3:]
        stats = series_statistics(candles)
        expected = [math.log(102 / 100), math.log(103 / 104), math.log(106 / 103)]
        self.assertEqual(stats["skipped_noncontiguous_transitions"], 1)
        self.assertEqual(stats["log_returns"]["count"], 3)
        self.assertAlmostEqual(stats["log_returns"]["mean"], sum(expected) / 3)

    def test_csv_calibration_uses_explicit_subset_and_records_source(self):
        candles = sample_candles()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.csv"
            write_candles_csv(path, candles)
            profile = calibrate_csv(path, "BTCUSDT", allowed_start=candles[1].timestamp,
                                    allowed_end=candles[4].timestamp)
            self.assertEqual(profile["observations"], 4)
            self.assertEqual(profile["statistics"]["log_returns"]["count"], 3)
            self.assertEqual(profile["source"]["path"], str(path))
            self.assertEqual(len(profile["source"]["sha256"]), 64)

    def test_profile_write_failure_does_not_publish_partial_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profile.json"
            with patch('market_levels.data_processing.synthetic.io.profiles.write_json', side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    save_profile(path, sample_profile())
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_profile_roundtrip_and_approval_requires_training_bounds(self):
        profile = sample_profile()
        candles = sample_candles()
        approved = approve_profile(profile, training_start=candles[0].timestamp,
                                   training_end=candles[-1].timestamp, split_id="fixture-v1", reviewed_by="test")
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(profile["status"], "unapproved")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profile.json"
            save_profile(path, approved)
            self.assertEqual(load_profile(path, symbol="BTCUSDT"), approved)
            with self.assertRaises(FileExistsError):
                save_profile(path, approved)
            with self.assertRaises(ValueError):
                load_profile(path, symbol="ETHUSDT")
        with self.assertRaises(ValueError):
            approve_profile(profile, training_start=candles[1].timestamp,
                            training_end=candles[-1].timestamp, split_id="fixture", reviewed_by="test")

    def test_bad_periods_profiles_and_input_are_rejected(self):
        candles = sample_candles()
        for start, end in ((candles[-1].timestamp, candles[0].timestamp),
                           (candles[0].timestamp.replace(tzinfo=None), candles[-1].timestamp),
                           (candles[0].timestamp + timedelta(hours=1), candles[-1].timestamp)):
            with self.assertRaises(ValueError):
                calibrate(candles, "BTCUSDT", allowed_start=start, allowed_end=end, source={"fixture": 1})
        for mutate in (lambda p: p.update(version=99), lambda p: p.update(status="approved"),
                       lambda p: p["generator_parameters"].update(sigma_4h=math.nan),
                       lambda p: p["generator_parameters"].update(initial_price_range=[2, 1]),
                       lambda p: p.update(observations=400)):
            profile = sample_profile()
            mutate(profile)
            with self.assertRaises(ValueError):
                validate_profile(profile)


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.result = generate_example("BTCUSDT", 8, diagnostic_profile("BTCUSDT"), SyntheticSettings(diagnostic=True))

    def test_invalid_prices_times_continuity_and_metadata(self):
        result = self.result
        for change in (dict(open=Decimal("NaN")), dict(low=Decimal("0")), dict(high=Decimal("0.1")),
                       dict(timestamp=result.candles[0].timestamp.replace(tzinfo=None)), dict(source_archive="binance.zip")):
            candles = list(result.candles)
            candles[0] = replace(candles[0], **change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_synthetic(candles, result.metadata["regimes"], 8)
        for candles in (result.candles[:-1], result.candles[:2] + result.candles[3:],
                        [result.candles[0]] + result.candles, list(reversed(result.candles))):
            with self.assertRaises(ValueError):
                validate_synthetic(candles, result.metadata["regimes"], 8)
        regimes = deepcopy(result.metadata["regimes"])
        regimes[0]["length"] -= 1
        with self.assertRaises(ValueError):
            validate_synthetic(result.candles, regimes, 8)
        candles = list(result.candles)
        candle = candles[1]
        candles[1] = replace(candle, open=(candle.open + candle.close) / 2)
        with self.assertRaisesRegex(ValueError, "Nieciągłość"):
            validate_synthetic(candles, result.metadata["regimes"], 8)

    def test_csv_roundtrip_and_canonical_decimal_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "candles.csv"
            write_candles_csv(path, self.result.candles)
            self.assertEqual(read_candles_csv(path, source=self.result.candles[0].source_archive), self.result.candles)
        first = sample_candles()
        second = [replace(c, open=c.open.quantize(Decimal("0.000")), source_archive="other") for c in first]
        self.assertEqual(canonical_hash(first), canonical_hash(second))

    def test_csv_rejects_invalid_format(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.csv"
            for content in ("wrong,columns\n", "open_time_utc,open,high,low,close\n2024-01-01T00:00:00,1,2,1,2\n",
                            "open_time_utc,open,high,low,close\n2024-01-01T00:00:00+00:00,NaN,2,1,2\n"):
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_candles_csv(path, source="test")

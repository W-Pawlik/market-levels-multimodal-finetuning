"""Regresja v1 oraz matematyczne i deterministyczne kontrakty v2."""
from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
import platform
import random
import statistics
import unittest
from unittest.mock import patch

from market_levels.data_processing.synthetic.domain.profiles.v1 import diagnostic_profile, profile_hash
from market_levels.data_processing.synthetic.domain.profiles.validation import validate_generator_profile
from market_levels.data_processing.synthetic.domain.generation.v1 import generate_example
from market_levels.data_processing.synthetic.domain.generation.seeds import example_seed
from market_levels.data_processing.synthetic.domain.generation.v2 import generate_example_v2
from market_levels.data_processing.synthetic.domain.profiles.v2 import diagnostic_profile_v2
from market_levels.data_processing.synthetic.domain.profiles.validation import validate_profile_v2
from market_levels.data_processing.synthetic.config.generation import SyntheticSettings
from market_levels.data_processing.synthetic.config.regimes import RegimeSettings
from market_levels.data_processing.synthetic.domain.generation.processes import brownian_bridge, mixture_value, normal_mixture, stream_seed, volatility_multiplier, volatility_states
from market_levels.data_processing.synthetic.domain.parameters import V2Parameters, VARIANTS
from market_levels.data_processing.synthetic.domain.diagnostics import tail_diagnostics

from support.paths import PROJECT


class V1RegressionTests(unittest.TestCase):
    def test_original_candles_metadata_and_seed_algorithm(self):
        fixture = json.loads(((PROJECT / "tests") / "fixtures/synthetic_v1_regression.json").read_text())
        if platform.python_version() != fixture["python"] or platform.python_implementation() != "CPython":
            self.skipTest("Golden v1 potwierdzono na CPython " + fixture["python"])
        for symbol in ("BTCUSDT", "ETHUSDT"):
            result = generate_example(symbol, example_seed(20261103, symbol, 0), diagnostic_profile(symbol),
                                      SyntheticSettings(diagnostic=True))
            self.assertEqual(result.metadata["ohlc_sha256"], fixture["examples"][symbol]["ohlc"])
            self.assertEqual(profile_hash(result.metadata), fixture["examples"][symbol]["metadata"])
            self.assertNotIn("generator_version", result.metadata["configuration"])


class StochasticProcessTests(unittest.TestCase):
    def test_bridge_endpoints_steps_reproduction_and_midpoint_variance(self):
        path = brownian_bridge(random.Random(12), 3, 4, 1, 1)
        self.assertEqual((len(path), path[0], path[-1]), (13, 3, 4))
        self.assertEqual(path, brownian_bridge(random.Random(12), 3, 4, 1, 1))
        rng = random.Random(12345)
        midpoints = [brownian_bridge(rng, 0, 0, 1, 1)[6] for _ in range(6000)]
        # B_(1/2) ~ N(0, 1/4); tolerancja wielokrotnie większa od błędu Monte Carlo.
        self.assertAlmostEqual(statistics.mean(midpoints), 0, delta=0.04)
        self.assertAlmostEqual(statistics.variance(midpoints), 0.25, delta=0.025)
        with patch.object(random.Random, "gauss", return_value=0) as draws:
            self.assertEqual(brownian_bridge(random.Random(1), 0, 12, 1, 1), list(range(13)))
            self.assertEqual(draws.call_count, 12)

    def test_mixture_mean_variance_and_heavier_tails(self):
        rng, normal_rng = random.Random(431), random.Random(432)
        values = [normal_mixture(rng, 0.05, 3) for _ in range(100000)]
        normals = [normal_rng.gauss(0, 1) for _ in range(100000)]
        self.assertAlmostEqual(statistics.mean(values), 0, delta=0.02)
        self.assertAlmostEqual(statistics.variance(values), 1, delta=0.04)
        self.assertGreater(sum(abs(v)>3 for v in values), 2 * sum(abs(v)>3 for v in normals))
        self.assertEqual([normal_mixture(random.Random(4), .05, 3) for _ in range(2)],
                         [normal_mixture(random.Random(4), .05, 3) for _ in range(2)])
        self.assertEqual(mixture_value(2.5, .5, 0, 3), 2.5)

    def test_stationary_volatility_variance_normalization_and_memory(self):
        states = volatility_states(random.Random(12), 100000, 0, 0.4)
        multipliers = [volatility_multiplier(h, 0.4) for h in states]
        self.assertAlmostEqual(statistics.mean(m*m for m in multipliers), 1, delta=0.03)
        self.assertTrue(all(math.isfinite(m) and m>0 for m in multipliers))
        remembered = volatility_states(random.Random(13), 20000, .95, .4)
        self.assertEqual(remembered, volatility_states(random.Random(13), 20000, .95, .4))
        covariance = statistics.mean(a*b for a,b in zip(remembered,remembered[1:]))
        self.assertAlmostEqual(covariance/statistics.mean(h*h for h in remembered), .95, delta=.02)
        # Stan startowy pochodzi z rozkładu stacjonarnego, nie zawsze z zera.
        self.assertNotEqual(remembered[0], 0)
        self.assertEqual(volatility_states(random.Random(1), 3, .9, 0), [0, 0, 0])

    def test_bad_parameters_and_numerical_overflow_fail(self):
        for p,k in ((-1,3), (1,3), (.1,1), (math.nan,3), (.1,math.inf)):
            with self.assertRaises(ValueError):
                normal_mixture(random.Random(1),p,k)
        for phi,sd in ((1,.3), (-.1,.3), (.9,-1), (math.inf,.3)):
            with self.assertRaises(ValueError):
                volatility_states(random.Random(1),2,phi,sd)
        for field,value in (("bridge_gamma",0),("tail_probability",.5),("tail_scale",-1),
                            ("volatility_phi",1),("volatility_stationary_std",2)):
            with self.assertRaises(ValueError):
                replace(V2Parameters(),**{field:value}).validate()
        with self.assertRaises(ValueError):
            volatility_multiplier(1000,.3)
        with self.assertRaises(ValueError):
            brownian_bridge(random.Random(1),0,0,0,1)

    def test_tail_metric_definition_and_undefined_kurtosis(self):
        result = tail_diagnostics([-1,-1,1,1])
        self.assertEqual(result["pearson_kurtosis"],1)
        self.assertEqual(result["exceedance_abs_2sigma"],0)
        self.assertIsNone(tail_diagnostics([0,0])["pearson_kurtosis"])


class V2GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.settings = SyntheticSettings(generator_version="v2", diagnostic=True)
        self.profile = diagnostic_profile_v2("BTCUSDT",self.settings)

    def test_all_variants_ohlc_metadata_reproduction_and_independence(self):
        hashes = set()
        for variant in VARIANTS:
            settings=replace(self.settings,v2_variant=variant)
            result=generate_example_v2("BTCUSDT",55,self.profile,settings)
            self.assertEqual(result,generate_example_v2("BTCUSDT",55,self.profile,settings))
            self.assertEqual(len(result.candles),120)
            self.assertEqual(result.metadata["total_internal_steps"],1440)
            self.assertTrue(result.metadata["validation"]["valid"])
            self.assertEqual(result.metadata["generator_version"],"2.0.0")
            self.assertEqual(result.metadata["profile_version"],2)
            self.assertEqual(len(set(result.metadata["rng_stream_seeds"].values())),6)
            self.assertEqual(result.metadata["configured_parameters"],self.profile["v2_parameters"])
            self.assertEqual(result.metadata['effective_parameters']['bridge_gamma'],
                             self.profile['v2_parameters']['bridge_gamma'] if variant in ('bridge','full','bridge_volatility') else 1)
            for a,b in zip(result.candles,result.candles[1:]):
                self.assertEqual(a.close,b.open)
            for candle in result.candles:
                self.assertGreater(candle.low,0)
                self.assertGreaterEqual(candle.high,max(candle.open,candle.close))
                self.assertLessEqual(candle.low,min(candle.open,candle.close))
            hashes.add(result.metadata["ohlc_sha256"])
        self.assertEqual(len(hashes),len(VARIANTS))

    def test_gamma_and_bridge_switch_do_not_change_closes_or_regime_planning(self):
        settings=replace(self.settings,v2_variant="bridge")
        changed=deepcopy(self.profile)
        changed["v2_parameters"]["bridge_gamma"]=2.2
        first=generate_example_v2("BTCUSDT",8,self.profile,settings)
        second=generate_example_v2("BTCUSDT",8,changed,settings)
        base=generate_example_v2("BTCUSDT",8,self.profile,replace(settings,v2_variant="base"))
        self.assertEqual([c.close for c in first.candles],[c.close for c in second.candles])
        self.assertEqual([c.close for c in first.candles],[c.close for c in base.candles])
        self.assertNotEqual([c.high for c in first.candles],[c.high for c in second.candles])
        self.assertEqual(first.metadata["regimes"],second.metadata["regimes"])
        self.assertEqual(first.metadata["rng_stream_seeds"],base.metadata["rng_stream_seeds"])

    def test_continuous_volatility_state_across_regimes(self):
        settings=replace(self.settings,min_regimes=2,max_regimes=3)
        profile=diagnostic_profile_v2("BTCUSDT",settings)
        result=generate_example_v2("BTCUSDT",6,profile,settings)
        self.assertGreaterEqual(len(result.metadata['regimes']),2)
        expected=volatility_states(random.Random(stream_seed(6,"volatility")),120,.95,.35)
        self.assertEqual([row["h"] for row in result.metadata["volatility_trace"]],expected)
        # Test rozkładu niezależnie od przypadkowej liczby faz w tym seedzie.
        self.assertEqual(len(result.metadata["volatility_trace"]),120)

    def test_profile_versions_invalid_metadata_and_unapproved_candidate(self):
        with self.assertRaises(ValueError):
            validate_generator_profile(diagnostic_profile("BTCUSDT"),generator_version="v2")
        with self.assertRaises(ValueError):
            generate_example("BTCUSDT",1,self.profile,SyntheticSettings(diagnostic=True))
        with self.assertRaises(ValueError):
            generate_example_v2("BTCUSDT",1,self.profile,replace(self.settings,diagnostic=False))
        for mutate in (lambda p:p.update(generator_version="1.0.0"),
                       lambda p:p["v2_parameters"].update(tail_scale=math.nan),
                       lambda p:p.update(parameter_provenance={}),lambda p:p.update(status="approved")):
            profile=deepcopy(self.profile);mutate(profile)
            with self.assertRaises(ValueError):
                validate_profile_v2(profile)

    def test_numerical_failure_does_not_clip_path(self):
        with patch('market_levels.data_processing.synthetic.domain.generation.v2.brownian_bridge',return_value=[1000.0]*13):
            with self.assertRaises(ValueError):
                generate_example_v2("BTCUSDT",1,self.profile,self.settings)

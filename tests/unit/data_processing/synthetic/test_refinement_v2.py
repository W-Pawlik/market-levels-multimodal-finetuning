"""Kontrolowane błędy celu i regresja strumieni historycznych wariantów."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import platform
import unittest
from unittest.mock import patch

from market_levels.data_processing.synthetic.domain.profiles.v1 import profile_hash
from market_levels.data_processing.synthetic.domain.generation.v2 import generate_example_v2
from market_levels.data_processing.synthetic.domain.profiles.v2 import diagnostic_profile_v2
from market_levels.data_processing.synthetic.config.refinement import METRIC_KINDS, RefinementSettings
from market_levels.data_processing.synthetic.domain.calibration.objectives import refinement_objective, _trial_score
from market_levels.data_processing.synthetic.domain.profiles.validation import _objective_results_match
from market_levels.data_processing.synthetic.config.generation import SyntheticSettings
from market_levels.data_processing.synthetic.domain.parameters import mechanisms

from support.paths import PROJECT


class RefinementObjectiveTests(unittest.TestCase):
    def setUp(self):
        self.policy = RefinementSettings()
        self.reference = dict.fromkeys(METRIC_KINDS, .2)

    def test_exact_fit_priority_weights_and_control_guard(self):
        self.assertEqual(refinement_objective(self.reference, self.reference, self.policy)["loss"], 0)
        observed = dict(self.reference, abs_ac1=.3)
        result = refinement_objective(observed, self.reference, self.policy, baseline=self.reference)
        self.assertAlmostEqual(result['loss'], 12/15)
        self.assertTrue(result['tolerance_exceeded']['abs_ac1'])
        self.assertEqual(result['control_guard_terms']['abs_q99'], 0)
        control = dict(self.reference, abs_q99=.29)
        guarded = refinement_objective(control, self.reference, self.policy, baseline=self.reference)
        self.assertAlmostEqual(guarded['control_guard_terms']['abs_q99'], 4)
        self.assertGreater(guarded['loss'], refinement_objective(control, self.reference, self.policy)['loss'])

    def test_mean_worst_seed_blend_and_undefined_rejection(self):
        bad = dict(self.reference, abs_ac1=.3)
        score, terms = _trial_score([self.reference, self.reference, bad], self.reference, self.policy,
                                    [self.reference]*3)
        self.assertAlmostEqual(score, .75*terms[2]['loss']/3+.25*terms[2]['loss'])
        for value in (None, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                refinement_objective(dict(self.reference, abs_ac1=value), self.reference, self.policy)

    def test_search_is_bounded_and_seeds_are_separate(self):
        self.policy.validate()
        for changes in ({'simulation_seeds':[1,2]}, {'simulation_seeds':[1,1,2]},
                        {'diagnostic_seeds':[73001,4]}, {'volatility_phi':[1]},
                        {'volatility_stationary_std':[-.1]}, {'weights':{}}, {'worst_seed_weight':2}):
            with self.assertRaises(ValueError):
                replace(self.policy, **changes).validate()


class ObjectiveAuditPortabilityTests(unittest.TestCase):
    def test_reported_last_bit_difference_is_accepted(self):
        stored = [{'control_guard_terms': {'abs_q99': 0.0016521334745063683}}]
        computed = [{'control_guard_terms': {'abs_q99': 0.0016521334745063685}}]
        self.assertNotEqual(stored, computed)
        self.assertTrue(_objective_results_match(stored, computed))
        self.assertTrue(_objective_results_match(0.0, 1e-19))

    def test_material_changes_and_nonfinite_results_are_rejected(self):
        for a, b in ((.0016521334745063683, .00165214), (0.0, 1e-12), (1.0, 1.00000001),
                     (float('nan'), float('nan')), (float('inf'), float('inf'))):
            with self.subTest(stored=a, computed=b):
                self.assertFalse(_objective_results_match(a, b))

    def test_structure_field_names_types_flags_and_order_are_exact(self):
        expected = [{'loss': 1.0, 'flag': True, 'guard': 0, 'name': 'abs_q99'}]
        for changed in ([], expected*2, tuple(expected), [{'loss': 1.0}],
                        [dict(expected[0], extra=0)], [dict(expected[0], loss=1)],
                        [dict(expected[0], loss='1.0')], [dict(expected[0], flag=1)],
                        [dict(expected[0], guard=0.0)], [dict(expected[0], name='abs_q95')]):
            with self.subTest(changed=changed):
                self.assertFalse(_objective_results_match(changed, expected))
        self.assertFalse(_objective_results_match([1.0, 2.0], [2.0, 1.0]))


class RefinementMechanismsTests(unittest.TestCase):
    def test_bridge_volatility_uses_bridge_and_ar_without_mixture(self):
        self.assertEqual(mechanisms('bridge_volatility'), {'bridge':True,'tails':False,'volatility':True})
        settings = SyntheticSettings(generator_version='v2', diagnostic=True, v2_variant='bridge_volatility')
        profile = diagnostic_profile_v2('BTCUSDT', settings)
        original = generate_example_v2('BTCUSDT',55,profile,settings)
        changed = deepcopy(profile)
        changed['v2_parameters'].update(tail_probability=.2,tail_scale=6)
        with patch('market_levels.data_processing.synthetic.domain.generation.v2.mixture_value', side_effect=AssertionError('mixture')):
            again = generate_example_v2('BTCUSDT',55,changed,settings)
        self.assertEqual(original.metadata['ohlc_sha256'],again.metadata['ohlc_sha256'])
        self.assertEqual(original,generate_example_v2('BTCUSDT',55,profile,settings))
        for name, value in (('bridge_gamma',.4), ('volatility_phi',.5), ('volatility_stationary_std',.1)):
            changed = deepcopy(profile); changed['v2_parameters'][name] = value
            self.assertNotEqual(original.metadata['ohlc_sha256'],
                generate_example_v2('BTCUSDT',55,changed,settings).metadata['ohlc_sha256'])

    def test_five_original_v2_variants_match_prechange_golden(self):
        fixture = json.loads(((PROJECT / "tests")/'fixtures/synthetic_v2_regression.json').read_text())
        if platform.python_version()!=fixture['python'] or platform.python_implementation()!='CPython':
            self.skipTest('Golden CPython '+fixture['python'])
        settings = SyntheticSettings(generator_version='v2',diagnostic=True)
        for symbol, variants in fixture['examples'].items():
            profile = diagnostic_profile_v2(symbol, settings)
            for variant, expected in variants.items():
                result = generate_example_v2(symbol,fixture['seed'],profile,replace(settings,v2_variant=variant))
                self.assertEqual(result.metadata['ohlc_sha256'],expected['ohlc'])
                self.assertEqual(profile_hash(result.metadata),expected['metadata'])

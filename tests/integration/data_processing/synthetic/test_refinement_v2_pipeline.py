"""Mały offline refinement -> profil -> partie -> raport czterech grup."""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from market_levels.core.ohlc.model import UTC
from market_levels.data_processing.io.candles import write_candles_csv
from market_levels.data_processing.synthetic.workflows.calibration import calibrate_csv
from market_levels.data_processing.synthetic.io.profiles import save_profile, load_profile
from market_levels.data_processing.synthetic.workflows.calibration import calibrate_v2_csv
from market_levels.data_processing.synthetic.domain.profiles.validation import validate_profile_v2
from market_levels.data_processing.synthetic.config.refinement import FROZEN_FIELDS, RefinementSettings
from market_levels.data_processing.synthetic.workflows.refinement import refine_v2_volatility
from market_levels.data_processing.synthetic.config.generation import SyntheticSettings
from market_levels.data_processing.io.chronology import load_chronological_split
from market_levels.data_processing.synthetic.workflows.generation import run
from market_levels.data_processing.synthetic.io.profiles import prepare_profiles
from market_levels.data_processing.synthetic.workflows.comparison import build_comparison, save_comparison
from market_levels.data_processing.synthetic.workflows.summary import build_variant_summary
from market_levels.data_processing.synthetic.reporting.variants import variant_summary_markdown
from support.calibration import small_search
from support.comparison import CONFIG, real_fixture


class RefinementPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.csv = cls.root/'real.csv'
        write_candles_csv(cls.csv,real_fixture())
        cls.split = load_chronological_split(CONFIG)
        cls.start,cls.end = cls.split.periods['train']
        cls.settings = SyntheticSettings(generator_version='v2',diagnostic=True,count=2,symbols=('BTCUSDT',))
        cls.search = RefinementSettings(volatility_phi=[.7,.9],volatility_stationary_std=[.2,.4],
            simulation_seeds=[101,102,103],diagnostic_seeds=[500,501],examples_per_seed=1)
        cls.original = calibrate_v2_csv(cls.csv,'BTCUSDT',start=cls.start,end=cls.end,split=cls.split,
            settings=cls.settings,search=small_search())
        cls.source = cls.root/'original.json'
        save_profile(cls.source,cls.original)
        cls.source_bytes = cls.source.read_bytes()
        cls.refined = {v: cls.fit(v) for v in ('full','bridge_volatility')}

    @classmethod
    def fit(cls, variant='full', **overrides):
        args = dict(symbol='BTCUSDT',variant=variant,start=cls.start,end=cls.end,split=cls.split,
                    settings=cls.settings,search=cls.search)
        args.update(overrides)
        return refine_v2_volatility(cls.csv,cls.source,**args)

    def test_reproduction_frozen_fields_baseline_and_roundtrip(self):
        profile = self.refined['full']
        self.assertEqual(profile,self.fit())
        for variant, result in self.refined.items():
            for field in FROZEN_FIELDS:
                self.assertEqual(result[field],self.original[field])
            for field in ('bridge_gamma','tail_probability','tail_scale'):
                self.assertEqual(result['v2_parameters'][field],self.original['v2_parameters'][field])
            audit = result['calibration']
            self.assertEqual(audit['variant'],variant)
            self.assertEqual(audit['source_profile_file_sha256'],hashlib.sha256(self.source_bytes).hexdigest())
            self.assertEqual(audit['trials'][0]['parameters'],self.original['v2_parameters'])
            self.assertLessEqual(audit['selected_loss'],audit['baseline_loss'])
            path = self.root/(variant+'-roundtrip.json')
            save_profile(path,result)
            self.assertEqual(load_profile(path,symbol='BTCUSDT'),result)
            with self.assertRaises(FileExistsError): save_profile(path,result)
        self.assertEqual(self.source.read_bytes(),self.source_bytes)

    def test_reject_tampered_audit_frozen_values_and_incomplete_evaluation(self):
        mutations = [lambda p:p['v2_parameters'].update(bridge_gamma=.3),
            lambda p:p['generator_parameters'].update(sigma_4h=.003),
            lambda p:p['calibration'].update(source_profile_sha256='0'*64),
            lambda p:p['calibration'].update(selected_loss=123),
            lambda p:p['calibration']['trials'][0].update(loss=456),
            lambda p:p['calibration'].update(phase='evaluation'),
            lambda p:p['calibration']['reference_selection']['windows'][1].update(
                csv_record_indices=p['calibration']['reference_selection']['windows'][0]['csv_record_indices']),
            lambda p:p['calibration'].update(criterion='made up')]
        for mutate in mutations:
            bad = deepcopy(self.refined['full']); mutate(bad)
            with self.assertRaises(ValueError): validate_profile_v2(bad)
        evaluation = deepcopy(self.refined['full']);evaluation['calibration']['phase']='evaluation'
        with self.assertRaises(ValueError): save_profile(self.root/'incomplete.json',evaluation)
        with self.assertRaises(ValueError):
            prepare_profiles(replace(self.settings,v2_variant='bridge_volatility',
                profiles={'BTCUSDT':str(self._save('bound',self.refined['full']))}))

    def test_provenance_future_period_budget_and_recursive_source_rejected(self):
        with self.assertRaises(ValueError): self.fit(expected_source_sha256='0'*64)
        with self.assertRaises(ValueError): self.fit(end=datetime(2024,1,1,tzinfo=UTC))
        with patch('market_levels.data_processing.synthetic.workflows.refinement.generate_example_v2',side_effect=AssertionError('simulation')):
            with self.assertRaisesRegex(ValueError,'budżet'):
                self.fit(search=replace(self.search,max_candidates=1))
        changed = self.root/'other.csv';write_candles_csv(changed,real_fixture(851))
        with self.assertRaisesRegex(ValueError,'SHA-256'):
            refine_v2_volatility(changed,self.source,symbol='BTCUSDT',variant='full',start=self.start,
                end=self.end,split=self.split,settings=self.settings,search=self.search)
        refined_path = self._save('recursive',self.refined['full'])
        with self.assertRaisesRegex(ValueError,'oryginalnego'):
            refine_v2_volatility(self.csv,refined_path,symbol='BTCUSDT',variant='full',start=self.start,
                end=self.end,split=self.split,settings=self.settings,search=self.search)

    def test_validator_accepts_roundoff_in_nested_objective_without_rewriting(self):
        profile = deepcopy(self.refined['full'])
        terms = profile['calibration']['trials'][0]['seed_objectives'][0]
        original = terms['normalized_absolute_errors']['abs_ac1']
        terms['normalized_absolute_errors']['abs_ac1'] = math.nextafter(original, math.inf)
        self.assertNotEqual(terms['normalized_absolute_errors']['abs_ac1'], original)
        before = deepcopy(profile)
        validate_profile_v2(profile)
        self.assertEqual(profile, before)

    def test_validator_rejects_material_objective_changes_and_schema_changes(self):
        for mutate in (
            lambda t: t['normalized_absolute_errors'].__setitem__('abs_ac1', 123.0),
            lambda t: t['control_guard_terms'].__setitem__('abs_q99', 1e-6),
            lambda t: t.__setitem__('extra', 0.0),
            lambda t: t.pop('tolerance_exceeded'),
            lambda t: t.__setitem__('loss', str(t['loss'])),
            lambda t: t['tolerance_exceeded'].__setitem__('abs_ac1', int(t['tolerance_exceeded']['abs_ac1']))):
            profile = deepcopy(self.refined['full'])
            mutate(profile['calibration']['trials'][0]['seed_objectives'][0])
            with self.assertRaisesRegex(ValueError, 'wynik funkcji celu'):
                validate_profile_v2(profile)
        profile = deepcopy(self.refined['full'])
        profile['v2_parameters']['bridge_gamma'] = math.nextafter(profile['v2_parameters']['bridge_gamma'], math.inf)
        with self.assertRaises(ValueError): validate_profile_v2(profile)

    def _save(self, name, profile):
        path = self.root/(name+'.json');save_profile(path,profile);return path

    def reports(self, name, second_seed=False):
        old = calibrate_csv(self.csv,'BTCUSDT',allowed_start=self.start,allowed_end=self.end)
        profiles = [('v1','full',old),('v2','full',self.original)]
        profiles += [('v2',v,p) for v,p in self.refined.items()]
        paths = []
        for index,(version,variant,profile) in enumerate(profiles):
            path = self._save(f'{name}-{index}',profile)
            for seed in ([500,501] if second_seed else [500]):
                manifest = run(replace(self.settings,generator_version=version,v2_variant=variant,
                    seed=seed,profiles={'BTCUSDT':str(path)},output=self.root/f'{name}-{index}-{seed}'))/'manifest.json'
                report = build_comparison(symbol='BTCUSDT',real_csv=self.csv,synthetic_manifest=manifest,
                    start=self.start,end=self.end,count=2,selection_seed=13,split=self.split)
                paths.append(save_comparison(self.root/'reports',report)/'BTCUSDT_comparison.json')
        return paths

    def test_small_end_to_end_four_groups_metrics_and_paired_seeds(self):
        paths = self.reports('e2e',second_seed=True)
        summary = build_variant_summary(paths,symbol='BTCUSDT')
        self.assertEqual(set(summary['variants']),{'V1','V2-full-original','V2-full-refined','V2-bridge_volatility-refined'})
        self.assertEqual(summary['variants']['V2-full-refined']['run_count'],2)
        review = summary['refinement_review']
        self.assertEqual(len(review['mixture_ablation']),9)
        for group in review['groups'].values():
            self.assertEqual(sum(group['metric_counts'].values()),9)
            self.assertEqual(sum(group['priority_metric_counts'].values()),3)
        self.assertIn('V2-full-original',variant_summary_markdown(summary))
        self.assertGreater(summary['variants']['V2-full-refined']['metrics']['return_std']['std_between_seeds'],0)
        with self.assertRaisesRegex(ValueError,'seedów'):
            build_variant_summary(paths[:-1],symbol='BTCUSDT')
        with self.assertRaisesRegex(ValueError,'wymaga'):
            build_variant_summary(paths[:-2],symbol='BTCUSDT')
        # Prawidłowy hash raportu nie pozwala mieszać profili w jednej grupie.
        changed = json.loads(paths[5].read_text(encoding='utf-8'))
        p = changed['synthetic_source']['profile'];p['calibration']['source_profile_path']+='-other'
        from market_levels.data_processing.synthetic.domain.profiles.v1 import profile_hash
        changed['synthetic_source']['profile_sha256'] = profile_hash(p)
        changed.pop('comparison_id')
        changed['comparison_id'] = hashlib.sha256(json.dumps(changed,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()[:24]
        other = self.root/'mixed.json';other.write_text(json.dumps(changed),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'samego profilu'):
            build_variant_summary(paths[:5]+[other]+paths[6:],symbol='BTCUSDT')

    def test_cli_small_calibration_output_guard_and_dry_run(self):
        config = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
        config['volatility_refinement_v1'] = asdict(self.search)
        path = self.root/'config.json';path.write_text(json.dumps(config),encoding='utf-8')
        output = self.root/'cli-profile.json'
        args = [sys.executable,'-m','market_levels.cli.refine_v2_volatility','--config',str(path),
            '--symbol','BTCUSDT','--input',str(self.csv),'--source-profile',str(self.source),
            '--variant','bridge_volatility','--start',self.start.isoformat(),'--end',self.end.isoformat(),
            '--output',str(output)]
        result = subprocess.run(args+['--dry-run'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(output.exists())
        result = subprocess.run(args,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(load_profile(output,symbol='BTCUSDT'),self.refined['bridge_volatility'])
        result = subprocess.run(args,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)

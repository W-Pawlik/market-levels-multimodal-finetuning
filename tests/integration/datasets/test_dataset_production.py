"""Offline production contracts on small artificial, explicitly calibrated fixtures."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_levels.core.ohlc.model import Candle, UTC, CANDLE_DELTA
from market_levels.data_processing.io.candles import write_candles_csv
from market_levels.shared.json_io import write_json
from market_levels.data_processing.synthetic.io.profiles import save_profile, load_profile
from market_levels.data_processing.synthetic.domain.profiles.v1 import profile_hash
from market_levels.data_processing.synthetic.workflows.calibration import calibrate_v2_csv
from market_levels.data_processing.synthetic.domain.profiles.validation import validate_profile_v2
from market_levels.data_processing.synthetic.domain.profiles.v2 import diagnostic_profile_v2
from market_levels.data_processing.synthetic.config.refinement import RefinementSettings
from market_levels.data_processing.synthetic.workflows.refinement import refine_v2_volatility
from market_levels.data_processing.synthetic.config.generation import SyntheticSettings
from market_levels.data_processing.io.chronology import load_chronological_split
from market_levels.data_processing.synthetic.io.profiles import prepare_profiles
from market_levels.datasets.workflows.approval import approve_refined
from market_levels.datasets.workflows.planning import publish_plan
from market_levels.shared.manifests import seal, verify_files
from market_levels.datasets.config import SYMBOLS
from market_levels.datasets.workflows.planning import build_plan
from market_levels.datasets.workflows.production import build_dataset
from market_levels.datasets.workflows.verification import verify_dataset
from support.calibration import small_search
from support.comparison import real_fixture, CONFIG


def silent(*args, **kwargs):
    pass


class DatasetProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='ds-prod-fixture-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.split = load_chronological_split(CONFIG)
        cls.start, cls.end = cls.split.periods['train']
        cls.paths, cls.profiles, cls.approved = {}, {}, {}
        cls.settings = SyntheticSettings(generator_version='v2', diagnostic=True)
        for k, symbol in enumerate(SYMBOLS):
            candles = [replace(c, open=c.open+1000*k, high=c.high+1000*k,
                               low=c.low+1000*k, close=c.close+1000*k) for c in real_fixture()]
            for year in (2024, 2025):
                for i in range(120):
                    p = Decimal(2000+year+k*10000+i)
                    candles.append(Candle(datetime(year, 1, 1, tzinfo=UTC)+i*CANDLE_DELTA, p, p+2, p-1, p+1, 'fixture'))
            path = cls.root/f'{symbol}_4h_fixture.csv'
            cls.paths[symbol] = path
            write_candles_csv(path, candles)
            base = calibrate_v2_csv(path, symbol, start=cls.start, end=cls.end, split=cls.split,
                                    settings=cls.settings, search=small_search())
            base_path = cls.root/f'{symbol}_base.json'
            save_profile(base_path, base)
            search = RefinementSettings(volatility_phi=[.7], volatility_stationary_std=[.4],
                simulation_seeds=[101,102,103], diagnostic_seeds=[500,501], examples_per_seed=1)
            refined = refine_v2_volatility(path, base_path, symbol=symbol, variant='full',
                start=cls.start, end=cls.end, split=cls.split, settings=cls.settings, search=search)
            cls.profiles[symbol] = refined
            cls.approved[symbol] = approve_refined(refined, cls.split, decision_date='2026-11-07', original_file_sha256='0'*64)

    def setUp(self):
        self.temp_case = tempfile.TemporaryDirectory(prefix='ds-prod-case-')
        self.addCleanup(self.temp_case.cleanup)
        self.case = Path(self.temp_case.name)
        self.config = self.case/'experiment.json'
        self.doc = json.loads(CONFIG.read_text(encoding='utf-8'))
        for split, groups in self.doc['dataset_build']['targets'].items():
            for source, counts in groups.items():
                counts.update({s: (1 if source == 'real' or split == 'train' else 0) for s in SYMBOLS})
        self.doc['dataset_build']['synthetic_history_root'] = str(self.case/'history')
        (self.case/'history').mkdir()
        for symbol in SYMBOLS:
            path = self.case/f'{symbol}.json'
            save_profile(path, self.approved[symbol])
            self.doc['dataset_build']['profiles'][symbol] = str(path)
        write_json(self.config, self.doc)
        self.preflight = Path('results/diagnostics')/('pre-'+self.case.name)
        self.output = Path('data/datasets')/self.case.name
        self.addCleanup(self.cleanup)

    def cleanup(self):
        import shutil
        for p in (self.preflight, self.output):
            if p.exists():
                shutil.rmtree(p)

    def publish(self):
        plan = build_plan(self.config, self.paths)
        publish_plan(plan, self.preflight)
        return plan

    def build(self):
        self.publish()
        return build_dataset(self.config, self.preflight, self.output, progress=silent)

    def test_approval_preserves_every_field_and_historical_audit(self):
        for symbol in SYMBOLS:
            old, new = self.profiles[symbol], self.approved[symbol]
            self.assertEqual(old['status'], 'unapproved')
            self.assertEqual(new['status'], 'approved')
            self.assertEqual(new['approval']['reviewed_by'], 'autor pracy')
            self.assertEqual(new['approval']['split_id'], 'chronological_v1')
            self.assertNotEqual(profile_hash(old), profile_hash(new))
            self.assertEqual({k:v for k,v in new.items() if k not in ('status','approval')},
                             {k:v for k,v in old.items() if k not in ('status','approval')})
            validate_profile_v2(new, symbol=symbol)

    def test_missing_approval_mismatched_split_and_changed_math_rejected(self):
        for mutation in (lambda p: p.pop('approval'), lambda p: p['approval'].update(split_id='other'),
                         lambda p: p['approval'].update(training_end='2026-01-01T00:00:00+00:00'),
                         lambda p: p['v2_parameters'].update(bridge_gamma=999),
                         lambda p: p['calibration'].update(selected_loss=999)):
            changed = deepcopy(self.approved['BTCUSDT'])
            mutation(changed)
            with self.assertRaises(ValueError):
                validate_profile_v2(changed)

    def test_diagnostic_and_wrong_variant_cannot_be_approved(self):
        diagnostic = diagnostic_profile_v2('BTCUSDT', self.settings)
        with self.assertRaises(ValueError):
            approve_refined(diagnostic, self.split, decision_date='2026-11-07', original_file_sha256='0'*64)
        changed = deepcopy(self.profiles['BTCUSDT'])
        changed['calibration']['variant'] = 'bridge_volatility'
        with self.assertRaises(ValueError):
            approve_refined(changed, self.split, decision_date='2026-11-07', original_file_sha256='0'*64)

    def test_unapproved_production_gate_still_blocks(self):
        path = self.case/'unapproved.json'
        save_profile(path, self.profiles['BTCUSDT'])
        with self.assertRaisesRegex(ValueError, 'niezatwierdzony'):
            prepare_profiles(replace(self.settings, diagnostic=False, symbols=('BTCUSDT',), profiles={'BTCUSDT': str(path)}))

    def test_full_production_replay_exact_counts_isolated_splits_and_repeatable_plan(self):
        plan = self.publish()
        self.assertEqual(plan, build_plan(self.config, self.paths))
        self.assertEqual(plan['totals']['total'], 8)
        build_dataset(self.config, self.preflight, self.output, progress=silent)
        report = verify_dataset(self.output, check_sources=True, progress=silent)
        self.assertEqual(report['split_counts'], {'train': 4, 'validation': 2, 'test': 2})
        self.assertEqual(report['synthetic_regenerated'], 2)
        self.assertEqual(report['renderer_differences'], [])
        for split in ('train','validation','test'):
            rows = [json.loads(x) for x in (self.output/f'splits/{split}.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertTrue(all(r['split'] == split for r in rows))
        with self.assertRaises(FileExistsError):
            build_dataset(self.config, self.preflight, self.output, progress=silent)

    def test_outdated_plan_fails_before_generation(self):
        self.publish()
        self.doc['dataset_build']['selection_seed'] += 1
        write_json(self.config, self.doc)
        with patch('market_levels.datasets.workflows.production.generate_example', side_effect=AssertionError('generation forbidden')):
            with self.assertRaisesRegex(ValueError, 'zmieniło'):
                build_dataset(self.config, self.preflight, self.output, progress=silent)
        self.assertFalse(self.output.exists())

    def test_render_failure_never_publishes(self):
        self.publish()
        with patch('market_levels.datasets.workflows.production.render_window', side_effect=RuntimeError('render failed')):
            with self.assertRaises(RuntimeError):
                build_dataset(self.config, self.preflight, self.output, progress=silent)
        self.assertFalse(self.output.exists())

    def test_rehashed_jsonl_tampering_rejected(self):
        self.build()
        path = self.output/'splits/test.jsonl'
        path.write_text(path.read_text(encoding='utf-8').replace('"test"','"train"'), encoding='utf-8')
        manifest = json.loads((self.output/'manifest.json').read_text())
        (self.output/'manifest.json').unlink()
        (self.output/'manifest.sha256').unlink()
        manifest.pop('files')
        seal(self.output, manifest)
        with self.assertRaisesRegex(ValueError, 'JSONL'):
            verify_dataset(self.output, progress=silent)

    def test_raw_image_tampering_rejected(self):
        self.build()
        entry = verify_files(self.output)['entries'][0]
        path = self.output/entry['image']
        path.write_bytes(path.read_bytes()+b'tamper')
        with self.assertRaisesRegex(ValueError, 'hash'):
            verify_dataset(self.output, progress=silent)

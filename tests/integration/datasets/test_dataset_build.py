"""Offline fixtures; no downloader, calibration or production generation."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_levels.shared.configuration import read_configuration
from market_levels.charts.io.rendering import render_window
from market_levels.core.ohlc.model import Candle, CANDLE_DELTA, UTC
from market_levels.data_processing.io.candles import write_candles_csv
from market_levels.shared.json_io import write_json
from market_levels.data_processing.synthetic.domain.profiles.v2 import diagnostic_profile_v2, regime_configuration
from market_levels.datasets.workflows.smoke import run_smoke
from market_levels.datasets.workflows.verification import verify_smoke
from market_levels.shared.manifests import verify_files, seal
from market_levels.datasets.workflows.planning import publish_plan
from market_levels.datasets.workflows.planning import build_plan, inspect_synthetic, require_production_ready
from market_levels.datasets.config import synthetic_settings, SYMBOLS
from market_levels.shared.integrity import SourceLedger
from market_levels.cli.build_dataset import main

from support.paths import PROJECT

CONFIG = PROJECT/'configs/experiment.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reseal(root):
    manifest = json.loads((root/'manifest.json').read_text())
    (root/'manifest.json').unlink()
    (root/'manifest.sha256').unlink()
    manifest.pop('files')
    seal(root, manifest)


class DatasetSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='ds-fixture-')
        cls.root = Path(cls.temp.name)
        cls.pilot = cls.root/'pilot'
        cls.pilot.mkdir()
        records = []
        for i in range(32):
            symbol = SYMBOLS[i//16]
            source = 'real' if i % 16 < 8 else 'synthetic'
            start = datetime(2020 if source == 'real' else 2000, 1, 1, tzinfo=UTC)
            cs = []
            for j in range(120):
                price = Decimal(100+i*10)+Decimal(j % 11)/10
                cs.append(Candle(start+j*CANDLE_DELTA, price, price+2, price-1, price+1, 'fixture'))
            write_candles_csv(cls.pilot/f'{i:03d}.csv', cs)
            rendering = render_window(cs, cls.pilot/f'{i:03d}.png')
            record = dict(id=f'{symbol}_{i:03d}', symbol=symbol, source=source,
                          png=f'{i:03d}.png', window_csv=f'{i:03d}.csv',
                          window_csv_sha256=sha(cls.pilot/f'{i:03d}.csv'),
                          start_utc=cs[0].timestamp.isoformat(), end_utc=cs[-1].timestamp.isoformat(),
                          seed=i if source == 'synthetic' else None,
                          master_seed=123 if source == 'synthetic' else None,
                          profile_sha256='fixture-only' if source == 'synthetic' else None,
                          variant='V2-full-refined' if source == 'synthetic' else None, **rendering)
            write_json(cls.pilot/f'{i:03d}.json', record)
            records.append(record)
        write_json(cls.pilot/'manifest.json', {'actual_count': 32, 'images': records})

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ds-result-')
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        # Keep the published diagnostic constraint relative to the test cwd.
        self.output = Path('results/diagnostics')/('test-'+self.directory.name)
        self.addCleanup(self.cleanup_output)

    def cleanup_output(self):
        import shutil
        if self.output.exists():
            shutil.rmtree(self.output)

    def build(self):
        with patch('market_levels.data_processing.synthetic.domain.generation.dispatch.generate_example', side_effect=AssertionError('forbidden')):
            return run_smoke(self.pilot, self.output, per_group=1)

    def test_roundtrip_exact_json_no_leakage_source_integrity_no_overwrite(self):
        before = {p.name: sha(p) for p in self.pilot.iterdir()}
        self.build()
        self.assertEqual(verify_smoke(self.output)['count'], 4)
        self.assertEqual(before, {p.name: sha(p) for p in self.pilot.iterdir()})
        rows = [json.loads(line) for line in (self.output/'examples.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(set(rows[0]), {'id', 'split', 'image', 'instruction', 'answer'})
        self.assertTrue(all(r['split'] is None for r in rows))
        for i in range(4):
            target = (self.output/f'labels/{i:03d}.json').read_text()
            self.assertEqual(set(json.loads(target)), {'supports', 'resistances'})
            import re
            for token in re.findall(r'\d+(?:\.\d+)?', target):
                self.assertRegex(token, r'^\d+\.\d{2}$')
        with self.assertRaises(FileExistsError):
            self.build()

    def test_manifest_and_untracked_file_tampering(self):
        self.build()
        extra = self.output/'surprise.txt'
        extra.write_text('x')
        with self.assertRaisesRegex(ValueError, 'inwentarz'):
            verify_files(self.output)
        extra.unlink()
        with (self.output/'manifest.json').open('a') as stream:
            stream.write(' ')
        with self.assertRaisesRegex(ValueError, 'manifestu'):
            verify_files(self.output)

    def test_semantic_corruption_detected_after_rehashing(self):
        self.build()
        label = self.output/'labels/000.json'
        label.write_text('{"supports":[1,2,3,4],"resistances":[]}', encoding='utf-8')
        reseal(self.output)
        with self.assertRaises(ValueError):
            verify_smoke(self.output, re_render=False)

    def test_input_overlay_rejected_and_failure_never_publishes(self):
        from market_levels.datasets.workflows.smoke import diagnostic_records
        loaded, ledger = diagnostic_records(self.pilot, 1)
        record, cs = loaded[0]
        record = deepcopy(record)
        record['visualization']['target_lines'] = True
        loaded[0] = (record, cs)
        with patch('market_levels.datasets.workflows.smoke.diagnostic_records', return_value=(loaded, ledger)):
            with self.assertRaisesRegex(ValueError, 'bez poziomów'):
                self.build()
        self.assertFalse(self.output.exists())
        with patch('market_levels.datasets.workflows.smoke.render_window', side_effect=RuntimeError('render failure')):
            with self.assertRaises(RuntimeError):
                self.build()
        self.assertFalse(self.output.exists())

    def test_restrictions_and_cli(self):
        with self.assertRaises(ValueError):
            run_smoke(self.pilot, self.directory/'bad')
        with self.assertRaises(ValueError):
            run_smoke(self.pilot, self.output, per_group=3)
        self.assertEqual(main(['verify', '--output', str(self.directory/'missing')]), 1)
        self.build()
        self.assertEqual(main(['verify', '--output', str(self.output)]), 0)


class DatasetPlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ds-plan-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root/'config.json'
        self.doc = read_configuration(CONFIG)

    def save_config(self):
        write_json(self.config, self.doc)

    def test_small_fixtures_preflight_shortage_missing_sources_and_repeatability(self):
        paths = {}
        for k, symbol in enumerate(SYMBOLS):
            path = self.root/f'{symbol}_4h_fixture.csv'
            paths[symbol] = path
            candles = []
            for year in (2020, 2024, 2025):
                start = datetime(year, 1, 1, tzinfo=UTC)
                for j in range(240):
                    p = Decimal(100+year+j+k*10000)
                    candles.append(Candle(start+j*CANDLE_DELTA, p, p+2, p-1, p+1, 'fixture'))
            write_candles_csv(path, candles)
        self.save_config()
        # The synthetic stage is independently tested below; these fixtures isolate split behavior.
        with patch('market_levels.datasets.workflows.planning.inspect_synthetic', return_value={}), patch('market_levels.datasets.workflows.planning.load_profile') as load:
            load.side_effect = lambda path, symbol: {'source': {'sha256': sha(paths[symbol])}}
            first = build_plan(self.config, paths)
            self.assertFalse(first['real_feasible'])
            self.assertEqual(first, build_plan(self.config, paths))
            self.assertEqual(first['groups']['BTCUSDT']['train']['available'], 3)
            self.assertEqual(first['selected_real'], [])
            paths['ETHUSDT'] = self.root/'missing.csv'
            self.assertIn('Brak CSV ETHUSDT', ' '.join(build_plan(self.config, paths)['problems']))

    def test_existing_production_gate_rejects_unapproved_without_generation(self):
        for symbol in SYMBOLS:
            path = self.root/f'{symbol}.json'
            settings = synthetic_settings(CONFIG, symbol, output=self.root/'output')
            write_json(path, diagnostic_profile_v2(symbol, settings))
            self.doc['dataset_build']['profiles'][symbol] = str(path)
        self.save_config()
        with patch('market_levels.data_processing.synthetic.workflows.generation.generate_example', side_effect=AssertionError('forbidden')):
            with self.assertRaisesRegex(ValueError, 'niezatwierdzony profil'):
                require_production_ready(self.config)
        self.assertFalse((self.root/'output').exists())

    def test_schema_matches_canonical_instruction(self):
        from market_levels.datasets.domain.examples import INSTRUCTION
        schema = json.loads((CONFIG.parent/'dataset_example.schema.json').read_text(encoding='utf-8'))
        self.assertEqual(schema['properties']['instruction']['const'], INSTRUCTION)

    def test_escaping_path(self):
        from market_levels.shared.paths import child
        with self.assertRaises(ValueError):
            child(self.root, '../escape')
        with self.assertRaises(ValueError):
            child(self.root, str(self.root.parent/'absolute.csv'))

    def test_seed_collision_and_profile_mismatch_inspection(self):
        history = self.root/'history'
        history.mkdir()
        self.doc['dataset_build']['synthetic_history_root'] = str(history)
        profiles = {}
        for symbol in SYMBOLS:
            path = self.root/f'{symbol}.json'
            path.write_text('{}')
            self.doc['dataset_build']['profiles'][symbol] = str(path)
            settings = synthetic_settings(CONFIG, symbol, output=self.root/'output')
            profiles[symbol] = {'version': 2, 'estimation_kind': 'training', 'status': 'unapproved',
                'calibration': {'method': 'volatility_refinement_v1', 'variant': 'full'},
                'regime_configuration': regime_configuration(settings),
                'source': {'chronological_split': self.doc['chronological_split']},
                'period': {'allowed_start': '2020-01-01T00:00:00+00:00', 'allowed_end': '2023-12-31T20:00:00+00:00'},
                'v2_parameters': {}, 'generator_version': '2.0.0'}
        self.save_config()
        with patch('market_levels.datasets.workflows.planning.load_profile', side_effect=lambda p, symbol: profiles[symbol]), patch('market_levels.datasets.workflows.planning.require_production_ready', side_effect=ValueError('unapproved')):
            first = inspect_synthetic(self.config, SourceLedger())
            self.assertFalse(first['production_ready'])
            self.assertEqual(len(first['planned_examples']), 440)
            write_json(history/'manifest.json', {'identity': {'configuration': {'seed': self.doc['dataset_build']['synthetic_master_seed']}}, 'examples': []})
            with self.assertRaisesRegex(ValueError, 'Kolizja'):
                inspect_synthetic(self.config, SourceLedger())
            (history/'manifest.json').unlink()
            profiles['ETHUSDT']['calibration']['variant'] = 'bridge_volatility'
            with self.assertRaisesRegex(ValueError, 'Niezgodny profil'):
                inspect_synthetic(self.config, SourceLedger())

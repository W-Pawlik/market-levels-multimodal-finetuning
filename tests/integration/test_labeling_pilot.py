"""Pilotaż offline: publikacja, integralność, odtworzenie i ochrona oryginałów."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_levels.charts.renderer import render_window
from market_levels.data_processing.storage import write_candles_csv, write_json
from market_levels.labeling.pilot import read_pilot, run_labeling, verify_labeling
from market_levels.cli.label_pilot import main
from unit.test_labeling import peaks


class LabelingPilotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='sr-test-')
        self.root = Path(self.temporary.name)
        self.previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(os.chdir, self.previous)
        self.pilot = self.root/'pilot'
        self.pilot.mkdir()
        candles = peaks([(10, 103), (14, 100), (18, 101)])
        metadata = render_window(candles, self.pilot/'000.png')
        payload = (self.pilot/'000.png').read_bytes()
        records = []
        for i in range(32):
            name = f'{i:03d}'
            if i:
                (self.pilot/f'{name}.png').write_bytes(payload)
            write_candles_csv(self.pilot/f'{name}.csv', candles)
            record = dict(metadata, id=f'manual-{i}', png=f'{name}.png', window_csv=f'{name}.csv',
                          window_csv_sha256=hashlib.sha256((self.pilot/f'{name}.csv').read_bytes()).hexdigest(),
                          symbol='BTCUSDT', source='manual', seed=None, profile_status='unapproved')
            write_json(self.pilot/f'{name}.json', record)
            records.append(record)
        write_json(self.pilot/'manifest.json', {'actual_count': 32, 'images': records})
        self.output = self.root/'results/diagnostics/sr-test'

    def test_full_pilot_replay_integrity_no_overwrite_and_tampering(self):
        before = {p.name: p.read_bytes() for p in self.pilot.iterdir()}
        with patch('market_levels.data_processing.synthetic.generator.generate_example', side_effect=AssertionError('forbidden')):
            run_labeling(pilot=self.pilot, output=self.output)
        verify_labeling(self.output, self.pilot, re_render=True)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.pilot.iterdir()})
        self.assertEqual(len(list((self.output/'overlays').glob('*.png'))), 32)
        self.assertEqual(json.loads((self.output/'labels/000.json').read_text()), {'supports': [], 'resistances': [101.0]})
        with self.assertRaises(FileExistsError):
            run_labeling(pilot=self.pilot, output=self.output)
        target = self.output/'labels/000.json'
        target.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'hash'):
            verify_labeling(self.output, self.pilot)

    def test_source_hash_and_sidecar_tampering(self):
        target = self.pilot/'000.csv'
        target.write_bytes(target.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            run_labeling(pilot=self.pilot, output=self.output)
        self.assertFalse(self.output.exists())

    def test_bad_manifest_count_and_traversal(self):
        path = self.pilot/'manifest.json'
        document = json.loads(path.read_text())
        document['actual_count'] = 31
        write_json(path, document)
        with self.assertRaises(ValueError):
            read_pilot(self.pilot)
        document['actual_count'] = 32
        document['images'][0]['png'] = '../escape.png'
        write_json(path, document)
        with self.assertRaisesRegex(ValueError, 'poza'):
            read_pilot(self.pilot)

    def test_render_failure_never_publishes_partial_output(self):
        with patch('market_levels.labeling.pilot.render_levels', side_effect=RuntimeError('render failure')):
            with self.assertRaisesRegex(RuntimeError, 'render failure'):
                run_labeling(pilot=self.pilot, output=self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.output.parent.glob('.labels-*')), [])

    def test_output_restrictions_and_cli_errors(self):
        for output in (self.root/'data/wrong', self.pilot/'wrong'):
            with self.assertRaises(ValueError):
                run_labeling(pilot=self.pilot, output=output)
        for args in (['--verify'], ['--re-render']):
            with self.assertRaises(SystemExit) as error:
                main(['--pilot', str(self.pilot)]+args)
            self.assertEqual(error.exception.code, 1)


if __name__ == '__main__':
    unittest.main()

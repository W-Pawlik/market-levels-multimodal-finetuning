"""Configuration composition preserves consumer settings and portable snapshots."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import unittest

from market_levels.configuration import ConfigurationError, load_download_settings
from market_levels.data_processing.io.chronology import load_chronological_split
from market_levels.data_processing.synthetic.config.generation import load_synthetic_settings
from market_levels.data_processing.synthetic.config.calibration import load_calibration_v2_settings
from market_levels.data_processing.synthetic.config.refinement import load_refinement_settings
from market_levels.datasets.config import load_plan_config
from market_levels.shared.configuration import (
    configuration_snapshot, configuration_sources, read_configuration, track_configuration,
)
from market_levels.shared.integrity import SourceLedger
from support.paths import CONFIG


class ConfigurationFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, value):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return path

    def test_flat_bom_crlf_and_non_object_behavior_remain_unchanged(self):
        path = self.root/'flat.json'
        for raw in (b'\xef\xbb\xbf{\r\n "value": 1.0\r\n}\r\n', b'[1, 2]', b'null'):
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                self.assertEqual(read_configuration(path), json.loads(path.read_text(encoding='utf-8-sig')))
                self.assertEqual(configuration_snapshot(path), raw)
                self.assertEqual(configuration_sources(path), (path.resolve(),))
        path.write_bytes(b'{\r\n "bad":\r\n}\r\n')
        with self.assertRaises(json.JSONDecodeError) as expected:
            json.loads(path.read_text(encoding='utf-8-sig'))
        with self.assertRaises(json.JSONDecodeError) as actual:
            read_configuration(path)
        self.assertEqual(str(actual.exception), str(expected.exception))

    def test_sections_preserve_field_order_types_and_unique_sources(self):
        shared = self.write('parts/generation.json', {'a': {'integer': 1, 'float': 1.0}, 'b': [False, None]})
        root = self.write('experiment.json', {
            'first': 4, 'a': {'$file': 'parts/generation.json', '$section': 'a'},
            'middle': 'literal', 'b': {'$file': 'parts/generation.json', '$section': 'b'},
        })
        result = read_configuration(root)
        self.assertEqual(list(result), ['first', 'a', 'middle', 'b'])
        self.assertIs(type(result['a']['integer']), int)
        self.assertIs(type(result['a']['float']), float)
        self.assertEqual(result['b'], [False, None])
        self.assertEqual(configuration_sources(root), (root.resolve(), shared.resolve()))

    def test_fragment_paths_follow_config_but_output_paths_keep_cwd_meaning(self):
        document = read_configuration(CONFIG)
        self.write('bundle/download.json', document['download'])
        document['download'] = {'$file': 'download.json'}
        root = self.write('bundle/experiment.json', document)
        elsewhere = self.root/'elsewhere'
        elsewhere.mkdir()
        previous = Path.cwd()
        try:
            os.chdir(elsewhere)
            settings = load_download_settings(root)
            self.assertEqual(settings.output, Path('data'))
            self.assertEqual(settings.output.resolve(), elsewhere/'data')
        finally:
            os.chdir(previous)

    def test_snapshot_survives_removal_of_source_fragments(self):
        fragment = self.write('fragment.json', {'text': 'zażółć', 'values': [1, 2.0]})
        root = self.root/'experiment.json'
        root.write_bytes(b'\xef\xbb\xbf{\r\n  "section": {"$file": "fragment.json"}\r\n}\r\n')
        expected = read_configuration(root)
        snapshot = self.root/'moved/config.json'
        snapshot.parent.mkdir()
        snapshot.write_bytes(configuration_snapshot(root))
        fragment.unlink()
        self.assertEqual(read_configuration(snapshot), expected)
        self.assertTrue(snapshot.read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertIn(b'\r\n', snapshot.read_bytes())
        self.assertEqual(configuration_sources(snapshot), (snapshot.resolve(),))

    def test_ledger_detects_fragment_changes_even_when_root_is_unchanged(self):
        fragment = self.write('fragment.json', {'seed': 11})
        root = self.write('experiment.json', {'search': {'$file': 'fragment.json'}})
        ledger = SourceLedger()
        track_configuration(root, ledger)
        self.assertEqual(set(ledger.files), {str(root.resolve()), str(fragment.resolve())})
        original = root.read_bytes()
        fragment.write_text('{"seed": 12}', encoding='utf-8')
        self.assertEqual(root.read_bytes(), original)
        with self.assertRaisesRegex(ValueError, 'Zmienione źródła'):
            ledger.verify()

    def test_invalid_or_chained_references_fail_without_writing_output(self):
        self.write('fragment.json', {'value': 1})
        cases = [
            {'$file': ''}, {'$file': 1}, {'$file': str((self.root/'fragment.json').resolve())},
            {'$file': '/rooted.json'}, {'$file': '\\rooted.json'},
            {'$file': 'C:\\absolute.json'}, {'$file': 'C:drive-relative.json'},
            {'$file': 'fragment.json', 'override': 2},
            {'$file': 'fragment.json', '$section': 'missing'},
            {'$file': 'fragment.json', '$section': False},
            {'$file': 'experiment.json', '$section': 'section'},
            {'$file': 'experiment.json'},
        ]
        for reference in cases:
            with self.subTest(reference=reference):
                root = self.write('experiment.json', {'section': reference})
                with self.assertRaises(ValueError):
                    read_configuration(root)
        document = read_configuration(CONFIG)
        document['download'] = {'$file': 'missing.json'}
        root = self.write('experiment.json', document)
        with self.assertRaises(ConfigurationError):
            load_download_settings(root)
        self.assertFalse((self.root/'data').exists())

    def test_all_consumers_match_a_self_contained_flat_configuration(self):
        document = read_configuration(CONFIG)
        flat = self.write('legacy.json', document)
        loaders = [load_download_settings, load_calibration_v2_settings, load_refinement_settings]
        for loader in loaders:
            with self.subTest(loader=loader.__name__):
                self.assertEqual(asdict(loader(CONFIG)), asdict(loader(flat)))
        for version in ('v1', 'v2'):
            self.assertEqual(load_synthetic_settings(CONFIG, generator_version=version).document(),
                             load_synthetic_settings(flat, generator_version=version).document())
        self.assertEqual(load_chronological_split(CONFIG).document(), load_chronological_split(flat).document())
        self.assertEqual(load_plan_config(CONFIG), load_plan_config(flat))
        self.assertEqual(json.loads(configuration_snapshot(CONFIG)), document)

    def test_unused_domain_options_are_not_validated_by_other_consumers(self):
        document = read_configuration(CONFIG)
        self.write('synthetic.json', {'unsupported_setting': True})
        document['synthetic'] = {'$file': 'synthetic.json'}
        root = self.write('experiment.json', document)
        self.assertEqual(load_download_settings(root), load_download_settings(CONFIG))
        with self.assertRaisesRegex(ValueError, 'Nieobsługiwane ustawienia synthetic'):
            load_synthetic_settings(root)

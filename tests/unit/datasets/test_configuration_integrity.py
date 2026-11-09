"""Historical flat config pins survive splitting without relaxing other SHA pins."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from market_levels.datasets.workflows.verification import _check_sources
from market_levels.shared.configuration import configuration_snapshot, track_configuration
from market_levels.shared.integrity import SourceLedger


class ConfigurationIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root/'experiment.json'
        self.saved = self.root/'config.json'
        self.other = self.root/'source.json'
        self.fragment = self.root/'fragment.json'
        self.document = {'selection_seed': 17, 'synthetic': {'count': 2, 'scale': 1.0}}
        self.config.write_text(json.dumps(self.document, indent=2), encoding='utf-8')
        self.saved.write_bytes(self.config.read_bytes())
        self.other.write_text('{"other": true}', encoding='utf-8')
        self.plan = {'source_integrity': {'sha256': {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.config, self.other)
        }}}

    def split(self):
        self.fragment.write_text(json.dumps(self.document['synthetic']), encoding='utf-8')
        self.config.write_text(json.dumps(dict(self.document, synthetic={'$file': 'fragment.json'}), indent=2), encoding='utf-8')

    def test_only_exact_historical_config_bytes_can_be_reconstructed(self):
        self.split()
        self.assertEqual(configuration_snapshot(self.config), self.saved.read_bytes())
        _check_sources(self.plan, saved_config=self.saved)
        with self.assertRaisesRegex(ValueError, 'Źródło planu zmieniło się'):
            _check_sources(self.plan)
        for change in ('value', 'other_source', 'float_type', 'invalid_fragment'):
            with self.subTest(change=change):
                self.split()
                self.other.write_text('{"other": true}', encoding='utf-8')
                if change == 'value':
                    self.fragment.write_text('{"count": 3, "scale": 1.0}', encoding='utf-8')
                elif change == 'float_type':
                    self.fragment.write_text('{"count": 2, "scale": 1}', encoding='utf-8')
                elif change == 'other_source':
                    self.other.write_bytes(self.other.read_bytes()+b'\n')
                else:
                    self.fragment.write_text('{bad JSON}', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'Źródło planu zmieniło się'):
                    _check_sources(self.plan, saved_config=self.saved)

    def test_new_composed_plans_keep_raw_fragment_hashes_strict(self):
        self.split()
        ledger = SourceLedger()
        track_configuration(self.config, ledger)
        plan = {'source_integrity': ledger.verify()}
        _check_sources(plan, saved_config=self.saved)
        self.fragment.write_bytes(self.fragment.read_bytes()+b'\n')
        self.assertEqual(configuration_snapshot(self.config), self.saved.read_bytes())
        with self.assertRaisesRegex(ValueError, 'Źródło planu zmieniło się'):
            _check_sources(plan, saved_config=self.saved)

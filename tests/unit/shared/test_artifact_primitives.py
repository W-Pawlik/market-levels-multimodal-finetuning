"""Byte contracts of the consolidated technical primitives."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_levels.shared.integrity import sha256_file
from market_levels.shared.json_io import read_json
from market_levels.shared.paths import child, _child, _batch_path
from market_levels.data_processing.synthetic.config.generation import SyntheticSettings
from market_levels.data_processing.synthetic.io.profiles import prepare_profiles
from market_levels.data_processing.synthetic.workflows.comparison import save_comparison
from support.paths import PROJECT


class ArtifactPrimitiveTests(unittest.TestCase):
    def test_source_processed_guard_from_another_working_directory(self):
        original = Path.cwd()
        target = PROJECT / 'data/processed/refactor-guard-never-written'
        with tempfile.TemporaryDirectory() as temporary:
            try:
                os.chdir(temporary)
                # Even a broken guard cannot write to the author's data in this test.
                with patch.object(Path, 'mkdir', side_effect=AssertionError('write forbidden')):
                    with self.assertRaisesRegex(ValueError, 'processed'):
                        prepare_profiles(SyntheticSettings(output=target, diagnostic=True))
                    with self.assertRaisesRegex(ValueError, 'processed'):
                        save_comparison(target, {})
            finally:
                os.chdir(original)

    def test_sha256_empty_and_across_chunk_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'bytes'
            for payload in (b'', b'a' * (128 * 1024 - 1), b'a' * (128 * 1024 + 1)):
                path.write_bytes(payload)
                self.assertEqual(sha256_file(path), hashlib.sha256(payload).hexdigest())
            with self.assertRaises(FileNotFoundError):
                sha256_file(Path(temporary) / 'missing')

    def test_json_bom_and_object_requirement_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'value.json'
            path.write_text('{"value": 2}', encoding='utf-8-sig')
            self.assertEqual(read_json(path), {'value': 2})
            path.write_text('[]', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Oczekiwano obiektu JSON'):
                read_json(path)

    def test_distinct_path_policies_and_errors_remain_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.assertEqual(child(root, 'a'), root / 'a')
            self.assertEqual(_child(root, 'a'), root / 'a')
            for function, text in ((child, 'pilotażu'), (_child, 'partię')):
                with self.assertRaisesRegex(ValueError, text):
                    function(root, '..')
                with self.assertRaises(ValueError):
                    function(root, '.')
            # The historical batch reader allows the root; pilot children do not.
            self.assertEqual(_batch_path(root, '.'), root)
            with self.assertRaisesRegex(ValueError, 'względnych'):
                _batch_path(root, str(root / 'a'))

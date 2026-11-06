"""Granica Windows MAX_PATH bez polegania na obsłudze long paths hosta."""
import json
from pathlib import Path, PureWindowsPath
import tempfile
import unittest
from unittest.mock import patch
import uuid

from market_levels.cli import refinement_comparison as runner


class RunnerPathTests(unittest.TestCase):
    def windows_root(self, target, mode='smoke'):
        base = PureWindowsPath('C:/r')
        length = len(str(runner.longest_output_path(base, mode)))
        return PureWindowsPath('C:/')/('r'+'x'*(target-length))

    def test_exactly_260_is_rejected_and_259_is_accepted(self):
        for mode in ('smoke','full'):
            with self.subTest(mode=mode):
                bad = self.windows_root(260, mode)
                self.assertEqual(len(str(runner.longest_output_path(bad,mode))),260)
                with self.assertRaisesRegex(ValueError,'260.*OutputDirectory'):
                    runner.validate_output_paths(bad,mode)
                self.assertEqual(runner.validate_output_paths(self.windows_root(259,mode),mode),259)

    def test_short_output_checks_bridge_and_preserves_filename_seed_and_hash_lengths(self):
        root = PureWindowsPath('D:/rc/new')
        longest = runner.longest_output_path(root,'smoke')
        self.assertIn('bridge_volatility-20261107',longest.parts)
        self.assertIn('diagnostics',longest.parts)
        self.assertEqual(len(longest.parent.parent.name),24)
        self.assertEqual(longest.name,'BTCUSDT_000000_'+'f'*64+'.json')
        self.assertLess(runner.validate_output_paths(root,'smoke'),260)

    def test_reported_staging_path_260_is_rejected_before_any_generation(self):
        tail = PureWindowsPath('full-20261107/.synthetic-xxxxxxxx/batch/BTCUSDT')/('BTCUSDT_000000_'+'f'*64+'.json')
        base = PureWindowsPath('C:/r')
        root = PureWindowsPath('C:/')/('r'+'x'*(260-len(str(base/tail))))
        self.assertEqual(len(str(root/tail)),260)
        self.assertGreater(len(str(runner.longest_output_path(root,'smoke'))),260)
        with patch.object(runner,'cli',side_effect=AssertionError('must fail before CLI')):
            with self.assertRaisesRegex(ValueError,'OutputDirectory'):
                runner.execute(Path('.'),{},'smoke',root)

    def test_windows_length_counts_utf16_units(self):
        root = PureWindowsPath('C:/rc/\U0001f600')
        length = runner.validate_output_paths(root,'smoke')
        self.assertEqual(length,len(str(runner.longest_output_path(root,'smoke')))+1)

    def test_short_default_has_full_run_id_and_can_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp).resolve()
            run_id = '0123456789abcdef0123456789abcdef'
            with patch.object(runner,'preflight',return_value={}), patch.object(runner,'execute') as execute, \
                    patch.object(runner.uuid,'uuid4',return_value=uuid.UUID(hex=run_id)):
                with patch('sys.argv',['runner','--mode','smoke','--project',str(project)]):
                    runner.main()
                root = project/'data/synthetic/rc-0123456789ab'
                identity = runner.read_json(root/'run.json')
                self.assertEqual(identity['run_id'],run_id)
                with patch('sys.argv',['runner','--mode','smoke','--project',str(project),'--resume',str(root)]):
                    runner.main()
                self.assertEqual(execute.call_count,2)
                self.assertEqual(runner.read_json(root/'run.json'),identity)

    def test_bad_custom_root_is_rejected_before_mkdir_and_check_only_checks_it(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()/'r'
            length = len(str(runner.longest_output_path(base,'smoke')))
            root = base.parent/('r'+'x'*(260-length))
            for mode in ('smoke','full','check'):
                with patch.object(runner,'preflight',return_value={}), patch.object(runner,'execute') as execute, \
                        patch('sys.argv',['runner','--mode',mode,'--project',temp,'--output',str(root)]):
                    with self.assertRaisesRegex(ValueError,'OutputDirectory'):
                        runner.main()
                    execute.assert_not_called()
                    self.assertFalse(root.exists())

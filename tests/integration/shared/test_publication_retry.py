"""Kontrolowane blokady rename; bez zależności od antywirusa."""
from dataclasses import replace
import errno
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import call, patch

from market_levels.shared import publication as staging
from market_levels.data_processing.synthetic.workflows import generation as synthetic, comparison as compare_synthetic
from market_levels.data_processing.synthetic.config.generation import SyntheticSettings
from market_levels.experiments.refinement.workflows import runner
from market_levels.cli import refinement_comparison as runner_cli
from market_levels.experiments.refinement.workflows import preflight as runner_preflight
from market_levels.experiments.refinement import config as runner_config, paths as runner_paths, io as runner_io
from market_levels.experiments.refinement.domain import plan as runner_plan
from support.comparison import CONFIG


def blocked(code):
    error = PermissionError(errno.EACCES, f'controlled WinError {code}')
    error.winerror = code
    return error


class PublicationRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.root/'batch';self.stage.mkdir()
        (self.stage/'manifest.json').write_text('{"complete":true}')
        self.final = self.root/'final'

    def test_winerror_5_then_success(self):
        original = Path.rename;attempts = []
        def rename(path, target):
            attempts.append((path,target))
            if len(attempts)==1:raise blocked(5)
            return original(path,target)
        with patch.object(Path,'rename',autospec=True,side_effect=rename), \
                patch.object(staging.time,'sleep') as sleep, self.assertLogs(staging.LOGGER,'WARNING'):
            staging.publish_directory(self.stage,self.final)
        self.assertEqual(len(attempts),2);sleep.assert_called_once_with(.05)
        self.assertEqual((self.final/'manifest.json').read_text(),'{"complete":true}')

    def test_two_locks_32_and_33_then_success(self):
        original = Path.rename;attempts = []
        def rename(path,target):
            attempts.append(path)
            if len(attempts)<=2:raise blocked((32,33)[len(attempts)-1])
            return original(path,target)
        with patch.object(Path,'rename',autospec=True,side_effect=rename), \
                patch.object(staging.time,'sleep') as sleep, self.assertLogs(staging.LOGGER,'WARNING'):
            staging.publish_directory(self.stage,self.final)
        self.assertEqual(len(attempts),3)
        self.assertEqual(sleep.call_args_list,[call(.05),call(.15)])

    def test_permanent_conflict_logs_every_attempt_and_preserves_first_error(self):
        errors = [blocked(code) for code in (5,32,33,5)]
        with patch.object(Path,'rename',side_effect=errors) as rename, \
                patch.object(staging.time,'sleep') as sleep, self.assertLogs(staging.LOGGER,'WARNING') as logs:
            with self.assertRaises(OSError) as caught:staging.publish_directory(self.stage,self.final)
        self.assertIs(caught.exception,errors[0]);self.assertEqual(rename.call_count,4)
        self.assertEqual(sleep.call_args_list,[call(.05),call(.15),call(.3)])
        for i in range(1,5):self.assertIn(f'próba {i}/4','\n'.join(logs.output))
        self.assertTrue(self.stage.is_dir());self.assertFalse(self.final.exists())

    def test_other_filesystem_errors_are_not_retried(self):
        errors = [OSError(n,'controlled') for n in (errno.EIO,errno.ENOSPC,errno.EXDEV,errno.ENOENT)]
        other_windows = blocked(87);errors.append(other_windows)
        for error in errors:
            with self.subTest(error=error), patch.object(Path,'rename',side_effect=error) as rename, \
                    patch.object(staging.time,'sleep') as sleep, self.assertLogs(staging.LOGGER,'WARNING'):
                with self.assertRaises(OSError) as caught:staging.publish_directory(self.stage,self.final)
                self.assertIs(caught.exception,error);self.assertEqual(rename.call_count,1);sleep.assert_not_called()

    def test_existing_target_never_overwritten(self):
        self.final.mkdir();sentinel = self.final/'keep';sentinel.write_text('preserve')
        with patch.object(Path,'rename') as rename:
            with self.assertRaisesRegex(FileExistsError,'Kolizja'):
                staging.publish_directory(self.stage,self.final)
        rename.assert_not_called();self.assertEqual(sentinel.read_text(),'preserve')

    def test_target_appears_between_attempts(self):
        def collision(_):self.final.mkdir()
        with patch.object(Path,'rename',side_effect=blocked(5)) as rename, \
                patch.object(staging.time,'sleep',side_effect=collision), self.assertLogs(staging.LOGGER,'WARNING'):
            with self.assertRaisesRegex(FileExistsError,'Kolizja'):
                staging.publish_directory(self.stage,self.final)
        self.assertEqual(rename.call_count,1);self.assertTrue(self.stage.exists());self.assertTrue(self.final.exists())

    def test_target_appears_during_rename_is_not_success(self):
        def collision(*_):
            self.final.mkdir();raise blocked(5)
        with patch.object(Path,'rename',side_effect=collision), patch.object(staging.time,'sleep') as sleep, \
                self.assertLogs(staging.LOGGER,'WARNING'):
            with self.assertRaises(FileExistsError):staging.publish_directory(self.stage,self.final)
        sleep.assert_not_called();self.assertTrue(self.stage.exists())

    def test_generation_not_repeated_and_manifest_csv_unchanged(self):
        settings = SyntheticSettings(generator_version='v2',diagnostic=True,count=2,output=self.root/'baseline')
        baseline = synthetic.run(settings)
        original = Path.rename;attempts = 0
        def rename(path,target):
            nonlocal attempts
            attempts += 1
            if attempts<=2:raise blocked(5)
            return original(path,target)
        with patch.object(Path,'rename',autospec=True,side_effect=rename), \
                patch.object(staging.time,'sleep'), self.assertLogs(staging.LOGGER,'WARNING'), \
                patch.object(synthetic,'generate_example',wraps=synthetic.generate_example) as generate:
            final = synthetic.run(replace(settings,output=self.root/'retried'))
        self.assertEqual(generate.call_count,4);self.assertEqual(attempts,3)
        self.assertEqual((final/'manifest.json').read_bytes(),(baseline/'manifest.json').read_bytes())
        manifest = json.loads((final/'manifest.json').read_text())
        for entry in manifest['examples']:
            self.assertEqual((final/entry['csv']).read_bytes(),(baseline/entry['csv']).read_bytes())

    def test_report_publication_retries_without_rewriting_payload(self):
        report = {'comparison_id':'retry-fixture','symbol':'BTCUSDT','fixture':True}
        original = Path.rename;attempts = 0
        def rename(path,target):
            nonlocal attempts
            attempts += 1
            if attempts==1:raise blocked(33)
            return original(path,target)
        with patch.object(Path,'rename',autospec=True,side_effect=rename), patch.object(staging.time,'sleep'), \
                self.assertLogs(staging.LOGGER,'WARNING'), \
                patch.object(compare_synthetic,'write_json',wraps=compare_synthetic.write_json) as write:
            final = compare_synthetic.save_comparison(self.root/'reports',report,summary_text='fixture\n')
        self.assertEqual(attempts,2);self.assertEqual(write.call_count,1)
        self.assertEqual(json.loads((final/'BTCUSDT_comparison.json').read_text()),report)
        self.assertEqual((final/'BTCUSDT_summary.md').read_text(),'fixture\n')

    def test_unpublished_staging_manifest_is_not_resumed(self):
        root = self.root/'run';output = root/'full-20261107'
        partial = output/'.synthetic-locked'/'batch';partial.mkdir(parents=True)
        sentinel = partial/'manifest.json';sentinel.write_text('{"complete":true}')
        with patch.object(runner,'cli',side_effect=AssertionError('must stop before CLI')):
            with self.assertRaises(ValueError) as caught:
                runner.execute(CONFIG.parents[1],{'config':str(CONFIG)},'smoke',root)
        text = str(caught.exception)
        self.assertIn(str(output.resolve()),text);self.assertIn('Move-Item',text)
        self.assertIn('ResumeDirectory',text);self.assertIn('Ukończone etapy',text)
        self.assertEqual(sentinel.read_text(),'{"complete":true}')
        report_root = self.root/'partial-reports';(report_root/'.comparison-locked'/'report').mkdir(parents=True)
        (report_root/'.comparison-locked'/'report'/'BTCUSDT_comparison.json').write_text('{}')
        self.assertIsNone(runner.unique_file(report_root,'*_comparison.json'))

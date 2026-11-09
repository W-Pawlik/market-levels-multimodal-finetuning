"""Kontrole wejść i wznowienie na izolowanych sztucznych danych."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from market_levels.experiments.refinement.workflows import runner
from market_levels.cli import refinement_comparison as runner_cli
from market_levels.experiments.refinement.workflows import preflight as runner_preflight
from market_levels.experiments.refinement import config as runner_config, paths as runner_paths, io as runner_io
from market_levels.experiments.refinement.domain import plan as runner_plan
from market_levels.data_processing.synthetic.workflows.calibration import calibrate_csv
from market_levels.data_processing.synthetic.io.profiles import save_profile
from market_levels.data_processing.synthetic.workflows.calibration import calibrate_v2_csv
from market_levels.data_processing.synthetic.config.refinement import RefinementSettings
from market_levels.data_processing.synthetic.workflows.refinement import refine_v2_volatility
from market_levels.data_processing.synthetic.config.generation import SyntheticSettings
from market_levels.data_processing.io.chronology import load_chronological_split
from market_levels.data_processing.io.candles import write_candles_csv
from market_levels.data_processing.synthetic.workflows.generation import run
from market_levels.data_processing.synthetic.workflows.comparison import build_comparison
from market_levels.data_processing.synthetic.domain.diagnostics import aggregate_windows
from market_levels.data_processing.synthetic.io.batches import load_synthetic_windows
from market_levels.data_processing.windows.domain.selection import select_real_windows
from market_levels.data_processing.synthetic.domain.generation.seeds import example_seed
from market_levels.shared.configuration import read_configuration
from support.calibration import small_search
from support.comparison import real_fixture, CONFIG

from support.refinement import prepare_runner_fixture




class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prepare_runner_fixture(cls)

    def test_preflight_and_missing_or_duplicate_inputs(self):
        plan = runner_preflight.preflight(self.project,self.inputs)
        self.assertEqual(len(plan['old_reports']),12);self.assertEqual(len(plan['profiles']),4)
        for field,key,value in (
            ('profiles','BTCUSDT|full',str(self.root/'missing-profile.json')),
            ('historical_reports',0,str(self.root/'missing-report.json')),
            ('historical_reports',0,self.options['historical_reports'][1])):
            options = deepcopy(self.options);options[field][key] = value
            path = self.root/'bad-inputs.json';path.write_text(json.dumps(options),encoding='utf-8')
            with self.assertRaises((ValueError,OSError)):runner_preflight.preflight(self.project,path)

    def test_preflight_pins_fragment_changes_for_resume_identity(self):
        document = read_configuration(CONFIG)
        fragment = self.root/'split-fragment.json'
        fragment.write_text(json.dumps(document['chronological_split']), encoding='utf-8')
        document['chronological_split'] = {'$file': fragment.name}
        config = self.root/'composed-config.json'
        config.write_text(json.dumps(document), encoding='utf-8')
        options = dict(self.options, config=str(config))
        inputs = self.root/'composed-inputs.json'
        inputs.write_text(json.dumps(options), encoding='utf-8')
        first = runner_preflight.preflight(self.project, inputs)
        self.assertIn(str(fragment.resolve()), first['digests'])
        fragment.write_bytes(fragment.read_bytes()+b'\n')
        second = runner_preflight.preflight(self.project, inputs)
        self.assertEqual(first['digests'][str(config.resolve())], second['digests'][str(config.resolve())])
        self.assertNotEqual(first['digests'][str(fragment.resolve())], second['digests'][str(fragment.resolve())])

    def test_missing_module_and_foreign_install_are_rejected(self):
        original = runner_preflight.importlib.import_module
        def missing(name):
            if name == 'market_levels.data_processing.synthetic':
                raise ModuleNotFoundError(name)
            return original(name)
        with patch.object(runner_preflight.importlib,'import_module',side_effect=missing):
            with self.assertRaises(ModuleNotFoundError):runner_preflight.check_environment(self.project)
        with self.assertRaisesRegex(ValueError,'Konflikt'):
            runner_preflight.check_environment(self.root)

    def test_native_powershell_check_only_from_other_directory(self):
        ps = shutil.which('powershell')
        if not ps:self.skipTest('Windows PowerShell niedostępny')
        result = subprocess.run([ps,'-NoProfile','-ExecutionPolicy','Bypass','-File',
            str(self.project/'scripts/run_refinement_comparison.ps1'),'-CheckOnly','-InputsFile',str(self.inputs)],
            cwd=self.root,capture_output=True,text=True,errors='replace')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('12 starych raportow',result.stdout)
        failed = subprocess.run([ps,'-NoProfile','-ExecutionPolicy','Bypass','-File',
            str(self.project/'scripts/run_refinement_comparison.ps1'),'-CheckOnly','-InputsFile',str(self.root/'missing.json')],
            cwd=self.root,capture_output=True,text=True,errors='replace')
        self.assertNotEqual(failed.returncode,0)
        self.assertIn('FileNotFoundError',failed.stdout+failed.stderr)
        self.assertIn('Przerwano procedure',failed.stdout+failed.stderr)

    def test_smoke_resume_after_publication_and_refuse_modified_data(self):
        plan = runner_preflight.preflight(self.project,self.inputs)
        output = self.root/'interrupted';output.mkdir()
        original = runner.cli
        def interrupted(module,args,project,log=None):
            original(module,args,project,log)
            if module == 'generate_synthetic':raise RuntimeError('simulated interruption after publication')
        with patch.object(runner,'cli',side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError,'interruption'):
                runner.execute(self.project,plan,'smoke',output)
        manifest = next((output/'full-20261107').rglob('manifest.json'))
        before = {p:runner.sha(p) for p in manifest.parent.rglob('*') if p.is_file()}
        with patch.object(runner,'cli',wraps=original) as commands:
            runner.execute(self.project,plan,'smoke',output)
        generated = [c for c in commands.call_args_list if c.args[0]=='generate_synthetic']
        self.assertEqual(len(generated),1)
        self.assertEqual({p:runner.sha(p) for p in before},before)
        self.assertEqual(len(list((output/'comparisons').rglob('*_comparison.json'))),4)
        with patch.object(runner,'cli',side_effect=AssertionError('must reuse complete outputs')):
            runner.execute(self.project,plan,'smoke',output)
        csv = next(manifest.parent.rglob('*.csv'));csv.write_text('corrupt',encoding='utf-8')
        with self.assertRaises(ValueError):runner.execute(self.project,plan,'smoke',output)

    def test_cli_refuses_new_output_over_existing_and_changed_resume_identity(self):
        output = self.root/'occupied';output.mkdir();(output/'sentinel').write_text('preserve')
        args = [sys.executable,'-I','-m','market_levels.cli.refinement_comparison','--mode','smoke',
                '--project',str(self.project),'--inputs',str(self.inputs)]
        result = subprocess.run(args+['--output',str(output)],capture_output=True)
        self.assertNotEqual(result.returncode,0);self.assertEqual((output/'sentinel').read_text(),'preserve')
        (output/'run.json').write_text('{}')
        result = subprocess.run(args+['--resume',str(output)],capture_output=True)
        self.assertNotEqual(result.returncode,0);self.assertIn(b'Wznowienie',result.stderr)

    def test_run_lock_released_on_error_and_excludes_concurrent_resume(self):
        path = self.root/'test.lock'
        with self.assertRaises(RuntimeError):
            with runner_io.run_lock(path):raise RuntimeError('interrupt')
        with runner_io.run_lock(path):
            with self.assertRaises(OSError):
                with runner_io.run_lock(path):pass
        with runner_io.run_lock(path):pass

    def test_incomplete_unpublished_output_is_not_regenerated_or_deleted(self):
        plan = runner_preflight.preflight(self.project,self.inputs)
        output = self.root/'partial';partial = output/'full-20261107';partial.mkdir(parents=True)
        sentinel = partial/'incomplete.csv';sentinel.write_text('preserve')
        with patch.object(runner,'cli',side_effect=AssertionError('no generation')):
            with self.assertRaisesRegex(ValueError,'Niekompletny'):
                runner.execute(self.project,plan,'smoke',output)
        self.assertEqual(sentinel.read_text(),'preserve')

    def test_recovered_manifest_with_wrong_example_count_is_rejected(self):
        plan = runner_preflight.preflight(self.project,self.inputs)
        output = self.root/'wrong-count';output.mkdir()
        settings = SyntheticSettings(generator_version='v2',diagnostic=True,count=1,seed=20261107,
            experiment_id='refinement-comparison',symbols=runner_config.SYMBOLS,
            profiles={s:plan['profiles'][s+'|full'] for s in runner_config.SYMBOLS},output=output/'full-20261107')
        run(settings)
        with patch.object(runner,'cli',side_effect=AssertionError('no regeneration')):
            with self.assertRaisesRegex(ValueError,'liczność'):
                runner.execute(self.project,plan,'smoke',output)

    def test_cli_traceback_is_preserved_in_log(self):
        log = self.root/'original-traceback.log'
        with self.assertRaises(RuntimeError):
            runner.cli('refinement_comparison',['--mode','check','--project',str(self.root)],self.project,log)
        text = log.read_text(encoding='utf-8')
        self.assertIn('Traceback (most recent call last)',text)
        self.assertIn('Konflikt instalacji',text)

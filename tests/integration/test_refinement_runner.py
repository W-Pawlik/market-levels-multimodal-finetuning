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

from market_levels.cli import refinement_comparison as runner
from market_levels.data_processing.synthetic.calibration import calibrate_csv, save_profile
from market_levels.data_processing.synthetic.calibration_v2 import calibrate_v2_csv
from market_levels.data_processing.synthetic.refinement import RefinementSettings, refine_v2_volatility
from market_levels.data_processing.synthetic.settings import SyntheticSettings
from market_levels.data_processing.synthetic.training_period import load_chronological_split
from market_levels.data_processing.storage import write_candles_csv
from market_levels.data_processing.pipelines.synthetic import run
from market_levels.data_processing.pipelines.compare_synthetic import build_comparison
from market_levels.data_processing.synthetic.comparison import aggregate_windows, load_synthetic_windows
from market_levels.data_processing.synthetic.selection import select_real_windows
from market_levels.data_processing.synthetic.generator import example_seed
from integration.test_synthetic_v2_pipeline import small_search
from unit.test_synthetic_comparison import real_fixture, CONFIG


def write_report(path, report):
    report = deepcopy(report);report.pop('comparison_id', None)
    report['comparison_id'] = hashlib.sha256(json.dumps(report,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()[:24]
    path.write_text(json.dumps(report),encoding='utf-8')


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name);cls.project = CONFIG.parents[1]
        cls.split = load_chronological_split(CONFIG);cls.start,cls.end = cls.split.periods['train']
        cls.options = {'config':str(CONFIG),'profiles':{},'real_csv':{},'historical_reports':[]}
        settings = SyntheticSettings(generator_version='v2',diagnostic=True,count=2,symbols=runner.SYMBOLS)
        search = RefinementSettings(volatility_phi=[.7],volatility_stationary_std=[.2],
            simulation_seeds=[101,102,103],diagnostic_seeds=[500,501],examples_per_seed=1)
        originals, old_paths = {}, {}
        for symbol in runner.SYMBOLS:
            csv = cls.root/(symbol+'.csv');write_candles_csv(csv,real_fixture(7400))
            cls.options['real_csv'][symbol] = str(csv)
            original = calibrate_v2_csv(csv,symbol,start=cls.start,end=cls.end,split=cls.split,settings=settings,search=small_search())
            source = cls.root/(symbol+'-original.json');save_profile(source,original)
            originals[symbol] = source
            v1 = cls.root/(symbol+'-v1.json');save_profile(v1,calibrate_csv(csv,symbol,allowed_start=cls.start,allowed_end=cls.end))
            old_paths[symbol] = v1
            for variant in runner.VARIANTS:
                profile = refine_v2_volatility(csv,source,symbol=symbol,variant=variant,start=cls.start,end=cls.end,
                    split=cls.split,settings=settings,search=search)
                path = cls.root/(symbol+'-'+variant+'.json');save_profile(path,profile)
                cls.options['profiles'][symbol+'|'+variant] = str(path)
        # Małe prawdziwe partie; historyczne JSON fixture opisują powtórzone okna
        # jako kontrolowaną referencję 60. Nie generujemy 720 serii na potrzeby testu.
        for version, profiles in (('v1',old_paths),('v2',originals)):
            manifest = run(replace(settings,generator_version=version,profiles={s:str(p) for s,p in profiles.items()},
                output=cls.root/version))/'manifest.json'
            for symbol in runner.SYMBOLS:
                csv = Path(cls.options['real_csv'][symbol])
                report = build_comparison(symbol=symbol,real_csv=csv,synthetic_manifest=manifest,start=cls.start,end=cls.end,
                    count=2,selection_seed=runner.SELECTION_SEED,split=cls.split)
                windows,selection = select_real_windows(real_fixture(7400),symbol=symbol,start=cls.start,end=cls.end,
                    count=60,seed=runner.SELECTION_SEED,split=cls.split)
                synthetic,_ = load_synthetic_windows(manifest,symbol=symbol,count=2,split=cls.split)
                report.update(selection=selection,real=aggregate_windows(windows),synthetic=aggregate_windows(synthetic*30))
                for seed in runner.SEEDS:
                    fixture = deepcopy(report);source = fixture['synthetic_source']
                    source['master_seed'] = seed;source['run_id'] = f'fixture-{version}-{symbol}-{seed}'
                    source['examples'] = [dict(source['examples'][i%2],seed=example_seed(seed,symbol,i)) for i in range(60)]
                    path = cls.root/f'{version}-{symbol}-{seed}.json';write_report(path,fixture)
                    cls.options['historical_reports'].append(str(path))
        cls.inputs = cls.root/'inputs.json';cls.inputs.write_text(json.dumps(cls.options),encoding='utf-8')

    def test_preflight_and_missing_or_duplicate_inputs(self):
        plan = runner.preflight(self.project,self.inputs)
        self.assertEqual(len(plan['old_reports']),12);self.assertEqual(len(plan['profiles']),4)
        for field,key,value in (
            ('profiles','BTCUSDT|full',str(self.root/'missing-profile.json')),
            ('historical_reports',0,str(self.root/'missing-report.json')),
            ('historical_reports',0,self.options['historical_reports'][1])):
            options = deepcopy(self.options);options[field][key] = value
            path = self.root/'bad-inputs.json';path.write_text(json.dumps(options),encoding='utf-8')
            with self.assertRaises((ValueError,OSError)):runner.preflight(self.project,path)

    def test_missing_module_and_foreign_install_are_rejected(self):
        original = runner.importlib.import_module
        def missing(name):
            if name == 'market_levels.data_processing.synthetic':
                raise ModuleNotFoundError(name)
            return original(name)
        with patch.object(runner.importlib,'import_module',side_effect=missing):
            with self.assertRaises(ModuleNotFoundError):runner.check_environment(self.project)
        with self.assertRaisesRegex(ValueError,'Konflikt'):
            runner.check_environment(self.root)

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
        plan = runner.preflight(self.project,self.inputs)
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
            with runner.run_lock(path):raise RuntimeError('interrupt')
        with runner.run_lock(path):
            with self.assertRaises(OSError):
                with runner.run_lock(path):pass
        with runner.run_lock(path):pass

    def test_incomplete_unpublished_output_is_not_regenerated_or_deleted(self):
        plan = runner.preflight(self.project,self.inputs)
        output = self.root/'partial';partial = output/'full-20261107';partial.mkdir(parents=True)
        sentinel = partial/'incomplete.csv';sentinel.write_text('preserve')
        with patch.object(runner,'cli',side_effect=AssertionError('no generation')):
            with self.assertRaisesRegex(ValueError,'Niekompletny'):
                runner.execute(self.project,plan,'smoke',output)
        self.assertEqual(sentinel.read_text(),'preserve')

    def test_recovered_manifest_with_wrong_example_count_is_rejected(self):
        plan = runner.preflight(self.project,self.inputs)
        output = self.root/'wrong-count';output.mkdir()
        settings = SyntheticSettings(generator_version='v2',diagnostic=True,count=1,seed=20261107,
            experiment_id='refinement-comparison',symbols=runner.SYMBOLS,
            profiles={s:plan['profiles'][s+'|full'] for s in runner.SYMBOLS},output=output/'full-20261107')
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

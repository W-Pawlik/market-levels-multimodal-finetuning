"""Nowe seedy: cztery grupy, osobne raporty i wznowienie małej próby."""
from copy import deepcopy
import json
from pathlib import Path, PureWindowsPath
import shutil
import subprocess
import unittest
from unittest.mock import patch

from market_levels.experiments.refinement.workflows import runner
from market_levels.cli import refinement_comparison as runner_cli
from market_levels.experiments.refinement.workflows import preflight as runner_preflight
from market_levels.experiments.refinement import config as runner_config, paths as runner_paths, io as runner_io
from market_levels.experiments.refinement.domain import plan as runner_plan
from support.refinement import prepare_runner_fixture


class FreshSeedsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Tylko fixture setup, bez dziedziczenia i powielania dawnych testów.
        prepare_runner_fixture(cls)
        cls.fresh_options = deepcopy(cls.options)
        cls.fresh_options['baseline_profiles'] = {
            s+'|'+family: str(cls.root/(s+suffix))
            for s in runner_config.SYMBOLS for family,suffix in (('v1','-v1.json'),('original','-original.json'))}
        cls.fresh_inputs = cls.root/'fresh-inputs.json'
        cls.fresh_inputs.write_text(json.dumps(cls.fresh_options),encoding='utf-8')

    def test_full_plan_is_960_and_smoke_is_32_without_running_full(self):
        tasks = runner_plan.experiment_tasks('full',fresh=True)
        self.assertEqual(len(tasks),8)
        self.assertEqual({t['seed'] for t in tasks},{20261201,20261211})
        self.assertEqual({t['family'] for t in tasks},{'v1','original','full','bridge_volatility'})
        self.assertEqual(sum(t['count']*2 for t in tasks),960)
        self.assertEqual(sum(t['count']*2 for t in runner_plan.experiment_tasks('smoke',fresh=True)),32)
        # Dotychczasowy eksperyment nadal generuje tylko dwie nowe grupy.
        self.assertEqual(sum(t['count']*2 for t in runner_plan.experiment_tasks('full')),720)

    def test_preflight_binds_all_eight_profiles_and_rejects_wrong_baseline(self):
        plan = runner_preflight.preflight(self.project,self.fresh_inputs,fresh=True)
        self.assertEqual(len(plan['profiles']),8)
        self.assertEqual(plan['seeds'],[20261201,20261211])
        self.assertEqual(plan['experiment'],runner_config.FRESH_EXPERIMENT)
        wrong = deepcopy(self.fresh_options)
        wrong['baseline_profiles']['BTCUSDT|original'] = wrong['profiles']['BTCUSDT|full']
        path = self.root/'wrong-baseline.json';path.write_text(json.dumps(wrong),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'bazowy'):
            runner_preflight.preflight(self.project,path,fresh=True)
        with self.assertRaises(ValueError):runner_preflight.preflight(self.project,self.fresh_inputs)

    def test_fresh_windows_path_budget(self):
        root = PureWindowsPath('D:/rf/new')
        self.assertLess(runner_paths.validate_output_paths(root,'full',fresh=True),260)
        path = runner_paths.longest_output_path(root,'full',fresh=True)
        self.assertTrue(any(str(seed) in str(path) for seed in runner_config.FRESH_SEEDS))
        delta = 260-len(str(path))
        long_root = PureWindowsPath('D:/rf')/('new'+'x'*delta)
        with self.assertRaisesRegex(ValueError,'OutputDirectory'):
            runner_paths.validate_output_paths(long_root,'smoke',fresh=True)

    def test_native_fresh_check_only_from_other_working_directory(self):
        ps = shutil.which('powershell')
        if not ps:self.skipTest('Windows PowerShell niedostępny')
        result = subprocess.run([ps,'-NoProfile','-ExecutionPolicy','Bypass','-File',
            str(self.project/'scripts/run_refinement_fresh_seeds.ps1'),'-CheckOnly','-InputsFile',str(self.fresh_inputs)],
            cwd=self.root,capture_output=True,text=True,errors='replace')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('20261201/20261211',result.stdout)

    def test_smoke_interrupt_resume_four_groups_and_no_old_seed_mixing(self):
        plan = runner_preflight.preflight(self.project,self.fresh_inputs,fresh=True)
        before = {p:runner.sha(Path(p)) for p in plan['digests']}
        root = self.root/'rf';root.mkdir()
        original = runner.cli
        def interrupted(module,args,project,log=None):
            original(module,args,project,log)
            if module=='generate_synthetic':raise RuntimeError('published then interrupted')
        with patch.object(runner,'cli',side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError,'interrupted'):
                runner.execute(self.project,plan,'smoke',root)
        with patch.object(runner,'cli',wraps=original) as calls:
            runner.execute(self.project,plan,'smoke',root)
        self.assertEqual(sum(c.args[0]=='generate_synthetic' for c in calls.call_args_list),7)
        self.assertEqual(len(list(root.rglob('manifest.json'))),8)
        self.assertEqual(len(list((root/'comparisons').rglob('*_comparison.json'))),16)
        for symbol in runner_config.SYMBOLS:
            report = runner_io.checked_report(next((root/'summary'/symbol).rglob('*_comparison.json')))
            self.assertEqual(set(report['variants']),{'V1','V2-full-original','V2-full-refined','V2-bridge_volatility-refined'})
            self.assertTrue(all(v['run_count']==2 for v in report['variants'].values()))
            self.assertEqual({r['master_seed'] for r in report['reports']},set(runner_config.FRESH_SEEDS))
            focus = (root/'summary'/symbol/'STABILITY.md').read_text(encoding='utf-8')
            for metric in ('abs_ac1','window_std_mean','window_std_std','abs_q99','body_fraction','relative_range_mean'):
                self.assertIn(metric,focus)
            self.assertIn('20261201, 20261211',focus)
        with patch.object(runner,'cli',side_effect=AssertionError('must reuse all results')):
            runner.execute(self.project,plan,'smoke',root)
        self.assertEqual({p:runner.sha(Path(p)) for p in before},before)
        from market_levels.data_processing.synthetic.workflows.summary import build_variant_summary
        def mixed(*args,**kwargs):
            value = build_variant_summary(*args,**kwargs)
            value['reports'][0]['master_seed'] = 20261105
            return value
        with patch('market_levels.data_processing.synthetic.workflows.summary.build_variant_summary',side_effect=mixed):
            with self.assertRaisesRegex(ValueError,'tylko obu nowych'):
                runner.execute(self.project,plan,'smoke',root)

"""Kalibracja, profile, warianty i wspólne raporty na małych danych offline."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from market_levels.core.candles import UTC
from market_levels.data_processing.storage import write_candles_csv
from market_levels.data_processing.pipelines.synthetic import run, prepare_profiles
from market_levels.data_processing.pipelines.compare_synthetic import build_comparison, save_comparison
from market_levels.data_processing.synthetic.calibration import load_profile, save_profile, calibrate_csv
from market_levels.data_processing.synthetic.calibration_v2 import CalibrationV2Settings, calibrate_v2_csv
from market_levels.data_processing.synthetic.comparison import load_synthetic_windows
from market_levels.data_processing.synthetic.experiments import build_variant_summary, variant_summary_markdown
from market_levels.data_processing.synthetic.settings import SyntheticSettings, load_synthetic_settings
from market_levels.data_processing.synthetic.training_period import load_chronological_split
from market_levels.data_processing.synthetic.v2_parameters import VARIANTS
from unit.test_synthetic_comparison import CONFIG, real_fixture


def small_search():
    return CalibrationV2Settings(simulation_seeds=[91,92],selection_seed=93,examples_per_seed=1,rounds=1,
        bridge_gamma=[1,1.8],tail_probability=[0,.05],tail_scale=[3],
        volatility_phi=[.8,.95],volatility_stationary_std=[.2])


class V2PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.csv=self.root/'real.csv'; self.candles=real_fixture()
        write_candles_csv(self.csv,self.candles)
        self.split=load_chronological_split(CONFIG)
        self.start,self.end=self.split.periods['train']
        self.settings=SyntheticSettings(generator_version='v2',diagnostic=True,count=2,symbols=('BTCUSDT',))

    def calibrated(self):
        return calibrate_v2_csv(self.csv,'BTCUSDT',start=self.start,end=self.end,split=self.split,
                                settings=self.settings,search=small_search())

    def report(self,manifest):
        return build_comparison(symbol='BTCUSDT',real_csv=self.csv,synthetic_manifest=manifest,
            start=self.start,end=self.end,count=2,selection_seed=13,split=self.split)

    def test_calibration_reproduction_provenance_audit_and_safe_save(self):
        profile=self.calibrated()
        self.assertEqual(profile,self.calibrated())
        self.assertEqual((profile['version'],profile['status'],profile['generator_version']),(2,'unapproved','2.0.0'))
        self.assertEqual(profile['source']['chronological_split'],self.split.document())
        self.assertGreater(len(profile['calibration']['trials']),2)
        self.assertEqual(profile['v2_parameters'],profile['calibration']['selected_parameters'])
        self.assertEqual(profile['calibration']['simulation_seeds'],[91,92])
        path=self.root/'v2.json'; save_profile(path,profile)
        self.assertEqual(load_profile(path,symbol='BTCUSDT'),profile)
        with self.assertRaises(FileExistsError): save_profile(path,profile)
        with self.assertRaises(ValueError): load_profile(path,symbol='ETHUSDT')
        corrupt=deepcopy(profile); corrupt['calibration']['selected_loss']+=1
        with self.assertRaises(ValueError): save_profile(self.root/'corrupt.json',corrupt)

    def test_future_prices_do_not_change_fit_and_outside_training_is_rejected(self):
        first=self.calibrated()
        future=real_fixture(20,datetime(2024,1,1,tzinfo=UTC))
        future=[replace(c,open=Decimal(9999),close=Decimal(9999),high=Decimal(10000),low=Decimal(9998)) for c in future]
        write_candles_csv(self.csv,self.candles+future)
        second=self.calibrated()
        self.assertEqual(first['v2_parameters'],second['v2_parameters'])
        self.assertEqual(first['calibration'],second['calibration'])
        self.assertEqual(first['statistics'],second['statistics'])
        self.assertNotEqual(first['source']['sha256'],second['source']['sha256'])
        with self.assertRaises(ValueError):
            calibrate_v2_csv(self.csv,'BTCUSDT',start=self.start,end=future[-1].timestamp,
                split=self.split,settings=self.settings,search=small_search())

    def test_every_variant_roundtrip_report_and_version_checks(self):
        profile=self.calibrated(); path=self.root/'profile.json';save_profile(path,profile)
        for variant in VARIANTS:
            settings=replace(self.settings,v2_variant=variant,profiles={'BTCUSDT':str(path)},output=self.root/variant)
            manifest=run(settings)/'manifest.json'
            windows,metadata=load_synthetic_windows(manifest,symbol='BTCUSDT',count=2,split=self.split)
            self.assertEqual(len(windows),2)
            self.assertEqual(metadata['variant'],variant)
            self.assertEqual(metadata['generator_version'],'2.0.0')
            report=self.report(manifest)
            self.assertEqual(report['real']['window_count'],2)
            with self.assertRaises(FileExistsError): run(settings)
        with self.assertRaises(ValueError):
            prepare_profiles(replace(self.settings,generator_version='v1',profiles={'BTCUSDT':str(path)}))
        with self.assertRaises(ValueError):
            prepare_profiles(replace(self.settings,diagnostic=False,profiles={'BTCUSDT':str(path)}))

    def test_summary_same_reference_and_metric_error_directions(self):
        profile=self.calibrated();path=self.root/'v2.json';save_profile(path,profile)
        old=calibrate_csv(self.csv,'BTCUSDT',allowed_start=self.start,allowed_end=self.end)
        oldpath=self.root/'v1.json';save_profile(oldpath,old)
        v1=run(SyntheticSettings(diagnostic=True,count=2,symbols=('BTCUSDT',),profiles={'BTCUSDT':str(oldpath)},output=self.root/'v1'))/'manifest.json'
        paths=[save_comparison(self.root/'reports',self.report(v1))/'BTCUSDT_comparison.json']
        for variant in VARIANTS:
            manifest=run(replace(self.settings,v2_variant=variant,profiles={'BTCUSDT':str(path)},output=self.root/variant))/'manifest.json'
            paths.append(save_comparison(self.root/'reports',self.report(manifest))/'BTCUSDT_comparison.json')
        summary=build_variant_summary(paths,symbol='BTCUSDT')
        self.assertEqual(len(summary['variants']),1+len(VARIANTS))
        self.assertEqual(summary,build_variant_summary(paths,symbol='BTCUSDT'))
        self.assertIn('| Realne | V1 | V2-base |',variant_summary_markdown(summary))
        for variant in summary['variants'].values():
            metric=variant['metrics']['return_std']
            self.assertAlmostEqual(metric['mean_absolute_error'],abs(metric['difference']))
            self.assertIn(metric['error_direction'],('decreased','increased','unchanged'))
        with self.assertRaises(ValueError): build_variant_summary(paths[1:],symbol='BTCUSDT')
        with self.assertRaises(ValueError): build_variant_summary(paths+[paths[0]],symbol='BTCUSDT')
        with self.assertRaises(ValueError): build_variant_summary(paths,symbol='ETHUSDT')
        second_manifest=run(replace(self.settings,seed=20261104,profiles={'BTCUSDT':str(path)},
                                    output=self.root/'second-seed'))/'manifest.json'
        second_report=self.report(second_manifest)
        second_path=save_comparison(self.root/'reports',second_report)/'BTCUSDT_comparison.json'
        multi=build_variant_summary(paths+[second_path],symbol='BTCUSDT')
        self.assertEqual(multi['variants']['V2-full']['run_count'],2)
        metric=multi['variants']['V2-full']['metrics']['return_std']
        self.assertGreater(metric['std_between_seeds'],0)
        self.assertGreaterEqual(metric['mean_absolute_error']+1e-15,abs(metric['difference']))
        other_reference=build_comparison(symbol='BTCUSDT',real_csv=self.csv,synthetic_manifest=second_manifest,
            start=self.start,end=self.end,count=2,selection_seed=14,split=self.split)
        wrong_path=save_comparison(self.root/'reports',other_reference)/'BTCUSDT_comparison.json'
        with self.assertRaisesRegex(ValueError,'identycznych'):
            build_variant_summary([paths[0],wrong_path],symbol='BTCUSDT')
        command=[sys.executable,'-X','utf8','-m','market_levels.cli.compare_synthetic','--symbol','BTCUSDT',
                 '--reports',*(str(p) for p in paths),'--output',str(self.root/'summary')]
        result=subprocess.run(command+['--dry-run'],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse((self.root/'summary').exists())
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr)

    def test_cli_version_selection_dry_run_and_metadata_tampering(self):
        settings=load_synthetic_settings(CONFIG,generator_version='v2',diagnostic=True)
        self.assertEqual(settings.generator_version,'v2')
        output=self.root/'cli'
        args=[sys.executable,'-X','utf8','-m','market_levels.cli.generate_synthetic','--config',str(CONFIG),
              '--diagnostic','--generator-version','v2','--v2-variant','bridge','--count','1',
              '--symbols','BTCUSDT','--output',str(output)]
        result=subprocess.run(args+['--dry-run'],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr);self.assertFalse(output.exists())
        result=subprocess.run(args,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr)
        manifest=next(output.glob('diagnostics/*/manifest.json'))
        # Ręczny profil nie jest podstawą empirycznego porównania.
        with self.assertRaises(ValueError):load_synthetic_windows(manifest,symbol='BTCUSDT',count=1,split=self.split)

    def test_empirical_v2_metadata_and_trace_tampering_is_rejected(self):
        profile=self.calibrated();path=self.root/'v2.json';save_profile(path,profile)
        manifest=run(replace(self.settings,profiles={'BTCUSDT':str(path)},output=self.root/'runs'))/'manifest.json'
        document=json.loads(manifest.read_text(encoding='utf-8'))
        metadata_path=manifest.parent/document['examples'][0]['metadata']
        original=json.loads(metadata_path.read_text(encoding='utf-8'))
        for mutate in (lambda m:m['mechanisms'].update(tails=False),
                       lambda m:m['volatility_trace'][0].update(h=100),
                       lambda m:m.update(profile_version=1),
                       lambda m:m['effective_parameters'].update(bridge_gamma=5)):
            metadata=deepcopy(original);mutate(metadata)
            metadata_path.write_text(json.dumps(metadata),encoding='utf-8')
            with self.assertRaises(ValueError):
                load_synthetic_windows(manifest,symbol='BTCUSDT',count=2,split=self.split)
        metadata_path.write_text(json.dumps(original),encoding='utf-8')
        invalid=deepcopy(document);invalid['rejected_count']=-1
        manifest.write_text(json.dumps(invalid),encoding='utf-8')
        with self.assertRaises(ValueError):
            load_synthetic_windows(manifest,symbol='BTCUSDT',count=2,split=self.split)
        document['identity']['generator_version']='1.0.0'
        document['run_id']=hashlib.sha256(json.dumps(document['identity'],sort_keys=True,allow_nan=False).encode()).hexdigest()[:24]
        manifest.write_text(json.dumps(document),encoding='utf-8')
        with self.assertRaises(ValueError):
            load_synthetic_windows(manifest,symbol='BTCUSDT',count=2,split=self.split)

    def test_search_configuration_requires_multiple_seeds_and_stable_process(self):
        for search in (replace(small_search(),simulation_seeds=[1]),replace(small_search(),simulation_seeds=[1,1]),
                       replace(small_search(),volatility_phi=[1]),replace(small_search(),rounds=4)):
            with self.assertRaises(ValueError):search.validate()

    def test_calibration_cli_v2_without_overwriting_v1(self):
        config=json.loads(CONFIG.read_text(encoding='utf-8'))
        config['synthetic_v2_calibration']=deepcopy(small_search().__dict__)
        configpath=self.root/'config.json';configpath.write_text(json.dumps(config),encoding='utf-8')
        path=self.root/'profile.json'
        command=[sys.executable,'-X','utf8','-m','market_levels.cli.calibrate_synthetic','--config',str(configpath),
                 '--generator-version','v2','--symbol','BTCUSDT','--input',str(self.csv),
                 '--start',self.start.isoformat(),'--end',self.end.isoformat(),'--output',str(path)]
        result=subprocess.run(command+['--dry-run'],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr);self.assertFalse(path.exists())
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(load_profile(path)['version'],2)
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
        self.assertNotEqual(result.returncode,0)

"""Renderer contracts and quantitative audit, without network or local market data."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_levels.core.ohlc.model import Candle, CANDLE_DELTA, UTC
from market_levels.data_processing.io.candles import write_candles_csv
from market_levels.shared.json_io import write_json
from market_levels.data_processing.synthetic.domain.profiles.v1 import profile_hash
from market_levels.data_processing.synthetic.domain.generation.seeds import example_seed
from market_levels.core.ohlc.identity import canonical_hash
from market_levels.shared.integrity import SourceLedger
from market_levels.charts.domain.metrics import fit_thresholds, movement, window_metrics
from market_levels.data_processing.windows.io.training_csv import read_training_csv
from market_levels.charts.domain.diversity import summarize
from market_levels.data_processing.windows.domain.candidates import training_windows
from market_levels.charts.io.audit_sources import discover_batches, read_synthetic
from market_levels.charts.domain.selection import select_pilot, tags
from market_levels.charts.workflows.audit import run_audit
from market_levels.charts.io.rendering import build_figure, render_window
from market_levels.charts.domain.validation import validate_window
from market_levels.shared.paths import require_short_path

from support.charts import fixture




class RendererTests(unittest.TestCase):
    def test_exact_dimensions_determinism_sha_and_exclusive_write(self):
        from PIL import Image
        candles = fixture()
        before = deepcopy(candles)
        with tempfile.TemporaryDirectory() as directory:
            a,b = Path(directory)/"a.png", Path(directory)/"b.png"
            meta = render_window(candles,a)
            render_window(candles,b)
            self.assertEqual(a.read_bytes(),b.read_bytes())
            with Image.open(a) as image:
                self.assertEqual(image.size,(1024,768))
                self.assertEqual(image.format,"PNG")
                self.assertNotIn("sensitive-origin-id",str(image.info))
            self.assertEqual(meta['png_sha256'],hashlib.sha256(a.read_bytes()).hexdigest())
            self.assertEqual(meta['ohlc_sha256'],canonical_hash(candles))
            self.assertEqual(meta['candle_count'],120)
            payload = a.read_bytes()
            with self.assertRaises(FileExistsError): render_window(candles,a)
            self.assertEqual(a.read_bytes(),payload)
        self.assertEqual(candles,before)

    def test_artists_contain_exactly_candles_generic_axes_and_no_target_lines(self):
        from matplotlib.text import Text
        candles = fixture()
        fig = build_figure(candles)
        try:
            fig.canvas.draw()
            ax = fig.axes[0]
            self.assertEqual(len(ax.patches),120)
            self.assertEqual(len(ax.lines),0)
            self.assertEqual(len(ax.collections),1)
            self.assertEqual(len(ax.collections[0].get_segments()),120)
            for i, (segment,candle,body) in enumerate(zip(ax.collections[0].get_segments(),candles,ax.patches),1):
                self.assertEqual(list(segment[:,0]),[i,i])
                self.assertEqual(list(segment[:,1]),[float(candle.low),float(candle.high)])
                self.assertAlmostEqual(body.get_y(),min(float(candle.open),float(candle.close)))
                self.assertAlmostEqual(body.get_height(),abs(float(candle.close)-float(candle.open)))
            texts = {t.get_text() for t in fig.findobj(Text) if t.get_text()}
            allowed = {'Candle position','Price (USDT)'}
            for text in texts-allowed:
                float(text.replace('−','-'))
            self.assertFalse(any(line.get_visible() for line in ax.get_xgridlines()+ax.get_ygridlines()))
        finally:
            fig.clear()

    def test_pixels_ignore_source_identifiers_and_simulation_dates(self):
        candles = fixture()
        other = [replace(c,timestamp=c.timestamp.replace(year=2000),source_archive='synthetic:full:secret:seed') for c in candles]
        with tempfile.TemporaryDirectory() as directory:
            a,b = Path(directory)/'a.png',Path(directory)/'b.png'
            render_window(candles,a);render_window(other,b)
            self.assertEqual(a.read_bytes(),b.read_bytes())

    def test_count_order_duplicates_and_gaps_rejected(self):
        candles = fixture(121)
        for bad in (candles, candles[:119], list(reversed(candles[:120])),
                    candles[:30]+candles[31:], candles[:30]+[candles[29]]+candles[31:120]):
            with self.subTest(length=len(bad)), self.assertRaises(ValueError): validate_window(bad)

    def test_invalid_ohlc_finiteness_positive_and_timestamp_rejected(self):
        candles = fixture()
        bad_values = [dict(low=Decimal('500')),dict(high=Decimal('1')),
                      dict(open=Decimal('0')),dict(close=Decimal('-1')),
                      dict(close=Decimal('NaN')),dict(high=Decimal('Infinity')),
                      dict(timestamp=datetime(2020,1,1)),dict(timestamp=datetime(2020,1,1,1,tzinfo=UTC))]
        for change in bad_values:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_window([replace(candles[0],**change)]+candles[1:])

    def test_long_paths_rejected_before_writing(self):
        with self.assertRaisesRegex(ValueError,'260'):
            require_short_path(Path('x'*260)/'plot.png')


class DiversityTests(unittest.TestCase):
    def test_known_metrics_and_body_wick_shares(self):
        start = datetime(2020,1,1,tzinfo=UTC)
        candles = [Candle(start+i*CANDLE_DELTA,Decimal(100+i),Decimal(102+i),Decimal(99+i),Decimal(101+i),'fixture') for i in range(120)]
        m = window_metrics(candles,{'volatility_q33':1,'volatility_q67':2,'range_q95':.02,'abs_return_q99':.5})
        self.assertAlmostEqual(m['price_change'],1.2)
        self.assertAlmostEqual(m['relative_range'],1.22)
        self.assertEqual(m['directionality'],1)
        self.assertEqual(m['volatility_band'],'low')
        self.assertEqual(m['extreme_move_share'],0)
        self.assertAlmostEqual(m['large_candle_share'],51/120)
        for k in ('body_fraction','upper_wick_fraction','lower_wick_fraction'):
            self.assertAlmostEqual(m[k],1/3)

    def test_all_flat_prices_have_defined_metrics_and_missing_fractions(self):
        candles = [replace(c,open=Decimal(100),high=Decimal(100),low=Decimal(100),close=Decimal(100)) for c in fixture()]
        m = window_metrics(candles)
        self.assertEqual(m['flat_candles'],120)
        self.assertIsNone(m['body_fraction'])
        self.assertEqual(m['directionality'],0)
        self.assertEqual(m['log_return_std'],0)

    def test_training_parser_never_parses_future_ohlc(self):
        candles = fixture(240)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'source.csv'
            write_candles_csv(path,candles)
            with path.open('a',encoding='utf8') as stream:
                stream.write('2024-01-01T00:00:00+00:00,FORBIDDEN,FUTURE,OHLC,NaN\n')
            payload = path.read_bytes()
            train = read_training_csv(path,candles[0].timestamp,candles[-1].timestamp)
            self.assertEqual(len(train),240)
            self.assertEqual(fit_thresholds(train)['reference_window_count'],2)
            self.assertEqual(path.read_bytes(),payload)

    def test_windows_skip_real_gap_without_interpolation(self):
        candles = fixture(361)
        damaged = candles[:120]+candles[121:]
        windows,gaps = training_windows(damaged)
        self.assertEqual(gaps,1)
        self.assertEqual(len(windows),3)
        for _, window in windows:
            validate_window(window)
        self.assertEqual(windows[1][1][0],candles[121])

    def test_regime_counts_shares_transitions_and_direction_agreement(self):
        def r(kind,length,matches=None):
            return dict(kind=kind,length=length,declared_direction_matches=matches)
        metrics = window_metrics(fixture(),{'volatility_q33':1,'volatility_q67':2,'range_q95':1,'abs_return_q99':1})
        records = [{'master_seed':1,'metrics':metrics,'regimes':[r('consolidation',120)]},
                   {'master_seed':2,'metrics':metrics,'regimes':[r('consolidation',40),r('breakout',20),r('uptrend',60,False)]}]
        s = summarize(records)
        self.assertEqual(s['regime_count'],{'1':1,'2':0,'3':1})
        self.assertEqual(s['regime_occurrences']['consolidation'],2)
        self.assertEqual(s['candle_counts']['consolidation'],160)
        self.assertAlmostEqual(s['candle_shares']['consolidation'],2/3)
        self.assertAlmostEqual(sum(s['candle_shares'].values()),1)
        self.assertEqual(s['transitions']['consolidation -> breakout'],1)
        self.assertEqual(s['consolidation_breakout_trend'],1)
        self.assertEqual(s['declared_segment_direction_agreement']['uptrend']['opposite_or_flat'],1)
        self.assertEqual(s['regime_lengths']['consolidation']['histogram'],{40:1,120:1})

    def test_selection_seed_order_independence_and_coverage(self):
        metrics = window_metrics(fixture(),{'volatility_q33':1,'volatility_q67':2,'range_q95':1,'abs_return_q99':1})
        records = [dict(id=str(i),ohlc_sha256=str(i),source='real',metrics=metrics) for i in range(40)]
        a = select_pilot(records,8,42)
        self.assertEqual(a,select_pilot(list(reversed(records)),8,42))
        self.assertNotEqual(a,select_pilot(records,8,43))
        self.assertEqual(len({r['id'] for r in a}),8)
        with self.assertRaises(ValueError): select_pilot(records+records[:1],8,42)

    def test_source_ledger_detects_changes_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'input.csv';path.write_bytes(b'original')
            ledger = SourceLedger();ledger.track(path)
            self.assertTrue(ledger.verify()['unchanged'])
            self.assertEqual(path.read_bytes(),b'original')
            path.write_bytes(b'user-change')
            with self.assertRaises(ValueError): ledger.verify()
            self.assertEqual(path.read_bytes(),b'user-change')

    def test_discovery_reports_missing_smoke_and_rejects_ambiguous_batches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = {'calibration':{'method':'volatility_refinement_v1','variant':'full'}}
            def save(name,count):
                path = root/name;path.mkdir()
                (path/'manifest.json').write_text(json.dumps({'identity':{'configuration':{'seed':20261105,'generator_version':'v2','v2_variant':'full'},'profiles':{'BTCUSDT':profile,'ETHUSDT':profile}},'examples':[{}]*count}),encoding='utf8')
            save('full',120);save('smoke',4)
            selected,info = discover_batches(root,SourceLedger())
            self.assertEqual(len(selected),1)
            self.assertEqual(len(info['missing_seeds']),4)
            self.assertEqual(info['excluded_batches'][0]['count'],4)
            save('ambiguous',120)
            with self.assertRaisesRegex(ValueError,'Niejednoznaczne'): discover_batches(root,SourceLedger())

    def test_output_collision_and_data_directory_rejected_before_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            args = dict(synthetic_root=Path(directory)/'synthetic',real_csv={},config=Path('absent'))
            with self.assertRaises(FileExistsError): run_audit(output=Path(directory),**args)
            with self.assertRaises(ValueError): run_audit(output=Path('data/charts/disallowed-new'),**args)

    def test_synthetic_identity_hash_regime_and_missing_files_checks(self):
        # Isolate manifest validation; the complete refinement profile validator has
        # its own regression suite and is called once per profile by this reader.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'batch';root.mkdir()
            symbol, master = 'BTCUSDT', 20261105
            seed = example_seed(master,symbol,0)
            identifier = f'{symbol}_000000_{seed:064x}'
            profile = dict(symbol=symbol,status='unapproved',version=2,generator_version='2.0.0',
                           estimation_kind='training',v2_parameters={})
            config = dict(seed=master,count=1,diagnostic=True,profiles={symbol:str(root/'absent-profile.json')})
            candles = fixture()
            regimes = [dict(kind='consolidation',length=120,start=0,end_exclusive=120,
                            mu=0,sigma=.01,mean_reversion=.1,center_log_price=4)]
            shares = dict(uptrend=0.,downtrend=0.,consolidation=1.,breakout=0.)
            entry = dict(id=identifier,symbol=symbol,seed=seed,csv='source.csv',metadata='meta.json',
                         ohlc_sha256=canonical_hash(candles),regime_shares=shares)
            meta = dict(entry,calibration_profile=profile,profile_sha256=profile_hash(profile),status='diagnostic',
                        origin='synthetic',generator_version='2.0.0',v2_variant='full',configuration=dict(config,output='unused'),
                        effective_parameters={},roundtrip_valid=True,regimes=regimes)
            manifest = dict(run_id='batch',status='diagnostic',origin='synthetic',accepted_count=1,rejected_count=0,
                            identity=dict(configuration=config,profiles={symbol:profile}),examples=[entry])
            write_candles_csv(root/'source.csv',candles)
            write_json(root/'meta.json',meta)
            before = (root/'source.csv').read_bytes()
            with patch('market_levels.charts.io.audit_sources.validate_profile_v2') as validator:
                records,errors,complete = read_synthetic([(root/'manifest.json',manifest)],SourceLedger())
                validator.assert_called_once()
                self.assertEqual(len(records),1);self.assertEqual(errors,[])
                self.assertEqual(complete[0]['analyzed'],1)
                mutations = [lambda m:m.update(seed=1),lambda m:m.update(ohlc_sha256='0'*64),
                             lambda m:m.update(v2_variant='bridge'),lambda m:m.update(profile_sha256='0'*64),
                             lambda m:m['regimes'][0].update(length=119),lambda m:m.update(status='candidate')]
                for mutate in mutations:
                    changed = deepcopy(meta);mutate(changed);write_json(root/'meta.json',changed)
                    good,bad,_ = read_synthetic([(root/'manifest.json',manifest)],SourceLedger())
                    self.assertEqual(good,[]);self.assertEqual(len(bad),1)
                write_json(root/'meta.json',meta)
                missing = deepcopy(manifest);missing['examples'][0]['csv']='absent.csv'
                good,bad,complete = read_synthetic([(root/'manifest.json',missing)],SourceLedger())
                self.assertEqual(good,[]);self.assertEqual(len(bad),1)
                self.assertEqual(len(complete[0]['missing_symbol_indices']),2)
            self.assertEqual((root/'source.csv').read_bytes(),before)

    def test_profile_failure_excludes_examples(self):
        manifest = dict(identity=dict(configuration=dict(seed=20261105,count=1),profiles={'BTCUSDT':{}}),examples=[])
        with patch('market_levels.charts.io.audit_sources.validate_profile_v2',side_effect=ValueError('invalid')):
            records,errors,complete = read_synthetic([(Path('not-written/manifest.json'),manifest)],SourceLedger())
            self.assertEqual(records,[])
            self.assertEqual(complete[0]['analyzed'],0)
            self.assertIn('invalid',complete[0]['batch_errors'][0])


if __name__ == '__main__':
    unittest.main()

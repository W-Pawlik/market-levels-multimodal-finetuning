"""Official CLI test/compare/verify on two newly created synthetic references."""
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

from market_levels.cli.evaluate import main
from market_levels.core.ohlc.model import Candle
from market_levels.core.ohlc.identity import canonical_hash
from market_levels.data_processing.io.candles import write_candles_csv
from market_levels.datasets.domain.examples import INSTRUCTION
from market_levels.shared.integrity import sha256_file
from market_levels.shared.manifests import seal
from market_levels.shared.publication import _cleanup
from market_levels.evaluation.protocol import PROTOCOL_SHA256
from market_levels.evaluation.workflows.verification import read_evaluation, read_comparison


class FinalEvaluationFixtureTests(unittest.TestCase):
    def test_official_cli_test_compare_verify_and_pair_invariants(self):
        with tempfile.TemporaryDirectory(prefix='final-fixture-') as tmp:
            root=Path(tmp);dataset=root/'synthetic-dataset'
            for sub in ['splits','labels','ohlc','metadata']:(dataset/sub).mkdir(parents=True)
            entries=[];rows=[]
            start=datetime(2000,1,1,tzinfo=timezone.utc)
            candles=[Candle(start+timedelta(hours=4*i),Decimal(100),Decimal(102),Decimal(98),Decimal(100),'manual_fixture') for i in range(120)]
            for number,symbol in enumerate(['BTCUSDT','ETHUSDT']):
                identity=f'final46-synthetic-{number}'
                entry={'id':identity,'symbol':symbol,'source':'manual_fixture','split':'test','image':None,
                       'ohlc':f'ohlc/{identity}.csv','label':f'labels/{identity}.json','metadata':f'metadata/{identity}.json'}
                answer={'supports':[100],'resistances':[]}
                (dataset/entry['label']).write_text(json.dumps(answer),encoding='utf-8')
                write_candles_csv(dataset/entry['ohlc'],candles)
                meta={**entry,'ohlc_sha256':canonical_hash(candles),'csv_sha256':sha256_file(dataset/entry['ohlc']),
                      'label_sha256':sha256_file(dataset/entry['label'])}
                (dataset/entry['metadata']).write_text(json.dumps(meta),encoding='utf-8')
                entries.append(entry);rows.append({'id':identity,'split':'test','image':None,'instruction':INSTRUCTION,'answer':answer})
            (dataset/'splits/test.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            seal(dataset,{'kind':'evaluation_fixture_dataset','status':'manual_fixture','count':2,'entries':entries})
            output=Path('results/diagnostics')/root.name
            output.mkdir(parents=True)
            try:
                for variant in ['a','b']:
                    response='```json\n{"supports":[100],"resistances":[]}\n```' if variant=='a' else '{"supports":[100],"resistances":[]}'
                    predictions=root/f'{variant}.jsonl';predictions.write_text(''.join(json.dumps({'id':r['id'],'response':response})+'\n' for r in rows),encoding='utf-8')
                    run={'run_id':f'fixture-{variant}','model_id':'synthetic-model','checkpoint_id':variant,
                         'variant':'technical_fixture','protocol_version':'sr-eval-v1','instruction_version':'pl-sr-v1',
                         'inference':{'base_revision':'synthetic-revision','generation':{'do_sample':False}},
                         'prediction_kind':'technical_fixture','dataset_manifest_sha256':sha256_file(dataset/'manifest.json'),'split':'test'}
                    manifest=root/f'{variant}.json';manifest.write_text(json.dumps(run),encoding='utf-8')
                    args=['evaluate','--dataset',str(dataset),'--split','test','--predictions',str(predictions),
                          '--run-manifest',str(manifest),'--output',str(output/variant)]
                    self.assertEqual(main(args),0)
                    self.assertEqual(main(['verify','--output',str(output/variant)]),0)
                self.assertEqual(main(['compare','--baseline',str(output/'a'),'--candidate',str(output/'b'),'--output',str(output/'comparison')]),0)
                self.assertEqual(main(['verify','--output',str(output/'comparison')]),0)
                a=read_evaluation(output/'a');b=read_evaluation(output/'b')
                self.assertEqual(a['summary']['tolerances']['0.5']['overall']['valid_json_count'],0)
                self.assertEqual(b['summary']['tolerances']['0.5']['overall']['tp'],2)
                self.assertEqual(len(read_comparison(output/'comparison')['paired_examples']),2)
                self.assertEqual(PROTOCOL_SHA256,'dafd622fc17e78fe9e095d0849b4a4ae1f8a748d203a3b8fa48a373e4b3ccf58')
                # Missing, duplicate and unknown predictions never publish an official result.
                for label,pred in [('missing',rows[:1]),('duplicate',[rows[0],rows[0]]),('unknown',[rows[0],{'id':'unknown'}])]:
                    predictions=root/f'bad-{label}.jsonl'
                    predictions.write_text(''.join(json.dumps({'id':r['id'],'response':'{}'})+'\n' for r in pred),encoding='utf-8')
                    self.assertEqual(main(['evaluate','--dataset',str(dataset),'--split','test','--predictions',str(predictions),
                        '--run-manifest',str(root/'b.json'),'--output',str(output/label)]),2)
                    self.assertFalse((output/label).exists())
            finally:
                # This new, temporary fixture output is the only tree removed by this test.
                assert output.resolve().parent==Path('results/diagnostics').resolve()
                error=_cleanup(output.resolve())
                if error:raise error


if __name__=='__main__':unittest.main()

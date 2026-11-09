"""Manual fixture readback, complete ID gates, atomicity and paired reports."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from market_levels.shared.manifests import seal, verify_files
from market_levels.shared.publication import _cleanup
from market_levels.evaluation.io.inputs import InputError, read_references
from market_levels.evaluation.workflows.evaluate import evaluate
from market_levels.evaluation.workflows.compare import compare
from market_levels.evaluation.workflows.verification import read_evaluation, read_comparison
from market_levels.evaluation.protocol import dumps, loads, PROTOCOL_SHA256
from market_levels.cli.evaluate import main

from support.paths import PROJECT

FIXTURE = (PROJECT / "tests")/'fixtures/evaluation_v1'


class EvaluationPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='evaluation-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inputs = self.root/'inputs'
        shutil.copytree(FIXTURE, self.inputs)
        self.output = Path('results/diagnostics')/self.root.name
        self.output.mkdir(parents=True)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        resolved = self.output.resolve()
        assert resolved.parent == Path('results/diagnostics').resolve()
        error = _cleanup(resolved)
        if error:
            raise error

    def run_case(self, name='a', output=None, split='validation', **overrides):
        args = dict(dataset=self.inputs/'dataset', predictions=self.inputs/f'predictions-{name}.jsonl',
                    run_manifest=self.inputs/f'run-{name}.json', output=output or self.output/name, split=split)
        args.update(overrides)
        return evaluate(**args)

    def modify_predictions(self, transform):
        path = self.inputs/'predictions-a.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows = transform(rows)
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')

    def modify_run(self, name='b', **changes):
        path = self.inputs/f'run-{name}.json'
        obj = json.loads(path.read_text())
        obj.update(changes)
        path.write_text(json.dumps(obj),encoding='utf-8')

    def reseal(self, output):
        doc = json.loads((output/'manifest.json').read_text())
        (output/'manifest.json').unlink()
        (output/'manifest.sha256').unlink()
        doc.pop('files')
        seal(output,doc)

    def test_known_manual_counts_at_all_three_tolerances_and_raw_preservation(self):
        self.run_case()
        r = read_evaluation(self.output/'a')
        expected = {'0.25':(6,7,7), '0.5':(9,4,4), '1.0':(10,3,3)}
        for k, counts in expected.items():
            summary = r['summary']['tolerances'][k]['overall']
            self.assertEqual(tuple(summary[x] for x in ('tp','fp','fn')),counts)
        s = r['summary']['tolerances']['0.5']['overall']
        self.assertLess(abs(s['micro_f1']-Decimal('0.69230769230769230769')),Decimal('1e-20'))
        self.assertLess(abs(s['mean_example_f1']-Decimal('0.58333333333333333333')),Decimal('1e-20'))
        self.assertEqual((s['valid_json_count'],s['duplicate_prices']), (10,1))
        self.assertEqual(s['price_error']['normalized_pairs'],8)
        self.assertEqual(s['price_error']['zero_atr_excluded_pairs'],1)
        self.assertEqual((self.output/'a/predictions.jsonl').read_bytes(),(self.inputs/'predictions-a.jsonl').read_bytes())
        self.assertIn('Nie jest oceną VLM',(self.output/'a/RAPORT.md').read_text(encoding='utf-8'))

    def test_missing_ids_refuse_publication_with_report(self):
        self.modify_predictions(lambda rows: rows[:-1])
        with self.assertRaises(InputError) as error:
            self.run_case()
        self.assertEqual(error.exception.problems['missing_ids'], ['fixture_zero_atr'])
        self.assertFalse((self.output/'a').exists())

    def test_unknown_and_duplicate_ids(self):
        self.modify_predictions(lambda rows: rows+[rows[0],{'id':'unknown','response':'{}'}])
        with self.assertRaises(InputError) as error:
            self.run_case()
        self.assertEqual(error.exception.problems['duplicate_ids'],['fixture_exact'])
        self.assertEqual(error.exception.problems['unknown_ids'],['unknown'])

    def test_mixed_train_and_test_ids_refused(self):
        self.modify_predictions(lambda rows: rows+[{'id':'fixture_train_guard','response':'{}'}, {'id':'fixture_test_guard','response':'{}'}])
        with self.assertRaises(InputError) as error:
            self.run_case()
        self.assertEqual(error.exception.problems['wrong_split_ids'], {'fixture_train_guard':'train','fixture_test_guard':'test'})

    def test_malformed_outer_jsonl_rows_are_not_model_format_errors(self):
        self.modify_predictions(lambda rows: rows+[{'id':'extra','response':{'supports':[],'resistances':[]}}])
        with self.assertRaises(InputError) as error:
            self.run_case()
        self.assertEqual(len(error.exception.problems['malformed_lines']),1)
        self.assertFalse((self.output/'a').exists())

    def test_prediction_order_does_not_change_metrics_or_example_order(self):
        self.run_case(output=self.output/'original')
        self.modify_predictions(lambda rows:list(reversed(rows)))
        self.run_case(output=self.output/'reversed')
        for name in ('summary.json','per_example.jsonl'):
            self.assertEqual((self.output/'original'/name).read_bytes(),(self.output/'reversed'/name).read_bytes())

    def test_same_inputs_produce_identical_artifacts_and_no_source_writes(self):
        before = {p.relative_to(self.inputs).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.inputs.rglob('*') if p.is_file()}
        self.run_case(output=self.output/'one')
        self.run_case(output=self.output/'two')
        first = {p.name:p.read_bytes() for p in (self.output/'one').iterdir()}
        self.assertEqual(first,{p.name:p.read_bytes() for p in (self.output/'two').iterdir()})
        self.assertEqual(before,{p.relative_to(self.inputs).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.inputs.rglob('*') if p.is_file()})

    def test_overwrite_and_partial_publication_protection(self):
        self.run_case()
        with self.assertRaises(FileExistsError):
            self.run_case()
        with patch('market_levels.evaluation.workflows.evaluate._write', side_effect=RuntimeError('write failure')):
            with self.assertRaises(RuntimeError):
                self.run_case(output=self.output/'failure')
        self.assertFalse((self.output/'failure').exists())
        self.assertEqual(list(self.output.glob('.eval-*')),[])

    def test_pairing_same_examples_reports_correct_delta_and_replays(self):
        self.run_case('a'); self.run_case('b')
        compare(self.output/'a',self.output/'b',self.output/'comparison')
        result = read_comparison(self.output/'comparison')
        self.assertEqual(len(result['paired_examples']),12)
        self.assertEqual(result['candidate']['tolerances']['0.5']['overall']['micro_f1'],1)
        delta = result['delta_candidate_minus_baseline']['tolerances']['0.5']['overall']
        self.assertLess(abs(delta['micro_f1']-Decimal('0.30769230769230769230')), Decimal('1e-20'))
        self.assertEqual(result['prediction_kind'],'technical_fixture')
        self.assertIn('nie porównanie rzeczywistych VLM',(self.output/'comparison/RAPORT.md').read_text(encoding='utf-8'))

    def test_comparison_rejects_different_model_and_inference(self):
        self.run_case('a')
        for i, mutation in enumerate(({'model_id':'different'}, {'inference':{'different':'settings'}})):
            self.modify_run(**mutation)
            self.run_case('b',output=self.output/f'b-{i}')
            with self.assertRaises(ValueError):
                compare(self.output/'a',self.output/f'b-{i}',self.output/f'comparison-{i}')
            self.assertFalse((self.output/f'comparison-{i}').exists())
            self.modify_run(model_id='manual-fixtures-no-vlm', inference={'source':'hand_authored','model_inference_performed':False})

    def test_compare_validation_with_explicit_fixture_test_split_refused(self):
        self.run_case('a')
        self.modify_run(split='test')
        path = self.inputs/'predictions-b.jsonl'
        path.write_text('{"id":"fixture_test_guard","response":"{\\"supports\\":[100],\\"resistances\\":[]}"}\n')
        self.run_case('b',split='test')
        with self.assertRaises(ValueError):
            compare(self.output/'a',self.output/'b',self.output/'bad-pair')

    def test_semantically_modified_summary_rejected_even_after_rehash(self):
        self.run_case()
        path = self.output/'a/summary.json'
        doc = loads(path.read_text(encoding='utf-8'))
        doc['tolerances']['0.5']['overall']['tp'] = 999
        path.write_text(dumps(doc)+'\n',encoding='utf-8')
        self.reseal(self.output/'a')
        with self.assertRaisesRegex(ValueError,'metryki'):
            read_evaluation(self.output/'a')

    def test_protocol_version_and_manifest_hash_protection(self):
        self.run_case()
        path = self.output/'a/manifest.json'
        doc = json.loads(path.read_text())
        doc['protocol_version'] = 'other'
        path.write_text(json.dumps(doc))
        (self.output/'a/manifest.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest()+'\n')
        with self.assertRaisesRegex(ValueError,'niezgodny'):
            read_evaluation(self.output/'a')

    def test_cli_defaults_validation_and_verify_and_rejects_train(self):
        args = ['evaluate','--dataset',str(self.inputs/'dataset'),'--predictions',str(self.inputs/'predictions-a.jsonl'),
                '--run-manifest',str(self.inputs/'run-a.json'),'--output',str(self.output/'cli')]
        self.assertEqual(main(args),0)
        self.assertEqual(main(['verify','--output',str(self.output/'cli')]),0)
        with self.assertRaises(ValueError):
            read_references(self.inputs/'dataset','train')
        self.modify_predictions(lambda rows:rows[:-1])
        args[-1] = str(self.output/'missing')
        self.assertEqual(main(args),2)

    def test_run_manifest_wrong_split_or_dataset_refused(self):
        for changes in ({'split':'test'},{'dataset_manifest_sha256':'0'*64},{'protocol_version':'other'}):
            self.modify_run(name='a',**changes)
            with self.assertRaises(ValueError):
                self.run_case()
            shutil.copyfile(FIXTURE/'run-a.json',self.inputs/'run-a.json')

    def test_corrupt_reference_dataset_does_not_produce_result(self):
        label=self.inputs/'dataset/labels/fixture_exact.json'
        label.write_text('{}')
        with self.assertRaisesRegex(ValueError,'hash'):
            self.run_case()
        self.assertFalse((self.output/'a').exists())

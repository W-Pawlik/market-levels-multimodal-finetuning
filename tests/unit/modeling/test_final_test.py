"""Final-test gates and crash/resume behavior on synthetic IDs, never production answers."""
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from market_levels.cli.final_test import main
from market_levels.inference.final_config import load_plan, require_approval
from market_levels.inference.domain.inputs import ImageInput
from market_levels.inference.io.final_inputs import read_test_images
from market_levels.inference.io.final_model import attach_adapter
from market_levels.inference.io.final_state import encoded, read, digest, atomic, read_records, commit_record, session_lock
from market_levels.inference.workflows import final_test as workflow
from market_levels.inference.workflows import final_scoring
from market_levels.shared.configuration import read_configuration
from market_levels.shared.integrity import sha256_file
from market_levels.shared.manifests import seal

CONFIG = Path('configs/vlm/final-test.json')


class FinalConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'plan.json'
        self.config = read_configuration(CONFIG)

    def check_bad(self, change):
        config = copy.deepcopy(self.config); change(config)
        self.path.write_text(json.dumps(config), encoding='utf-8')
        with self.assertRaises(ValueError): load_plan(self.path)

    def test_approved_frozen_plan_loads_without_ml_import(self):
        c,s=load_plan(CONFIG)
        self.assertEqual(c['split'],'test')
        self.assertEqual(s['experiment_id'],'vlm44-extra-epoch')

    def test_both_approvals_are_required(self):
        for configured,explicit in [(False,False),(False,True),(True,False)]:
            with self.subTest(configured=configured,explicit=explicit), self.assertRaises(ValueError):
                require_approval({'execution_approved':configured},explicit)
        require_approval({'execution_approved':True},True)

    def test_generation_revision_image_or_model_changes_rejected(self):
        changes=[lambda c:c['runtime']['generation'].update(max_new_tokens=257),
                 lambda c:c['runtime']['generation'].update(do_sample=True),
                 lambda c:c['runtime']['models']['qwen3-vl'].update(revision='another'),
                 lambda c:c['runtime']['models']['qwen3-vl'].update(id='another'),
                 lambda c:c['runtime']['image_budgets'].update(native=1)]
        for change in changes: self.check_bad(change)

    def test_other_dataset_selection_hash_split_resources_output_refused(self):
        for field,value in [('dataset','another'),('selection','another.json'),('selection_sha256','0'*64),
                            ('split','validation'),('output','results/a-second-test')]:
            self.check_bad(lambda c:c.update({field:value}))
        self.check_bad(lambda c:c['resources'].update(minimum_ram_mib=1))

    def test_unknown_fields_refused(self):
        self.check_bad(lambda c:c.update(temperature=0.1))

    def test_no_authorization_refuses_before_audit_backend_or_creation(self):
        with patch.object(workflow,'audit_plan') as audit, patch.object(workflow,'FinalModel') as backend:
            with self.assertRaises(ValueError):
                workflow.execute(CONFIG,Path('results/vlm46-final-test'),'base-nf4',False)
            audit.assert_not_called();backend.assert_not_called()

    def test_cli_split_guard_and_old_guards_preserved(self):
        from market_levels.cli.train_vlm import main as train_main
        from market_levels.inference.io.stability import read_split
        for call in [lambda:main(['dry-run','--dataset','x','--selection','y','--split','validation']),
                     lambda:train_main(['validate-adapter','--split','test'])]:
            with self.assertRaises(SystemExit) as error:call()
            self.assertEqual(error.exception.code,2)
        with self.assertRaises(ValueError):read_split(Path('does-not-exist'),'test')

    def test_plain_cli_missing_approval_never_calls_model(self):
        args=['infer','--dataset',self.config['dataset'],'--selection',self.config['selection'],
              '--split','test','--session',self.config['output'],'--variant','base-nf4']
        with patch.object(workflow,'audit_plan') as audit,patch.object(workflow,'FinalModel') as backend:
            self.assertEqual(main(args),1)
            audit.assert_not_called();backend.assert_not_called()

    def test_audit_rejects_wrong_adapter_hash_before_any_model(self):
        config,selection=load_plan(CONFIG);selection['adapter_sha256']='0'*64
        with patch.object(workflow,'load_plan',return_value=(config,selection)),patch.object(workflow,'FinalModel') as backend:
            with self.assertRaises(ValueError):workflow.audit_plan(CONFIG)
            backend.assert_not_called()

    def test_audit_rejects_fingerprint_and_wrong_dataset_before_model(self):
        config,selection=load_plan(CONFIG)
        with patch.object(workflow,'load_plan',return_value=(config,selection)):
            with self.assertRaises(ValueError):workflow.audit_plan(CONFIG,dataset=Path('another'))
            with patch.object(workflow,'read_test_images',return_value=([],{'image_input_fingerprint':'0'*64})):
                with self.assertRaises(ValueError):workflow.audit_plan(CONFIG)


class ImageOnlyLoaderTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        Image.new('RGB',(1024,768)).save(self.root/'original.png')
        # Sentinel content must be hashed but never parsed as targets or OHLC.
        (self.root/'labels.secret').write_bytes(b'NOT JSON: reference values forbidden')
        (self.root/'ohlc.secret').write_bytes(b'NOT CSV: price values forbidden')
        entries=[]
        for split,count in [('train',698),('validation',36),('test',66)]:
            entries.extend({'id':f'{split}-{i:03d}','split':split,'symbol':'BTCUSDT' if i<count//2 else 'ETHUSDT',
                            'source':'real','image':'original.png','label':'labels.secret','ohlc':'ohlc.secret'} for i in range(count))
        self.payload={'kind':'production_dataset','status':'complete','count':800,'entries':entries}
        self.seal()

    def seal(self):
        for n in ['manifest.json','manifest.sha256']:
            p=self.root/n
            if p.exists():p.unlink()  # Temporary fixture only.
        seal(self.root,self.payload)

    def test_no_target_or_ohlc_values_enter_inputs(self):
        inputs,binding=read_test_images(self.root,sha256_file(self.root/'manifest.json'))
        self.assertEqual(len(inputs),66)
        self.assertEqual(set(vars(inputs[0])),{'id','image','instruction'})
        self.assertNotIn('answer',json.dumps(binding))
        self.assertEqual(binding['images'][0]['id'],'test-000')

    def test_duplicate_or_missing_manifest_ids_refused(self):
        self.payload['entries'][-1]['id']=self.payload['entries'][-2]['id'];self.seal()
        with self.assertRaises(ValueError):read_test_images(self.root,sha256_file(self.root/'manifest.json'))

    def test_hash_mismatch_refused(self):
        with self.assertRaises(ValueError):read_test_images(self.root,'0'*64)
        (self.root/'ohlc.secret').write_bytes(b'changed')
        with self.assertRaises(ValueError):read_test_images(self.root,sha256_file(self.root/'manifest.json'))

    def test_wrong_image_format_or_dimensions_refused(self):
        from PIL import Image
        Image.new('RGB',(2,2)).save(self.root/'original.png');self.seal()
        with self.assertRaises(ValueError):read_test_images(self.root,sha256_file(self.root/'manifest.json'))


class SyntheticBackend:
    calls=[]
    failure=None
    details={'environment':'synthetic fixture','no_optimizer_updates':True}
    def __init__(self,*args):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def generate(self,item):
        if self.failure and item.id==self.failure[0]:raise self.failure[1]
        self.calls.append(item.id)
        return ' \n```json\n{"supports":[1.23456789],"resistances":[]}\n```\t',{'seconds':.01}


class FinalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'one-session'
        self.config={'output':str(self.root),'execution_approved':True,'runtime':{'generation':{
            'do_sample':False,'num_beams':1,'max_new_tokens':256,'use_cache':True},'seed':20261109}}
        self.selection={'selected_adapter':str(Path(self.tmp.name)/'adapter'),'base_model':'fixture-model',
            'base_revision':'fixture-revision','adapter_sha256':'a'*64,'dataset_id':'fixture-only',
            'dataset_manifest_sha256':'b'*64}
        self.plan={'binding':{'image_input_fingerprint':'c'*64},'source_sha256':{'fixture':'d'*64}}
        self.inputs=[ImageInput(f'fixture-{i}',Path('unused.png'),'frozen instruction') for i in range(3)]
        for name,value in [('load_plan',(self.config,self.selection)),('audit_plan',(self.config,self.selection,self.inputs,self.plan))]:
            p=patch.object(workflow,name,return_value=value);p.start();self.addCleanup(p.stop)
        p=patch.object(workflow,'FinalModel',SyntheticBackend);p.start();self.addCleanup(p.stop)
        SyntheticBackend.calls=[];SyntheticBackend.failure=None
        workflow.prepare(CONFIG,self.root,True)

    def execute(self,variant='base-nf4',resume=False):
        return workflow.execute(CONFIG,self.root,variant,True,adapter=Path(self.selection['selected_adapter']) if variant=='finetuned-nf4' else None,resume=resume)

    def test_completed_pair_same_settings_different_run_ids_raw_no_repair(self):
        self.execute();self.execute('finetuned-nf4')
        a=read(self.root/'base-nf4/run.json');b=read(self.root/'finetuned-nf4/run.json')
        self.assertEqual(a['inference'],b['inference']);self.assertNotEqual(a['run_id'],b['run_id'])
        self.assertEqual((a['variant'],b['variant']),('base','finetuned'))
        self.assertIsNone(a['adapter_sha256']);self.assertEqual(b['adapter_sha256'],'a'*64)
        self.assertEqual(workflow.verify_pair(CONFIG,self.root)['verified'],True)
        rows=[json.loads(l) for l in (self.root/'base-nf4/predictions.jsonl').read_text().splitlines()]
        self.assertEqual(rows[0]['response'],' \n```json\n{"supports":[1.23456789],"resistances":[]}\n```\t')
        self.assertFalse((self.root/'base-nf4/summary.json').exists())

    def test_existing_directory_and_finished_variant_refused(self):
        with self.assertRaises(FileExistsError):workflow.prepare(CONFIG,self.root,True)
        self.execute()
        for resume in [False,True]:
            with self.assertRaises(ValueError):self.execute(resume=resume)
        self.assertEqual(len(SyntheticBackend.calls),3)

    def test_wrong_adapter_or_base_adapter_refused_before_backend(self):
        for variant,adapter in [('base-nf4',Path('unexpected')),('finetuned-nf4',Path('different')),('finetuned-nf4',None)]:
            with self.assertRaises(ValueError):workflow.execute(CONFIG,self.root,variant,True,adapter=adapter)
        self.assertFalse(SyntheticBackend.calls)

    def test_finetuned_requires_completed_base(self):
        with self.assertRaises(OSError):self.execute('finetuned-nf4')
        self.assertFalse(SyntheticBackend.calls)

    def test_oom_preserves_answers_and_resume_skips_committed(self):
        SyntheticBackend.failure=('fixture-1',RuntimeError('synthetic CUDA OOM'))
        with self.assertRaises(RuntimeError):self.execute()
        self.assertEqual(SyntheticBackend.calls,['fixture-0'])
        self.assertFalse((self.root/'base-nf4/manifest.sha256').exists())
        with self.assertRaises(FileExistsError):self.execute()
        SyntheticBackend.failure=None;self.execute(resume=True)
        self.assertEqual(SyntheticBackend.calls,['fixture-0','fixture-1','fixture-2'])
        events=[json.loads(l)['event'] for l in (self.root/'base-nf4/events.jsonl').read_text().splitlines()]
        self.assertIn('failed',events);self.assertIn('resumed',events)

    def test_keyboard_interrupt_and_stop_preserve_partial(self):
        SyntheticBackend.failure=('fixture-1',KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):self.execute()
        (self.root/'base-nf4/STOP').write_text('')
        SyntheticBackend.failure=None
        with self.assertRaises(InterruptedError):self.execute(resume=True)
        (self.root/'base-nf4/STOP').unlink()
        self.execute(resume=True)
        self.assertEqual(SyntheticBackend.calls,['fixture-0','fixture-1','fixture-2'])

    def test_changed_session_plan_refused_before_generation(self):
        self.plan['binding']['image_input_fingerprint']='changed'
        with self.assertRaises(ValueError):self.execute()
        self.assertFalse(SyntheticBackend.calls)

    def test_duplicate_unknown_and_missing_prediction_records_rejected(self):
        self.execute()
        folder=self.root/'base-nf4'; run=read(folder/'run.json');ids=[i.id for i in self.inputs]
        path=folder/'records/001-fixture-1.json';original=path.read_bytes()
        for identity in ['fixture-0','unknown']:
            row=json.loads(original);row['id']=identity;atomic(path,encoded(row))
            with self.assertRaises(ValueError):read_records(folder,run,ids)
        path.write_bytes(original);path.unlink()
        with self.assertRaises(ValueError):read_records(folder,run,ids)

    def test_changed_predictions_refused_on_resume(self):
        SyntheticBackend.failure=('fixture-1',RuntimeError('stop'))
        with self.assertRaises(RuntimeError):self.execute()
        (self.root/'base-nf4/predictions.jsonl').write_text('{"id":"other","response":"edited"}\n')
        SyntheticBackend.failure=None
        with self.assertRaises(ValueError):self.execute(resume=True)
        self.assertEqual(SyntheticBackend.calls,['fixture-0'])

    def test_committed_record_survives_crash_before_prefix_publication(self):
        from market_levels.inference.io import final_state
        with patch.object(final_state,'publish_predictions',side_effect=OSError('power loss')):
            with self.assertRaises(OSError):self.execute()
        self.execute(resume=True)
        self.assertEqual(SyntheticBackend.calls,['fixture-0','fixture-1','fixture-2'])

    def test_crash_during_seal_recovers_without_loading_model(self):
        original=workflow.atomic
        def failing(path,value):
            if path.name=='manifest.sha256':raise OSError('power loss')
            return original(path,value)
        with patch.object(workflow,'atomic',side_effect=failing):
            with self.assertRaises(OSError):self.execute()
        with patch.object(workflow,'FinalModel') as backend:
            self.execute(resume=True);backend.assert_not_called()
        self.assertEqual(SyntheticBackend.calls,['fixture-0','fixture-1','fixture-2'])

    def test_no_incomplete_publication_or_early_quality_scoring(self):
        SyntheticBackend.failure=('fixture-1',RuntimeError('stop'))
        with self.assertRaises(RuntimeError):self.execute()
        with self.assertRaises(OSError):workflow.verify_pair(CONFIG,self.root)
        with patch.object(final_scoring,'load_plan',return_value=(self.config,self.selection)),patch.object(final_scoring,'evaluate') as evaluate:
            with self.assertRaises(OSError):final_scoring.score_pair(CONFIG,self.root,True)
            evaluate.assert_not_called()

    def test_process_lock_prevents_parallel_execution(self):
        with session_lock(self.root):
            with self.assertRaises(OSError):self.execute()


class AdapterMemoryTests(unittest.TestCase):
    def test_resource_guard_refuses_before_cuda_and_model(self):
        from market_levels.inference.io.final_model import FinalModel
        with (patch('market_levels.inference.io.final_model.guard',side_effect=RuntimeError('GPU busy')),
                patch('market_levels.inference.io.final_model.setup') as setup,
                patch('market_levels.inference.io.final_model.load_model') as load):
            with self.assertRaises(RuntimeError):
                FinalModel({'runtime':{},'resources':{}},{},'base-nf4').__enter__()
            setup.assert_not_called();load.assert_not_called()

    def test_exact_tensor_check_and_inference_only_loading(self):
        tensors={f'fixture.{i}':SimpleNamespace(dtype='float32',shape=(1,),value=i) for i in range(112)}
        torch=SimpleNamespace(equal=lambda a,b:a.value==b.value,isfinite=lambda a:SimpleNamespace(all=lambda:True))
        loader=Mock(return_value='loaded-model')
        modules={'peft':SimpleNamespace(PeftModel=SimpleNamespace(from_pretrained=loader)),
                 'safetensors':SimpleNamespace(), 'safetensors.torch':SimpleNamespace(load_file=lambda *a,**k:tensors)}
        with patch.dict(sys.modules,modules),patch('market_levels.inference.io.final_model.adapter_state',return_value=tensors):
            model,report=attach_adapter('base',Path('fixture-adapter'),torch)
            self.assertEqual(model,'loaded-model');self.assertTrue(report['tensor_values_exact'])
            loader.assert_called_once_with('base',Path('fixture-adapter'),is_trainable=False)
        changed=dict(tensors);changed['fixture.0']=SimpleNamespace(dtype='float32',shape=(1,),value=-1)
        with patch.dict(sys.modules,modules),patch('market_levels.inference.io.final_model.adapter_state',return_value=changed):
            with self.assertRaises(ValueError):attach_adapter('base',Path('fixture-adapter'),torch)


if __name__=='__main__':unittest.main()

"""Offline gates, lineage and local schedule; never load Qwen or CUDA."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from market_levels.cli.train_vlm import main
from market_levels.training.config import load_config
from market_levels.training.domain.schedule import initial_state, epoch_order, lr_multiplier, total_steps
from market_levels.training.domain.provenance import stage_progress
from market_levels.training.io.events import Events
from market_levels.training.io.initialization import (extra_context, require_extra_approval,
    validate_parent_spec, validate_parent_tensors, verify_parent)
from market_levels.training.workflows.pipeline import plan, preflight, run_training, train_loop
from market_levels.shared.configuration import read_configuration
from market_levels.inference.workflows.adapter_validation import validate_adapter
from unit.modeling.test_training_pipeline import FakeBackend

CONFIG = Path('configs/vlm/extra-epoch-approved-local.json')


class ExtraEpochTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(CONFIG)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_exact_new_schedule_and_original_unchanged(self):
        c = self.config
        self.assertEqual((c['pipeline']['epochs'], c['pipeline']['warmup_steps'],
                          c['runtime']['training']['learning_rate']), (1,9,.00005))
        self.assertEqual(total_steps(698,c['pipeline']),175)
        self.assertFalse(c['pipeline']['full_approved'])
        old = load_config(Path('configs/vlm/training-approved-local.json'))
        self.assertEqual((old['pipeline']['epochs'],old['pipeline']['warmup_steps'],
                          old['runtime']['training']['learning_rate']),(2,18,.0002))
        self.assertEqual(c['fixed'],old['fixed'])

    def test_config_rejects_changed_revision_plan_and_guards(self):
        for area,key,value in [('pipeline','epochs',3),('pipeline','max_steps',25),
                ('pipeline','seed',20261110),('pipeline','minimum_ram_mib',1),
                ('pipeline','full_approved',True),('pipeline','warmup_steps',0)]:
            raw = read_configuration(CONFIG)
            raw[area][key] = value
            p = self.root/'bad.json'; p.write_text(json.dumps(raw))
            with self.subTest(key=key), self.assertRaises(ValueError): load_config(p)
        raw = read_configuration(CONFIG)
        raw['runtime']['models']['qwen3-vl']['revision']='bad'
        p.write_text(json.dumps(raw))
        with self.assertRaises(ValueError): load_config(p)

    def test_both_approvals_required_without_side_effects(self):
        for configured,explicit in ((False,False),(False,True),(True,False)):
            c=copy.deepcopy(self.config); c['extra_epoch']['approved']=configured
            with self.assertRaises(ValueError): require_extra_approval(c,explicit)
        with patch('market_levels.cli.train_vlm.run_training') as run, \
                patch('market_levels.cli.train_vlm.preflight') as pf, \
                contextlib.redirect_stdout(io.StringIO()):
            for command in ('extra-epoch','preflight','dry-run'):
                self.assertEqual(main([command,'--config',str(CONFIG),'--output',str(self.root/'vlm44-blocked')]),1)
            run.assert_not_called(); pf.assert_not_called()
        self.assertFalse((self.root/'vlm44-blocked').exists())

    def test_configuration_approval_false_refuses_even_with_cli_flag(self):
        raw=read_configuration(CONFIG); raw['extra_epoch']['approved']=False
        p=self.root/'bad.json'; p.write_text(json.dumps(raw))
        with patch('market_levels.cli.train_vlm.run_training') as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['extra-epoch','--config',str(p),'--approve-extra-epoch','--output','unused']),1)
            run.assert_not_called()

    def test_initialize_and_resume_mutually_exclusive(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            main(['extra-epoch','--resume','old','--initialize-adapter','parent'])
        self.assertEqual(exc.exception.code,2)
        with self.assertRaisesRegex(ValueError,'mutually exclusive'):
            extra_context(self.config,Path('old'),Path('parent'))

    def test_old_checkpoint_rejected_before_cuda(self):
        with patch('market_levels.training.io.initialization.verify_parent',return_value={'parent':350}), \
                patch('market_levels.training.io.initialization.checkpoint_metadata',return_value={'identity':{'config':{'old':True}}}), \
                patch('market_levels.training.workflows.pipeline.guard') as guard:
            with self.assertRaisesRegex(ValueError,'resume config/provenance'):
                run_training(self.config,self.root/'vlm44-new','extra-epoch',Path('old'))
            guard.assert_not_called()
            self.assertFalse((self.root/'vlm44-new').exists())

    def test_changed_resume_provenance_rejected(self):
        meta={'identity':{'config':self.config,'provenance':{'changed':True}}}
        with patch('market_levels.training.io.initialization.verify_parent',return_value={'parent':350}), \
                patch('market_levels.training.io.initialization.checkpoint_metadata',return_value=meta):
            with self.assertRaisesRegex(ValueError,'provenance'): extra_context(self.config,Path('new'))

    def test_wrong_initial_adapter_rejected_before_source_read(self):
        with patch('market_levels.training.io.initialization.verify_parent') as verify:
            with self.assertRaisesRegex(ValueError,'pinned parent'):
                extra_context(self.config,initialize_adapter=self.root/'wrong')
            verify.assert_not_called()

    def test_corrupt_parent_hash_rejected_without_tensor_import(self):
        c=copy.deepcopy(self.config)
        c['extra_epoch']['parent_manifest_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'SHA-256'): verify_parent(c)

    def test_parent_architecture_rejects_wrong_scaling_and_vision(self):
        spec=json.loads(Path(self.config['extra_epoch']['parent_adapter'],'adapter_config.json').read_text())
        validate_parent_spec(spec)
        for key,value in [('r',16),('lora_alpha',32),('target_modules',['visual.q_proj']),
                          ('target_modules',['q_proj']),('use_rslora',True),('modules_to_save',['lm_head'])]:
            with self.subTest(key=key),self.assertRaises(ValueError): validate_parent_spec(spec|{key:value})

    def test_parent_tensor_count_shapes_and_finiteness(self):
        tensors={}
        for i in range(28):
            for q,out in [('q_proj',2048),('v_proj',1024)]:
                for part,shape in [('A',(8,2048)),('B',(out,8))]:
                    tensors[f'base_model.model.model.language_model.layers.{i}.self_attn.{q}.lora_{part}.weight']=SimpleNamespace(
                        shape=shape,dtype='float32',numel=lambda shape=shape:shape[0]*shape[1])
        torch=SimpleNamespace(float32='float32',isfinite=lambda _:SimpleNamespace(all=lambda:True))
        validate_parent_tensors(torch,tensors)
        bad=dict(tensors); bad.pop(next(iter(bad)))
        with self.assertRaisesRegex(ValueError,'112'): validate_parent_tensors(torch,bad)
        first=next(iter(tensors)); bad=dict(tensors); bad[first]=SimpleNamespace(shape=(1,),dtype='float32')
        with self.assertRaisesRegex(ValueError,'shape'): validate_parent_tensors(torch,bad)
        torch.isfinite=lambda _:SimpleNamespace(all=lambda:False)
        with self.assertRaisesRegex(ValueError,'nonfinite'): validate_parent_tensors(torch,tensors)

    def test_third_epoch_permutation_without_validation_selection(self):
        ids=[str(i) for i in range(698)]
        self.assertEqual(epoch_order(ids,20261112,0),epoch_order(ids,20261110,2))
        self.assertNotEqual(epoch_order(ids,20261112,0),epoch_order(ids,20261110,0))

    def test_25_then_175_no_replay_and_two_example_tail(self):
        settings=self.config['pipeline']; ids=[str(i) for i in range(698)]
        state=initial_state(ids,settings); backend=FakeBackend()
        with contextlib.redirect_stdout(io.StringIO()):
            events=Events(self.root/'events.jsonl')
            self.assertEqual(train_loop(settings,ids,state,backend,events,lambda:False,25),'stopped')
            self.assertEqual((state['global_step'],state['processed_examples']),(25,100))
            restored=copy.deepcopy(backend.saved[-1])
            self.assertEqual(train_loop(settings,ids,restored,backend,events,lambda:False),'complete')
        self.assertEqual((restored['global_step'],restored['processed_examples']),(175,698))
        self.assertEqual([x for group in backend.groups for x in group],epoch_order(ids,20261112,0))
        self.assertEqual(len(backend.groups[-1]),2)
        self.assertEqual(lr_multiplier(0,175,9,'linear'),0)
        self.assertEqual(lr_multiplier(9,175,9,'linear'),1)
        self.assertGreater(lr_multiplier(25,175,9,'linear'),0)
        self.assertEqual(lr_multiplier(175,175,9,'linear'),0)

    def test_extra_mode_cannot_bypass_full_or_smoke(self):
        for mode in ('full','smoke-test'):
            with self.assertRaises(ValueError): plan(self.config,mode)
        with self.assertRaises(ValueError): plan(load_config(Path('configs/vlm/training.json')),'extra-epoch')

    def test_progress_keeps_new_counts_separate(self):
        progress=stage_progress({'provenance':{'parent_checkpoint_step':350}},
                                {'global_step':25,'processed_examples':100})
        self.assertEqual(progress['additional_optimizer_steps'],25)
        self.assertEqual(progress['cumulative_optimizer_updates_for_reference'],375)
        self.assertEqual(progress['total_training_examples_seen_in_new_stage'],100)

    def test_extra_cli_preserves_exit_code_and_initialization_argument(self):
        for code in (0,1,3):
            with patch('market_levels.cli.train_vlm.run_training',return_value=code) as run:
                self.assertEqual(main(['extra-epoch','--config',str(CONFIG),'--approve-extra-epoch',
                    '--initialize-adapter','parent','--output','vlm44-unused','--stop-after','25']),code)
                self.assertEqual(run.call_args.kwargs['initialize_adapter'],Path('parent'))

    def test_new_export_identity_is_accepted_by_validation_before_gpu(self):
        adapter=self.root/'adapter'; adapter.mkdir()
        from market_levels.shared.integrity import sha256_file
        identity={'config':self.config,'dataset':{'manifest_sha256':sha256_file(
            Path(self.config['runtime']['dataset'])/'manifest.json')}}
        (adapter/'training-identity.json').write_text(json.dumps(identity))
        with patch('market_levels.inference.workflows.adapter_validation.verify_files',
                   return_value={'kind':'vlm_inference_adapter','status':'complete'}), \
                patch('market_levels.inference.workflows.adapter_validation.guard',side_effect=RuntimeError('guard reached')):
            with self.assertRaisesRegex(RuntimeError,'guard reached'):
                validate_adapter(self.config,adapter,self.root/'validation')

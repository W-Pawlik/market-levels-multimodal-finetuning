"""Offline behavior tests for exact data cursors, safe stops and diagnostics."""
import copy
import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from market_levels.training.config import load_config, DEFAULTS
from market_levels.training.domain.schedule import initial_state, next_group, advance, validate_state, epoch_order, total_steps
from market_levels.training.workflows.pipeline import train_loop
from market_levels.training.io.events import Events
from market_levels.training.io.checkpoints import checkpoint_metadata, save_checkpoint
from market_levels.training.io.data import read_train
from market_levels.cli.train_vlm import main, require_full_approval
from market_levels.shared.configuration import read_configuration
from market_levels.shared.manifests import seal
from market_levels.inference.domain.price_diagnostics import unwrap_fence, diagnostic_scores
from market_levels.evaluation.domain.models import Reference, Levels
from market_levels.evaluation.domain.responses import parse_response
from market_levels.evaluation.domain.scoring import score_example
from market_levels.evaluation.domain.metrics import aggregate


class FakeBackend:
    def __init__(self, fail=None):
        self.groups, self.saved, self.fail = [], [], fail

    def step(self, group):
        if self.fail:
            raise self.fail
        self.groups.append(list(group))
        return {'loss': 1.0, 'learning_rate': .001, 'input_tokens': len(group)*12, 'supervised_tokens': len(group)*3}

    def memory(self):
        return {'available_ram_mib': 10000, 'commit_headroom_mib': 20000, 'rss_mib': 100}

    def save(self, state):
        self.saved.append(copy.deepcopy(state))


class TrainingPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = DEFAULTS | {'epochs': 2, 'max_steps': None, 'validate_every_steps': 100}
        self.ids = [str(i) for i in range(9)]
        self.events = Events(self.root / 'events.jsonl')

    def tearDown(self):
        self.temp.cleanup()

    def test_effective_config_and_frozen_conditions(self):
        c = load_config(Path('configs/vlm/training.json'))
        self.assertFalse(c['pipeline']['full_approved'])
        self.assertEqual(c['fixed']['vision_dtype'], 'bfloat16')
        raw = read_configuration(Path('configs/vlm/training.json'))
        for field, value in [('batch_size', 2), ('epochs', True), ('scheduler', 'magic'), ('smoke_steps', 21), ('extra', 1)]:
            with self.subTest(field=field):
                bad = copy.deepcopy(raw)
                bad['pipeline'][field] = value
                p = self.root / 'bad.json'
                p.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    load_config(p)

    def test_reject_wrong_revision_image_and_split(self):
        raw = read_configuration(Path('configs/vlm/training.json'))
        raw['runtime']['models']['qwen3-vl']['revision'] = 'wrong'
        p = self.root / 'bad.json'
        p.write_text(json.dumps(raw))
        with self.assertRaises(ValueError):
            load_config(p)
        for split in ('test', 'validation'):
            with self.assertRaises(ValueError):
                read_train(self.root, split)

    def test_deterministic_shuffle(self):
        self.assertEqual(epoch_order(self.ids, 1, 0), epoch_order(list(reversed(self.ids)), 1, 0))
        self.assertNotEqual(epoch_order(self.ids, 1, 0), epoch_order(self.ids, 1, 1))
        self.assertEqual(set(epoch_order(self.ids, 1, 0)), set(self.ids))

    def test_partial_group_and_epoch_counts(self):
        backend = FakeBackend()
        state = initial_state(self.ids, self.settings)
        self.assertEqual(train_loop(self.settings, self.ids, state, backend, self.events, lambda: False), 'complete')
        self.assertEqual([len(g) for g in backend.groups], [4,4,1,4,4,1])
        self.assertEqual(state['processed_examples'], 18)
        self.assertEqual(state['global_step'], 6)
        self.assertEqual(state['input_tokens'], 216)
        validate_state(state, self.ids, self.settings)

    def test_698_count_and_final_group(self):
        ids = [str(i) for i in range(698)]
        state = initial_state(ids, self.settings)
        self.assertEqual(total_steps(698, self.settings), 350)
        sizes = []
        for _ in range(175):
            sizes.append(len(next_group(state, self.settings)))
            advance(state, ids, self.settings, sizes[-1])
        self.assertEqual(sizes[-1], 2)
        self.assertEqual(sum(sizes), 698)
        validate_state(state, ids, self.settings)

    def test_resume_without_replay(self):
        a, b = FakeBackend(), FakeBackend()
        state_a = initial_state(self.ids, self.settings)
        train_loop(self.settings, self.ids, state_a, a, self.events, lambda: False)
        state_b = initial_state(self.ids, self.settings)
        self.assertEqual(train_loop(self.settings, self.ids, state_b, b, self.events, lambda: False, 2), 'stopped')
        restored = json.loads(json.dumps(b.saved[-1]))
        train_loop(self.settings, self.ids, restored, b, self.events, lambda: False)
        self.assertEqual(a.groups, b.groups)
        for key in ('global_step', 'processed_examples', 'epoch', 'position', 'order'):
            self.assertEqual(state_a[key], restored[key])

    def test_stop_file_after_optimizer_boundary(self):
        backend = FakeBackend()
        state = initial_state(self.ids, self.settings)
        status = train_loop(self.settings, self.ids, state, backend, self.events, lambda: len(backend.groups) >= 1)
        self.assertEqual(status, 'stopped')
        self.assertEqual(backend.saved[-1]['position'], 4)

    def test_simulated_oom_does_not_commit_sampler(self):
        state = initial_state(self.ids, self.settings)
        backend = FakeBackend(RuntimeError('CUDA out of memory'))
        with self.assertRaisesRegex(RuntimeError, 'out of memory'):
            train_loop(self.settings, self.ids, state, backend, self.events, lambda: False)
        self.assertEqual(state['global_step'], 0)
        self.assertFalse(backend.saved)

    def test_invalid_sampler_rejected(self):
        state = initial_state(self.ids, self.settings)
        state['position'] = 1
        with self.assertRaises(ValueError):
            validate_state(state, self.ids, self.settings)

    def test_full_requires_two_explicit_approvals(self):
        c = load_config(Path('configs/vlm/training.json'))
        for config_flag, cli_flag in [(False, False), (True, False), (False, True)]:
            c['pipeline']['full_approved'] = config_flag
            with self.assertRaises(ValueError):
                require_full_approval(c, cli_flag)
        c['pipeline']['full_approved'] = True
        require_full_approval(c, True)
        self.assertEqual(main(['full', '--output', str(self.root/'forbidden')]), 1)
        self.assertFalse((self.root/'forbidden').exists())

    def test_no_arguments_or_test_split_cannot_train(self):
        for args in ([], ['smoke-test', '--split', 'test']):
            with self.assertRaises(SystemExit):
                main(args)

    def test_checkpoint_incomplete_corrupt_or_wrong_identity(self):
        ckpt = self.root/'ckpt'
        ckpt.mkdir()
        with self.assertRaises((ValueError, OSError)):
            checkpoint_metadata(ckpt)
        (ckpt/'adapter').mkdir()
        for name in ('state.pt', 'adapter/adapter_config.json', 'adapter/adapter_model.safetensors'):
            (ckpt/name).write_text('fake')
        identity = {'revision': 'a', 'dataset': 'b', 'config': 'c'}
        (ckpt/'metadata.json').write_text(json.dumps({'schema': 1, 'identity': identity}))
        seal(ckpt, {'kind': 'vlm_training_checkpoint', 'schema': 1, 'status': 'complete'})
        checkpoint_metadata(ckpt, identity)
        for key in identity:
            with self.assertRaises(ValueError):
                checkpoint_metadata(ckpt, identity | {key: 'wrong'})
        (ckpt/'state.pt').write_text('corrupt')
        with self.assertRaises(ValueError):
            checkpoint_metadata(ckpt)

    def test_machine_log_is_parseable(self):
        self.events.emit('checkpoint', step=4, path='checkpoint')
        row = json.loads((self.root/'events.jsonl').read_text())
        self.assertEqual(row['event'], 'checkpoint')
        self.assertEqual(row['step'], 4)

    def test_low_memory_stops_after_complete_group_and_saves(self):
        backend = FakeBackend()
        backend.memory = lambda: {'available_ram_mib':100 if backend.groups else 10000, 'commit_headroom_mib':20000, 'rss_mib':100}
        state = initial_state(self.ids,self.settings)
        self.assertEqual(train_loop(self.settings,self.ids,state,backend,self.events,lambda:False),'memory_stop')
        self.assertEqual(state['position'],4)
        self.assertEqual(backend.saved[-1]['global_step'],1)

    def test_validation_boundary_ends_segment(self):
        settings = self.settings | {'validate_every_steps':2}
        backend = FakeBackend()
        state = initial_state(self.ids,settings)
        self.assertEqual(train_loop(settings,self.ids,state,backend,self.events,lambda:False),'validation_due')
        self.assertEqual(len(backend.groups),2)
        self.assertEqual(backend.saved[-1]['position'],8)

    def test_interrupted_publication_keeps_prior_checkpoint(self):
        def adapter(folder, **kwargs):
            folder.mkdir()
            (folder/'adapter_config.json').write_text('{}')
            (folder/'adapter_model.safetensors').write_bytes(b'test-only')
        model = SimpleNamespace(parameters=lambda:[],save_pretrained=adapter)
        optimizer = scheduler = SimpleNamespace(state_dict=lambda:{})
        payloads = []
        def save(payload, stream):
            payloads.append(payload)
            stream.write(b'test-state')
        fake_torch = SimpleNamespace(save=save,load=lambda *a,**k:payloads[-1])
        root = self.root/'checkpoints'
        state = initial_state(self.ids,self.settings)
        with patch('market_levels.training.io.checkpoints.capture_rng',return_value={}), patch('market_levels.training.io.checkpoints.restore_rng'):
            valid = save_checkpoint(fake_torch,model,optimizer,scheduler,state,{},root)
            before = (valid/'manifest.json').read_bytes()
            state = copy.deepcopy(state)
            state['global_step']=1
            fake_torch.save = lambda *args: (_ for _ in ()).throw(OSError('disk interruption'))
            with self.assertRaisesRegex(OSError,'disk interruption'):
                save_checkpoint(fake_torch,model,optimizer,scheduler,state,{},root)
        self.assertEqual((valid/'manifest.json').read_bytes(),before)
        self.assertEqual((root/'latest.txt').read_text().strip(),'step-000000')
        self.assertFalse((root/'step-000001').exists())
        checkpoint_metadata(valid,{})

    def test_checkpoint_with_live_gradient_is_forbidden(self):
        model = SimpleNamespace(parameters=lambda:[SimpleNamespace(requires_grad=True,grad=object())])
        with self.assertRaisesRegex(ValueError,'optimizer boundary'):
            save_checkpoint(None,model,None,None,{}, {},self.root/'ckpt')

    def test_staging_is_never_a_resume_candidate(self):
        with self.assertRaisesRegex(ValueError,'Staging'):
            checkpoint_metadata(self.root/'.step-000001.partial')


class PriceDiagnosticsTests(unittest.TestCase):
    def test_only_outer_fence_is_removed(self):
        text = '{"supports":[],"resistances":[]}'
        self.assertEqual(unwrap_fence('```json\n'+text+'\n```'), (text, True))
        self.assertEqual(unwrap_fence('```\r\n'+text+'\r\n```'), (text, True))
        for raw in ('explanation\n```json\n'+text+'\n```', '```json\n'+text+'\n```\nextra',
                    '```python\n'+text+'\n```', '```json\n```json\n'+text+'\n```\n```'):
            self.assertEqual(unwrap_fence(raw), (raw, False))

    def test_scoring_reuses_official_functions_and_preserves_raw(self):
        ref = Reference('a','BTCUSDT','validation',Levels((D(100),), ()),D(2))
        raw = {'a': '```json\n{"supports":[100.1],"resistances":[]}\n```'}
        before = dict(raw)
        result = diagnostic_scores([ref], raw, {'a': D(101)})
        expected = aggregate([score_example(ref, parse_response(unwrap_fence(raw['a'])[0]))])
        self.assertEqual(result['metrics'], expected)
        self.assertEqual(raw, before)
        self.assertIsNone(parse_response(raw['a']).levels)
        self.assertEqual(result['metrics']['tolerances']['0.5']['overall']['tp'], 1)

    def test_invalid_json_after_unwrap_stays_invalid(self):
        ref = Reference('a','ETHUSDT','validation',Levels((),()),D(2))
        for text in ('{"supports":[]}', '{"supports":["1"],"resistances":[]}', '{"supports":[],"supports":[],"resistances":[]}'):
            result = diagnostic_scores([ref], {'a':'```json\n'+text+'\n```'}, {'a':D(1)})
            self.assertEqual(result['metrics']['tolerances']['0.5']['overall']['valid_json_count'], 0)

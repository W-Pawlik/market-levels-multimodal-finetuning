"""Isolation, deterministic strata, strict configuration and fail-fast safety."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

from market_levels.cli.vlm_stability import gpu_guard, main
from market_levels.inference.io.stability import read_split, select_training
from market_levels.inference.io.pilot import append_response
from market_levels.modeling.stability_config import load_config, REVISION
from market_levels.shared.integrity import sha256_file
from market_levels.shared.manifests import seal
from market_levels.datasets.domain.examples import INSTRUCTION
from market_levels.evaluation.io.inputs import read_predictions, InputError
from market_levels.evaluation.domain.models import Reference, Levels


class StabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def records(self):
        return [dict(id=f'{symbol}-{source}-{i:02d}', split='train', symbol=symbol, source=source,
                     answer_tokens=i+10, level_count=i%7)
                for symbol in ('BTCUSDT', 'ETHUSDT') for source in ('real', 'synthetic') for i in range(16)]

    def test_strata_are_deterministic_and_each_step_has_four_different_groups(self):
        selected = select_training(self.records())
        self.assertEqual(selected, select_training(list(reversed(self.records()))))
        self.assertEqual(len({e['id'] for e in selected}), 32)
        for i in range(8):
            self.assertEqual(len({(e['symbol'], e['source']) for e in selected[i*4:(i+1)*4]}), 4)
        self.assertEqual(min(e['answer_tokens'] for e in selected), 10)
        self.assertEqual(max(e['answer_tokens'] for e in selected), 25)
        self.assertGreater(len({e['level_count'] for e in selected}), 1)

    def test_non_train_or_duplicate_selection_rejected(self):
        for split in ('validation', 'test'):
            rows = self.records(); rows[0]['split'] = split
            with self.assertRaises(ValueError):
                select_training(rows)
        with self.assertRaises(ValueError):
            select_training(self.records()*2)

    def test_test_rejected_before_read(self):
        with patch('market_levels.inference.io.stability.verify_files') as verify:
            with self.assertRaises(ValueError):
                read_split(self.root, 'test')
            verify.assert_not_called()

    def test_revision_and_conditions_cannot_drift(self):
        config = load_config(Path('configs/vlm/stability.json'))
        self.assertEqual(config['models']['qwen3-vl']['revision'], REVISION)
        for mutate in (lambda c: c['models']['qwen3-vl'].update(revision='main'),
                       lambda c: c['generation'].update(do_sample=True),
                       lambda c: c.update(dataset='test'),
                       lambda c: c['training'].update(rank=16),
                       lambda c: c['image_budgets'].update(native=393216)):
            changed = copy.deepcopy(config); mutate(changed)
            p = self.root/'config.json'; p.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                load_config(p)

    def test_gpu_guard_rejects_loaded_desktop_without_retry(self):
        with patch('market_levels.cli.vlm_stability.subprocess.check_output', return_value='600\n') as query:
            with self.assertRaises(RuntimeError):
                gpu_guard()
            self.assertEqual(query.call_count, 1)

    def fixture(self, candles=120, overlay=False, count=36):
        (self.root/'splits').mkdir()
        entries, rows = [], []
        for i in range(count):
            entry = dict(id=str(i), split='validation', symbol='BTCUSDT' if i<18 else 'ETHUSDT',
                         source='real', image=f'{i}.png', metadata=f'{i}.json', ohlc=f'{i}.csv')
            (self.root/entry['image']).write_bytes(b'pixels')
            (self.root/entry['ohlc']).write_text('header\n'+'row\n'*candles)
            (self.root/entry['metadata']).write_text(json.dumps({'rendering': {
                'visualization': {'target_lines': overlay}, 'png_sha256': sha256_file(self.root/entry['image'])}}))
            rows.append(dict(id=str(i), split='validation', image=entry['image'], instruction=INSTRUCTION,
                             answer={'supports': [1], 'resistances': []}))
            entries.append(entry)
        (self.root/'splits/validation.jsonl').write_text('\n'.join(json.dumps(r) for r in rows),encoding='utf-8')
        seal(self.root, {'kind': 'production_dataset', 'status': 'complete', 'entries': entries})

    def test_full_validation_inputs_do_not_expose_targets(self):
        self.fixture()
        inputs, records, targets = read_split(self.root, 'validation')
        self.assertEqual(len(inputs), 36)
        self.assertEqual(targets, {})
        self.assertEqual(set(vars(inputs[0])), {'id', 'image', 'instruction'})
        self.assertEqual(inputs[0].instruction, INSTRUCTION)

    def test_wrong_candle_count_rejected(self):
        self.fixture(candles=119)
        with self.assertRaisesRegex(ValueError, '120 candles'):
            read_split(self.root, 'validation')

    def test_overlay_rejected(self):
        self.fixture(overlay=True)
        with self.assertRaisesRegex(ValueError, 'overlay'):
            read_split(self.root, 'validation')

    def test_incomplete_validation_rejected(self):
        self.fixture(count=35)
        with self.assertRaisesRegex(ValueError, '36-image'):
            read_split(self.root, 'validation')

    def test_raw_predictions_match_evaluator_contract_and_missing_id_blocks(self):
        refs = [Reference(str(i), 'BTCUSDT', 'validation', Levels((), ()), 1) for i in range(36)]
        binding = {'all_ids': {str(i): 'validation' for i in range(36)}}
        path = self.root/'predictions.jsonl'
        raw = '```json\n{"supports": [], "resistances": []}\n```'
        for i in range(35):
            append_response(path, str(i), raw)
        with self.assertRaises(InputError):
            read_predictions(path, refs, binding)
        append_response(path, '35', raw)
        self.assertEqual(set(read_predictions(path, refs, binding).values()), {raw})

    def test_validation_cli_forbids_adapter(self):
        with self.assertRaises(SystemExit):
            main(['validate', '--output', str(self.root/'out'), '--precision', 'nf4', '--adapter', 'adapter'])

    def mocked_training(self, oom=False):
        from market_levels.training.workflows import stability as workflow
        from market_levels.inference.domain.inputs import ImageInput
        config = load_config(Path('configs/vlm/stability.json'))
        torch, model, processor = MagicMock(), MagicMock(), MagicMock()
        class OOM(RuntimeError):
            pass
        torch.cuda.OutOfMemoryError = OOM
        torch.nn.utils.clip_grad_norm_.return_value = 1.0
        torch.optim.AdamW.return_value.defaults = {'lr': 0.0002}
        processor.image_processor.to_dict.return_value = {}
        model.named_modules.return_value = [('model.language_model.layers.0.self_attn.q_proj', None)]
        param = MagicMock(); param.numel.return_value = 10
        param.grad.__ne__.return_value = MagicMock()
        labels = MagicMock()
        labels.__eq__.return_value = MagicMock()
        labels.__ne__.return_value = MagicMock()
        model.named_parameters.return_value = [('lora_A.weight', param)]
        model.base_model.model.model.visual.parameters.return_value = []
        model.get_nb_trainable_parameters.return_value = (10, 100)
        def forward(**kwargs):
            if oom:
                raise OOM('simulated OOM')
            model.base_model.model.model.visual.register_forward_hook.call_args.args[0]()
            return SimpleNamespace(loss=MagicMock())
        model.side_effect = forward
        class Batch(dict):
            def to(self, device):
                return self
        class Monitor:
            def __init__(self, torch):
                self.result = {}; self.elapsed = 1.0
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        peft = SimpleNamespace(LoraConfig=MagicMock(), get_peft_model=lambda *a, **kw: model,
                               prepare_model_for_kbit_training=lambda m, **kw: m)
        image = SimpleNamespace(open=MagicMock())
        image.open.return_value.__enter__.return_value.size = (1024, 768)
        inputs = [ImageInput(str(i), self.root/'image.png', INSTRUCTION) for i in range(32)]
        from contextlib import ExitStack
        with ExitStack() as stack:
            stack.enter_context(patch.dict('sys.modules', {'peft': peft, 'PIL': SimpleNamespace(Image=image),
                'safetensors.torch': SimpleNamespace(save_file=MagicMock())}))
            for name, value in {'load_model': (torch, model, processor, {}), 'environment': {},
                    'local_checkpoint': self.root, 'read_split': (inputs, [], {str(i): {} for i in range(32)}),
                    'prepare_input': None, 'set_resolution': {}, 'assistant_labels': labels,
                    'adapter_state': {}, 'probe': [], 'error_details': {'cuda_oom': True}}.items():
                if name == 'prepare_input':
                    stack.enter_context(patch.object(workflow, name, side_effect=lambda *a, **kw:
                        (Batch(input_ids=MagicMock()), {'input_tokens': 100})))
                else:
                    if name == 'error_details':
                        stack.enter_context(patch.object(workflow, name, side_effect=lambda error, torch:
                            {'cuda_oom': isinstance(error, OOM), 'message': str(error)}))
                    else:
                        stack.enter_context(patch.object(workflow, name, return_value=value))
            stack.enter_context(patch.object(workflow, 'Monitor', Monitor))
            stack.enter_context(patch('builtins.print'))
            result = workflow.run_stability(config, 'qwen3-vl', self.root/'run', 'native')
        return result, torch, model

    def test_eight_updates_share_one_optimizer_and_save_adapter(self):
        result, torch, model = self.mocked_training()
        self.assertEqual(result['status'], 'success', result.get('error'))
        self.assertEqual(result['optimizer_steps'], 8)
        torch.optim.AdamW.assert_called_once()
        self.assertEqual(torch.optim.AdamW.return_value.step.call_count, 8)
        self.assertEqual(model.call_count, 32)
        model.save_pretrained.assert_called_once_with(self.root/'run/adapter', safe_serialization=True)
        self.assertEqual(len(list((self.root/'run').glob('step-*.json'))), 8)

    def test_oom_stops_first_microbatch_without_retry_or_save(self):
        result, torch, model = self.mocked_training(oom=True)
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(result['error']['cuda_oom'])
        self.assertEqual(model.call_count, 1)
        torch.optim.AdamW.return_value.step.assert_not_called()
        model.save_pretrained.assert_not_called()

"""Protect data isolation, bounded configuration and lossless pilot outputs."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from market_levels.datasets.domain.examples import INSTRUCTION
from market_levels.inference.domain.inputs import ImageInput, conversation, spread_indices
from market_levels.inference.io.pilot import select_examples, append_response, write_json
from market_levels.modeling.config import load_config
from market_levels.modeling.io.checkpoints import download_plan
from market_levels.modeling.io.runtime import error_details, prepare_input, set_resolution
from market_levels.shared.manifests import seal
from market_levels.cli.vlm_feasibility import main
from market_levels.inference.workflows.pilot import run_inference
from support.paths import PROJECT


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vlm-pilot-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = load_config(PROJECT / 'configs/vlm/feasibility.json')

    def dataset(self, split='validation', overlay=False):
        root = self.root / 'dataset'
        (root / 'splits').mkdir(parents=True)
        (root / 'images').mkdir()
        (root / 'metadata').mkdir()
        rows, entries = [], []
        for symbol in ('BTCUSDT', 'ETHUSDT'):
            for i in range(18):
                identity = f'{symbol}-{i:02d}'
                entry = {'id': identity, 'split': split, 'symbol': symbol, 'source': 'real',
                         'image': f'images/{identity}.png', 'metadata': f'metadata/{identity}.json'}
                (root / entry['image']).write_bytes(b'fixture-pixels')
                meta = {'start_utc': f'2024-{i:02d}', 'rendering': {'visualization': {'target_lines': overlay}}}
                if split == 'train' and i == 0:
                    meta['start_utc'] = None  # Production synthetics have no real-world date.
                (root / entry['metadata']).write_text(json.dumps(meta), encoding='utf-8')
                rows.append({'id': identity, 'split': split, 'image': entry['image'], 'instruction': INSTRUCTION,
                             'answer': {'supports': [12345.67], 'resistances': [99999.99]}})
                entries.append(entry)
        # Deliberately scramble JSONL; chronology must come from dates/IDs.
        (root / f'splits/{split}.jsonl').write_text('\n'.join(json.dumps(r) for r in reversed(rows)), encoding='utf-8')
        seal(root, {'kind': 'production_dataset', 'status': 'complete', 'entries': entries})
        return root

    def test_configuration_is_pinned_and_preserves_requested_models(self):
        self.assertEqual(self.config['models']['qwen3-vl']['id'], 'Qwen/Qwen3-VL-2B-Instruct')
        self.assertIs(self.config['models']['qwen3.5']['enable_thinking'], False)
        self.assertEqual(self.config['generation']['max_new_tokens'], 256)

    def test_invalid_or_ignored_configuration_fails(self):
        for mutation in (lambda d: d.update(unknown=True),
                         lambda d: d['models']['qwen3-vl'].update(revision='main'),
                         lambda d: d['models']['qwen3-vl'].update(id='unknown/repo'),
                         lambda d: d['generation'].update(do_sample=True),
                         lambda d: d['image_budgets'].update(native=999999),
                         lambda d: d['training'].update(rank=64)):
            doc = copy.deepcopy(self.config)
            mutation(doc)
            path = self.root / 'bad.json'
            path.write_text(json.dumps(doc), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_config(path)

    def test_eight_stable_ids_spread_across_dates_without_answers(self):
        root = self.dataset()
        inputs, records, targets = select_examples(root)
        self.assertEqual([r['chronological_rank'] for r in records], [0, 6, 11, 17] * 2)
        self.assertEqual([x.id for x in inputs], [r['id'] for r in records])
        self.assertEqual([r['symbol'] for r in records], ['BTCUSDT'] * 4 + ['ETHUSDT'] * 4)
        self.assertEqual(targets, {})
        self.assertEqual(set(vars(inputs[0])), {'id', 'image', 'instruction'})
        self.assertEqual(inputs, select_examples(root)[0])

    def test_training_selects_four_train_only_and_keeps_targets_separate(self):
        inputs, records, targets = select_examples(self.dataset('train'), split='train')
        self.assertEqual(len(inputs), 4)
        self.assertTrue(all(r['split'] == 'train' for r in records))
        self.assertEqual(set(targets), {x.id for x in inputs})
        self.assertNotIn('answer', vars(inputs[0]))

    def test_test_split_rejected_before_any_read(self):
        with patch('market_levels.inference.io.pilot.verify_files') as verify:
            with self.assertRaises(ValueError):
                select_examples(Path('does-not-exist'), split='test')
            verify.assert_not_called()

    def test_overlay_refused(self):
        with self.assertRaisesRegex(ValueError, 'Overlay'):
            select_examples(self.dataset(overlay=True))

    def test_modified_image_detected_by_manifest(self):
        root = self.dataset()
        (root / 'images/BTCUSDT-00.png').write_bytes(b'modified')
        with self.assertRaises(ValueError):
            select_examples(root)

    def test_conversation_contains_only_pixels_and_unchanged_instruction(self):
        item = ImageInput('secret-id', Path('BTCUSDT.png'), INSTRUCTION)
        pixels = object()
        message = conversation(item, pixels)
        self.assertEqual(message, [{'role': 'user', 'content': [{'type': 'image', 'image': pixels},
                                                              {'type': 'text', 'text': INSTRUCTION}]}])

    def test_raw_response_is_preserved_with_invalid_json_and_leading_text(self):
        path = self.root / 'predictions.jsonl'
        raw = '  Wyjaśnienie\n```json\n{"supports": [NaN]}\n```\n'
        append_response(path, 'id-unchanged', raw)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'id': 'id-unchanged', 'response': raw})

    def test_metadata_write_refuses_overwrite(self):
        path = self.root / 'metadata.json'
        write_json(path, self.config)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), self.config)
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            write_json(path, {})
        self.assertEqual(path.read_bytes(), before)

    def test_existing_cli_output_is_never_touched(self):
        (self.root / 'keep').write_text('original')
        with self.assertRaises(SystemExit):
            main(['select', '--output', str(self.root)])
        self.assertEqual({p.name for p in self.root.iterdir()}, {'keep'})
        for args in (['select', '--model', 'qwen3.5'], ['infer', '--resolution', 'reduced']):
            output = self.root / 'new-output'
            with self.assertRaises(SystemExit):
                main(args + ['--config', str(PROJECT / 'configs/vlm/feasibility.json'), '--output', str(output)])
            self.assertFalse(output.exists())

    def test_resolution_budget_uses_supported_processor_api(self):
        processor = SimpleNamespace(image_processor=SimpleNamespace(size={}, to_dict=lambda: {'saved': True}))
        self.assertEqual(set_resolution(processor, 65536, 786432), {'saved': True})
        self.assertEqual(processor.image_processor.size, {'shortest_edge': 65536, 'longest_edge': 786432})

    def test_cuda_oom_has_explicit_classification_and_memory(self):
        class OutOfMemoryError(RuntimeError):
            pass
        torch = SimpleNamespace(cuda=SimpleNamespace(OutOfMemoryError=OutOfMemoryError))
        with patch('market_levels.modeling.io.runtime.gpu_snapshot', return_value={'allocated_bytes': 123}):
            result = error_details(OutOfMemoryError('CUDA out of memory'), torch)
        self.assertTrue(result['cuda_oom'])
        self.assertEqual(result['memory']['allocated_bytes'], 123)

    def test_selection_insufficient_group_refused(self):
        with self.assertRaises(ValueError):
            spread_indices(3, 4)

    def test_download_refuses_private_or_unpinned_identity_without_files(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({'id': 'bad/repo', 'sha': '0'*40}).encode()
        with patch('urllib.request.urlopen', return_value=response):
            with self.assertRaises(ValueError):
                download_plan(self.config)

    def test_oom_stops_each_resolution_after_one_attempt_and_saves_failure(self):
        from PIL import Image
        image = self.root / 'input.png'
        Image.new('RGB', (1024, 768), 'white').save(image)
        inputs = [ImageInput(str(i), image, INSTRUCTION) for i in range(8)]
        model = Mock()
        model.named_modules.return_value = [('model.visual', Mock())]
        processor = SimpleNamespace(image_processor=SimpleNamespace(size={}, to_dict=lambda: {}))
        torch = SimpleNamespace(cuda=SimpleNamespace(empty_cache=Mock()))
        module = 'market_levels.inference.workflows.pilot.'
        with patch(module+'select_examples', return_value=(inputs, [], {})), \
                patch(module+'load_model', return_value=(torch, model, processor, {})), \
                patch(module+'local_checkpoint', return_value=self.root), \
                patch(module+'prepare_input', side_effect=RuntimeError('CUDA out of memory')) as prepare, \
                patch(module+'error_details', return_value={'cuda_oom': True, 'message': 'CUDA out of memory'}):
            result = run_inference(self.config, 'qwen3-vl', self.root / 'oom')
        self.assertEqual(prepare.call_count, 2)
        self.assertTrue(all(r['completed'] == 0 and len(r['errors']) == 1 for r in result['resolutions'].values()))
        self.assertTrue((self.root / 'oom/summary.json').is_file())

    def test_download_plan_refuses_transfer_and_disk_over_budget(self):
        for size, free in ((19_000_000_000, 100_000_000_000), (1_000, 19_000_000_000)):
            responses = []
            for spec in self.config['models'].values():
                info = {'id': spec['id'], 'sha': spec['revision'], 'gated': False, 'private': False,
                        'cardData': {'license': 'apache-2.0'},
                        'siblings': [{'rfilename': 'model.safetensors', 'size': size}]}
                response = Mock()
                response.__enter__ = Mock(return_value=response)
                response.__exit__ = Mock(return_value=False)
                response.read.return_value = json.dumps(info).encode()
                responses.append(response)
            with patch('urllib.request.urlopen', side_effect=responses), \
                    patch('market_levels.modeling.io.checkpoints.shutil.disk_usage', return_value=SimpleNamespace(free=free)):
                with self.assertRaises(ValueError):
                    download_plan(self.config)

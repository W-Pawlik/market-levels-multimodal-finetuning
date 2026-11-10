"""Reject altered adapter tensors and configuration before claiming reload success."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from market_levels.modeling.io.adapter_check import check_adapter
from market_levels.modeling.stability_config import load_config, REVISION


class AdapterRoundtripTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.adapter = self.root/'adapter'; self.adapter.mkdir()
        self.config = load_config(Path('configs/vlm/stability.json'))
        (self.root/'config.json').write_text(json.dumps(self.config))
        self.spec = {'base_model_name_or_path': '/cache/'+REVISION, 'r': 8, 'lora_alpha': 16,
                     'target_modules': ['model.language_model.layers.0.self_attn.q_proj']}

    def check(self, disk=None, actual=None, before=None):
        (self.adapter/'adapter_config.json').write_text(json.dumps(self.spec))
        tensors = {'lora_A': [1, 2], 'lora_B': [3, 4]}
        torch = SimpleNamespace(equal=lambda a, b: a == b,
            isfinite=lambda value: SimpleNamespace(all=lambda: True))
        reader = lambda path: (before if before is not None else tensors) if 'before-save' in path else (disk if disk is not None else tensors)
        with patch.dict('sys.modules', {'torch': torch, 'safetensors.torch': SimpleNamespace(load_file=reader)}), \
                patch('market_levels.modeling.io.adapter_check.adapter_state', return_value=actual if actual is not None else tensors):
            return check_adapter(None, self.adapter, self.config)

    def test_exact_before_saved_and_reloaded_tensors(self):
        result = self.check()
        self.assertTrue(result['tensor_values_exact'])
        self.assertTrue(result['pre_save_tensors_exact'])
        self.assertTrue(result['config_exact'])

    def test_changed_serialized_or_loaded_tensor_rejected(self):
        with self.assertRaisesRegex(ValueError, 'pre-save'):
            self.check(disk={'lora_A': [9, 2], 'lora_B': [3, 4]})
        with self.assertRaisesRegex(ValueError, 'tensor mismatch'):
            self.check(actual={'lora_A': [9, 2], 'lora_B': [3, 4]})

    def test_different_run_config_rejected(self):
        original = copy.deepcopy(self.config)
        self.config['seed'] += 1
        with self.assertRaisesRegex(ValueError, 'configuration'):
            self.check()
        self.config = original

    def test_wrong_base_revision_or_visual_targets_rejected(self):
        self.spec['base_model_name_or_path'] = '/cache/wrong'
        with self.assertRaisesRegex(ValueError, 'structure'):
            self.check()
        self.spec['base_model_name_or_path'] = '/cache/'+REVISION
        self.spec['target_modules'] = ['model.visual.q_proj']
        with self.assertRaisesRegex(ValueError, 'structure'):
            self.check()

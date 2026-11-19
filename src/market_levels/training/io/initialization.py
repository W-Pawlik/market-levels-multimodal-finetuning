"""Verify parent artifacts and load only LoRA weights for a new experiment."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from ...modeling.io.adapter_check import adapter_state
from ...modeling.stability_config import REVISION
from ...shared.integrity import sha256_file
from ...shared.manifests import verify_files
from ..domain.schedule import validate_state
from .checkpoints import checkpoint_metadata


def require_extra_approval(config, explicit):
    if 'extra_epoch' not in config or not config['extra_epoch']['approved'] or not explicit:
        raise ValueError('Extra epoch requires extra_epoch.approved=true AND --approve-extra-epoch')


def validate_parent_spec(spec):
    """Check the source PEFT architecture, including options affecting scaling."""
    targets = spec.get('target_modules')
    expected_targets = {f'model.language_model.layers.{i}.self_attn.{q}'
                        for i in range(28) for q in ('q_proj', 'v_proj')}
    if (REVISION not in spec.get('base_model_name_or_path', '') or spec.get('peft_type') != 'LORA'
            or spec.get('task_type') != 'CAUSAL_LM' or spec.get('r') != 8
            or spec.get('lora_alpha') != 16 or spec.get('lora_dropout') != 0
            or spec.get('bias') != 'none' or not isinstance(targets, list)
            or set(targets) not in ({'q_proj', 'v_proj'}, expected_targets)
            or any(spec.get(k) for k in ('modules_to_save', 'rank_pattern', 'alpha_pattern',
                'use_dora', 'use_rslora', 'use_qalora', 'lora_bias', 'layer_replication',
                'target_parameters', 'trainable_token_indices', 'alora_invocation_tokens',
                'exclude_modules', 'layers_to_transform', 'layers_pattern'))):
        raise ValueError('Parent adapter LoRA architecture/revision mismatch')


def validate_parent_tensors(torch, tensors):
    expected = {}
    for layer in range(28):
        for projection, out_features in (('q_proj', 2048), ('v_proj', 1024)):
            prefix = f'base_model.model.model.language_model.layers.{layer}.self_attn.{projection}'
            expected[prefix + '.lora_A.weight'] = (8, 2048)
            expected[prefix + '.lora_B.weight'] = (out_features, 8)
    if set(tensors) != set(expected) or len(tensors) != 112:
        raise ValueError('Parent adapter requires exactly 112 language LoRA tensors')
    for key, shape in expected.items():
        tensor = tensors[key]
        if tuple(tensor.shape) != shape or tensor.dtype != torch.float32 or not bool(torch.isfinite(tensor).all()):
            raise ValueError(f'Parent adapter tensor shape/dtype/nonfinite mismatch: {key}')
    if sum(t.numel() for t in tensors.values()) != 1605632:
        raise ValueError('Parent adapter requires 1605632 parameters')


def verify_parent(config):
    """Verify CPU bytes/tensors; never deserialize the parent's state.pt."""
    extra = config['extra_epoch']
    adapter, checkpoint = Path(extra['parent_adapter']), Path(extra['parent_checkpoint'])
    for path, expected in ((adapter / 'manifest.json', extra['parent_manifest_sha256']),
                           (checkpoint / 'manifest.json', extra['parent_checkpoint_manifest_sha256']),
                           (adapter / 'adapter_model.safetensors', extra['parent_adapter_sha256'])):
        if sha256_file(path) != expected:
            raise ValueError(f'Parent artifact SHA-256 mismatch: {path}')
    manifest = verify_files(adapter)
    if manifest.get('kind') != 'vlm_inference_adapter' or manifest.get('status') != 'complete':
        raise ValueError('Parent must be a separately exported inference adapter')
    meta = checkpoint_metadata(checkpoint)
    identity = json.loads((adapter / 'training-identity.json').read_text(encoding='utf-8'))
    if identity != meta['identity']:
        raise ValueError('Parent export/checkpoint identities differ')
    old = identity['config']
    if (old['pipeline']['epochs'] != 2 or 'extra_epoch' in old
            or meta['sampler']['global_step'] != 350 or meta['sampler']['processed_examples'] != 1396
            or old['runtime']['models'] != config['runtime']['models'] or old['fixed'] != config['fixed']):
        raise ValueError('Parent must be the completed two-epoch Qwen experiment')
    expected_runtime = copy.deepcopy(old['runtime'])
    expected_runtime['seed'] = config['runtime']['seed']
    expected_runtime['training']['learning_rate'] = config['runtime']['training']['learning_rate']
    if expected_runtime != config['runtime']:
        raise ValueError('Parent runtime mismatch beyond approved seed/LR changes')
    validate_state(meta['sampler'], identity['dataset']['selected_ids'], old['pipeline'])
    if (sha256_file(Path(config['runtime']['dataset']) / 'manifest.json')
            != identity['dataset']['manifest_sha256']):
        raise ValueError('Parent dataset changed')
    for folder in (adapter, checkpoint / 'adapter'):
        validate_parent_spec(json.loads((folder / 'adapter_config.json').read_text(encoding='utf-8')))
    import torch
    from safetensors.torch import load_file
    saved = load_file(str(adapter / 'adapter_model.safetensors'), device='cpu')
    other = load_file(str(checkpoint / 'adapter/adapter_model.safetensors'), device='cpu')
    validate_parent_tensors(torch, saved)
    validate_parent_tensors(torch, other)
    if not all(torch.equal(saved[k], other[k]) for k in saved):
        raise ValueError('Parent export/checkpoint tensor values differ')
    return {'parent_experiment': extra['parent_experiment'], 'parent_checkpoint_step': 350,
            'parent_adapter_sha256': extra['parent_adapter_sha256'],
            'parent_manifest_sha256': extra['parent_manifest_sha256'],
            'parent_checkpoint_manifest_sha256': extra['parent_checkpoint_manifest_sha256'],
            'additional_epochs': 1, 'optimizer_state': 'new', 'scheduler_state': 'new',
            'rng_state': 'new seed, not inherited', 'tensor_count': 112,
            'trainable_parameters': 1605632, 'parent_tensor_values_exact': True}


def extra_context(config, resume=None, initialize_adapter=None):
    if resume is not None and initialize_adapter is not None:
        raise ValueError('Initialization and resume are mutually exclusive')
    if initialize_adapter is not None and Path(initialize_adapter).resolve() != Path(config['extra_epoch']['parent_adapter']).resolve():
        raise ValueError('Initialize adapter differs from pinned parent')
    provenance = verify_parent(config)
    if resume is not None:
        meta = checkpoint_metadata(resume)
        if meta['identity']['config'] != config or meta['identity'].get('provenance') != provenance:
            raise ValueError('Extra-epoch resume config/provenance mismatch; old checkpoint cannot be resumed')
    return provenance


def load_initial_adapter(torch, model, adapter: Path, expected_sha256):
    """Load into the single existing PEFT adapter and require exact tensors."""
    if sha256_file(adapter / 'adapter_model.safetensors') != expected_sha256:
        raise ValueError('Initial adapter changed since verification')
    from peft import set_peft_model_state_dict
    from safetensors.torch import load_file
    saved = load_file(str(adapter / 'adapter_model.safetensors'), device='cpu')
    actual = adapter_state(model)
    if saved.keys() != actual.keys() or any(saved[k].shape != actual[k].shape or saved[k].dtype != actual[k].dtype for k in saved):
        raise ValueError('Initial adapter tensor keys/shapes/dtypes differ from model')
    result = set_peft_model_state_dict(model, saved)
    actual = adapter_state(model)
    if result.unexpected_keys or not all(torch.equal(actual[k], saved[k]) for k in saved):
        raise ValueError('Initial adapter tensor values differ after loading')
    trainable = {name: p for name, p in model.named_parameters() if p.requires_grad}
    if (len(trainable) != len(saved) or any('lora_' not in k for k in trainable)
            or sum(p.numel() for p in trainable.values()) != sum(t.numel() for t in saved.values())):
        raise ValueError('Unexpected/non-trainable initial adapter parameters')
    return {'tensor_values_exact': True, 'tensor_count': len(saved),
            'trainable_parameters': sum(t.numel() for t in saved.values()),
            'parent_adapter_sha256': expected_sha256, 'optimizer_state': 'new', 'scheduler_state': 'new'}



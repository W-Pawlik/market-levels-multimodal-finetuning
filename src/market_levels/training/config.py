"""Effective stage 4.2 settings; frozen model conditions reuse the pilot."""
from __future__ import annotations

import math
from pathlib import Path

from ..shared.configuration import read_configuration
from ..modeling.stability_config import REVISION

DEFAULTS = {
    'epochs': 2, 'max_steps': None, 'gradient_accumulation': 4, 'batch_size': 1,
    'scheduler': 'linear', 'warmup_steps': 18, 'seed': 20261110,
    'max_sequence_tokens': 2048, 'save_every_steps': 25, 'validate_every_steps': 175,
    'log_every_steps': 1, 'smoke_examples': 9, 'smoke_steps': 3,
    'empty_cache_reserved_mib': 8000, 'minimum_ram_mib': 4096,
    'minimum_commit_headroom_mib': 8192, 'maximum_idle_vram_mib': 450,
    'required_gpu': 'NVIDIA GeForce RTX 3060 Ti', 'full_approved': False,
}


def load_config(path: Path) -> dict:
    config = read_configuration(path)
    if set(config) != {'runtime', 'pipeline'} or set(config['pipeline']) - DEFAULTS.keys():
        raise ValueError('Unknown training configuration fields')
    runtime = config['runtime']
    if set(runtime) != {'dataset', 'cache', 'models', 'generation', 'image_budgets', 'min_pixels', 'seed', 'training'}:
        raise ValueError('Unknown runtime fields')
    if runtime['models'] != {'qwen3-vl': {'id': 'Qwen/Qwen3-VL-2B-Instruct', 'revision': REVISION,
            'architecture': 'Qwen3VLForConditionalGeneration', 'enable_thinking': None}}:
        raise ValueError('Approved model and revision required')
    if runtime['dataset'] != 'data/datasets/ds35-800-20261107-a':
        raise ValueError('Approved dataset required; test split forbidden')
    if (runtime['generation'] != {'do_sample': False, 'num_beams': 1, 'max_new_tokens': 256, 'use_cache': True}
            or runtime['image_budgets'] != {'native': 786432} or runtime['min_pixels'] != 65536):
        raise ValueError('Frozen generation/image settings changed')
    training = runtime['training']
    if set(training) != {'rank', 'alpha', 'learning_rate', 'gradient_checkpointing'} or any(
            training[k] != v for k, v in {'rank': 8, 'alpha': 16, 'gradient_checkpointing': True}.items()):
        raise ValueError('Frozen QLoRA settings changed')
    if isinstance(training['learning_rate'], bool) or not isinstance(training['learning_rate'], (float, int)) or not math.isfinite(training['learning_rate']) or training['learning_rate'] <= 0:
        raise ValueError('Invalid learning rate')
    if not isinstance(runtime['cache'], str) or not runtime['cache'] or type(runtime['seed']) is not int:
        raise ValueError('Invalid cache/seed')
    settings = DEFAULTS | config['pipeline']
    for name, value in settings.items():
        if name in ('max_steps', 'scheduler', 'required_gpu', 'full_approved'):
            continue
        if type(value) is not int or value < (0 if name in ('seed', 'warmup_steps', 'empty_cache_reserved_mib') else 1):
            raise ValueError(f'Invalid integer: {name}')
    if settings['max_steps'] is not None and (type(settings['max_steps']) is not int or settings['max_steps'] < 1):
        raise ValueError('Invalid max_steps')
    if settings['scheduler'] not in ('linear', 'cosine', 'constant') or settings['batch_size'] != 1:
        raise ValueError('Unsupported scheduler or batch size')
    if type(settings['full_approved']) is not bool or settings['required_gpu'] != DEFAULTS['required_gpu']:
        raise ValueError('Invalid approval/GPU')
    if settings['smoke_steps'] > 10 or settings['smoke_examples'] > 32:
        raise ValueError('Smoke must stay bounded: <=10 steps, <=32 examples')
    runtime = {**runtime, 'seed': settings['seed']}
    return {'runtime': runtime, 'pipeline': settings,
            'fixed': {'quantization': 'NF4', 'double_quantization': True, 'compute_dtype': 'bfloat16',
                'vision_dtype': 'bfloat16', 'other_unquantized_frozen_dtype': 'float32',
                'lora_targets': 'language self_attn q_proj/v_proj only', 'lora_dropout': 0.0,
                'use_reentrant': False, 'optimizer': 'AdamW', 'betas': [0.9, 0.999],
                'eps': 1e-8, 'weight_decay': 0.01, 'gradient_clip': 1.0,
                'optimizer_options': {'amsgrad': False, 'foreach': None, 'maximize': False,
                                      'capturable': False, 'differentiable': False, 'fused': None},
                'quantization_skip_modules': ['model.visual', 'lm_head'], 'attention': 'sdpa',
                'device_map': {'': 'cuda:0'}, 'tf32': False, 'deterministic_algorithms': 'warn_only',
                'loss_aggregation': 'mean of per-example mean supervised-token losses; divide by actual group size',
                'workers': 0, 'image_size': [1024, 768], 'instruction_version': 'pl-sr-v1',
                'retention': 'keep all; no automatic deletion', 'ordering': 'shuffle sorted train IDs with Random(seed+epoch)'}}

"""Frozen conditions for stage 4.1 part 2; no model selection or full training."""
from pathlib import Path

from ..shared.configuration import read_configuration

REVISION = '89644892e4d85e24eaac8bacfd4f463576704203'


def load_config(path: Path) -> dict:
    config = read_configuration(path)
    expected = {'dataset', 'cache', 'models', 'generation', 'image_budgets', 'min_pixels', 'seed', 'training'}
    if set(config) != expected:
        raise ValueError('Unknown stability configuration fields')
    if config['models'] != {'qwen3-vl': {'id': 'Qwen/Qwen3-VL-2B-Instruct', 'revision': REVISION,
            'architecture': 'Qwen3VLForConditionalGeneration', 'enable_thinking': None}}:
        raise ValueError('Stage requires the approved pinned Qwen3-VL checkpoint')
    if config['dataset'] != 'data/datasets/ds35-800-20261107-a':
        raise ValueError('Stage requires the approved production dataset')
    if config['generation'] != {'do_sample': False, 'num_beams': 1, 'max_new_tokens': 256, 'use_cache': True}:
        raise ValueError('Generation conditions are frozen')
    if config['image_budgets'] != {'native': 786432} or config['min_pixels'] != 65536:
        raise ValueError('Image conditions are frozen')
    if config['training'] != {'rank': 8, 'alpha': 16, 'learning_rate': 0.0002, 'gradient_checkpointing': True}:
        raise ValueError('Training conditions are frozen')
    if type(config['seed']) is not int or not isinstance(config['cache'], str) or not config['cache']:
        raise ValueError('Invalid seed/cache')
    return config

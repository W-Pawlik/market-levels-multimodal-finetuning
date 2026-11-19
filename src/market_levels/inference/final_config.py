"""Frozen final-test plan, independent from training approvals and split guards."""
from pathlib import Path

from ..shared.configuration import read_configuration
from ..shared.integrity import sha256_file
from ..evaluation.protocol import PROTOCOL_SHA256

SELECTION = Path('docs/vlm/FINAL_MODEL_SELECTION.json')
SELECTION_SHA256 = '287e45bd688de30293b129a536086133be380116202ca74a0fe69c6ab9bd921e'
OUTPUT = Path('results/vlm46-final-test')
VARIANTS = ('base-nf4', 'finetuned-nf4')


def load_plan(path: Path) -> tuple[dict, dict]:
    config = read_configuration(path)
    required = {'purpose', 'execution_approved', 'selection', 'selection_sha256', 'dataset',
                'split', 'output', 'runtime', 'resources', 'image_input_fingerprint'}
    if set(config) != required or config['purpose'] != 'one_final_test_pair_v1':
        raise ValueError('A separate final-test plan is required')
    if (Path(config['selection']).resolve() != SELECTION.resolve()
            or config['selection_sha256'] != SELECTION_SHA256
            or sha256_file(SELECTION) != SELECTION_SHA256):
        raise ValueError('Frozen selection SHA-256/path mismatch')
    selection = read_configuration(SELECTION)
    historical = read_configuration(Path('configs/vlm/stability.json'))
    original = read_configuration(Path('results/vlm41-cz2-20261110-1840/base-nf4/config.json'))
    if historical != original:
        raise ValueError('Historical NF4 configuration no longer matches its original run')
    if config['runtime'] != historical:
        raise ValueError('Final inference must exactly match the historical NF4 runtime')
    expected = selection['effective_config']['runtime']
    for key in ('models', 'generation', 'image_budgets', 'min_pixels', 'cache', 'dataset'):
        if config['runtime'][key] != expected[key]:
            raise ValueError(f'Frozen model/inference mismatch: {key}')
    pipeline = selection['effective_config']['pipeline']
    resources = {key: pipeline[key] for key in ('required_gpu', 'maximum_idle_vram_mib',
                 'minimum_ram_mib', 'minimum_commit_headroom_mib')}
    if (config['split'] != 'test' or config['dataset'] != selection['dataset_manifest'].rsplit('/', 1)[0]
            or Path(config['output']).resolve() != OUTPUT.resolve() or config['resources'] != resources
            or type(config['execution_approved']) is not bool):
        raise ValueError('Frozen final split/dataset/output/resource plan mismatch')
    if (selection['evaluation_protocol_sha256'] != PROTOCOL_SHA256
            or selection['base_revision'] != historical['models']['qwen3-vl']['revision']):
        raise ValueError('Frozen protocol or revision mismatch')
    if not isinstance(config['image_input_fingerprint'], str) or len(config['image_input_fingerprint']) != 64:
        raise ValueError('Pinned image-input fingerprint required')
    return config, selection


def require_approval(config: dict, explicit: bool) -> None:
    if config['execution_approved'] is not True or explicit is not True:
        raise ValueError('Final test requires execution_approved=true AND --approve-final-test')

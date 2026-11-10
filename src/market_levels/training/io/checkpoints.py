"""Sealed, atomically published full training checkpoints, separate PEFT exports."""
from __future__ import annotations

import json
import os
import random
import uuid
from pathlib import Path

from ...shared.manifests import seal, verify_files
from ...shared.publication import publish_directory
from ...shared.json_io import write_json

SCHEMA = 1


def capture_rng(torch):
    import numpy as np
    return {'python': random.getstate(), 'numpy': np.random.get_state(), 'cpu': torch.get_rng_state(),
            'cuda': torch.cuda.get_rng_state_all() if torch.cuda.is_available() else []}


def restore_rng(torch, state):
    import numpy as np
    random.setstate(state['python'])
    np.random.set_state(state['numpy'])
    torch.set_rng_state(state['cpu'])
    if state['cuda']:
        torch.cuda.set_rng_state_all(state['cuda'])


def checkpoint_metadata(path: Path, identity: dict | None = None, *, allow_staging=False):
    if not allow_staging and any(part.endswith('.partial') for part in path.parts):
        raise ValueError('Staging directory is not a published checkpoint')
    manifest = verify_files(path)
    if manifest.get('kind') != 'vlm_training_checkpoint' or manifest.get('schema') != SCHEMA or manifest.get('status') != 'complete':
        raise ValueError('Incomplete/unsupported training checkpoint')
    required = {'state.pt', 'metadata.json', 'adapter/adapter_config.json', 'adapter/adapter_model.safetensors'}
    if not required <= manifest['files'].keys():
        raise ValueError('Missing checkpoint components')
    meta = json.loads((path / 'metadata.json').read_text(encoding='utf-8'))
    if meta.get('schema') != SCHEMA or (identity is not None and meta['identity'] != identity):
        raise ValueError('Checkpoint model/config/dataset/processor/environment mismatch')
    return meta


def save_checkpoint(torch, model, optimizer, scheduler, state, identity, root: Path):
    if any(p.grad is not None for p in model.parameters() if p.requires_grad):
        raise ValueError('Checkpoint requires optimizer boundary with cleared gradients')
    root.mkdir(parents=True, exist_ok=True)
    name = f"step-{state['global_step']:06d}"
    final = root / name
    stage = root / ('.' + name + '-' + uuid.uuid4().hex[:8] + '.partial')
    stage.mkdir()
    rng = capture_rng(torch)
    try:
        model.save_pretrained(stage / 'adapter', safe_serialization=True)
        payload = {'optimizer': optimizer.state_dict(), 'scheduler': scheduler.state_dict(),
                   'sampler': state, 'rng': rng}
        with (stage / 'state.pt').open('xb') as stream:
            torch.save(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        write_json(stage / 'metadata.json', {'schema': SCHEMA, 'identity': identity, 'sampler': state,
                                            'trusted_local_torch_state_only': True})
        seal(stage, {'kind': 'vlm_training_checkpoint', 'schema': SCHEMA, 'status': 'complete'})
        checkpoint_metadata(stage, identity, allow_staging=True)
        # Verify deserialization before making the checkpoint discoverable.
        loaded = torch.load(stage / 'state.pt', map_location='cpu', weights_only=False)
        if set(loaded) != {'optimizer', 'scheduler', 'sampler', 'rng'} or loaded['sampler'] != state:
            raise ValueError('Incomplete training state')
        publish_directory(stage, final)
        latest = root / ('.latest-' + uuid.uuid4().hex + '.tmp')
        latest.write_text(name + '\n', encoding='utf-8')
        latest.replace(root / 'latest.txt')
        return final
    finally:
        # Saving must not change the stochastic trajectory of an uninterrupted run.
        restore_rng(torch, rng)


def load_checkpoint(torch, path, identity, model, optimizer, scheduler):
    meta = checkpoint_metadata(path, identity)  # Check bytes before unpickling trusted local state.
    payload = torch.load(path / 'state.pt', map_location='cpu', weights_only=False)
    if set(payload) != {'optimizer', 'scheduler', 'sampler', 'rng'}:
        raise ValueError('Missing training state')
    if payload['sampler'] != meta['sampler']:
        raise ValueError('Sampler metadata differs from serialized state')
    from peft import set_peft_model_state_dict
    from ...modeling.io.adapter_check import adapter_state
    from safetensors.torch import load_file
    saved = load_file(str(path / 'adapter/adapter_model.safetensors'))
    expected = adapter_state(model)
    if saved.keys() != expected.keys() or any(saved[k].shape != expected[k].shape for k in saved):
        raise ValueError('Missing/extra adapter tensors or invalid shapes')
    result = set_peft_model_state_dict(model, saved)
    if result.unexpected_keys:
        raise ValueError('Unexpected adapter tensor keys')
    optimizer.load_state_dict(payload['optimizer'])
    scheduler.load_state_dict(payload['scheduler'])
    restore_rng(torch, payload['rng'])
    return payload['sampler']


def export_adapter(model, path: Path, identity: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_name('.' + path.name + '-' + uuid.uuid4().hex[:8] + '.partial')
    stage.mkdir()
    model.save_pretrained(stage, safe_serialization=True)
    write_json(stage / 'training-identity.json', identity)
    seal(stage, {'kind': 'vlm_inference_adapter', 'schema': SCHEMA, 'status': 'complete'})
    verify_files(stage)
    publish_directory(stage, path)

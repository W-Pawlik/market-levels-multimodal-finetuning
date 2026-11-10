"""Match QLoRA frozen dtypes and verify adapter tensors in a fresh process."""
from pathlib import Path


def prepare_nf4(model, torch, checkpointing=False):
    from peft import prepare_model_for_kbit_training
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=checkpointing,
        gradient_checkpointing_kwargs={'use_reentrant': False})
    model.model.visual.to(dtype=torch.bfloat16)
    return model


def adapter_state(model):
    from peft import get_peft_model_state_dict
    return {k: v.detach().cpu().contiguous().clone() for k, v in get_peft_model_state_dict(model).items()}


def check_adapter(model, folder: Path, config: dict):
    import json
    import torch
    from safetensors.torch import load_file
    from ..stability_config import REVISION
    expected = json.loads((folder.parent / 'config.json').read_text(encoding='utf-8'))
    if config != expected or config['models']['qwen3-vl']['revision'] != REVISION:
        raise ValueError('Adapter configuration or base revision mismatch')
    saved = load_file(str(folder / 'adapter_model.safetensors'))
    before = load_file(str(folder.parent / 'adapter-before-save.safetensors'))
    spec = json.loads((folder / 'adapter_config.json').read_text(encoding='utf-8'))
    if (REVISION not in spec['base_model_name_or_path'] or spec['r'] != 8 or spec['lora_alpha'] != 16
            or not spec['target_modules'] or any(name not in ('q_proj', 'v_proj') and
                ('language_model.layers.' not in name or not name.endswith(('.q_proj', '.v_proj')))
                for name in spec['target_modules'])):
        raise ValueError('Adapter structure or base checkpoint path mismatch')
    if before.keys() != saved.keys() or not all(torch.equal(before[k], saved[k]) for k in saved):
        raise ValueError('Serialized adapter differs from pre-save tensors')
    actual = adapter_state(model)
    # PEFT may serialize target suffixes rather than full names. Exact state keys
    # below still require the same language layers and reject any extra vision LoRA.
    if saved.keys() != actual.keys() or not all(torch.equal(saved[k], actual[k]) for k in saved):
        raise ValueError('Adapter tensor mismatch')
    if not all(bool(torch.isfinite(v).all()) for v in actual.values()):
        raise ValueError('Nonfinite adapter')
    return {'tensor_count': len(saved), 'tensor_values_exact': True, 'pre_save_tensors_exact': True, 'config_exact': True,
            'base_revision': REVISION, 'all_finite': True}

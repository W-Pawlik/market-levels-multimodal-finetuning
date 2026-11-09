"""Four train microbatches, one and only one optimizer update."""
from __future__ import annotations

import re
import warnings
from pathlib import Path

from ...evaluation.protocol import dumps
from ...inference.domain.inputs import conversation
from ...inference.io.pilot import select_examples, write_json
from ...modeling.io.checkpoints import local_checkpoint
from ...modeling.io.runtime import load_model, environment, Monitor, prepare_input, set_resolution, error_details
from ..domain.masking import assistant_labels


def run_one_step(config: dict, key: str, output: Path, resolution: str) -> dict:
    if key != 'qwen3-vl':
        raise ValueError('Praktyczny pilot treningu obejmuje tylko zweryfikowanego kandydata Qwen3-VL')
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'config.json', config)
    write_json(output / 'environment.json', environment())
    inputs, selected, targets = select_examples(Path(config['dataset']), split='train')
    write_json(output / 'selected-train.json', selected)
    result = {'status': 'started', 'optimizer_steps': 0, 'microbatch_count': len(inputs),
              'model': config['models'][key], 'resolution': resolution, 'method': 'NF4 double quantization + LoRA', 'warnings': []}
    torch = None
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            torch, model, processor, details = load_model(config, key, local_checkpoint(config, key), quantized=True)
            write_json(output / 'model.json', {**config['models'][key], **details})
            set_resolution(processor, config['min_pixels'], config['image_budgets'][resolution])
            write_json(output / 'image-processor.json', processor.image_processor.to_dict())
            from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
            model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=config['training']['gradient_checkpointing'],
                                                    gradient_checkpointing_kwargs={'use_reentrant': False})
            # PEFT promotes non-quantized parameters to FP32. Keep the frozen vision tower
            # in the verified compute dtype; its output is cast by the language model.
            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported(including_emulation=False) else torch.float16
            model.model.visual.to(dtype=dtype)
            targets_modules = [name for name, _ in model.named_modules()
                               if re.fullmatch(r'model\.language_model\.layers\.\d+\.self_attn\.(q_proj|v_proj)', name)]
            if not targets_modules:
                raise ValueError('Brak zweryfikowanych projekcji językowych; nie stosujemy konfiguracji do encodera obrazu')
            model = get_peft_model(model, LoraConfig(r=config['training']['rank'], lora_alpha=config['training']['alpha'],
                                   lora_dropout=0.0, target_modules=targets_modules, bias='none', task_type='CAUSAL_LM'))
            model.config.use_cache = False
            model.train()
            visual = model.base_model.model.model.visual
            visual.eval()
            if any(p.requires_grad for p in visual.parameters()):
                raise ValueError('Encoder wizualny musi być zamrożony')
            trainable = {name: p for name, p in model.named_parameters() if p.requires_grad}
            if any('lora_' not in name for name in trainable):
                raise ValueError('Trenowane parametry wykraczają poza adapter')
            before = {name: p.detach().cpu().clone() for name, p in trainable.items()}
            optimizer = torch.optim.AdamW(trainable.values(), lr=config['training']['learning_rate'])
            optimizer.zero_grad(set_to_none=True)
            result['trainable_parameters'] = sum(p.numel() for p in trainable.values())
            result['trainable_tensor_names'] = list(trainable)
            result['lora_target_modules'] = targets_modules
            result['total_parameters_reported_by_peft'] = model.get_nb_trainable_parameters()[1]
            visual_calls = []
            hook = visual.register_forward_hook(lambda *args: visual_calls.append(True))
            losses = []
            batches = []
            from PIL import Image
            with Monitor(torch) as measurement:
                for item in inputs:
                    with Image.open(item.image) as original:
                        image = original.convert('RGB')
                    messages = conversation(item, image)
                    prompt, _ = prepare_input(processor, messages, config['models'][key])
                    messages.append({'role': 'assistant', 'content': [{'type': 'text', 'text': dumps(targets[item.id])}]})
                    batch, info = prepare_input(processor, messages, config['models'][key], generation=False)
                    batch['labels'] = assistant_labels(batch['input_ids'], prompt['input_ids'])
                    info.update(id=item.id, supervised_tokens=int((batch['labels'] != -100).sum()),
                                masked_tokens=int((batch['labels'] == -100).sum()))
                    if info['input_tokens'] > 2048:
                        raise ValueError('Zbyt długa sekwencja pilotażu; bez cichego obcinania obrazu lub instrukcji')
                    batches.append(info)
                    batch = batch.to('cuda:0')
                    with torch.autocast('cuda', dtype=dtype):
                        loss = model(**batch, use_cache=False).loss
                    if not bool(torch.isfinite(loss)):
                        raise ValueError('Niefinitywna strata')
                    losses.append(float(loss.detach()))
                    (loss / len(inputs)).backward()
                    del batch, prompt, loss
                gradients = [p.grad for p in trainable.values() if p.grad is not None]
                if not gradients or any(not bool(torch.isfinite(g).all()) for g in gradients):
                    raise ValueError('Brak gradientów lub NaN/Inf')
                result['gradient_tensors'] = len(gradients)
                result['nonzero_gradient_tensors'] = sum(bool((g != 0).any()) for g in gradients)
                result['gradient_norm'] = float(torch.nn.utils.clip_grad_norm_(trainable.values(), 1.0))
                if result['nonzero_gradient_tensors'] == 0:
                    raise ValueError('Wszystkie gradienty zerowe')
                optimizer.step()
                result['optimizer_steps'] = 1
                torch.cuda.synchronize()
            hook.remove()
            changes = {name: float((p.detach().cpu() - before[name]).abs().max()) for name, p in trainable.items()}
            result.update(losses=losses, batches=batches, measurement=measurement.result,
                          vision_forward_calls=len(visual_calls), parameter_max_abs_changes=changes,
                          changed_adapter_tensors=sum(v > 0 for v in changes.values()), vision_frozen=True)
            if not result['changed_adapter_tensors'] or len(visual_calls) < len(inputs):
                raise ValueError('Adapter nie zmienił parametrów lub obraz pominięty')
            # Adapter remains local, outside any automatic publication/handoff.
            model.save_pretrained(output / 'adapter', safe_serialization=True)
            result['adapter_saved'] = True
            result['status'] = 'success'
            result['warnings'] = [str(w.message) for w in caught]
    except Exception as error:
        result['status'] = 'failed'
        result['error'] = error_details(error, torch) if torch is not None else {'type': type(error).__name__, 'message': str(error)}
        result['warnings'] = [str(w.message) for w in caught] if 'caught' in locals() else []
    write_json(output / 'training-result.json', result)
    print(dumps(result), flush=True)
    return result

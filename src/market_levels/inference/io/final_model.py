"""Historical NF4 preparation and decoding with an inference-only adapter."""
import json
from pathlib import Path

from ...modeling.io.runtime import load_model, environment, setup, set_resolution, prepare_input, Monitor
from ...modeling.io.checkpoints import local_checkpoint
from ...modeling.io.adapter_check import prepare_nf4, adapter_state
from ...training.io.resources import guard, snapshot, pressure
from ..domain.inputs import conversation


def attach_adapter(model, adapter: Path, torch):
    from peft import PeftModel
    from safetensors.torch import load_file
    model = PeftModel.from_pretrained(model, adapter, is_trainable=False)
    saved = load_file(str(adapter/'adapter_model.safetensors'), device='cpu')
    actual = adapter_state(model)
    if (len(saved) != 112 or saved.keys() != actual.keys()
            or not all(saved[k].dtype == actual[k].dtype and saved[k].shape == actual[k].shape
                       and torch.equal(saved[k], actual[k]) and bool(torch.isfinite(actual[k]).all()) for k in saved)):
        raise ValueError('Adapter tensors in memory differ from the frozen source')
    return model, {'tensor_values_exact': True, 'tensor_count': len(saved), 'is_trainable': False, 'merged': False}


class FinalModel:
    """One fresh process model, reused only for the unfinished prefix of one variant."""
    def __init__(self, config: dict, selection: dict, variant: str):
        self.config, self.selection, self.variant = config, selection, variant

    def __enter__(self):
        config, runtime = self.config, self.config['runtime']
        # These checks precede model loading and reject implicit FP16 fallback.
        before = guard(config['resources'])
        versions = environment()
        expected = json.loads((Path(self.selection['selected_adapter'])/'training-identity.json').read_text(encoding='utf-8'))
        if versions != expected['environment']:
            raise RuntimeError('Final inference requires the pinned historical VLM environment')
        torch = setup(runtime['seed'])
        if (torch.cuda.device_count() != 1 or torch.cuda.get_device_name(0) != config['resources']['required_gpu']
                or not torch.cuda.is_bf16_supported(including_emulation=False)):
            raise RuntimeError('One approved GPU with native BF16 is required')
        torch, model, processor, details = load_model(runtime, 'qwen3-vl', local_checkpoint(runtime, 'qwen3-vl'), quantized=True)
        model = prepare_nf4(model, torch)
        set_resolution(processor, runtime['min_pixels'], runtime['image_budgets']['native'])
        for key, actual in [('processor', processor.to_dict()), ('image_processor', processor.image_processor.to_dict()),
                            ('tokenizer', processor.tokenizer.init_kwargs)]:
            # Match the historical identity's normalization, including AddedToken objects.
            normalized = json.loads(json.dumps(actual, default=str))
            if normalized != expected[key]:
                raise ValueError(f'Historical processor/chat-template mismatch: {key}')
        adapter_check = {'adapter_loaded': False}
        if self.variant == 'finetuned-nf4':
            model, adapter_check = attach_adapter(model, Path(self.selection['selected_adapter']), torch)
            adapter_check['adapter_loaded'] = True
        elif hasattr(model, 'peft_config'):
            raise ValueError('Base variant must have no adapter')
        for parameter in model.parameters():
            parameter.requires_grad_(False)
        model.eval()
        model.config.use_cache = True
        if any(p.requires_grad or p.grad is not None for p in model.parameters()) or model.training:
            raise ValueError('Final model must be eval-only with no gradients')
        self.torch, self.model, self.processor = torch, model, processor
        self.details = {'environment': versions, 'memory_before_cuda': before, 'model': details,
                        'adapter_check': adapter_check, 'no_optimizer_updates': True,
                        'processor': processor.to_dict(), 'tokenizer': expected['tokenizer'],
                        'generation': {**model.generation_config.to_dict(), **runtime['generation']}}
        return self

    def generate(self, item):
        from PIL import Image
        torch, model, processor = self.torch, self.model, self.processor
        memory = snapshot(torch)
        if pressure(memory, self.config['resources']):
            raise RuntimeError('Host RAM/commit pressure; no automatic retry')
        with Image.open(item.image) as source:
            if source.size != (1024, 768):
                raise ValueError('Image dimensions changed')
            image = source.convert('RGB')
        batch, info = prepare_input(processor, conversation(item, image), self.config['runtime']['models']['qwen3-vl'])
        if (info['processed_width'], info['processed_height'], info['image_tokens']) != (1024, 768, 768):
            raise ValueError('Historical image tokenization mismatch')
        batch = batch.to('cuda:0')
        with torch.inference_mode(), Monitor(torch) as monitor:
            generated = model.generate(**batch, **self.config['runtime']['generation'])
        completion = generated[:, batch['input_ids'].shape[-1]:]
        text = processor.batch_decode(completion, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
        info.update(output_token_ids=completion[0].tolist(), measurement=monitor.result, memory_after=snapshot(torch))
        del batch, generated, completion
        return text, info

    def __exit__(self, *args):
        del self.model, self.processor

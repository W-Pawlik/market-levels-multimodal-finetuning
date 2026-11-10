"""Complete raw base validation and bounded adapter roundtrip probes."""
import statistics
from pathlib import Path

from ...datasets.domain.examples import INSTRUCTION_VERSION
from ...evaluation.domain.responses import parse_response
from ...modeling.io.checkpoints import local_checkpoint
from ...modeling.io.runtime import load_model, environment, Monitor, prepare_input, set_resolution, error_details
from ...modeling.io.adapter_check import prepare_nf4, check_adapter, adapter_state
from ...shared.integrity import sha256_file
from ..domain.inputs import conversation
from ..io.pilot import write_json, append_response
from ..io.stability import read_split


def generate_records(config, model, processor, torch, inputs, output: Path, *, logits=False):
    from PIL import Image
    from safetensors.torch import save_file
    records = []
    model.eval()
    model.config.use_cache = True
    for index, item in enumerate(inputs):
        row = {'id': item.id}
        try:
            with Image.open(item.image) as original:
                if original.size != (1024, 768):
                    raise ValueError('Original 1024x768 image required')
                image = original.convert('RGB')
            batch, info = prepare_input(processor, conversation(item, image), config['models']['qwen3-vl'])
            row.update(info)
            batch = batch.to('cuda:0')
            with torch.inference_mode(), Monitor(torch) as monitor:
                generated = model.generate(**batch, **config['generation'])
            completion = generated[:, batch['input_ids'].shape[-1]:]
            token_ids = completion[0].tolist()
            text = processor.batch_decode(completion, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
            eos = model.generation_config.eos_token_id
            eos = eos if isinstance(eos, list) else [eos]
            parsed = parse_response(text)
            row.update(response=text, output_token_ids=token_ids, output_tokens=len(token_ids),
                       measurement=monitor.result, valid_json=parsed.levels is not None,
                       format_error=parsed.error,
                       hit_token_limit=len(token_ids) == config['generation']['max_new_tokens'],
                       truncated=len(token_ids) == config['generation']['max_new_tokens'] and token_ids[-1] not in eos)
            if logits:
                with torch.inference_mode():
                    values = model(**batch, use_cache=False, logits_to_keep=1).logits[0, -1].float().cpu().contiguous()
                save_file({'last_prompt_logits': values}, str(output / f'logits-{item.id}.safetensors'))
                del values
            append_response(output / 'predictions.jsonl', item.id, text)
            del batch, generated, completion
        except Exception as error:
            row['error'] = error_details(error, torch)
            write_json(output / f'{index:02d}-{item.id}.json', row)
            # Terminate the process through the CLI; no retries or fabricated responses.
            raise
        write_json(output / f'{index:02d}-{item.id}.json', row)
        records.append(row)
        print(f'{index+1}/{len(inputs)} {item.id} {row["measurement"]["seconds"]:.2f}s', flush=True)
    return records


def probe(config, model, processor, torch, output: Path):
    output.mkdir(exist_ok=False)
    inputs, selected, _ = read_split(Path(config['dataset']), 'validation')
    # One fixed image per instrument, chosen by ID before generation.
    indices = [0, 18]
    write_json(output / 'selected.json', [selected[i] for i in indices])
    return generate_records(config, model, processor, torch, [inputs[i] for i in indices], output, logits=True)


def run_validation(config: dict, output: Path, precision: str, adapter: Path | None = None, *, resave=False):
    if precision not in ('bf16', 'nf4') or (adapter is not None and precision != 'nf4'):
        raise ValueError('Unsupported precision/adapter combination')
    output.mkdir(exist_ok=False, parents=True)
    write_json(output / 'config.json', config)
    write_json(output / 'environment.json', environment())
    torch, model, processor, details = load_model(config, 'qwen3-vl', local_checkpoint(config, 'qwen3-vl'), quantized=precision == 'nf4')
    if precision == 'nf4':
        model = prepare_nf4(model, torch)
    set_resolution(processor, config['min_pixels'], config['image_budgets']['native'])
    write_json(output / 'model.json', details)
    write_json(output / 'processor.json', processor.to_dict())
    processor.tokenizer.save_pretrained(output / 'tokenizer')
    write_json(output / 'generation.json', {**model.generation_config.to_dict(), **config['generation']})
    if adapter is not None:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter, is_trainable=False)
        check = check_adapter(model, adapter, config)
        if resave:
            from safetensors.torch import save_file
            probe(config, model, processor, torch, output / 'probe-before')
            save_file(adapter_state(model), str(output / 'adapter-before-save.safetensors'))
            model.save_pretrained(output / 'adapter', safe_serialization=True)
            write_json(output / 'resave-check.json', {**check, 'no_optimizer_updates': True,
                'source_adapter': str(adapter), 'snapshot_and_probe_precede_serialization': True})
            return check
        after = probe(config, model, processor, torch, output / 'probe')
        import json
        from safetensors.torch import load_file
        comparisons = []
        before_folder = adapter.parent / 'probe-before'
        for index, row in enumerate(after):
            previous = json.loads((before_folder / f'{index:02d}-{row["id"]}.json').read_text(encoding='utf-8'))
            name = f'logits-{row["id"]}.safetensors'
            a = load_file(str(before_folder / name))['last_prompt_logits']
            b = load_file(str(output / 'probe' / name))['last_prompt_logits']
            comparisons.append({'id': row['id'], 'response_exact': row['response'] == previous['response'],
                'token_ids_exact': row['output_token_ids'] == previous['output_token_ids'],
                'logits_max_abs_diff': float((a-b).abs().max()),
                'logits_allclose': bool(torch.allclose(a, b, atol=0.05, rtol=0.01))})
        check.update(logit_criterion={'atol': 0.05, 'rtol': 0.01}, comparisons=comparisons)
        write_json(output / 'adapter-check.json', check)
        if not all(r['logits_allclose'] for r in comparisons):
            raise ValueError('Roundtrip logits outside declared tolerance')
        return check
    inputs, selected, _ = read_split(Path(config['dataset']), 'validation')
    write_json(output / 'selected-validation.json', selected)
    write_json(output / 'run.json', {'run_id': output.name, 'model_id': config['models']['qwen3-vl']['id'],
        'checkpoint_id': config['models']['qwen3-vl']['revision'], 'variant': 'base', 'protocol_version': 'sr-eval-v1',
        'instruction_version': INSTRUCTION_VERSION, 'prediction_kind': 'model', 'split': 'validation',
        'dataset_manifest_sha256': sha256_file(Path(config['dataset']) / 'manifest.json'),
        'inference': {'generation': config['generation'], 'precision': precision, 'image_budget': 786432,
                      'nf4_frozen_dtypes': 'PEFT preparation, vision BF16' if precision == 'nf4' else None},
        'role': 'primary future NF4+adapter baseline' if precision == 'nf4' else 'auxiliary higher precision baseline'})
    rows = generate_records(config, model, processor, torch, inputs, output)
    times = sorted(r['measurement']['seconds'] for r in rows)
    summary = {'completed': len(rows), 'expected': 36, 'valid_json': sum(r['valid_json'] for r in rows),
        'errors': 0, 'truncated': sum(r['truncated'] for r in rows), 'generation_seconds': times,
        'mean_generation_seconds': statistics.mean(times), 'median_generation_seconds': statistics.median(times),
        'min_generation_seconds': min(times), 'max_generation_seconds': max(times),
        'max_global_vram_mib': max(s['vram_used_mib'] for r in rows for s in r['measurement']['samples'] if 'vram_used_mib' in s)}
    write_json(output / 'summary.json', summary)
    return summary

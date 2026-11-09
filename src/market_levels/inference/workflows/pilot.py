"""Run the same eight validation images without labels or external inference."""
from __future__ import annotations

import statistics
import time
import warnings
from pathlib import Path

from ...modeling.io.checkpoints import local_checkpoint
from ...modeling.io.runtime import load_model, environment, Monitor, prepare_input, set_resolution, error_details
from ..domain.inputs import ImageInput, conversation
from ..io.pilot import select_examples, write_json, append_response


def run_inference(config: dict, key: str, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'config.json', config)
    write_json(output / 'environment.json', environment())
    inputs, selected, _ = select_examples(Path(config['dataset']))
    write_json(output / 'selected-validation.json', selected)
    torch, model, processor, details = load_model(config, key, local_checkpoint(config, key))
    write_json(output / 'model.json', {**config['models'][key], **details})
    model.eval()
    visual_calls = []
    handles = [module.register_forward_hook(lambda *args: visual_calls.append(time.perf_counter()))
               for name, module in model.named_modules() if name == 'model.visual']
    if len(handles) != 1:
        raise RuntimeError('Nie znaleziono jednoznacznego encodera wizualnego')
    from PIL import Image
    summary = {'kind': 'bounded_validation_pilot_not_full_evaluation', 'model': config['models'][key], 'resolutions': {}}
    for resolution, budget in config['image_budgets'].items():
        folder = output / resolution
        folder.mkdir()
        write_json(folder / 'image-processor.json', set_resolution(processor, config['min_pixels'], budget))
        records = []
        control = ImageInput(inputs[0].id, inputs[0].image,
            'Opisz typ wykresu, kolory świec i odczytaj dwie etykiety osi cenowej. Odpowiedz krótko.')
        cases = [('control-chart', control), ('control-blank', control)] + [('sr', item) for item in inputs]
        for index, (kind, item) in enumerate(cases):
            print(f'{key} {resolution} {kind} {item.id}', flush=True)
            row = {'id': item.id, 'kind': kind, 'resolution': resolution, 'max_pixels': budget,
                   'model_id': config['models'][key]['id'], 'revision': config['models'][key]['revision'],
                   'generation': config['generation'], 'warnings': []}
            try:
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter('always')
                    start = time.perf_counter()
                    with Image.open(item.image) as original:
                        if original.size != (1024, 768):
                            raise ValueError('Pilot wymaga oryginalnego PNG 1024 x 768')
                        image = original.convert('RGB')
                    row['image_read_seconds'] = time.perf_counter() - start
                    row['original_size'] = list(image.size)
                    if kind == 'control-blank':
                        image = Image.new('RGB', image.size, 'white')
                    batch, info = prepare_input(processor, conversation(item, image), config['models'][key])
                    row.update(info)
                    row['pixel_values_abs_mean'] = float(batch['pixel_values'].abs().mean())
                    start = time.perf_counter()
                    batch = batch.to('cuda:0')
                    torch.cuda.synchronize()
                    row['host_to_device_seconds'] = time.perf_counter() - start
                    previous_calls = len(visual_calls)
                    with torch.inference_mode(), Monitor(torch) as monitor:
                        generated = model.generate(**batch, **config['generation'])
                    row['measurement'] = monitor.result
                    row['vision_forward_calls'] = len(visual_calls) - previous_calls
                    completion = generated[:, batch['input_ids'].shape[-1]:]
                    row['output_tokens'] = completion.shape[-1]
                    row['output_token_ids'] = completion[0].tolist()
                    row['response'] = processor.batch_decode(completion, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
                    row['decoded_with_special_tokens'] = processor.batch_decode(completion, skip_special_tokens=False, clean_up_tokenization_spaces=False)[0]
                    row['tokens_per_second'] = row['output_tokens'] / monitor.elapsed
                    row['hit_token_limit'] = row['output_tokens'] == config['generation']['max_new_tokens']
                    row['warnings'] = [str(w.message) for w in caught]
                    if row['vision_forward_calls'] < 1:
                        raise RuntimeError('Obraz nie przeszedł przez encoder wizualny')
                    if kind == 'sr':
                        append_response(folder / 'predictions.jsonl', item.id, row['response'])
                    print(row['response'], flush=True)
                    del batch, generated, completion
            except Exception as error:
                row['error'] = error_details(error, torch)
                row['warnings'] = [str(w.message) for w in caught] if 'caught' in locals() else []
                records.append(row)
                write_json(folder / f'{index:02d}-{kind}-{item.id}.json', row)
                if row['error']['cuda_oom']:
                    torch.cuda.empty_cache()
                    break  # One failed attempt per resolution, never eight repeated OOMs.
                raise
            records.append(row)
            write_json(folder / f'{index:02d}-{kind}-{item.id}.json', row)
        completed = [r for r in records if r['kind'] == 'sr' and 'response' in r]
        summary['resolutions'][resolution] = {
            'completed': len(completed), 'expected': 8,
            'mean_generation_seconds_after_controls': statistics.mean(r['measurement']['seconds'] for r in completed) if completed else None,
            'mean_tokens_per_second': statistics.mean(r['tokens_per_second'] for r in completed) if completed else None,
            'max_allocated_bytes': max((r['measurement']['peak_allocated_bytes'] for r in completed), default=None),
            'max_global_vram_mib': max((s['vram_used_mib'] for r in records if 'measurement' in r
                                      for s in r['measurement']['samples'] if 'vram_used_mib' in s), default=None),
            'max_process_rss_bytes': max((s['rss_bytes'] for r in records if 'measurement' in r for s in r['measurement']['samples']), default=None),
            'errors': [r['error'] for r in records if 'error' in r]}
    for handle in handles:
        handle.remove()
    write_json(output / 'summary.json', summary)
    return summary

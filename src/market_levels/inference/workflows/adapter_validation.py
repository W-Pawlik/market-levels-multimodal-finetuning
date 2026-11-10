"""Fresh-process adapter inference; complete official validation or one train probe."""
import json
from pathlib import Path

from ...modeling.io.runtime import load_model, set_resolution
from ...modeling.io.adapter_check import prepare_nf4, adapter_state
from ...modeling.io.checkpoints import local_checkpoint
from ...shared.manifests import verify_files
from ...shared.integrity import sha256_file
from ...evaluation.workflows.evaluate import evaluate
from ...evaluation.workflows.verification import read_evaluation
from ...training.io.resources import guard
from ...training.io.data import read_train
from ...training.workflows.pipeline import verify_base
from ..io.pilot import write_json
from ..io.stability import read_split
from ..domain.inputs import ImageInput
from .validation import generate_records
from .price_diagnostics import run_diagnostics


def validate_adapter(config, adapter: Path, output: Path, *, probe=False):
    manifest = verify_files(adapter)
    if manifest.get('kind') != 'vlm_inference_adapter' or manifest.get('status') != 'complete':
        raise ValueError('Use separately exported inference adapter')
    identity = json.loads((adapter / 'training-identity.json').read_text(encoding='utf-8'))
    if (identity['config']['runtime'] != config['runtime'] or identity['config']['fixed'] != config['fixed']
            or identity['dataset']['manifest_sha256'] != sha256_file(Path(config['runtime']['dataset']) / 'manifest.json')):
        raise ValueError('Adapter revision/runtime/dataset mismatch')
    guard(config['pipeline'])
    runtime = config['runtime']
    verify_base(runtime)
    output.mkdir(parents=True, exist_ok=False)
    torch, model, processor, details = load_model(runtime, 'qwen3-vl', local_checkpoint(runtime, 'qwen3-vl'), quantized=True)
    model = prepare_nf4(model, torch)
    set_resolution(processor, runtime['min_pixels'], runtime['image_budgets']['native'])
    from peft import PeftModel
    from safetensors.torch import load_file
    model = PeftModel.from_pretrained(model, adapter, is_trainable=False)
    saved, actual = load_file(str(adapter / 'adapter_model.safetensors')), adapter_state(model)
    if saved.keys() != actual.keys() or not all(torch.equal(saved[k], actual[k]) for k in saved):
        raise ValueError('Reloaded adapter differs')
    write_json(output / 'model.json', details)
    write_json(output / 'adapter-reload.json', {'tensor_values_exact': True, 'count': len(saved), 'source': str(adapter)})
    if probe:
        rows, _ = read_train(Path(runtime['dataset']))
        row = rows[identity['dataset']['selected_ids'][0]]
        inputs = [ImageInput(row['id'], Path(runtime['dataset']) / row['image'], row['instruction'])]
        generate_records(runtime, model, processor, torch, inputs, output)
        return 0
    inputs, selected, _ = read_split(Path(runtime['dataset']), 'validation')
    baseline = json.loads(Path('results/evaluation/vlm41-cz2-20261110-1840-nf4/run.json').read_text(encoding='utf-8'))
    run = {**baseline, 'run_id': output.name, 'checkpoint_id': sha256_file(adapter / 'adapter_model.safetensors'),
           'variant': 'finetuned', 'base_revision': runtime['models']['qwen3-vl']['revision']}
    write_json(output / 'run.json', run)
    write_json(output / 'selected-validation.json', selected)
    generate_records(runtime, model, processor, torch, inputs, output)
    official = Path('results/evaluation') / output.name
    evaluate(Path(runtime['dataset']), output / 'predictions.jsonl', output / 'run.json', official, split='validation')
    read_evaluation(official)
    run_diagnostics(Path(runtime['dataset']), output / 'predictions.jsonl', output / 'price-diagnostics')
    return 0

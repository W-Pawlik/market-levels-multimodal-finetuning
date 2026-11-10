"""Stage 4.1 part 2: preflight, eight-step stability, reload, full base validation."""
import argparse
import json
import subprocess
from pathlib import Path

from ..modeling.stability_config import load_config
from ..modeling.io.checkpoints import local_checkpoint
from ..modeling.io.runtime import environment, setup, gpu_snapshot
from ..shared.integrity import sha256_file
from ..inference.io.pilot import write_json


def gpu_guard():
    output = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'], text=True)
    used = int(output.splitlines()[0].strip())
    # Prior run had only 269 MiB physical headroom. Desktop use around 320 MiB.
    if used > 450:
        raise RuntimeError(f'GPU baseline {used} MiB exceeds 450 MiB; diagnose other GPU applications before training')
    return used


def preflight(config, output):
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'config.json', config)
    torch = setup(config['seed'])
    if not torch.cuda.is_bf16_supported(including_emulation=False):
        raise RuntimeError('Native BF16 required')
    baseline = gpu_guard()
    checkpoint = local_checkpoint(config, 'qwen3-vl')
    historical = Path('results/vlm-feasibility-20261109-210209/downloaded-models.json')
    expected = json.loads(historical.read_text(encoding='utf-8'))[0]
    records = []
    for entry in expected['files']:
        path = checkpoint / entry['file']
        digest = sha256_file(path)
        if digest != entry['sha256'] or path.stat().st_size != entry['bytes']:
            raise ValueError(f'Checkpoint checksum mismatch: {path.name}')
        records.append({**entry, 'verified': True})
    write_json(output / 'checkpoint.json', {'model': config['models']['qwen3-vl'], 'files': records,
        'comparison_source': str(historical), 'comparison_source_sha256': sha256_file(historical)})
    write_json(output / 'cuda.json', {'gpu': torch.cuda.get_device_name(), 'memory': gpu_snapshot(torch),
        'baseline_vram_mib': baseline, 'bf16': True, **environment(),
        'previous_peak_mib': 7923, 'nominal_previous_headroom_mib': 269})
    (output / 'nvidia-smi.txt').write_bytes(subprocess.check_output(['nvidia-smi']))
    write_json(output / 'roles.json', {'bf16': 'auxiliary higher precision base checkpoint',
        'nf4': 'primary reference for future NF4 plus trained adapter; PEFT frozen dtypes matched',
        'adapter': 'technical roundtrip only; no official quality evaluation',
        'roundtrip_criteria': {'tensor_values': 'exact', 'config': 'exact',
            'logits_atol': 0.05, 'logits_rtol': 0.01, 'generation': 'report exact token and text agreement separately'}})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('preflight', 'train', 'resave', 'reload', 'validate'))
    parser.add_argument('--config', type=Path, default=Path('configs/vlm/stability.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--precision', choices=('bf16', 'nf4'))
    parser.add_argument('--adapter', type=Path)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.command == 'preflight':
        preflight(config, args.output)
    elif args.command == 'train':
        gpu_guard()
        from ..training.workflows.stability import run_stability
        return 0 if run_stability(config, 'qwen3-vl', args.output, 'native')['status'] == 'success' else 1
    else:
        if args.command in ('reload', 'resave') and (args.adapter is None or args.precision != 'nf4'):
            parser.error('reload/resave requires --adapter and --precision nf4')
        if args.command == 'validate' and (args.precision is None or args.adapter is not None):
            parser.error('validate requires precision and forbids adapters')
        from ..inference.workflows.validation import run_validation
        run_validation(config, args.output, args.precision, args.adapter, resave=args.command == 'resave')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

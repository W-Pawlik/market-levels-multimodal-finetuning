"""Explicit local pilot commands; no test split or full training option."""
from __future__ import annotations

import argparse
import traceback
from pathlib import Path

from ..inference.io.pilot import select_examples, write_json
from ..modeling.config import load_config


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('select', 'download', 'infer', 'train-step'))
    parser.add_argument('--config', type=Path, default=Path('configs/vlm/feasibility.json'))
    parser.add_argument('--model', choices=('qwen3-vl', 'qwen3.5'), help='infer/train-step; domyslnie qwen3-vl')
    parser.add_argument('--resolution', help='Tylko train-step; domyslnie native')
    parser.add_argument('--output', type=Path, required=True, help='Nowy, nieistniejący katalog')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.exit(2, 'Katalog wyników już istnieje\n')
    try:
        config = load_config(args.config)
        if args.command not in ('infer', 'train-step') and args.model is not None:
            raise ValueError('--model dotyczy tylko infer/train-step')
        if args.command != 'train-step' and args.resolution is not None:
            raise ValueError('--resolution dotyczy tylko train-step; infer sprawdza budzety konfiguracji')
        args.model = args.model or 'qwen3-vl'
        args.resolution = args.resolution or 'native'
        if args.resolution not in config['image_budgets']:
            raise ValueError('Nieznany budżet rozdzielczości')
        if args.command == 'select':
            args.output.mkdir(parents=True)
            for split in ('validation', 'train'):
                _, records, _ = select_examples(Path(config['dataset']), split=split)
                write_json(args.output / f'selected-{split}.json', records)
        elif args.command == 'download':
            from ..modeling.io.checkpoints import download_plan, download_models
            plan = download_plan(config)
            args.output.mkdir(parents=True)
            write_json(args.output / 'download-plan.json', plan)
            write_json(args.output / 'downloaded-models.json', download_models(plan))
        elif args.command == 'infer':
            from ..inference.workflows.pilot import run_inference
            run_inference(config, args.model, args.output)
        else:
            from ..training.workflows.one_step import run_one_step
            result = run_one_step(config, args.model, args.output, args.resolution)
            return 0 if result['status'] == 'success' else 2
        return 0
    except Exception as error:
        if args.output.is_dir() and not (args.output / 'failure.json').exists():
            write_json(args.output / 'failure.json', {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())

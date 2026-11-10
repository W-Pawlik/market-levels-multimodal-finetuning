"""Stage 4.2 training, bounded smoke and fence-only validation diagnostics."""
import argparse
import json
from pathlib import Path

from ..training.config import load_config
from ..training.domain.schedule import total_steps
from ..training.workflows.pipeline import plan, preflight, run_training
from ..training.io.checkpoints import checkpoint_metadata
from ..inference.io.pilot import write_json


def require_full_approval(config, explicit):
    if not config['pipeline']['full_approved'] or not explicit:
        raise ValueError('Full training requires separate author approval: full_approved=true AND --approve-full-training')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('preflight', 'dry-run', 'smoke-test', 'full', 'verify-checkpoint',
                                           'diagnostics', 'validate-adapter', 'probe-adapter'))
    parser.add_argument('--config', type=Path, default=Path('configs/vlm/training.json'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', type=Path)
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--adapter', type=Path)
    parser.add_argument('--predictions', type=Path)
    parser.add_argument('--split', choices=('train', 'validation'), help='test is always forbidden')
    parser.add_argument('--stop-after', type=int, help='Stop this process after N optimizer steps; does not change scheduler')
    parser.add_argument('--approve-full-training', action='store_true')
    parser.add_argument('--smoke-plan', action='store_true', help='Use bounded smoke identity for preflight/dry-run')
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.split is not None and args.split != ('validation' if args.command in ('diagnostics', 'validate-adapter') else 'train'):
            raise ValueError('Wrong split for this command')
        if args.stop_after is not None and args.stop_after < 1:
            raise ValueError('stop-after must be positive')
        if args.command == 'verify-checkpoint':
            if args.checkpoint is None:
                parser.error('--checkpoint required')
            meta = checkpoint_metadata(args.checkpoint)
            print(json.dumps({'verified': True, 'checkpoint': str(args.checkpoint),
                              'schema': meta['schema'], 'step': meta['sampler']['global_step']}, ensure_ascii=False))
            return 0
        if args.output is None:
            parser.error('--output required')
        if args.command == 'full':
            require_full_approval(config, args.approve_full_training)
        if args.command in ('full', 'smoke-test'):
            return run_training(config, args.output, args.command, args.resume, args.stop_after)
        if args.command == 'diagnostics':
            if args.predictions is None:
                parser.error('--predictions required')
            from ..inference.workflows.price_diagnostics import run_diagnostics
            run_diagnostics(Path(config['runtime']['dataset']), args.predictions, args.output)
            return 0
        if args.command in ('validate-adapter', 'probe-adapter'):
            if args.adapter is None:
                parser.error('--adapter required')
            from ..inference.workflows.adapter_validation import validate_adapter
            return validate_adapter(config, args.adapter, args.output, probe=args.command == 'probe-adapter')
        mode = 'smoke-test' if args.smoke_plan else 'full'
        if args.command == 'preflight':
            report = preflight(config, mode, args.resume)
        else:
            effective, rows, binding = plan(config, mode)
            if args.resume:
                meta = checkpoint_metadata(args.resume)
                if meta['identity']['config'] != effective or meta['identity']['dataset'] != binding:
                    raise ValueError('Resume configuration/dataset mismatch')
            report = {'effective_config': effective, 'dataset': binding, 'examples': len(rows),
                      'total_steps': total_steps(len(rows), effective['pipeline']), 'loads_model': False,
                      'checkpoint_pattern': 'checkpoints/step-NNNNNN', 'full_training_started': False}
        args.output.mkdir(parents=True, exist_ok=False)
        write_json(args.output / 'report.json', report)
        print(json.dumps({'command': args.command, 'output': str(args.output),
                          'examples': report.get('examples', len(report.get('dataset', {}).get('selected_ids', []))),
                          'total_steps': report.get('total_steps'), 'status': 'ok'}, ensure_ascii=False))
        return 0
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
        print(f'Błąd pipeline: {error}', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

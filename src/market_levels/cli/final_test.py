"""Explicitly approved final raw test inference; dry-run is CPU/read-only."""
import argparse
import json
from pathlib import Path

from ..inference.final_config import VARIANTS
from ..inference.workflows.final_test import audit_plan, prepare, execute, verify_pair


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('dry-run','prepare','infer','verify-pair','verify-variant','score-pair'))
    parser.add_argument('--config', type=Path, default=Path('configs/vlm/final-test.json'))
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--split', choices=('test',), required=True)
    parser.add_argument('--session', type=Path)
    parser.add_argument('--output', type=Path, help='New directory for prepare only')
    parser.add_argument('--variant', choices=VARIANTS)
    parser.add_argument('--adapter', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--approve-final-test', action='store_true')
    args = parser.parse_args(argv)
    options = {'dataset': args.dataset, 'selection_path': args.selection, 'split': args.split}
    try:
        if (args.output is not None and args.command != 'prepare'
                or args.resume and args.command != 'infer'
                or args.adapter is not None and args.command != 'infer'
                or args.variant is not None and args.command not in ('infer','verify-variant')):
            raise ValueError('Arguments do not apply to this command')
        if args.command == 'dry-run':
            config, selection, inputs, plan = audit_plan(args.config, **options)
            report = {'status': 'offline_plan_verified', 'examples': len(inputs),
                      'image_input_fingerprint': plan['binding']['image_input_fingerprint'],
                      'adapter_sha256': selection['adapter_sha256'], 'output': config['output'],
                      'loads_model': False, 'cuda_initialized': False, 'test_references_parsed': False}
        elif args.command == 'prepare':
            if args.output is None:
                parser.error('prepare requires --output')
            report = prepare(args.config, args.output, args.approve_final_test, **options)
        else:
            if args.session is None:
                parser.error('--session required')
            if args.command in ('infer','verify-variant') and args.variant is None:
                parser.error('--variant required')
            if args.command == 'infer':
                report = execute(args.config, args.session, args.variant, args.approve_final_test,
                                 adapter=args.adapter, resume=args.resume, **options)
            elif args.command == 'score-pair':
                from ..inference.workflows.final_scoring import score_pair
                report = score_pair(args.config, args.session, args.approve_final_test, **options)
            else:
                report = verify_pair(args.config, args.session,
                                     variant=args.variant if args.command == 'verify-variant' else None, **options)
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0
    except KeyboardInterrupt:
        print('Przerwano: zachowano zatwierdzone odpowiedzi; wznowienie wymaga --resume.', flush=True)
        return 130
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, ImportError) as error:
        print(f'Odmowa/błąd końcowego testu: {error}', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

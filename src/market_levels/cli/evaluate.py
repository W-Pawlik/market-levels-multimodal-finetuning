"""Evaluate saved raw responses; no inference, training or model adapter."""
import argparse
import sys
from pathlib import Path

from ..evaluation.io.inputs import InputError
from ..evaluation.workflows.evaluate import evaluate
from ..evaluation.workflows.compare import compare
from ..evaluation.workflows.verification import read_evaluation, read_comparison
from ..shared.manifests import verify_files
from ..evaluation.protocol import dumps


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    single = commands.add_parser('evaluate')
    single.add_argument('--dataset', type=Path, default=Path('data/datasets/ds35-800-20261107-a'))
    single.add_argument('--split', choices=('validation','test'), default='validation')
    single.add_argument('--predictions', type=Path, required=True)
    single.add_argument('--run-manifest', type=Path, required=True)
    single.add_argument('--output', type=Path, required=True)
    paired = commands.add_parser('compare')
    paired.add_argument('--baseline', type=Path, required=True)
    paired.add_argument('--candidate', type=Path, required=True)
    paired.add_argument('--output', type=Path, required=True)
    check = commands.add_parser('verify')
    check.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'evaluate':
            evaluate(args.dataset, args.predictions, args.run_manifest, args.output, split=args.split)
        elif args.command == 'compare':
            compare(args.baseline, args.candidate, args.output)
        else:
            kind = verify_files(args.output)['kind']
            if kind == 'evaluation_comparison':
                report = read_comparison(args.output)
                count = len(report['paired_examples'])
            else:
                report = read_evaluation(args.output)
                count = report['manifest']['count']
            print(dumps({'verified': True, 'count': count, 'kind': kind}))
            return 0
        print(f'Zapisano: {args.output}')
        return 0
    except InputError as error:
        print(dumps({'status': 'rejected_no_complete_result', 'problems': error.problems}), file=sys.stderr)
        return 2
    except (ValueError, KeyError, TypeError, OSError, ArithmeticError, RecursionError) as error:
        print(f'Błąd ewaluacji: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

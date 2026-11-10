"""Inventory and verify stage 4.2 evidence without running training/inference."""
import argparse
import json
import subprocess
from pathlib import Path

from market_levels.shared.integrity import sha256_file
from market_levels.shared.manifests import verify_files
from market_levels.training.io.checkpoints import checkpoint_metadata


def inventory(run):
    return {p.as_posix(): sha256_file(p) for base in ('data','results')
            for p in sorted(Path(base).rglob('*')) if p.is_file() and run.resolve() not in p.resolve().parents}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('before','after'))
    parser.add_argument('--run',type=Path,required=True)
    args = parser.parse_args()
    run = args.run
    if args.command == 'before':
        run.mkdir(parents=True,exist_ok=False)
        (run/'git-before.txt').write_bytes(subprocess.check_output(['git','status','--porcelain=v1']))
        (run/'integrity-before.json').write_text(json.dumps(inventory(run),indent=2),encoding='utf-8')
        return
    before = json.loads((run/'integrity-before.json').read_text(encoding='utf-8'))
    after = inventory(run)
    diagnostic_name = run.name.replace('vlm42-pipeline-','vlm42-price-baseline-')
    allowed = tuple(f'results/evaluation/{diagnostic_name}-{p}/' for p in ('nf4','bf16'))
    added = sorted(after.keys()-before.keys())
    summary = {'historical_files':len(before),
        'changed':[p for p in before.keys() & after.keys() if before[p]!=after[p]],
        'removed':sorted(before.keys()-after.keys()), 'added':added,
        'unexpected_added':[p for p in added if not p.startswith(allowed)],
        'production_dataset_files':sum(p.startswith('data/datasets/ds35-800-20261107-a/') for p in before)}
    (run/'integrity-after.json').write_text(json.dumps(after,indent=2),encoding='utf-8')
    (run/'integrity-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    if summary['changed'] or summary['removed'] or summary['unexpected_added']:
        raise ValueError('Historical integrity/inventory changed')
    for part in ('gpu-a','gpu-b1','gpu-b2'):
        result = json.loads((run/part/'result.json').read_text(encoding='utf-8'))
        checkpoint_metadata(Path(result['latest_checkpoint']))
        verify_files(Path(result['adapter']))
    for precision, expected in [('nf4',(48,168,99)),('bf16',(58,158,89))]:
        verify_files(run/('diagnostics-'+precision))
        d = json.loads((run/('diagnostics-'+precision)/'diagnostics.json').read_text(encoding='utf-8'))
        r = d['price_diagnostics']['metrics']['tolerances']['0.5']['overall']
        if tuple(r[k] for k in ('tp','fp','fn')) != expected or d['official']['tolerances']['0.5']['overall']['micro_f1'] != 0:
            raise ValueError('Baseline diagnostic regression')
    comparison = json.loads((run/'gpu-resume-comparison.json').read_text(encoding='utf-8'))
    if not all(comparison[k] for k in ('adapter_allclose','optimizer_allclose','scheduler_exact','sampler_exact','rng_exact')):
        raise ValueError('Resume comparison failed')
    (run/'git-after.txt').write_bytes(subprocess.check_output(['git','status','--porcelain=v1']))
    print(json.dumps(summary))


if __name__ == '__main__':
    main()

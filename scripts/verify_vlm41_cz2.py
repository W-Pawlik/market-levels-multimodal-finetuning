"""Inventory protected files before work, verify real stage 4.1 part 2 outputs after it."""
import argparse
import json
import math
from pathlib import Path

from market_levels.inference.io.pilot import write_json
from market_levels.shared.integrity import sha256_file
from market_levels.evaluation.workflows.verification import read_evaluation


def inventory(run):
    return {p.as_posix(): sha256_file(p) for base in ('data', 'results')
            for p in sorted(Path(base).rglob('*')) if p.is_file() and run.resolve() not in p.resolve().parents}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('before', 'after'))
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    run = args.run
    if args.command == 'before':
        run.mkdir(parents=True, exist_ok=False)
        write_json(run/'integrity-before.json', inventory(run))
        return
    before = json.loads((run/'integrity-before.json').read_text(encoding='utf-8'))
    after = inventory(run)
    official_prefixes = tuple(f'results/evaluation/{run.name}-{precision}/' for precision in ('bf16', 'nf4'))
    added = after.keys()-before.keys()
    official_added = sorted(p for p in added if p.startswith(official_prefixes))
    summary = {'before_count': len(before), 'after_count': len(after),
               'changed': [p for p in before.keys() & after.keys() if before[p] != after[p]],
               'removed': sorted(before.keys()-after.keys()),
               'added': sorted(added-set(official_added)), 'new_official_evaluation_files': official_added}
    write_json(run/'integrity-after.json', after)
    write_json(run/'integrity-summary.json', summary)
    if summary['changed'] or summary['removed'] or summary['added']:
        raise ValueError('Historical inventory changed; inspect integrity-summary.json')
    training = json.loads((run/'train/training-result.json').read_text(encoding='utf-8'))
    if training['status'] != 'success' or training['optimizer_steps'] != 8:
        raise ValueError('Incomplete stability run')
    for i in range(1, 9):
        row = json.loads((run/f'train/step-{i:02d}.json').read_text(encoding='utf-8'))
        if (row['step'] != i or row['processed_examples'] != 4*i or not row['changed_adapter_tensors']
                or not math.isfinite(row['gradient_norm']) or not all(math.isfinite(v) for v in row['losses'])):
            raise ValueError('Invalid optimizer step')
    check = json.loads((run/'reload/adapter-check.json').read_text(encoding='utf-8'))
    if not (check['tensor_values_exact'] and check['pre_save_tensors_exact'] and check['config_exact']
            and all(r['logits_allclose'] for r in check['comparisons'])):
        raise ValueError('Adapter roundtrip failed')
    strict = json.loads((run/'roundtrip-reload/adapter-check.json').read_text(encoding='utf-8'))
    resave = json.loads((run/'roundtrip-source/resave-check.json').read_text(encoding='utf-8'))
    if not (resave['snapshot_and_probe_precede_serialization'] and resave['no_optimizer_updates']
            and strict['pre_save_tensors_exact'] and strict['tensor_values_exact'] and strict['config_exact']
            and all(r['logits_allclose'] for r in strict['comparisons'])):
        raise ValueError('Strict pre-serialization roundtrip failed')
    for precision in ('bf16', 'nf4'):
        read_evaluation(Path('results/evaluation') / f'{run.name}-{precision}')
        read_evaluation(run/f'evaluation-{precision}')
        expected = {r['id'] for r in json.loads((run/f'base-{precision}/selected-validation.json').read_text(encoding='utf-8'))}
        rows = [json.loads(line) for line in (run/f'base-{precision}/predictions.jsonl').read_text(encoding='utf-8').splitlines()]
        if len(expected) != 36 or len(rows) != 36 or {r['id'] for r in rows} != expected:
            raise ValueError('Incomplete validation predictions')
    write_json(run/'completion-checks.json', {'protected_files_unchanged': len(before), 'optimizer_steps': 8,
        'adapter_roundtrip': True, 'validation_bf16': 36, 'validation_nf4': 36,
        'test_inference': False, 'full_training': False})
    print(json.dumps(summary))


if __name__ == '__main__':
    main()

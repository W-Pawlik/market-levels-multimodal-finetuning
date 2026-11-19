"""Offline evidence for report 4.6B. No model loading or official result writes.

Run from repository root with .venv/Scripts/python.exe scripts/audit_vlm46b.py.
The output directory must be new. Uses the existing fence-only transformation.
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from market_levels.shared.integrity import sha256_file
from market_levels.shared.manifests import verify_files
from market_levels.evaluation.protocol import dumps, loads, PROTOCOL_SHA256
from market_levels.evaluation.workflows.verification import read_evaluation, read_comparison
from market_levels.evaluation.domain.models import Reference
from market_levels.evaluation.domain.responses import parse_response
from market_levels.evaluation.domain.scoring import score_example
from market_levels.evaluation.domain.metrics import aggregate
from market_levels.inference.domain.price_diagnostics import unwrap_fence
from market_levels.inference.workflows.final_test import verify_pair


OUT = Path('docs/vlm/final46b')
SESSION = Path('results/vlm46-final-test')
DATA = Path('data/datasets/ds35-800-20261107-a')
EVAL = Path('results/evaluation')
SELECTION = Path('docs/vlm/FINAL_MODEL_SELECTION.json')
VARIANTS = ('base-nf4', 'finetuned-nf4')


def read(path):
    return loads(path.read_text(encoding='utf-8-sig'))


def write(name, value):
    (OUT/name).write_text(dumps(value)+'\n', encoding='utf-8')


def inventory(roots):
    paths = set()
    for root in roots:
        paths.update(p for p in root.rglob('*') if p.is_file()) if root.is_dir() else paths.add(root)
    return {p.as_posix(): {'bytes': p.stat().st_size, 'sha256': sha256_file(p)} for p in sorted(paths)}


def groups(content):
    yield 'overall', content['overall']
    for kind in ('by_symbol', 'by_side'):
        yield from content[kind].items()
    for symbol, sides in content['by_symbol_side'].items():
        for side, value in sides.items():
            yield symbol+'/'+side, value


def main():
    OUT.mkdir(exist_ok=False)
    selection = read(SELECTION)
    roots = [DATA, SESSION, Path(selection['selected_adapter']), Path(selection['effective_config_path']),
             Path(selection['validation_path']), SELECTION, Path('configs/vlm'), Path('src/market_levels'),
             Path('scripts/run_vlm_final_test.ps1'), Path('docs/evaluation/PROTOKOL_3_6.md')]
    roots += sorted(EVAL.glob('vlm46-final-test-*'))
    roots += sorted(Path('results').glob('vlm46-*.exit.json')) + sorted(Path('results').glob('vlm46-*.console.log'))
    before = inventory(roots)
    write('SOURCES.json', before)
    pair = verify_pair(Path('configs/vlm/final-test.json'), SESSION)
    manifest_checks = []
    for root in [DATA, Path(selection['selected_adapter']), *(SESSION/v for v in VARIANTS), *EVAL.glob('vlm46-final-test-*')]:
        m = verify_files(root)
        manifest_checks.append({'path': root.as_posix(), 'files': len(m['files']), 'sha256': sha256_file(root/'manifest.json')})
    reports = {v: read_evaluation(EVAL/f'vlm46-final-test-{v}') for v in VARIANTS}
    comparison = read_comparison(EVAL/'vlm46-final-test-comparison')
    validation = read_evaluation(Path(selection['validation_path']))
    write('verified_metrics.json', {v: r['summary'] for v, r in reports.items()})
    write('validation_metrics.json', validation['summary'])
    write('official_comparison.json', comparison)
    loaded, execution = {}, {}
    for v, report in reports.items():
        raw = SESSION/v
        assert (raw/'predictions.jsonl').read_bytes() == (EVAL/f'vlm46-final-test-{v}'/'predictions.jsonl').read_bytes()
        assert read(raw/'run.json') == report['run']
        events = [loads(l) for l in (raw/'events.jsonl').read_text(encoding='utf-8').splitlines()]
        loaded[v] = next(e['details'] for e in events if 'details' in e)
        assert loaded[v]['no_optimizer_updates'] is True
        records = [read(p) for p in sorted((raw/'records').glob('*.json'))]
        assert len(records) == len(report['rows']) == 66
        assert all(r['details']['image_tokens'] == 768 and r['details']['processed_width'] == 1024
                   and r['details']['processed_height'] == 768 for r in records)
        measurements = [r['details']['measurement'] for r in records]
        samples = [s for m in measurements for s in m['samples']]
        execution[v] = {'events': [{k: val for k, val in e.items() if k != 'details'} for e in events],
                        'adapter_check': loaded[v]['adapter_check'], 'environment': loaded[v]['environment'],
                        'count': len(records), 'record_ids': [r['id'] for r in records],
                        'sample_peak_vram_mib': max(s['vram_used_mib'] for s in samples),
                        'sample_peak_rss_mib': max(s['rss_bytes'] for s in samples)/1048576,
                        'peak_allocated_mib': max(m['peak_allocated_bytes'] for m in measurements)/1048576,
                        'peak_reserved_mib': max(m['peak_reserved_bytes'] for m in measurements)/1048576}
    for key in ('environment', 'generation', 'processor', 'tokenizer'):
        assert loaded[VARIANTS[0]][key] == loaded[VARIANTS[1]][key], key
    assert execution[VARIANTS[0]]['record_ids'] == execution[VARIANTS[1]]['record_ids']
    assert loaded['finetuned-nf4']['adapter_check'] == {'adapter_loaded': True, 'is_trainable': False,
                                                      'merged': False, 'tensor_count': 112, 'tensor_values_exact': True}
    assert reports[VARIANTS[0]]['binding'] == reports[VARIANTS[1]]['binding']
    assert sha256_file(SELECTION) == read(SESSION/'session.json')['plan']['selection_sha256']
    assert PROTOCOL_SHA256 == selection['evaluation_protocol_sha256']
    diagnostic_rows, transformed = [], []
    for row in reports['base-nf4']['rows']:
        text, removed = unwrap_fence(row['raw_response'])
        assert removed and row['raw_response'].lstrip().startswith('```json')
        ref = Reference(row['id'], row['symbol'], 'test', parse_response(dumps(row['reference'])).levels, row['atr'])
        diagnostic_rows.append(score_example(ref, parse_response(text)))
        transformed.append({'id': row['id'], 'response': text})
    diagnostic = aggregate(diagnostic_rows)
    assert diagnostic['tolerances']['0.5']['overall']['tp'] == 73
    for k, expected in [('0.25','0.1470137825'), ('0.5','0.2235834609'), ('1.0','0.3307810107')]:
        assert f"{diagnostic['tolerances'][k]['overall']['micro_f1']:.10f}" == expected
    write('diagnostic_base_summary.json', diagnostic)
    (OUT/'diagnostic_base_predictions.jsonl').write_text(''.join(dumps(r)+'\n' for r in transformed), encoding='utf-8')
    (OUT/'diagnostic_base_per_example.jsonl').write_text(''.join(dumps(r)+'\n' for r in diagnostic_rows), encoding='utf-8')
    table = []
    for label, summary in [(v, r['summary']) for v, r in reports.items()] + [('base-nf4-diagnostic', diagnostic)]:
        for tolerance, content in summary['tolerances'].items():
            for group, g in groups(content):
                tp, fp, fn = (g[k] for k in ('tp','fp','fn'))
                if tp+fp+fn:
                    assert abs(float(g['micro_f1']) - 2*tp/(2*tp+fp+fn)) < 1e-14
                table.append({'variant': label, 'tolerance_atr': tolerance, 'group': group,
                              **{k: g[k] for k in ('examples','tp','fp','fn','micro_precision','micro_recall','micro_f1',
                                 'predicted_levels','reference_levels','valid_json_count','complete_set_correct_count','zero_tp_examples')},
                              'mae_atr': g['price_error']['mae_atr']})
            for kind in ('by_symbol', 'by_side'):
                for key in ('tp','fp','fn','predicted_levels','reference_levels'):
                    assert sum(g[key] for g in content[kind].values()) == content['overall'][key]
    with (OUT/'metrics.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(table[0])); writer.writeheader(); writer.writerows(table)
    ft = reports['finetuned-nf4']['summary']['tolerances']['0.5']['overall']
    assert [ft[k] for k in ('tp','fp','fn','valid_json_count','predicted_levels','reference_levels',
                           'complete_set_correct_count','zero_tp_examples')] == [109,168,148,66,277,257,0,9]
    for key, value in [('micro_f1','0.4082397004'), ('micro_precision','0.3935018051'),
                       ('micro_recall','0.4241245136')]:
        assert f'{ft[key]:.10f}' == value
    assert f"{ft['price_error']['mae_atr']:.10f}" == '0.2402191219'
    error_ids = ['bef2f03dc933f5e4e8ca151f','9ae321c8cccbc677d118c424','ca556edc7c6210775a96e28f']
    write('error_cases.json', [r for r in reports['finetuned-nf4']['rows'] if r['id'] in error_ids])
    entries = read(DATA/'manifest.json')['entries']
    meta = [read(DATA/e['metadata']) for e in entries if e['split']=='test']
    write('test_metadata.json', meta)
    exits = []
    for p in sorted(Path('results').glob('vlm46-*.exit.json')):
        e = read(p); log = Path(e['log']); b = log.read_bytes()
        text = b.decode('utf-16') if b.startswith(b'\xff\xfe') else b.decode('utf-8-sig', errors='replace')
        exits.append({'source': p.as_posix(), **e, 'console_tail': text[-2000:]})
    write('execution_audit.json', {'verify_pair_offline': pair, 'manifest_checks': manifest_checks,
          'execution': execution, 'exit_codes': exits, 'configuration_equal': True,
          'binding_fingerprint': reports['base-nf4']['binding']['fingerprint'],
          'selection_unchanged_since_session': True, 'diagnostic_fence_removed_count': len(transformed),
          'diagnostic_rule': 'existing inference.domain.price_diagnostics.unwrap_fence; then sr-eval-v1',
          'validation_test_f1_delta': ft['micro_f1']-validation['summary']['tolerances']['0.5']['overall']['micro_f1']})
    after = inventory(roots)
    assert before == after, 'Protected evidence changed'
    assert 'torch' not in sys.modules and 'transformers' not in sys.modules
    write('integrity.json', {'status': 'passed', 'protected_files': len(before), 'dataset_files': len([p for p in before if p.startswith(DATA.as_posix()+'/')]),
          'changed': [], 'removed': [], 'added': [], 'manifests': manifest_checks,
          'model_libraries_imported': False, 'model_loaded': False, 'inference_run': False,
          'official_results_written': False, 'scope': 'SOURCES.json; exact byte hashes before/after'})
    print(dumps({'status': 'passed', 'protected_files': len(before), 'output': OUT.as_posix(),
                 'official_f1': ft['micro_f1'], 'diagnostic_f1': diagnostic['tolerances']['0.5']['overall']['micro_f1']}))


if __name__ == '__main__':
    main()

"""evaluation / workflows / verification."""
from __future__ import annotations

from pathlib import Path

from ...shared.manifests import verify_files
from ..io.inputs import read_predictions, read_run_manifest
from ..domain.metrics import aggregate
from ..protocol import VERSION, PROTOCOL_SHA256, RULES, dumps, loads
from ..domain.models import Reference
from ..domain.responses import parse_response
from ..domain.scoring import score_example
from ..reporting.markdown import _markdown
from ..domain.comparison import _comparison_content


def read_evaluation(output: Path) -> dict:
    manifest = verify_files(output)
    expected = {'predictions.jsonl','run-input.json','dataset_binding.json','protocol.json','per_example.jsonl',
                'summary.json','run.json','SOURCE_INTEGRITY.json','RAPORT.md'}
    if (manifest['kind'] != 'evaluation_result' or manifest['status'] != 'complete'
            or manifest['protocol_version'] != VERSION or manifest['protocol_sha256'] != PROTOCOL_SHA256
            or set(manifest['files']) != expected):
        raise ValueError('Niekompletny lub niezgodny wynik ewaluacji')
    protocol = loads((output/'protocol.json').read_text(encoding='utf-8'))
    if protocol != {'version': VERSION, 'sha256': PROTOCOL_SHA256, 'rules': RULES}:
        raise ValueError('Niezgodne reguły protokołu')
    binding = loads((output/'dataset_binding.json').read_text(encoding='utf-8'))
    refs = []
    for record in binding['selected']:
        r = record['reference']
        parsed = parse_response(dumps(r['levels']))
        if parsed.levels is None or r['symbol'] != record['symbol'] or r['id'] != record['id']:
            raise ValueError('Niespójna kopia referencji')
        refs.append(Reference(r['id'], r['symbol'], r['split'], parsed.levels, r['atr']))
    expected_ids = {k for k, v in binding['all_ids'].items() if v == binding['split']}
    if len({r.id for r in refs}) != len(refs) or {r.id for r in refs} != expected_ids or any(r.split != binding['split'] for r in refs):
        raise ValueError('Niezgodna kompletność kopii referencji')
    import hashlib
    if binding['fingerprint'] != hashlib.sha256(dumps({k:v for k,v in binding.items() if k != 'fingerprint'}).encode()).hexdigest():
        raise ValueError('Niezgodny fingerprint zbioru')
    predictions = read_predictions(output/'predictions.jsonl', refs, binding)
    run = read_run_manifest(output/'run-input.json', binding)
    if run != loads((output/'run.json').read_text(encoding='utf-8')) or manifest['prediction_kind'] != run['prediction_kind']:
        raise ValueError('Niezgodne metadane przebiegu')
    rows = [score_example(ref, parse_response(predictions[ref.id])) for ref in refs]
    if manifest['count'] != len(rows) or (output/'per_example.jsonl').read_text(encoding='utf-8') != ''.join(dumps(row)+'\n' for row in rows):
        raise ValueError('Niezgodne odtworzenie wyników jednostkowych')
    summary = aggregate(rows)
    if dumps(loads((output/'summary.json').read_text(encoding='utf-8'))) != dumps(summary):
        raise ValueError('Niezgodne metryki podsumowania')
    if (output/'RAPORT.md').read_text(encoding='utf-8') != _markdown(summary, run):
        raise ValueError('Niezgodny raport tekstowy')
    return {'manifest': manifest, 'binding': binding, 'run': run, 'rows': rows, 'summary': summary}


def read_comparison(output: Path) -> dict:
    manifest = verify_files(output)
    if (manifest['kind'] != 'evaluation_comparison' or manifest['status'] != 'complete'
            or manifest['protocol_version'] != VERSION or manifest['protocol_sha256'] != PROTOCOL_SHA256):
        raise ValueError('Niezgodny wynik porównania')
    protocol = loads((output/'protocol.json').read_text(encoding='utf-8'))
    if protocol != {'version': VERSION, 'sha256': PROTOCOL_SHA256, 'rules': RULES}:
        raise ValueError('Niezgodne reguły porównania')
    before, after = read_evaluation(output/'baseline'), read_evaluation(output/'candidate')
    expected = _comparison_content(before, after)
    actual = loads((output/'comparison.json').read_text(encoding='utf-8'))
    if dumps(actual) != dumps(expected) or manifest['paired_count'] != len(before['rows']):
        raise ValueError('Niezgodne odtworzenie porównania')
    expected_files = {'comparison.json','protocol.json','RAPORT.md'}
    for folder in ('baseline','candidate'):
        expected_files.update(folder+'/'+p.relative_to(output/folder).as_posix() for p in (output/folder).iterdir() if p.is_file())
    if set(manifest['files']) != expected_files:
        raise ValueError('Niezgodny inwentarz porównania')
    return expected

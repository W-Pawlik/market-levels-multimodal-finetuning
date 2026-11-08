"""Atomic evaluation reports and paired comparisons, with reproducible readback."""
from __future__ import annotations

from decimal import Decimal, localcontext
from pathlib import Path
import platform

from ..charts.renderer import require_short_path
from ..data_processing.staging import publication_workspace, publish_directory
from ..datasets.packaging import seal, verify_files
from ..labeling.algorithm import DECIMAL_CONTEXT
from .inputs import read_references, read_predictions, read_run_manifest
from .metrics import aggregate
from .protocol import VERSION, PROTOCOL_SHA256, RULES, MAIN_TOLERANCE, dumps, loads
from .scoring import Levels, Reference, parse_response, score_example


def _output(output: Path) -> Path:
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Odmowa nadpisania: {output}')
    output = output.resolve()
    if not any(Path(folder).resolve() in output.parents for folder in ('results/evaluation','results/diagnostics')):
        raise ValueError('Wynik ewaluacji wymaga nowego katalogu w results/evaluation lub results/diagnostics')
    for root in (output, output.parent/('.eval-'+'x'*8)/'batch'):
        require_short_path(root/'per_example.jsonl')
        require_short_path(root/'SOURCE_INTEGRITY.json')
    return output


def _write(path: Path, value) -> None:
    path.write_text(dumps(value)+'\n', encoding='utf-8')


def _markdown(summary: dict, run: dict) -> str:
    technical = run['prediction_kind'] == 'technical_fixture'
    lines = ['# Ewaluacja S/R', '',
             '**Test techniczny na ręcznie przygotowanych, sztucznych predykcjach. Nie jest oceną VLM.**' if technical else 'Ocena zapisanych odpowiedzi modelu; bez wykonywania inferencji.',
             '', f'Protokół: `{VERSION}`, SHA-256 reguł: `{PROTOCOL_SHA256}`.',
             f'Przebieg: `{run["run_id"]}`; model: `{run["model_id"]}`; checkpoint: `{run["checkpoint_id"]}`; split: `{run["split"]}`.',
             '', '| k × ATR | TP | FP | FN | Micro-P | Micro-R | Micro-F1 | Średni F1 przykładu | JSON poprawny [%] |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    def show(v):
        return 'niezdefiniowane' if v is None else format(v, '.6f')
    for k, scores in summary['tolerances'].items():
        s = scores['overall']
        lines.append(f'| {k} | {s["tp"]} | {s["fp"]} | {s["fn"]} | {show(s["micro_precision"])} | {show(s["micro_recall"])} | {show(s["micro_f1"])} | {show(s["mean_example_f1"])} | {show(s["valid_json_percent"])} |')
    lines += ['', 'Główny wynik: micro-F1 przy k=0.5. MAE USDT jest oddzielnie po instrumentach w summary.json; globalnie podajemy błąd/ATR.',
              'Niepoprawna odpowiedź: TP=FP=0, wszystkie referencje to FN, F1 przykładu=0 także przy pustej referencji. Micro-F1 nie odzwierciedla wtedy wszystkich błędów formatu.',
              'Poprawne puste listy nie tworzą sztucznych TP. Gdy TP=FP=FN=0 w agregacji, micro-F1 jest niezdefiniowane.',
              'MAE dotyczy tylko trafionych par i nie zastępuje F1. Brak par oznacza null; ATR=0 wyklucza tylko błąd znormalizowany.',
              'BTC/ETH z podobnych okresów i nakładające się okna nie są niezależnymi obserwacjami. Brak bootstrapu i testów statystycznych.', '']
    return '\n'.join(lines)


def evaluate(dataset: Path, predictions: Path, run_manifest: Path, output: Path,
             *, split: str = 'validation') -> Path:
    output = _output(output)
    refs, binding, ledger = read_references(dataset, split)
    ledger.track(predictions)
    ledger.track(run_manifest)
    responses = read_predictions(predictions, refs, binding)
    run = read_run_manifest(run_manifest, binding)
    rows = [score_example(ref, parse_response(responses[ref.id])) for ref in refs]
    summary = aggregate(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    with publication_workspace(output.parent, prefix='.eval-') as tmp:
        stage = tmp/'batch'
        stage.mkdir()
        (stage/'predictions.jsonl').write_bytes(predictions.read_bytes())
        (stage/'run-input.json').write_bytes(run_manifest.read_bytes())
        _write(stage/'dataset_binding.json', binding)
        _write(stage/'protocol.json', {'version': VERSION, 'sha256': PROTOCOL_SHA256, 'rules': RULES})
        (stage/'per_example.jsonl').write_text(''.join(dumps(row)+'\n' for row in rows), encoding='utf-8')
        _write(stage/'summary.json', summary)
        _write(stage/'run.json', run)
        _write(stage/'SOURCE_INTEGRITY.json', ledger.verify())
        (stage/'RAPORT.md').write_text(_markdown(summary, run), encoding='utf-8')
        seal(stage, {'kind': 'evaluation_result', 'schema_version': 1, 'status': 'complete',
                     'protocol_version': VERSION, 'protocol_sha256': PROTOCOL_SHA256,
                     'prediction_kind': run['prediction_kind'], 'count': len(refs),
                     'runtime': {'python': platform.python_version(), 'platform': platform.platform()}})
        read_evaluation(stage)
        publish_directory(stage, output)
    return output


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


def _delta(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return {k: _delta(a.get(k), b.get(k)) for k in sorted(set(a) | set(b))}
    if isinstance(a, (int, Decimal)) and not isinstance(a, bool) and isinstance(b, (int, Decimal)) and not isinstance(b, bool):
        return b-a
    return None


def _comparison_content(before: dict, after: dict) -> dict:
    a, b = before['run'], after['run']
    if before['binding'] != after['binding']:
        raise ValueError('Porównanie wymaga identycznych przykładów, obrazów, instrukcji i referencji')
    for key in ('model_id','protocol_version','instruction_version','inference','prediction_kind','split'):
        if a[key] != b[key]:
            raise ValueError(f'Porównanie wymaga identycznego {key}')
    if a['run_id'] == b['run_id']:
        raise ValueError('Porównanie wymaga różnych identyfikatorów przebiegów')
    if a['prediction_kind'] == 'model' and (a['variant'], b['variant']) != ('base','finetuned'):
        raise ValueError('Oczekiwane warianty tego samego modelu: base oraz finetuned')
    with localcontext(DECIMAL_CONTEXT):
        report = {'protocol_version': VERSION, 'protocol_sha256': PROTOCOL_SHA256,
            'prediction_kind': a['prediction_kind'], 'baseline_run': a, 'candidate_run': b,
            'baseline': before['summary'], 'candidate': after['summary'],
            'delta_candidate_minus_baseline': _delta(before['summary'], after['summary']),
            'paired_examples': [{'id': x['id'], 'symbol': x['symbol'],
                'example_f1_delta': {k: y['scores'][k]['example_f1']-x['scores'][k]['example_f1'] for k in x['scores']}}
                for x, y in zip(before['rows'], after['rows'])],
            'note': 'Sparowane wyniki tych samych wykresów. Różnice MAE dotyczą dopasowań, których liczebność może się różnić. Bez testu niezależności BTC/ETH.'}
    return report


def compare(baseline: Path, candidate: Path, output: Path) -> Path:
    output = _output(output)
    before, after = read_evaluation(baseline), read_evaluation(candidate)
    report = _comparison_content(before, after)
    a = before['run']
    output.parent.mkdir(parents=True, exist_ok=True)
    with publication_workspace(output.parent, prefix='.eval-') as tmp:
        stage = tmp/'batch'
        stage.mkdir()
        _write(stage/'comparison.json', report)
        _write(stage/'protocol.json', {'version': VERSION, 'sha256': PROTOCOL_SHA256, 'rules': RULES})
        heading = '**Test techniczny na sztucznych predykcjach, nie porównanie rzeczywistych VLM.**' if a['prediction_kind'] == 'technical_fixture' else 'Sparowane porównanie modelu bazowego i dostrojonego.'
        delta = report['delta_candidate_minus_baseline']['tolerances'][MAIN_TOLERANCE]['overall']
        (stage/'RAPORT.md').write_text('# Porównanie S/R\n\n'+heading+'\n\nRóżnice candidate − baseline przy k=0.5:\n\n'+dumps(delta)+'\n', encoding='utf-8')
        for folder, label in ((baseline,'baseline'),(candidate,'candidate')):
            # Copy complete small evaluation artifacts, not mutable external pointers.
            destination = stage/label
            destination.mkdir()
            for path in folder.iterdir():
                if path.is_file():
                    (destination/path.name).write_bytes(path.read_bytes())
        seal(stage, {'kind': 'evaluation_comparison', 'schema_version': 1, 'status': 'complete',
                     'protocol_version': VERSION, 'protocol_sha256': PROTOCOL_SHA256,
                     'prediction_kind': a['prediction_kind'], 'paired_count': len(before['rows'])})
        read_comparison(stage)
        publish_directory(stage, output)
    return output


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

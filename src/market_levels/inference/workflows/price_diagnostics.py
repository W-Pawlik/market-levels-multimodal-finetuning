"""Re-score saved validation predictions without changing any official artifact."""
from pathlib import Path

from ...data_processing.io.candles import read_candles_csv
from ...evaluation.io.inputs import read_references, read_predictions
from ...evaluation.domain.metrics import aggregate
from ...evaluation.domain.scoring import score_example
from ...evaluation.domain.responses import parse_response
from ...evaluation.protocol import dumps, loads
from ...shared.integrity import sha256_file
from ...shared.paths import child
from ...shared.manifests import seal
from ..domain.price_diagnostics import diagnostic_scores


def run_diagnostics(dataset: Path, predictions: Path, output: Path):
    refs, binding, ledger = read_references(dataset, 'validation')
    ledger.track(predictions)
    raw = read_predictions(predictions, refs, binding)
    manifest = loads((dataset / 'manifest.json').read_text(encoding='utf-8'))
    selected = {r.id for r in refs}
    closes = {e['id']: read_candles_csv(child(dataset, e['ohlc']), source='diagnostic-validation')[-1].close
              for e in manifest['entries'] if e['id'] in selected}
    official = aggregate([score_example(ref, parse_response(raw[ref.id])) for ref in refs])
    diagnostic = diagnostic_scores(refs, raw, closes)
    ledger.verify()
    output.mkdir(parents=True, exist_ok=False)
    report = {'official_label': 'OFICJALNA OCENA sr-eval-v1 — surowe odpowiedzi',
              'official': official, 'price_diagnostics': diagnostic,
              'source_predictions': str(predictions), 'predictions_sha256': sha256_file(predictions),
              'dataset_fingerprint': binding['fingerprint']}
    (output / 'diagnostics.json').write_text(dumps(report) + '\n', encoding='utf-8')
    lines = ['# Diagnostyka zapisanych odpowiedzi validation', '',
             'Referencje pochodzą z algorytmu. MAE dotyczy wyłącznie dopasowanych par.', '',
             '## OFICJALNA OCENA `sr-eval-v1`', '',
             f"Micro-F1 (0,5 ATR): {official['tolerances']['0.5']['overall']['micro_f1']}", '',
             '## DIAGNOSTYKA TRAFNOŚCI CEN', '',
             f"Zdjęto wyłącznie ogrodzenie Markdown: {diagnostic['fence_removed_count']}/{len(refs)}.", '',
             '| Tolerancja ATR | TP | FP | FN | Pomocniczy micro-F1 | MAE/ATR dopasowanych |',
             '| --- | --- | --- | --- | --- | --- |']
    for k, values in diagnostic['metrics']['tolerances'].items():
        r = values['overall']
        lines.append(f"| {k} | {r['tp']} | {r['fp']} | {r['fn']} | {r['micro_f1']} | {r['price_error']['mae_atr']} |")
    lines.extend(['', 'Wszystkie przekroje BTC/ETH × supports/resistances, P/R, liczebności, puste listy',
                  'i strony względem Close są w diagnostics.json. Surowe predykcje pozostały bez zmian.'])
    (output / 'RAPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    seal(output, {'kind': 'auxiliary_price_diagnostics', 'status': 'complete'})
    return report

"""evaluation / reporting / markdown."""
from __future__ import annotations

from ..protocol import VERSION, PROTOCOL_SHA256


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

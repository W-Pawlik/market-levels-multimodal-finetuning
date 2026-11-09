"""Paired evaluation differences on identical dataset bindings."""
from __future__ import annotations

from decimal import Decimal, localcontext

from ...core.numeric.atr import DECIMAL_CONTEXT
from ..protocol import VERSION, PROTOCOL_SHA256


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

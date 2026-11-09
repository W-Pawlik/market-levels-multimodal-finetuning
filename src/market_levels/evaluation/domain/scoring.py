"""Original per-example scoring at the frozen ATR tolerances."""
from __future__ import annotations

from decimal import Decimal, localcontext

from ...core.ohlc.model import Candle
from ...core.ohlc.validation import validate_values
from ...core.numeric.atr import DECIMAL_CONTEXT, true_ranges, wilder_atr
from ..protocol import SIDES, TOLERANCES, ratio
from .models import Response, Reference
from .matching import match_levels


def final_atr(candles: list[Candle]) -> Decimal:
    if len(candles) != 120 or validate_values(candles)['missing_total']:
        raise ValueError('Ewaluacja wymaga tych samych 120 kolejnych świec 4h')
    with localcontext(DECIMAL_CONTEXT):
        return wilder_atr(true_ranges(candles))[-1]


def score_example(reference: Reference, response: Response) -> dict:
    if reference.atr < 0 or not reference.atr.is_finite():
        raise ValueError('Niepoprawny ATR referencji')
    scores = {}
    for k in TOLERANCES:
        with localcontext(DECIMAL_CONTEXT) as context:
            context.prec = max(50, len(reference.atr.as_tuple().digits)+len(k.as_tuple().digits)+4)
            tolerance = k*reference.atr
        sides = {}
        for side in SIDES:
            actual = getattr(reference.levels, side)
            predicted = getattr(response.levels, side) if response.levels else ()
            sides[side] = match_levels(predicted, actual, tolerance, reference.atr)
        tp, fp, fn = (sum(s[key] for s in sides.values()) for key in ('tp','fp','fn'))
        f1 = (ratio(2*tp, 2*tp+fp+fn) if tp+fp+fn else Decimal(1)) if response.levels is not None else Decimal(0)
        scores[str(k)] = {'tolerance': tolerance, 'sides': sides, 'tp': tp, 'fp': fp, 'fn': fn,
                          'example_f1': f1, 'complete_set_correct': response.levels is not None and fp == fn == 0}
    return {'id': reference.id, 'symbol': reference.symbol, 'split': reference.split,
            'atr': reference.atr, 'raw_response': response.raw, 'valid_json': response.levels is not None,
            'format_error': response.error, 'format_reason': response.reason,
            'reference': reference.levels, 'predicted': response.levels, 'scores': scores}

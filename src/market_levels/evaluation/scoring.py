"""Strict response validation, exhaustive matching and per-example scores."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext, MAX_EMAX, MIN_EMIN

from ..core.candles import Candle
from ..data_processing.synthetic.quality import validate_values
from ..labeling.algorithm import DECIMAL_CONTEXT, true_ranges, wilder_atr
from .protocol import SIDES, TOLERANCES, loads, ratio


@dataclass(frozen=True)
class Levels:
    supports: tuple[Decimal, ...]
    resistances: tuple[Decimal, ...]


@dataclass(frozen=True)
class Response:
    raw: str
    levels: Levels | None
    error: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class Reference:
    id: str
    symbol: str
    split: str
    levels: Levels
    atr: Decimal


@dataclass(frozen=True)
class Match:
    predicted_index: int
    reference_index: int
    predicted: Decimal
    reference: Decimal
    absolute_error: Decimal
    atr_error: Decimal | None
    atr_error_reason: str | None


def parse_response(raw: str) -> Response:
    if not isinstance(raw, str):
        raise ValueError('response musi być surowym tekstem')
    try:
        obj = loads(raw)
    except (ValueError, ArithmeticError, RecursionError) as error:
        category = 'duplicate_key' if 'Powtórzony klucz' in str(error) else 'invalid_json'
        return Response(raw, None, category, str(error))
    if not isinstance(obj, dict):
        return Response(raw, None, 'not_object', 'Odpowiedź musi być obiektem JSON')
    if set(obj) != set(SIDES):
        return Response(raw, None, 'keys', 'Wymagane dokładnie supports i resistances')
    for side in SIDES:
        if not isinstance(obj[side], list):
            return Response(raw, None, 'not_array', f'{side} musi być tablicą')
        if len(obj[side]) > 3:
            return Response(raw, None, 'too_many_prices', f'{side}: więcej niż trzy ceny')
        if any(not isinstance(v, Decimal) or not v.is_finite() or v <= 0 for v in obj[side]):
            return Response(raw, None, 'invalid_price', f'{side}: ceny muszą być dodatnimi skończonymi liczbami JSON')
    return Response(raw, Levels(*(tuple(obj[s]) for s in SIDES)))


def final_atr(candles: list[Candle]) -> Decimal:
    if len(candles) != 120 or validate_values(candles)['missing_total']:
        raise ValueError('Ewaluacja wymaga tych samych 120 kolejnych świec 4h')
    with localcontext(DECIMAL_CONTEXT):
        return wilder_atr(true_ranges(candles))[-1]


def _precision(values: tuple[Decimal, ...]) -> int:
    # Enough digits for exact subtraction/sums even when an answer uses >50 digits.
    return max(50, max(v.adjusted() for v in values)-min(v.as_tuple().exponent for v in values)+8)


def match_levels(predicted: tuple[Decimal, ...], reference: tuple[Decimal, ...],
                 tolerance: Decimal, atr: Decimal) -> dict:
    if len(predicted) > 3 or len(reference) > 3 or tolerance < 0 or atr < 0:
        raise ValueError('Niepoprawne dane dopasowania')
    values = predicted+reference+(tolerance, atr)
    if any(not isinstance(v, Decimal) or not v.is_finite() for v in values):
        raise ValueError('Dopasowanie wymaga skończonych Decimal')
    first, duplicates, seen = [], [], set()
    for i, value in enumerate(predicted):
        if value in seen:
            duplicates.append(i)
        else:
            first.append(i)
            seen.add(value)
    with localcontext() as context:
        context.prec = _precision(values)
        context.Emax, context.Emin = MAX_EMAX, MIN_EMIN
        candidates = []
        def search(position, used, pairs, distance):
            if position == len(first):
                candidates.append((tuple(pairs), distance))
                return
            pi = first[position]
            search(position+1, used, pairs, distance)
            for ri, target in enumerate(reference):
                error = abs(predicted[pi]-target)
                if ri not in used and error <= tolerance:
                    search(position+1, used | {ri}, pairs+[(pi, ri)], distance+error)
        search(0, set(), [], Decimal(0))
        pairs, _ = min(candidates, key=lambda entry: (-len(entry[0]), entry[1], entry[0]))
        matches = []
        for pi, ri in pairs:
            error = abs(predicted[pi]-reference[ri])
            matches.append(Match(pi, ri, predicted[pi], reference[ri], error,
                                 ratio(error, atr), 'zero_atr' if not atr else None))
    tp = len(matches)
    return {'tp': tp, 'fp': len(predicted)-tp, 'fn': len(reference)-tp,
            'predicted_count': len(predicted), 'reference_count': len(reference),
            'duplicate_indices': duplicates, 'matches': matches}


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

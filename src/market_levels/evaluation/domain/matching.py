"""Exhaustive maximum-TP matching with exact error and index tie-breaks."""
from __future__ import annotations

from decimal import Decimal, localcontext, MAX_EMAX, MIN_EMIN

from ..protocol import ratio
from .models import Match


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

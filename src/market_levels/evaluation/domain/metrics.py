"""evaluation / domain / metrics."""

from collections import Counter
from decimal import Decimal, localcontext

from ..protocol import ratio, SIDES, TOLERANCES, MAIN_TOLERANCE
from ...core.numeric.atr import DECIMAL_CONTEXT


def _summary(rows: list[dict], k: str, selected_sides: tuple[str, ...], *, usdt: bool) -> dict:
    tp = fp = fn = predicted = reference = duplicates = 0
    errors, normalized, example_f1 = [], [], []
    empty_reference = Counter()
    correct_empty = Counter()
    complete = zero_tp = missed_all = predicted_none = both_empty_reference = both_empty_correct = zero_atr_pairs = 0
    for row in rows:
        score = row['scores'][k]
        sides = [score['sides'][s] for s in selected_sides]
        for name, side in zip(selected_sides, sides):
            tp += side['tp']; fp += side['fp']; fn += side['fn']
            predicted += side['predicted_count']; reference += side['reference_count']
            duplicates += len(side['duplicate_indices'])
            for pair in side['matches']:
                errors.append(pair.absolute_error)
                if pair.atr_error is None:
                    zero_atr_pairs += 1
                else:
                    normalized.append(pair.atr_error)
            if side['reference_count'] == 0:
                empty_reference[name] += 1
                correct_empty[name] += row['valid_json'] and side['predicted_count'] == 0
        t, p, n = (sum(side[key] for side in sides) for key in ('tp','fp','fn'))
        ref_count = sum(side['reference_count'] for side in sides)
        predicted_none += row['valid_json'] and sum(s['predicted_count'] for s in sides) == 0
        zero_tp += t == 0
        missed_all += t == 0 and ref_count > 0
        complete += row['valid_json'] and p == n == 0
        both_empty_reference += ref_count == 0
        both_empty_correct += row['valid_json'] and ref_count == 0 and sum(s['predicted_count'] for s in sides) == 0
        example_f1.append((ratio(2*t, 2*t+p+n) if t+p+n else Decimal(1)) if row['valid_json'] else Decimal(0))
    count, valid = len(rows), sum(r['valid_json'] for r in rows)
    price = {'matched_pairs': len(errors), 'normalized_pairs': len(normalized),
             'mae_atr': ratio(sum(normalized, Decimal(0)), len(normalized)),
             'zero_atr_excluded_pairs': zero_atr_pairs}
    if usdt:
        price['mae_usdt'] = ratio(sum(errors, Decimal(0)), len(errors))
    ordered = sorted(example_f1)
    def quantile(q):
        if not ordered:
            return None
        index = (len(ordered)-1)*q
        lo = int(index)
        hi = min(lo+1, len(ordered)-1)
        return ordered[lo]+(ordered[hi]-ordered[lo])*(index-lo)
    return {'examples': count, 'tp': tp, 'fp': fp, 'fn': fn,
            'micro_precision': ratio(tp, tp+fp), 'micro_recall': ratio(tp, tp+fn),
            'micro_f1': ratio(2*tp, 2*tp+fp+fn), 'mean_example_f1': ratio(sum(example_f1, Decimal(0)), count),
            'valid_json_count': valid, 'valid_json_percent': ratio(100*valid, count),
            'format_errors': dict(sorted(Counter(r['format_error'] for r in rows if not r['valid_json']).items())),
            'predicted_levels': predicted, 'reference_levels': reference, 'duplicate_prices': duplicates,
            'complete_set_correct_count': complete, 'complete_set_correct_percent': ratio(100*complete, count),
            'empty_reference_examples': both_empty_reference, 'correct_empty_examples': both_empty_correct,
            'correct_empty_percent_of_empty_references': ratio(100*both_empty_correct, both_empty_reference),
            'empty_sides': {s: {'reference_empty': empty_reference[s], 'correct_empty': correct_empty[s],
                               'percent_of_empty_references': ratio(100*correct_empty[s], empty_reference[s])} for s in selected_sides},
            'zero_tp_examples': zero_tp, 'missed_all_nonempty_reference_examples': missed_all,
            'predicted_no_levels_valid_examples': predicted_none, 'price_error': price,
            'example_f1_distribution': {'min': ordered[0] if ordered else None, 'q25': quantile(Decimal('.25')),
                'median': quantile(Decimal('.5')), 'q75': quantile(Decimal('.75')), 'max': ordered[-1] if ordered else None,
                'zero_count': sum(v == 0 for v in ordered), 'one_count': sum(v == 1 for v in ordered)}}


def aggregate(rows: list[dict]) -> dict:
    with localcontext(DECIMAL_CONTEXT):
        return {'main_tolerance': MAIN_TOLERANCE, 'tolerances': {str(k): {
            'overall': _summary(rows, str(k), SIDES, usdt=False),
            'by_side': {s: _summary(rows, str(k), (s,), usdt=False) for s in SIDES},
            'by_symbol': {symbol: _summary([r for r in rows if r['symbol'] == symbol], str(k), SIDES, usdt=True)
                          for symbol in ('BTCUSDT', 'ETHUSDT')},
            'by_symbol_side': {symbol: {s: _summary([r for r in rows if r['symbol'] == symbol], str(k), (s,), usdt=True) for s in SIDES}
                               for symbol in ('BTCUSDT', 'ETHUSDT')}
        } for k in TOLERANCES}}

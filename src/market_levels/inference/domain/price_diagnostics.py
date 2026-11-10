"""Auxiliary fence-only diagnostics; the official evaluator remains unchanged."""
import re

from ...evaluation.domain.responses import parse_response
from ...evaluation.domain.scoring import score_example
from ...evaluation.domain.metrics import aggregate
from ...evaluation.protocol import SIDES, ratio


def unwrap_fence(raw: str) -> tuple[str, bool]:
    match = re.fullmatch(r'[ \t\r\n]*```(?:json)?[ \t]*\r?\n(.*?)\r?\n```[ \t\r\n]*', raw, re.DOTALL)
    if match is None or '```' in match[1]:
        return raw, False
    return match[1], True


def diagnostic_scores(references, predictions, closes):
    rows, details = [], []
    wrong = {side: {'wrong_side_levels': 0, 'generated_levels': 0, 'empty_lists': 0,
                    'valid_responses': 0} for side in SIDES}
    for ref in references:
        text, stripped = unwrap_fence(predictions[ref.id])
        parsed = parse_response(text)
        rows.append(score_example(ref, parsed))
        details.append({'id': ref.id, 'fence_removed': stripped, 'valid_json': parsed.levels is not None,
                        'format_error': parsed.error})
        if parsed.levels is not None:
            for side in SIDES:
                levels = getattr(parsed.levels, side)
                wrong[side]['valid_responses'] += 1
                wrong[side]['empty_lists'] += not levels
                wrong[side]['generated_levels'] += len(levels)
                wrong[side]['wrong_side_levels'] += sum(
                    price >= closes[ref.id] if side == 'supports' else price <= closes[ref.id] for price in levels)
    for counts in wrong.values():
        counts['wrong_side_fraction_of_generated'] = ratio(counts['wrong_side_levels'], counts['generated_levels'])
        counts['empty_list_fraction_of_valid'] = ratio(counts['empty_lists'], counts['valid_responses'])
    removed = sum(r['fence_removed'] for r in details)
    return {'label': 'DIAGNOSTYKA TRAFNOŚCI CEN — NIE OFICJALNY WYNIK',
            'metrics': aggregate(rows), 'fence_removed_count': removed,
            'fence_removed_fraction': ratio(removed, len(rows)), 'details': details,
            'close_side_diagnostics': wrong,
            'mae_scope': 'Only matched pairs; USDT by symbol; algorithmic reference levels, not market truth'}

"""Frozen rules and exact JSON serialization for sr-eval-v1."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from decimal import Decimal, localcontext
import hashlib
import json

from ..labeling.algorithm import DECIMAL_CONTEXT

VERSION = 'sr-eval-v1'
TOLERANCES = (Decimal('0.25'), Decimal('0.5'), Decimal('1.0'))
MAIN_TOLERANCE = '0.5'
SIDES = ('supports', 'resistances')
RULES = {
    'version': VERSION, 'main_k': MAIN_TOLERANCE, 'k': [str(k) for k in TOLERANCES],
    'atr': 'existing true_ranges + wilder_atr, 120 candles, final ATR, Decimal context 50 ROUND_HALF_UP',
    'matching': 'same side; max TP, min total absolute error, lexicographic (prediction index, reference index) pairs',
    'boundary': 'abs(pred-reference) <= k*ATR; zero ATR allows exact matches only',
    'duplicates': 'first occurrence within each side eligible; every later occurrence is FP',
    'invalid_response': 'TP=FP=0, FN=reference count; example F1=0 even for empty reference',
    'empty': 'no artificial TP; valid empty/empty example F1=1; all-zero micro counts => null',
    'zero_denominator': 'precision/recall/F1/MAE null when denominator zero',
    'price_error': 'matched pairs only; USDT MAE by symbol; normalized MAE excludes zero ATR',
    'format': 'exact keys supports/resistances, 0..3 positive finite JSON numbers per side; no repair',
    'comparison': 'paired IDs, same dataset fingerprint, protocol, model_id, instruction and inference settings',
    'statistics': 'descriptive; no bootstrap or assumption of independent BTC/ETH windows',
}
PROTOCOL_SHA256 = hashlib.sha256(json.dumps(RULES, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def ratio(numerator, denominator) -> Decimal | None:
    if not denominator:
        return None
    with localcontext(DECIMAL_CONTEXT):
        return Decimal(numerator)/Decimal(denominator)


def dumps(value) -> str:
    """Decimal remains a JSON number; never silently emit NaN or convert to float."""
    if is_dataclass(value):
        return dumps(asdict(value))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('Niefinitywna liczba wyniku')
        return str(value)
    if isinstance(value, dict):
        return '{'+', '.join(json.dumps(str(k), ensure_ascii=False)+': '+dumps(v) for k, v in value.items())+'}'
    if isinstance(value, (list, tuple)):
        return '['+', '.join(dumps(v) for v in value)+']'
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def reject_constant(value):
    raise ValueError(f'Niedozwolona stała JSON: {value}')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Powtórzony klucz JSON: {key}')
        result[key] = value
    return result


def loads(text: str):
    return json.loads(text, parse_float=Decimal, parse_int=Decimal,
                      parse_constant=reject_constant, object_pairs_hook=unique_object)

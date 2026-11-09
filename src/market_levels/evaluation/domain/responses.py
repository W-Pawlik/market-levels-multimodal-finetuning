"""Strict raw JSON response validation without repair."""
from __future__ import annotations

from decimal import Decimal

from ..protocol import SIDES, loads
from .models import Levels, Response


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

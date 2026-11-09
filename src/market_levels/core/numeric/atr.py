"""True ranges, Wilder ATR and the shared 50-digit Decimal context."""
from __future__ import annotations

from decimal import Context, ROUND_HALF_UP, Decimal

from ..ohlc.model import Candle


DECIMAL_CONTEXT = Context(prec=50, rounding=ROUND_HALF_UP)


def true_ranges(candles: list[Candle]) -> tuple[Decimal, ...]:
    return tuple(max(c.high-c.low, abs(c.high-candles[i-1].close),
                     abs(c.low-candles[i-1].close)) if i else c.high-c.low
                 for i, c in enumerate(candles))


def wilder_atr(tr: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    """Pierwszy element odpowiada świecy 13; ostatni końcowi okna."""
    if len(tr) < 14:
        raise ValueError("ATR(14) wymaga minimum 14 TR")
    values = [sum(tr[:14], Decimal(0))/14]
    for value in tr[14:]:
        values.append((values[-1]*13+value)/14)
    return tuple(values)

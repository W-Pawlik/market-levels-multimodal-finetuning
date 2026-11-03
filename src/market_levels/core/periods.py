"""Zakresy miesięcy i dni używane przy pozyskiwaniu archiwów."""
from __future__ import annotations

from datetime import date, timedelta
from collections.abc import Iterator


def iter_months(start: str, end: str) -> Iterator[date]:
    """Zwróć miesiące z domkniętego zakresu YYYY-MM lub zgłoś ValueError."""
    try:
        y1, m1 = map(int, start.split("-"))
        y2, m2 = map(int, end.split("-"))
        assert 1 <= m1 <= 12 and 1 <= m2 <= 12
        first, last = date(y1, m1, 1), date(y2, m2, 1)
    except (AssertionError, ValueError) as exc:
        raise ValueError("Okres musi mieć format YYYY-MM z poprawnym miesiącem") from exc
    if first > last:
        raise ValueError("Data początkowa jest późniejsza niż końcowa")
    d = first
    while d <= last:
        yield d
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def _last_closed_month(today: date) -> date:
    return date(today.year - (today.month == 1), (today.month - 2) % 12 + 1, 1)


def _days_in_month(month: date) -> Iterator[date]:
    next_month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    d = month
    while d < next_month:
        yield d
        d += timedelta(days=1)

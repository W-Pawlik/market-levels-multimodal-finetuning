"""Descriptive distributions with the original linear quantiles."""
from __future__ import annotations

import math
import statistics


def distribution(values: list[float]) -> dict:
    if not values or any(not math.isfinite(v) for v in values):
        raise ValueError("Statystyki wymagają niepustych skończonych obserwacji")
    ordered = sorted(values)
    def quantile(q):
        position = (len(ordered) - 1) * q
        low = math.floor(position)
        high = math.ceil(position)
        return ordered[low] + (ordered[high] - ordered[low]) * (position - low)
    return {"count": len(values), "mean": statistics.mean(values),
            "std": statistics.stdev(values) if len(values) > 1 else 0.0,
            "min": ordered[0], "max": ordered[-1],
            "quantiles": {str(q): quantile(q) for q in (0.01, 0.05, 0.5, 0.95, 0.99)}}

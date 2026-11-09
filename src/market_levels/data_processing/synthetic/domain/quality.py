"""Synthetic continuity checks and original series observations."""
from __future__ import annotations

import math

from ....core.ohlc.model import Candle, DataValidationError, CANDLE_DELTA
from ....core.ohlc.validation import validate_values
from ....core.numeric.statistics import distribution


def validate_synthetic(candles: list[Candle], regimes: list[dict], seed: int) -> dict:
    report = validate_values(candles)
    if len(candles) != 120 or report["missing_total"]:
        raise DataValidationError("Wymagane 120 kolejnych świec 4h")
    if type(seed) is not int or seed < 0:
        raise DataValidationError("Niepoprawny seed")
    if not 1 <= len(regimes) <= 3:
        raise DataValidationError("Wymagane 1..3 reżimy")
    cursor = 0
    previous_kind = None
    for regime in regimes:
        kind = regime["kind"]
        if kind not in ("uptrend", "downtrend", "consolidation", "breakout"):
            raise DataValidationError("Nieznany reżim")
        if kind == previous_kind or (kind == "breakout" and previous_kind != "consolidation"):
            raise DataValidationError("Niedozwolona kolejność reżimów")
        if (type(regime["length"]) is not int or regime["length"] <= 0
                or regime["start"] != cursor or regime["end_exclusive"] != cursor + regime["length"]):
            raise DataValidationError("Niepoprawne zakresy reżimów")
        for name in ("mu", "sigma", "mean_reversion", "center_log_price"):
            if type(regime[name]) not in (int, float) or not math.isfinite(regime[name]):
                raise DataValidationError("Nieskończony parametr reżimu")
        if regime["sigma"] <= 0 or not 0 <= regime["mean_reversion"] <= 1:
            raise DataValidationError("Niepoprawny parametr reżimu")
        cursor += regime["length"]
        previous_kind = kind
    if cursor != 120:
        raise DataValidationError("Długości reżimów muszą sumować się do 120")
    for previous, current in zip(candles, candles[1:]):
        if previous.close != current.open:
            raise DataValidationError("Nieciągłość ceny Open/Close")
    if any(not c.source_archive.startswith("synthetic:") for c in candles):
        raise DataValidationError("Brak syntetycznego pochodzenia")
    return dict(report, valid=True, seed=seed, regime_count=len(regimes))


def series_observations(candles: list[Candle]) -> dict[str, list[float]]:
    """Surowe obserwacje dla wspólnych statystyk, bez przejść przez luki."""
    validate_values(candles)
    return _series_observations(candles)


def _series_observations(candles: list[Candle]) -> dict[str, list[float]]:
    returns = [math.log(float(b.close)) - math.log(float(a.close))
               for a, b in zip(candles, candles[1:]) if b.timestamp - a.timestamp == CANDLE_DELTA]
    if not returns:
        raise ValueError("Brak sąsiadujących obserwacji 4h do obliczenia stóp zwrotu")
    ranges, bodies, upper, lower, body_proportions = [], [], [], [], []
    for candle in candles:
        o, h, l, c = (float(getattr(candle, k)) for k in ("open", "high", "low", "close"))
        span = h - l
        ranges.append(span / o)
        bodies.append(abs(c - o) / o)
        upper.append((h - max(o, c)) / span if span else 0.0)
        lower.append((min(o, c) - l) / span if span else 0.0)
        body_proportions.append(abs(c - o) / span if span else 0.0)
    return {"log_returns": returns, "absolute_log_returns": [abs(r) for r in returns],
            "relative_range": ranges, "relative_body": bodies,
            "body_fraction": body_proportions, "upper_wick_fraction": upper,
            "lower_wick_fraction": lower, "close_prices": [float(c.close) for c in candles]}


def series_statistics(candles: list[Candle]) -> dict:
    """Stopy close-close tylko przez dokładnie 4h; proporcje względem zakresu."""
    report = validate_values(candles)
    result = {key: distribution(values) for key, values in _series_observations(candles).items()}
    result.update({"window_close_change": float(candles[-1].close / candles[0].open) - 1,
            "window_relative_range": float(max(c.high for c in candles) / min(c.low for c in candles)) - 1,
            "skipped_noncontiguous_transitions": len(report["gaps"])})
    return result


def compare_statistics(observed: dict, reference: dict) -> dict:
    """Różnice opisowe, bez automatycznego odrzucania nietypowych rynków."""
    return {key: {metric: observed[key][metric] - reference[key][metric]
                  for metric in ("mean", "std")}
            for key in ("log_returns", "relative_range", "relative_body", "body_fraction",
                        "upper_wick_fraction", "lower_wick_fraction")}

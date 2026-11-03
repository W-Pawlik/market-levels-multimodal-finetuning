"""Kontrola techniczna i opisowa diagnostyka, bez progów podobieństwa."""
from __future__ import annotations

import hashlib
import json
import math
import statistics

from ...core.candles import CANDLE_DELTA, Candle, DataValidationError
from ..validation import (check_series, _positive_decimal, validate_candle_timestamp,
                          validate_ohlc)


def validate_values(candles: list[Candle]) -> dict:
    """Sprawdź wartości, UTC, kolejność i wspólny kontrakt szeregu."""
    for index, candle in enumerate(candles):
        stamp = candle.timestamp
        if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
            raise DataValidationError("Wymagany czas UTC")
        validate_candle_timestamp(stamp, candle.source_archive, index)
        for name in ("open", "high", "low", "close"):
            _positive_decimal(str(getattr(candle, name)), name)
        validate_ohlc(candle.open, candle.high, candle.low, candle.close, candle.source_archive, index)
    report = check_series(candles)
    if any(b.timestamp <= a.timestamp for a, b in zip(candles, candles[1:])):
        raise DataValidationError("Świece muszą być uporządkowane chronologicznie")
    return report


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


def canonical_hash(candles: list[Candle]) -> str:
    """Hash samych cen; daty indeksu i pochodzenie nie maskują duplikatów."""
    # Format stałopozycyjny i usunięcie końcowych zer bez kontekstowego normalize().
    def canonical(value):
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    rows = [[canonical(getattr(c, k)) for k in ("open", "high", "low", "close")] for c in candles]
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


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

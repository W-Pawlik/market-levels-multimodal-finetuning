"""Observed window diagnostics; never target labels or selection feedback."""
from __future__ import annotations

import math
import statistics

from ...core.ohlc.model import Candle, CANDLE_DELTA
from .validation import validate_window
from ...data_processing.windows.domain.candidates import training_windows


def quantile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("Brak danych do progu")
    ordered = sorted(values)
    position = (len(ordered)-1)*q
    a, b = math.floor(position), math.ceil(position)
    return ordered[a] + (ordered[b]-ordered[a])*(position-a)


def movement(candles: list[Candle]) -> dict:
    """Open-to-last-Close net/path, including the first candle and real gaps in price."""
    prices = [float(candles[0].open)] + [float(c.close) for c in candles]
    path = sum(abs(b-a) for a, b in zip(prices, prices[1:]))
    return {"price_change": prices[-1]/prices[0]-1,
            "directionality": abs(prices[-1]-prices[0])/path if path else 0.0}


def observed_motion(metrics: dict) -> str:
    if metrics["directionality"] >= 0.18:
        return "upward" if metrics["price_change"] > 0 else "downward"
    return "low_directionality" if metrics["directionality"] <= 0.08 else "intermediate"


def window_metrics(candles: list[Candle], thresholds: dict | None = None) -> dict:
    validate_window(candles)
    changes = [math.log(float(b.close))-math.log(float(a.close)) for a, b in zip(candles, candles[1:])]
    spans = [float((c.high-c.low)/c.open) for c in candles]
    fractions = [(float(abs(c.close-c.open)/(c.high-c.low)),
                  float((c.high-max(c.open,c.close))/(c.high-c.low)),
                  float((min(c.open,c.close)-c.low)/(c.high-c.low)))
                 for c in candles if c.high > c.low]
    # Flat bars have no defined proportions: report count, average nonflat bars only.
    result = dict(movement(candles),
                  relative_range=float((max(c.high for c in candles)-min(c.low for c in candles))/candles[0].open),
                  log_return_std=statistics.stdev(changes),
                  body_fraction=statistics.mean(f[0] for f in fractions) if fractions else None,
                  upper_wick_fraction=statistics.mean(f[1] for f in fractions) if fractions else None,
                  lower_wick_fraction=statistics.mean(f[2] for f in fractions) if fractions else None,
                  flat_candles=120-len(fractions))
    result["observed_motion"] = observed_motion(result)
    # Breakout proxy is local only: 20 preceding bars, no target S/R calculation.
    events = []
    for i in range(20, 120):
        preceding = candles[i-20:i]
        baseline = statistics.stdev(changes[i-20:i-1])
        outside = candles[i].close > max(c.high for c in preceding) or candles[i].close < min(c.low for c in preceding)
        if outside and abs(changes[i-1]) > 2*baseline:
            events.append(i+1)
    first, second = movement(candles[:60]), movement(candles[60:])
    result.update(breakout_proxy_positions=events,
                  reversal_proxy=(first["directionality"] >= 0.18 and second["directionality"] >= 0.18
                                  and first["price_change"]*second["price_change"] < 0))
    if thresholds is not None:
        std = result["log_return_std"]
        result.update(volatility_band="low" if std <= thresholds["volatility_q33"] else "high" if std > thresholds["volatility_q67"] else "medium",
                      large_candle_share=sum(v >= thresholds["range_q95"] for v in spans)/120,
                      extreme_move_share=sum(abs(v) >= thresholds["abs_return_q99"] for v in changes)/119)
    return result


def fit_thresholds(candles: list[Candle]) -> dict:
    windows, _ = training_windows(candles)
    stds = [window_metrics(w)["log_return_std"] for _, w in windows]
    returns = [abs(math.log(float(b.close))-math.log(float(a.close))) for a,b in zip(candles,candles[1:]) if b.timestamp-a.timestamp == CANDLE_DELTA]
    return {"method": "train_only_linear_quantiles_v1", "window_stride": 120,
            "reference_window_count": len(stds), "volatility_q33": quantile(stds, 1/3),
            "volatility_q67": quantile(stds, 2/3),
            "range_q95": quantile([float((c.high-c.low)/c.open) for c in candles], .95),
            "abs_return_q99": quantile(returns, .99)}

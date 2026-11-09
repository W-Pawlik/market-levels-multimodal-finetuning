"""data_processing / synthetic / domain / calibration / features."""
from __future__ import annotations

from ..diagnostics import lag1_absolute_correlation
from .....core.numeric.statistics import distribution
from ..quality import series_observations


def calibration_features(stats: dict) -> dict:
    pooled, window = stats["pooled_observations"], stats["window_distributions"]
    result = {"return_std": pooled["log_returns"]["std"],
              "abs_q95": pooled["absolute_log_returns"]["quantiles"]["0.95"],
              "abs_q99": pooled["absolute_log_returns"]["quantiles"]["0.99"],
              "range_mean": pooled["relative_range"]["mean"],
              "range_q95": pooled["relative_range"]["quantiles"]["0.95"],
              "body_fraction": pooled["body_fraction"]["mean"],
              "upper_wick": pooled["upper_wick_fraction"]["mean"],
              "lower_wick": pooled["lower_wick_fraction"]["mean"],
              "window_std_mean": window["return_std"]["mean"],
              "window_std_std": window["return_std"]["std"],
              "abs_ac1": stats["absolute_return_lag1"]["value"]}
    for key in ("pearson_kurtosis", "exceedance_abs_2sigma", "exceedance_abs_3sigma"):
        result[key] = stats["return_diagnostics"][key]
    return result


def training_volatility_diagnostics(candles: list) -> dict:
    """Ruchome std z 24 zwrotów, bez przechodzenia przez luki; krok 1 świeca."""
    from .....core.ohlc.model import CANDLE_DELTA
    runs = []
    for candle in candles:
        if not runs or candle.timestamp - runs[-1][-1].timestamp != CANDLE_DELTA:
            runs.append([])
        runs[-1].append(candle)
    rolling, returns = [], []
    for run in runs:
        if len(run) < 2:
            continue
        r = series_observations(run)["log_returns"]
        returns.append(r)
        rolling.extend(distribution(r[i:i+24])["std"] for i in range(len(r)-23))
    return {"rolling_return_count": 24, "rolling_stride_candles": 1,
            "rolling_std": distribution(rolling) if rolling else None,
            "absolute_return_lag1": lag1_absolute_correlation(returns)}

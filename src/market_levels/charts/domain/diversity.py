"""Descriptive counts and distributions of every declared regime."""
from __future__ import annotations

from collections import Counter

from ...core.numeric.statistics import distribution
from ..config import KINDS


def summarize(records: list[dict]) -> dict:
    """All segments count; each chart contributes exactly 120 candle assignments."""
    count = Counter(str(len(r["regimes"])) for r in records)
    occurrences, candles, transitions, sequences = Counter(), Counter(), Counter(), Counter()
    lengths = {k: [] for k in KINDS}
    agreement = {k: Counter() for k in ("uptrend", "downtrend")}
    observed_segments = {k: Counter() for k in KINDS}
    for record in records:
        regimes = record["regimes"]
        kinds = [r["kind"] for r in regimes]
        sequences[" -> ".join(kinds)] += 1
        for a,b in zip(kinds,kinds[1:]):
            transitions[f"{a} -> {b}"] += 1
        for regime in regimes:
            k = regime["kind"]
            occurrences[k] += 1
            candles[k] += regime["length"]
            lengths[k].append(regime["length"])
            if "observed" in regime:
                observed_segments[k][regime["observed"]["motion"]] += 1
            if k in agreement:
                agreement[k]["matches" if regime["declared_direction_matches"] else "opposite_or_flat"] += 1
    total = len(records)*120
    metrics = [r["metrics"] for r in records]
    return {"charts": len(records), "master_seeds": dict(Counter(str(r["master_seed"]) for r in records)),
            "regime_count": {str(i): count[str(i)] for i in (1,2,3)},
            "regime_occurrences": {k: occurrences[k] for k in KINDS},
            "candle_counts": {k: candles[k] for k in KINDS},
            "candle_shares": {k: candles[k]/total if total else 0 for k in KINDS},
            "regime_lengths": {k: {"histogram": dict(sorted(Counter(lengths[k]).items())),
                                    "distribution": distribution(lengths[k]) if lengths[k] else None} for k in KINDS},
            "transitions": dict(transitions.most_common()), "sequences": dict(sequences.most_common()),
            "consolidation_breakout_trend": sum(v for k,v in sequences.items() if k in ("consolidation -> breakout -> uptrend", "consolidation -> breakout -> downtrend")),
            "declared_segment_direction_agreement": {k: dict(v) for k,v in agreement.items()},
            "declared_vs_observed_segments": {k:dict(v) for k,v in observed_segments.items()},
            "volatility_bands": dict(Counter(m["volatility_band"] for m in metrics)),
            "observed_motion": dict(Counter(m["observed_motion"] for m in metrics)),
            "breakout_proxy_charts": sum(bool(m["breakout_proxy_positions"]) for m in metrics),
            "metric_distributions": {k: distribution([m[k] for m in metrics if m[k] is not None])
                                     for k in ("price_change", "relative_range", "log_return_std", "directionality",
                                               "large_candle_share", "extreme_move_share", "body_fraction",
                                               "upper_wick_fraction", "lower_wick_fraction") if any(m[k] is not None for m in metrics)}}

"""Seeded diagnostic pilot selection by category coverage."""
from __future__ import annotations

import random


SELECTION_VERSION = "coverage_seeded_tiebreak_v1"


def tags(record: dict) -> set[str]:
    metrics = record["metrics"]
    result = {"motion:"+metrics["observed_motion"], "volatility:"+metrics["volatility_band"]}
    if metrics["breakout_proxy_positions"]:
        result.add("observed:breakout_proxy")
    if metrics["reversal_proxy"]:
        result.add("observed:reversal_proxy")
    if record["source"] == "synthetic":
        result.add("seed:"+str(record["master_seed"]))
        result.update("declared:"+r["kind"] for r in record["regimes"])
        if len(record["regimes"]) > 1:
            result.add("declared:mixed")
        if [r["kind"] for r in record["regimes"]] in (["consolidation", "breakout", "uptrend"], ["consolidation", "breakout", "downtrend"]):
            result.add("declared:consolidation_breakout_trend")
    return result


def select_pilot(records: list[dict], count: int, seed: int) -> list[dict]:
    """Greedy category coverage; seed changes ties, never market trajectories."""
    if type(seed) is not int or seed < 0 or type(count) is not int or count < 1:
        raise ValueError("Niepoprawny seed lub liczba próbek")
    ordered = sorted(records, key=lambda r: (r["id"], r["ohlc_sha256"]))
    if len({r["ohlc_sha256"] for r in ordered}) != len(ordered):
        raise ValueError("Duplikaty OHLC w puli selekcji")
    random.Random(seed).shuffle(ordered)
    chosen, covered = [], set()
    while ordered and len(chosen) < count:
        index = max(range(len(ordered)), key=lambda i: len(tags(ordered[i])-covered))
        record = ordered.pop(index)
        chosen.append(record)
        covered.update(tags(record))
    return chosen

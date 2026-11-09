"""Continuous-window grids, coverage and split validation."""
from __future__ import annotations

from collections import Counter

from ....core.ohlc.model import Candle, CANDLE_DELTA
from ....core.ohlc.validation import validate_values
from ....core.time.periods import ChronologicalSplit
from ....core.ohlc.identity import canonical_hash
from .models import Window


def training_windows(candles: list[Candle], stride: int = 120) -> tuple[list[tuple[int, list[Candle]]], int]:
    """Fixed positions in each continuous run; no windows cross a gap."""
    validate_values(candles)
    if type(stride) is not int or stride <= 0:
        raise ValueError("stride musi być dodatni")
    windows, runs = [], []
    for index, candle in enumerate(candles):
        if not runs or candle.timestamp - runs[-1][-1][1].timestamp != CANDLE_DELTA:
            runs.append([])
        runs[-1].append((index, candle))
    for run in runs:
        for offset in range(0, len(run)-119, stride):
            windows.append((run[offset][0], [c for _, c in run[offset:offset+120]]))
    return windows, len(runs)-1


def candidates(candles: list[Candle], symbol: str, split: ChronologicalSplit,
               strides: dict[str, int]) -> tuple[dict[str, list[Window]], dict]:
    """Validate full input before partitioning; never interpolate or sort bad data."""
    if symbol not in ("BTCUSDT", "ETHUSDT") or set(strides) != set(split.periods):
        raise ValueError("Niepoprawny symbol lub zestaw przesunięć")
    if any(type(v) is not int or v <= 0 for v in strides.values()):
        raise ValueError("Przesunięcie musi być dodatnią liczbą całkowitą")
    if any(strides[s] < 120 for s in ("validation", "test")):
        raise ValueError("Validation/test wymagają rozłącznych okien")
    validate_values(candles)
    result, audit = {}, {}
    for name, (start, end) in split.periods.items():
        indices = [i for i, c in enumerate(candles) if start <= c.timestamp <= end]
        fragments: list[list[int]] = []
        gaps = []
        for index in indices:
            if not fragments or candles[index].timestamp-candles[fragments[-1][-1]].timestamp != CANDLE_DELTA:
                if fragments:
                    previous = candles[fragments[-1][-1]].timestamp
                    gaps.append({"after": previous.isoformat(), "before": candles[index].timestamp.isoformat(),
                                 "missing_candles": int((candles[index].timestamp-previous)/CANDLE_DELTA)-1})
                fragments.append([])
            fragments[-1].append(index)
        windows, tails, rejected = [], [], []
        for fragment_number, fragment in enumerate(fragments):
            starts = list(range(0, len(fragment)-119, strides[name]))
            for position in starts:
                selected = tuple(fragment[position:position+120])
                windows.append(Window(symbol, name, selected, tuple(candles[i] for i in selected)))
            rejected.extend({"start_utc": candles[fragment[position]].timestamp.isoformat(),
                             "remaining_contiguous_candles": len(fragment)-position,
                             "reason": "gap" if fragment_number < len(fragments)-1 else "split_boundary_or_source_end"}
                            for position in range(0, len(fragment), strides[name]) if position+120 > len(fragment))
            # These starts are ineligible, not discarded valid candidates. No cross-fragment grid exists.
            tails.append({"start": candles[fragment[0]].timestamp.isoformat(),
                          "end": candles[fragment[-1]].timestamp.isoformat(), "candles": len(fragment),
                          "next_grid_start": candles[fragment[starts[-1]+strides[name]]].timestamp.isoformat()
                          if starts and starts[-1]+strides[name] < len(fragment) else None,
                          "unused_tail_candles": len(fragment)-(starts[-1]+120) if starts else len(fragment)})
        result[name] = windows
        audit[name] = {"candles": len(indices), "available": len(windows), "gaps": gaps,
                       "fragments": tails, "stride": strides[name], "ineligible_grid_starts": rejected,
                       "boundary_policy": "120 candles wholly inside one split and one fragment"}
    return result, audit


def validate_selection(windows: list[Window], split: ChronologicalSplit) -> None:
    seen = set()
    occupied: dict[tuple[str, str], list] = {}
    for window in windows:
        if window.symbol not in ("BTCUSDT", "ETHUSDT") or window.split not in split.periods:
            raise ValueError("Niepoprawny instrument/split")
        cs = list(window.candles)
        if len(cs) != 120 or validate_values(cs)["missing_total"]:
            raise ValueError("Wymagane 120 kolejnych świec 4h bez luk")
        if (len(window.indices) != 120 or any(b != a+1 for a, b in zip(window.indices, window.indices[1:]))):
            raise ValueError("Niespójne indeksy źródłowe")
        start, end = split.periods[window.split]
        if not start <= cs[0].timestamp <= cs[-1].timestamp <= end:
            raise ValueError("Okno przekracza granicę splitu")
        digest = canonical_hash(cs)
        if digest in seen:
            raise ValueError("Duplikat OHLC, również między splitami/instrumentami")
        seen.add(digest)
        if window.split != "train":
            key = (window.symbol, window.split)
            for first, last in occupied.setdefault(key, []):
                if cs[0].timestamp <= last and first <= cs[-1].timestamp:
                    raise ValueError("Nakładające się okna validation/test")
            occupied[key].append((cs[0].timestamp, cs[-1].timestamp))


def coverage(windows: list[Window]) -> dict:
    return {"count": len(windows),
            "years_by_window_start": dict(sorted(Counter(str(w.candles[0].timestamp.year) for w in windows).items())),
            "start_utc": min((w.candles[0].timestamp.isoformat() for w in windows), default=None),
            "end_utc": max((w.candles[-1].timestamp.isoformat() for w in windows), default=None)}

"""Chronological candidates; grids restart at each continuous fragment."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import random

from ...core.candles import Candle, CANDLE_DELTA
from ..synthetic.quality import canonical_hash, validate_values
from ..synthetic.training_period import ChronologicalSplit


@dataclass(frozen=True)
class Window:
    symbol: str
    split: str
    indices: tuple[int, ...]
    candles: tuple[Candle, ...]

    def document(self) -> dict:
        digest = canonical_hash(list(self.candles))
        start, end = self.candles[0].timestamp, self.candles[-1].timestamp
        identity = f"{self.symbol}:{self.split}:{start.isoformat()}:{digest}"
        return {"id": hashlib.sha256(identity.encode()).hexdigest()[:24],
                "symbol": self.symbol, "source": "real", "split": self.split,
                "start_utc": start.isoformat(), "end_utc": end.isoformat(),
                "csv_record_indices": list(self.indices), "ohlc_sha256": digest}


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


def select_training(windows: list[Window], count: int, seed: int) -> list[Window]:
    """One seeded draw per consecutive equal-count chronological stratum."""
    if type(seed) is not int or seed < 0 or type(count) is not int or not 0 <= count <= len(windows):
        raise ValueError("Niepoprawny seed/liczebność lub za mało kandydatów")
    ordered = sorted(windows, key=lambda w: w.candles[0].timestamp)
    if any(w.split != "train" for w in ordered):
        raise ValueError("Selekcja losowa jest dozwolona wyłącznie dla train")
    rng = random.Random(seed)
    return [ordered[rng.randrange(i*len(ordered)//count, (i+1)*len(ordered)//count)]
            for i in range(count)]


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

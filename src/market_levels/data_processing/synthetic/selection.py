"""Nienakładające się okna wyłącznie do diagnostyki generatora."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import random

from ...core.candles import Candle, CANDLE_DELTA
from .generator import example_seed
from .quality import canonical_hash, validate_values
from .settings import SYMBOLS, positive_int
from .training_period import ChronologicalSplit


def select_real_windows(candles: list[Candle], *, symbol: str, start: datetime,
                        end: datetime, count: int, seed: int,
                        split: ChronologicalSplit) -> tuple[list[list[Candle]], dict]:
    """Losuj wykonalne przydziały i położenia okien w ciągłych odcinkach."""
    split.require_training(start, end)
    positive_int(count, "window_count")
    if symbol not in SYMBOLS or type(seed) is not int or seed < 0:
        raise ValueError("Niepoprawny symbol lub seed selekcji")
    # Indeksy dotyczą rekordów wejściowego CSV (zero-based, bez nagłówka).
    selected = [(index, c) for index, c in enumerate(candles) if start <= c.timestamp <= end]
    coverage = validate_values([c for _, c in selected])
    runs = []
    for item in selected:
        if not runs or item[1].timestamp - runs[-1][-1][1].timestamp != CANDLE_DELTA:
            runs.append([])
        runs[-1].append(item)
    capacities = [len(run) // 120 for run in runs]
    maximum = sum(capacities)
    if count > maximum:
        raise ValueError(f"Za mało nienakładających się okien: żądano {count}, maksimum {maximum}")
    effective_seed = example_seed(seed, symbol, 0)
    rng = random.Random(effective_seed)
    # Losowanie miejsc pojemności gwarantuje wykonalny przydział liczby okien.
    slots = [i for i, capacity in enumerate(capacities) for _ in range(capacity)]
    allocation = Counter(rng.sample(slots, count))
    windows, entries = [], []
    for run_index, run in enumerate(runs):
        number = allocation[run_index]
        if not number:
            continue
        slack = len(run) - number * 120
        # Uporządkowane k różnych pozycji y w [0, slack+k) dają rozłączne
        # początki x_j=y_j+j*(120-1). Nie ma porażek zachłannego wyboru.
        positions = sorted(rng.sample(range(slack + number), number))
        for j, position in enumerate(positions):
            offset = position + j * 119
            indexed = run[offset:offset + 120]
            window = [c for _, c in indexed]
            windows.append(window)
            entries.append({"index": len(entries), "start": window[0].timestamp.isoformat(),
                            "end": window[-1].timestamp.isoformat(), "count": len(window),
                            "csv_record_indices": [i for i, _ in indexed],
                            "ohlc_sha256": canonical_hash(window)})
    return windows, {"symbol": symbol, "start": start.isoformat(), "end": end.isoformat(),
                     "selection_seed": seed, "effective_seed": effective_seed,
                     "window_count": count, "window_length": 120,
                     "max_nonoverlapping_windows": maximum,
                     "gaps": coverage["gaps"], "windows_with_gaps_allowed": False,
                     "method": "capacity_slots_then_uniform_nonoverlapping_positions_v1",
                     "method_note": "Losowy przydział pojemności odcinków, potem pozycje; nie jest to jednostajny rozkład wszystkich zestawów okien.",
                     "windows": entries}

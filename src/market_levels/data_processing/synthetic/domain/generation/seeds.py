"""data_processing / synthetic / domain / generation / seeds."""
from __future__ import annotations

import hashlib


def example_seed(master_seed: int, symbol: str, index: int) -> int:
    """Stabilny seed niezależny od kolejności instrumentów i rozmiaru partii."""
    if type(master_seed) is not int or master_seed < 0 or type(index) is not int or index < 0:
        raise ValueError("Seed i indeks muszą być nieujemnymi liczbami całkowitymi")
    return int.from_bytes(hashlib.sha256(f"{master_seed}:{symbol}:{index}".encode()).digest(), "big")


STREAMS = ("regimes", "close", "tail_selector", "intracandle", "volatility", "example")

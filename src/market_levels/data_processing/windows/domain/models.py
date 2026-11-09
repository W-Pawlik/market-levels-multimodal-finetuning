"""Chronological windows and their stable identities."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ....core.ohlc.model import Candle
from ....core.ohlc.identity import canonical_hash


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

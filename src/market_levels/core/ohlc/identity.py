"""Canonical identity of prices, independent of timestamps and provenance."""
from __future__ import annotations

import hashlib
import json

from .model import Candle


def canonical_hash(candles: list[Candle]) -> str:
    """Hash samych cen; daty indeksu i pochodzenie nie maskują duplikatów."""
    # Format stałopozycyjny i usunięcie końcowych zer bez kontekstowego normalize().
    def canonical(value):
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    rows = [[canonical(getattr(c, k)) for k in ("open", "high", "low", "close")] for c in candles]
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()

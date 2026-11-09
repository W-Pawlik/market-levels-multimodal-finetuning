"""data_processing / synthetic / domain / generation / models."""
from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass

from .....core.ohlc.model import UTC, Candle


GENERATOR_VERSION = "1.0.0"


SIMULATION_START = datetime(2000, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class SyntheticExample:
    candles: list[Candle]
    metadata: dict

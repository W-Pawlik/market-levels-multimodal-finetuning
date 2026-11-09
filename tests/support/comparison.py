"""Offline comparison fixtures shared by unit and integration tests."""
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from copy import deepcopy
import json
import math
from pathlib import Path
import unittest
import tempfile
from market_levels.core.ohlc.model import Candle, CANDLE_DELTA, UTC
from market_levels.data_processing.synthetic.domain.diagnostics import aggregate_windows, lag1_absolute_correlation
from market_levels.core.numeric.statistics import distribution
from market_levels.data_processing.synthetic.domain.quality import series_statistics
from market_levels.data_processing.windows.domain.selection import select_real_windows
from market_levels.data_processing.io.chronology import load_chronological_split
from .paths import CONFIG, PROJECT

def real_fixture(count=850, start=datetime(2020, 1, 1, tzinfo=UTC)):
    candles = []
    for i in range(count):
        price = Decimal(str(100 * math.exp(0.0001 * i + 0.01 * math.sin(i / 9))))
        candles.append(Candle(start + i * CANDLE_DELTA, price, price * Decimal("1.01"),
                              price * Decimal("0.99"), price, "fixture"))
    return candles

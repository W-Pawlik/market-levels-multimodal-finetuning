"""Offline synthetic fixtures shared by unit and integration tests."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
import math
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
from market_levels.core.ohlc.model import Candle, UTC, CANDLE_DELTA
from market_levels.data_processing.io.candles import write_candles_csv, read_candles_csv
from market_levels.data_processing.synthetic.domain.profiles.v1 import approve_profile, diagnostic_profile, validate_profile
from market_levels.data_processing.synthetic.workflows.calibration import calibrate, calibrate_csv
from market_levels.data_processing.synthetic.io.profiles import load_profile, save_profile
from market_levels.data_processing.synthetic.domain.generation.seeds import example_seed
from market_levels.data_processing.synthetic.domain.generation.v1 import generate_example
from market_levels.core.ohlc.identity import canonical_hash
from market_levels.data_processing.synthetic.domain.quality import series_statistics, validate_synthetic
from market_levels.core.ohlc.validation import validate_values
from market_levels.data_processing.synthetic.domain.generation.regimes import feasible_sequences, plan_regimes
from market_levels.data_processing.synthetic.config.regimes import RegimeSettings
from market_levels.data_processing.synthetic.config.generation import SyntheticSettings
from .paths import CONFIG, PROJECT

def sample_candles():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [Candle(start + i * CANDLE_DELTA, Decimal(c), Decimal(c + 2), Decimal(c - 2),
                   Decimal(c), "test") for i, c in enumerate((100, 102, 101, 104, 103, 106))]

def sample_profile():
    candles = sample_candles()
    return calibrate(candles, "BTCUSDT", allowed_start=candles[0].timestamp,
                     allowed_end=candles[-1].timestamp, source={"description": "test fixture"})

"""Offline charts fixtures shared by unit and integration tests."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from market_levels.core.ohlc.model import Candle, CANDLE_DELTA, UTC
from market_levels.data_processing.io.candles import write_candles_csv
from market_levels.shared.json_io import write_json
from market_levels.data_processing.synthetic.domain.profiles.v1 import profile_hash
from market_levels.data_processing.synthetic.domain.generation.seeds import example_seed
from market_levels.core.ohlc.identity import canonical_hash
from market_levels.shared.integrity import SourceLedger
from market_levels.charts.domain.metrics import fit_thresholds, movement, window_metrics
from market_levels.data_processing.windows.io.training_csv import read_training_csv
from market_levels.charts.domain.diversity import summarize
from market_levels.data_processing.windows.domain.candidates import training_windows
from market_levels.charts.io.audit_sources import discover_batches, read_synthetic
from market_levels.charts.domain.selection import select_pilot, tags
from market_levels.charts.workflows.audit import run_audit
from market_levels.charts.io.rendering import build_figure, render_window
from market_levels.charts.domain.validation import validate_window
from market_levels.shared.paths import require_short_path
from .paths import CONFIG, PROJECT

def fixture(count=120):
    start = datetime(2020,1,1,tzinfo=UTC)
    result = []
    for i in range(count):
        o = Decimal(str(100 + .04*i + math.sin(i/7)))
        c = Decimal(str(100 + .04*(i+1) + math.sin((i+1)/7)))
        result.append(Candle(start+i*CANDLE_DELTA, o, max(o,c)+1, min(o,c)-1, c, "sensitive-origin-id"))
    return result

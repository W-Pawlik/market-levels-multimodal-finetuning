"""Offline calibration fixtures shared by unit and integration tests."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from market_levels.core.ohlc.model import UTC
from market_levels.data_processing.io.candles import write_candles_csv
from market_levels.data_processing.synthetic.workflows.generation import run
from market_levels.data_processing.synthetic.io.profiles import prepare_profiles
from market_levels.data_processing.synthetic.workflows.comparison import build_comparison, save_comparison
from market_levels.data_processing.synthetic.io.profiles import load_profile, save_profile
from market_levels.data_processing.synthetic.workflows.calibration import calibrate_csv
from market_levels.data_processing.synthetic.config.calibration import CalibrationV2Settings
from market_levels.data_processing.synthetic.workflows.calibration import calibrate_v2_csv
from market_levels.data_processing.synthetic.io.batches import load_synthetic_windows
from market_levels.data_processing.synthetic.workflows.summary import build_variant_summary
from market_levels.data_processing.synthetic.reporting.variants import variant_summary_markdown
from market_levels.data_processing.synthetic.config.generation import SyntheticSettings, load_synthetic_settings
from market_levels.data_processing.io.chronology import load_chronological_split
from market_levels.data_processing.synthetic.domain.parameters import VARIANTS
from support.comparison import CONFIG, real_fixture
from .paths import CONFIG, PROJECT

def small_search():
    return CalibrationV2Settings(simulation_seeds=[91,92],selection_seed=93,examples_per_seed=1,rounds=1,
        bridge_gamma=[1,1.8],tail_probability=[0,.05],tail_scale=[3],
        volatility_phi=[.8,.95],volatility_stationary_std=[.2])

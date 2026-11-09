"""Reference outputs captured from the implementation before source relocation."""
import hashlib
import json
from pathlib import Path
import platform
import tempfile
import unittest

from market_levels.data_processing.synthetic.config.generation import SyntheticSettings
from market_levels.data_processing.synthetic.domain.generation.seeds import example_seed
from market_levels.data_processing.synthetic.domain.generation.v1 import generate_example
from market_levels.data_processing.synthetic.domain.generation.v2 import generate_example_v2
from market_levels.data_processing.synthetic.domain.profiles.v1 import diagnostic_profile
from market_levels.data_processing.synthetic.domain.profiles.v2 import diagnostic_profile_v2
from market_levels.data_processing.io.candles import write_candles_csv
from market_levels.core.ohlc.identity import canonical_hash
from market_levels.labeling.domain.algorithm import label_window
from market_levels.charts.domain.metrics import window_metrics
from support.paths import FIXTURES


BASELINE = json.loads((FIXTURES / 'refactor_behavior.json').read_text(encoding='utf-8'))


def object_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def reproduce(identity):
    symbol, master, version, variant = identity.split('-', 3)
    settings = SyntheticSettings(generator_version=version, v2_variant=variant, diagnostic=True)
    profile = diagnostic_profile(symbol) if version == 'v1' else diagnostic_profile_v2(symbol, settings)
    generate = generate_example if version == 'v1' else generate_example_v2
    return generate(symbol, example_seed(int(master), symbol, 0), profile, settings)

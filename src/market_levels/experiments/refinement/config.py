"""experiments / refinement / config."""
from __future__ import annotations


SYMBOLS = ('BTCUSDT', 'ETHUSDT')


VARIANTS = ('full', 'bridge_volatility')


SEEDS = (20261105, 20261115, 20261125)


FRESH_SEEDS = (20261201, 20261211)


FRESH_EXPERIMENT = 'refinement-fresh-seeds-v1'


SELECTION_SEED = 20261106


WINDOWS_MAX_PATH = 260  # Zawiera końcowy NUL; widoczna ścieżka musi mieć <260 jednostek UTF-16.

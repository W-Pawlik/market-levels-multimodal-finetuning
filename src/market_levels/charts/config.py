"""charts / config."""
from __future__ import annotations


SEEDS = (20261105, 20261115, 20261125, 20261201, 20261211)


SYMBOLS = ("BTCUSDT", "ETHUSDT")


KINDS = ("uptrend", "downtrend", "consolidation", "breakout")


RENDERER_VERSION = "1.0.0"


VISUALIZATION = {"width": 1024, "height": 768, "dpi": 100,
                 "x_axis": "window_position_1_based", "y_axis": "linear_original_price",
                 "padding_fraction": 0.05, "body_width": 0.64,
                 "up_color": "#16806a", "down_color": "#c94c4c",
                 "font": "DejaVu Sans", "grid": False, "target_lines": False}

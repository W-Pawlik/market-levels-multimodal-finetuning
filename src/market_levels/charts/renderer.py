"""Deterministyczne świece PNG; pochodzenie pozostaje poza obrazem."""
from __future__ import annotations

import hashlib
from io import BytesIO
import math
from pathlib import Path

from ..core.candles import Candle
from ..data_processing.synthetic.quality import canonical_hash, validate_values

RENDERER_VERSION = "1.0.0"
VISUALIZATION = {"width": 1024, "height": 768, "dpi": 100,
                 "x_axis": "window_position_1_based", "y_axis": "linear_original_price",
                 "padding_fraction": 0.05, "body_width": 0.64,
                 "up_color": "#16806a", "down_color": "#c94c4c",
                 "font": "DejaVu Sans", "grid": False, "target_lines": False}


def require_short_path(path: Path) -> None:
    """Fail before writing, including on Windows without long-path support."""
    if len(str(path.resolve()).encode("utf-16-le")) // 2 >= 260:
        raise ValueError(f"Ścieżka wymaga skrócenia (<260 UTF-16): {path}")


def validate_window(candles: list[Candle]) -> None:
    if len(candles) != 120:
        raise ValueError("Renderer wymaga dokładnie 120 świec")
    if validate_values(candles)["missing_total"]:
        raise ValueError("Okno z luką nie może być renderowane; brak interpolacji")
    if any(not math.isfinite(float(getattr(c, k))) or float(getattr(c, k)) <= 0
           for c in candles for k in ("open", "high", "low", "close")):
        raise ValueError("Ceny poza zakresem reprezentacji renderera")


def build_figure(candles: list[Candle]):
    """Only candles and generic axes can enter the figure; no metadata input."""
    validate_window(candles)
    import matplotlib as mpl
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.collections import LineCollection
    from matplotlib.figure import Figure
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import ScalarFormatter

    with mpl.rc_context(rc=mpl.rcParamsDefault):
        mpl.rcParams.update({"font.family": VISUALIZATION["font"], "font.size": 11})
        fig = Figure(figsize=(10.24, 7.68), dpi=100, facecolor="white")
        FigureCanvasAgg(fig)
        ax = fig.add_axes((0.115, 0.095, 0.85, 0.87))
        segments, colors = [], []
        for x, candle in enumerate(candles, 1):
            o, h, l, c = (float(getattr(candle, k)) for k in ("open", "high", "low", "close"))
            color = VISUALIZATION["up_color" if c >= o else "down_color"]
            segments.append(((x, l), (x, h)))
            colors.append(color)
            ax.add_patch(Rectangle((x - 0.32, min(o, c)), 0.64, abs(c-o),
                                   facecolor=color, edgecolor=color, linewidth=0.8))
        ax.add_collection(LineCollection(segments, colors=colors, linewidths=0.85))
        low, high = min(float(c.low) for c in candles), max(float(c.high) for c in candles)
        padding = max(high-low, high*0.001) * 0.05
        ax.set_ylim(max(0, low-padding), high+padding)
        ax.set_xlim(0, 121)
        ax.set_xticks([1, 20, 40, 60, 80, 100, 120])
        ax.set_xlabel("Candle position")
        ax.set_ylabel("Price (USDT)")
        formatter = ScalarFormatter(useOffset=False)
        formatter.set_scientific(False)
        ax.yaxis.set_major_formatter(formatter)
        ax.grid(False)
        ax.spines[["top", "right"]].set_visible(False)
        return fig


def render_window(candles: list[Candle], path: Path) -> dict:
    """Write PNG exclusively and return provenance-neutral rendering metadata."""
    path = Path(path)
    require_short_path(path)
    if path.exists():
        raise FileExistsError(f"Odmowa nadpisania: {path}")
    fig = build_figure(candles)
    try:
        buffer = BytesIO()
        fig.canvas.print_png(buffer, metadata={"Software": f"market-levels-renderer/{RENDERER_VERSION}"})
        payload = buffer.getvalue()
        with path.open("xb") as stream:
            stream.write(payload)
    finally:
        fig.clear()
    import matplotlib
    return {"renderer_version": RENDERER_VERSION, "matplotlib_version": matplotlib.__version__,
            "visualization": dict(VISUALIZATION), "candle_count": 120,
            "ohlc_sha256": canonical_hash(candles),
            "png_sha256": hashlib.sha256(payload).hexdigest()}

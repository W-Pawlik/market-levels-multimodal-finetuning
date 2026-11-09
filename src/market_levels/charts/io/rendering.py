"""Original deterministic candlestick figure construction and PNG output."""
from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

from ...core.ohlc.model import Candle
from ...core.ohlc.identity import canonical_hash
from ..config import VISUALIZATION, RENDERER_VERSION
from ..domain.validation import validate_window
from ...shared.paths import require_short_path


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

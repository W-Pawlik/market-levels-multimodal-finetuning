"""Publication figures using the original candlestick renderer and level style."""
from __future__ import annotations

from pathlib import Path

from ...charts.io.rendering import build_figure
from ...labeling.io.overlays import draw_levels
from ..domain.models import Levels


def _candle_panel(subfigure, candles, levels: Levels, title: str):
    build_figure(candles, figure=subfigure)
    ax = subfigure.axes[0]
    ax.set_position((0.15, 0.14, 0.81, 0.74))
    ax.set_xlabel("Pozycja świecy (4 h)")
    ax.set_ylabel("Cena (USDT)")
    subfigure.text(0.55, 0.965, title, fontsize=12, ha="center", va="top")
    draw_levels(ax, levels.supports, levels.resistances, minimum_gap=0.065)
    # Keep the chart itself clear; both sides share the same legend location.
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=2,
              fontsize=9, frameon=False, borderaxespad=0)
    return ax


def comparison_figure(candles, reference: Levels, predicted: Levels, *, scale_error=False):
    """Return two vector panels; scale errors use a common linear price axis."""
    import matplotlib as mpl
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FuncFormatter, MaxNLocator

    with mpl.rc_context(rc=mpl.rcParamsDefault):
        mpl.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
        fig = Figure(figsize=(13.6, 5.5), dpi=100, facecolor="white")
        FigureCanvasAgg(fig)
        left, right = fig.subfigures(1, 2, wspace=0)
        first = _candle_panel(left, candles, reference, "a) Poziomy referencyjne")
        if not scale_error:
            second = _candle_panel(right, candles, predicted, "b) Predykcje dostrojonego modelu")
            if first.get_ylim() != second.get_ylim() or first.get_xlim() != second.get_xlim():
                raise ValueError("Niezgodne osie porównywanych wykresów")
        else:
            ax = right.add_axes((0.23, 0.14, 0.72, 0.74))
            right.text(0.59, 0.965, "b) Referencje i predykcje modelu",
                       fontsize=12, ha="center", va="top")
            ticks, labels, values = [], [], []
            y = 11
            for levels, source, marker in ((reference, "Ref.", "o"), (predicted, "Model", "D")):
                for side, color, label in (("supports", "#2357c6", "wsparcie"),
                                           ("resistances", "#a52a82", "opór")):
                    for i, price in enumerate(getattr(levels, side), 1):
                        value = float(price)
                        ticks.append(y)
                        labels.append(f"{source} · {label} {i}")
                        values.append(value)
                        ax.scatter(value, y, color=color, marker=marker, s=35, zorder=3)
                        ax.annotate(f"{price:.2f}", (value, y), xytext=(0, 8),
                                    textcoords="offset points", ha="center", fontsize=9, color=color)
                        y -= 1
                y -= 0.6
            ax.set_yticks(ticks, labels, fontsize=9)
            ax.set_ylim(min(ticks)-0.7, max(ticks)+1)
            ax.set_xlim(0, max(values)*1.13)
            ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:,.0f}".replace(",", " ")))
            ax.set_xlabel("Cena (USDT)")
            ax.spines[["top", "right", "left"]].set_visible(False)
            ax.tick_params(axis="y", length=0)
            ax.grid(axis="x", color="#e4e4e4", linewidth=0.6)
            ax.set_axisbelow(True)
            handles = [Line2D([], [], color="#444444", linestyle="", marker=m, label=l)
                       for m, l in (("o", "Referencje"), ("D", "Predykcje"))]
            ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.01),
                      ncol=2, fontsize=9, frameon=False, borderaxespad=0)
        return fig


def save_figure(fig, stem: Path, *, dpi: int = 300) -> list[Path]:
    """Write PNG and true vector SVG, refusing to overwrite any existing file."""
    if dpi < 200:
        raise ValueError("Rysunki do pracy wymagają co najmniej 200 DPI")
    paths = [Path(str(stem)+suffix) for suffix in (".png", ".svg")]
    if any(p.exists() for p in paths):
        raise FileExistsError(f"Odmowa nadpisania rysunku: {stem}")
    stem.parent.mkdir(parents=True, exist_ok=True)
    try:
        for path in paths:
            with path.open("xb") as stream:
                fig.savefig(stream, format=path.suffix[1:], dpi=dpi, facecolor="white")
    finally:
        fig.clear()
    return paths

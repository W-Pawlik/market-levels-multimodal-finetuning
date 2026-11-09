"""labeling / io / overlays."""
from __future__ import annotations

from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from ...charts.io.rendering import build_figure
from ...shared.paths import require_short_path
from ..domain.models import LabelResult, VERSION


def render_levels(candles, result: LabelResult, path: Path) -> None:
    """Bazowe osie pozostają identyczne; etykiety mają rozdzielone pozycje."""
    require_short_path(path)
    fig = build_figure(candles)
    try:
        ax = fig.axes[0]
        low, high = ax.get_ylim()
        entries = []
        for groups, color, style, label in ((result.supports, "#2357c6", "--", "Wsparcie"),
                                           (result.resistances, "#a52a82", ":", "Opór")):
            for i, group in enumerate(groups):
                value = float(group.level)
                ax.axhline(value, color=color, linestyle=style, linewidth=1.4,
                           label=label if i == 0 else None)
                price = group.level.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                entries.append((value, color, f"{label}: {price:.2f}"))
        # Pozycje napisów w ułamku osi, odstęp co najmniej 0.045 wysokości.
        entries.sort()
        positions = []
        for value, _, _ in entries:
            positions.append(max((value-low)/(high-low), positions[-1]+0.045 if positions else 0.025))
        if positions:
            positions[-1] = min(positions[-1], 0.96)
            for i in range(len(positions)-2, -1, -1):
                positions[i] = min(positions[i], positions[i+1]-0.045)
        for (value, color, label), position in zip(entries, positions):
            ax.annotate(label, xy=(119, value), xycoords="data", xytext=(0.985, position),
                        textcoords="axes fraction", ha="right", va="center", fontsize=9,
                        color=color, bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": color, "pad": 2},
                        arrowprops={"arrowstyle": "-", "color": color, "linewidth": 0.6})
        if entries:
            ax.legend(loc="upper left", fontsize=9)
        ax.set_ylim(low, high)
        buffer = BytesIO()
        fig.canvas.print_png(buffer, metadata={"Software": f"market-levels-labeling/{VERSION}",
                                              "Purpose": "diagnostic_only_not_vlm_input"})
        with path.open("xb") as stream:
            stream.write(buffer.getvalue())
    finally:
        fig.clear()

"""Deterministyczne etykietowanie S/R wyłącznie z bieżącego okna OHLC."""
from .domain.models import LabelResult
from .domain.algorithm import label_window

__all__ = ["LabelResult", "label_window"]

"""Deterministyczne etykietowanie S/R wyłącznie z bieżącego okna OHLC."""
from .algorithm import LabelResult, label_window

__all__ = ["LabelResult", "label_window"]

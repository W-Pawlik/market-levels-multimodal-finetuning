"""Offline labeling fixtures shared by unit and integration tests."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D, localcontext
import json
import unittest
from market_levels.core.ohlc.model import Candle
from market_levels.labeling.domain.models import Extremum as E, Group
from market_levels.labeling.domain.algorithm import find_extrema, independent_reactions, label_window, price_groups, rank_groups, select_groups
from market_levels.core.numeric.atr import true_ranges, wilder_atr
from .paths import CONFIG, PROJECT

def fixture():
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [Candle(start+timedelta(hours=4*i), D(90), D(99), D(80), D(90), "manual") for i in range(120)]

def peaks(values):
    candles = fixture()
    for i, value in values:
        candles[i] = replace(candles[i], high=D(value))
    return candles

def group(identifier=0, level="100", indices=(10, 20), side="resistances"):
    members = tuple(E(i, D(level), "H") for i in indices)
    return Group(identifier, D(level), members, members, (), side, "")

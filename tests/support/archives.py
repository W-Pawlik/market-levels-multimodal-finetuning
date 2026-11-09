"""Offline archives fixtures shared by unit and integration tests."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from market_levels.core.ohlc.model import DataValidationError
from market_levels.data_processing.real.workflows.download import run
from market_levels.data_processing.real.binance_vision import archives, client, parsing
from .paths import CONFIG, PROJECT

def make_archive(root):
    path = root / "raw/BTCUSDT/4h/monthly/BTCUSDT-4h-2024-01.zip"
    path.parent.mkdir(parents=True)
    with ZipFile(path, "w") as bundle:
        bundle.writestr(path.stem + ".csv",
                        "1704081600000,100,112,91,110,1,0,2,3,4,5,0\n"
                        "1704110400000,100,112,91,110,1,0,2,3,4,5,0\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(path.name + ".CHECKSUM").write_text(digest + "  " + path.name + "\n")
    return path, digest

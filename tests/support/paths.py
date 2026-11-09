"""Stable paths independent of test nesting."""
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
CONFIG = PROJECT / "configs/experiment.json"
FIXTURES = PROJECT / "tests/fixtures"

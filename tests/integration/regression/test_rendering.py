"""PNG bytes compared with the original renderer, including diagnostic overlays."""
import hashlib
import importlib.metadata
from pathlib import Path
import platform
import tempfile
import unittest

from support.behavior import BASELINE, reproduce
from market_levels.charts.io.rendering import render_window
from market_levels.labeling.domain.algorithm import label_window
from market_levels.labeling.io.overlays import render_levels


class RenderingBaselineTests(unittest.TestCase):
    def test_png_and_overlay_match_original_28_cases(self):
        if platform.python_version() != BASELINE['python']:
            self.skipTest('Reference requires Python ' + BASELINE['python'])
        try:
            version = importlib.metadata.version('matplotlib')
        except importlib.metadata.PackageNotFoundError:
            self.skipTest('Matplotlib is not installed')
        if version != BASELINE['matplotlib']:
            self.skipTest('Reference requires Matplotlib ' + BASELINE['matplotlib'])
        with tempfile.TemporaryDirectory() as temporary:
            for i, (identity, expected) in enumerate(BASELINE['examples'].items()):
                with self.subTest(identity=identity):
                    example = reproduce(identity)
                    png = Path(temporary) / f'{i}.png'
                    overlay = Path(temporary) / f'{i}-overlay.png'
                    render_window(example.candles, png)
                    render_levels(example.candles, label_window(example.candles), overlay)
                    self.assertEqual(hashlib.sha256(png.read_bytes()).hexdigest(), expected['png'])
                    self.assertEqual(hashlib.sha256(overlay.read_bytes()).hexdigest(), expected['overlay'])

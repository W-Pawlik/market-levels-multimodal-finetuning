"""Figure contracts: identical candles, honest scale errors and readable labels."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from market_levels.charts.io.rendering import build_figure
from market_levels.data_processing.io.candles import read_candles_csv
from market_levels.evaluation.domain.models import Levels
from market_levels.evaluation.reporting.figures import comparison_figure, save_figure
from support.paths import FIXTURES


class ComparisonFigureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import matplotlib
        except ImportError:
            raise unittest.SkipTest("Matplotlib is not installed")
        cls.candles = read_candles_csv(
            FIXTURES/'evaluation_v1/dataset/ohlc/fixture_wrong_side.csv', source="fixture")

    def levels(self):
        # Close levels exercise annotation spacing independently of the renderer scale.
        base = self.candles[-1].close
        return Levels((base, base+Decimal('0.01')), (base+Decimal('0.02'),))

    def assert_readable(self, fig):
        from matplotlib.text import Annotation
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        for ax in fig.axes:
            labels = [t.get_bbox_patch().get_window_extent(renderer) for t in ax.texts
                      if isinstance(t, Annotation) and t.get_bbox_patch() is not None]
            for i, first in enumerate(labels):
                for second in labels[i+1:]:
                    self.assertFalse(first.overlaps(second), "Price labels overlap")
        for sub in fig.subfigs:
            for title in sub.texts:
                for ax in sub.axes:
                    if ax.get_legend() is not None:
                        self.assertFalse(title.get_window_extent(renderer).overlaps(
                            ax.get_legend().get_window_extent(renderer)), "Title overlaps legend")

    def test_two_panels_preserve_original_candles_axes_and_label_spacing(self):
        levels = self.levels()
        original = build_figure(self.candles)
        fig = comparison_figure(self.candles, levels, levels)
        try:
            for ax in fig.axes:
                self.assertEqual(ax.get_ylim(), original.axes[0].get_ylim())
                self.assertEqual(ax.get_xlim(), original.axes[0].get_xlim())
                self.assertEqual([p.get_bbox().bounds for p in ax.patches],
                                 [p.get_bbox().bounds for p in original.axes[0].patches])
            self.assert_readable(fig)
        finally:
            original.clear()
            fig.clear()

    def test_scale_error_points_remain_unmodified_and_candles_keep_original_range(self):
        levels = self.levels()
        predicted = Levels(tuple(p/10 for p in levels.supports), tuple(p/10 for p in levels.resistances))
        original = build_figure(self.candles)
        fig = comparison_figure(self.candles, levels, predicted, scale_error=True)
        try:
            self.assertEqual(fig.axes[0].get_ylim(), original.axes[0].get_ylim())
            values = [float(c.get_offsets()[0][0]) for c in fig.axes[1].collections]
            self.assertEqual(values, [float(v) for group in (levels, predicted)
                                     for side in (group.supports, group.resistances) for v in side])
            self.assertEqual(fig.axes[1].get_xscale(), "linear")
            self.assertEqual(fig.axes[1].get_xlim()[0], 0)
            self.assert_readable(fig)
        finally:
            original.clear()
            fig.clear()

    def test_png_svg_export_and_no_overwrite(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            stem = Path(tmp)/'figure'
            fig = comparison_figure(self.candles, self.levels(), self.levels())
            png, svg = save_figure(fig, stem, dpi=200)
            with Image.open(png) as image:
                self.assertGreaterEqual(image.info['dpi'][0], 199.99)
                image.verify()
            root = ET.parse(svg).getroot()
            self.assertTrue(root.tag.endswith('svg'))
            self.assertFalse(any(e.tag.endswith('image') for e in root.iter()), "SVG must remain vector")
            fig = comparison_figure(self.candles, self.levels(), self.levels())
            try:
                with self.assertRaises(FileExistsError):
                    save_figure(fig, stem)
            finally:
                fig.clear()

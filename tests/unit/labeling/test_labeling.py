"""Ręcznie skonstruowane przypadki zatwierdzonego algorytmu."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D, localcontext
import json
import unittest

from market_levels.core.ohlc.model import Candle
from market_levels.labeling.domain.models import Extremum as E, Group
from market_levels.labeling.domain.algorithm import find_extrema, independent_reactions, label_window, price_groups, rank_groups, select_groups
from market_levels.core.numeric.atr import true_ranges, wilder_atr

from support.labeling import fixture, peaks, group








class LabelingTests(unittest.TestCase):
    def test_tr_initial_and_previous_close_gaps(self):
        candles = fixture()[:3]
        candles[0] = replace(candles[0], high=D(100), low=D(80), close=D(100))
        candles[1] = replace(candles[1], open=D(70), high=D(75), low=D(65), close=D(70))
        candles[2] = replace(candles[2], open=D(90), high=D(100), low=D(80))
        self.assertEqual(true_ranges(candles), (D(20), D(35), D(30)))

    def test_wilder_seed_and_recursion(self):
        result = wilder_atr(tuple([D(2)]*14+[D(16), D(3)]))
        self.assertEqual(result, (D(2), D(3), D(3)))
        self.assertEqual(wilder_atr(tuple(map(D, range(1, 15)))), (D("7.5"),))

    def test_atr_short(self):
        with self.assertRaises(ValueError):
            wilder_atr((D(1),))

    def test_strict_extrema_and_excluded_edges(self):
        candles = peaks([(0, 200), (2, 200), (3, 110), (10, 105), (116, 106), (117, 200), (119, 200)])
        candles[40] = replace(candles[40], low=D(70))
        self.assertEqual(find_extrema(candles), (E(10, D(105), "H"), E(40, D(70), "L")))

    def test_equal_highs_and_lows_are_not_extrema(self):
        candles = peaks([(10, 105), (12, 105)])
        for i in (40, 43):
            candles[i] = replace(candles[i], low=D(70))
        self.assertEqual(find_extrema(candles), ())

    def test_inside_edge_indices_3_and_116(self):
        self.assertEqual([e.index for e in find_extrema(peaks([(3, 105), (116, 105)]))], [3, 116])

    def test_full_span_inclusive_no_chaining(self):
        extrema = tuple(E(i*10, D(p), "H") for i, p in enumerate((100, 102, 104, 105)))
        self.assertEqual([[e.price for e in g] for g in price_groups(extrema, D(4))],
                         [[D(100), D(102), D(104)], [D(105)]])
        self.assertEqual(len(price_groups(extrema, D("3.999"))), 2)

    def test_mixed_group(self):
        members = (E(10, D(100), "H"), E(20, D(101), "L"))
        self.assertEqual(price_groups(members, D(1)), [members])
        self.assertEqual(len(independent_reactions(members, D("100.5"))[0]), 2)

    def test_median_before_filter_even(self):
        result = label_window(peaks([(10, 100), (14, 103), (18, 101), (40, 104)]))
        self.assertEqual(result.groups[0].level, D(102))
        self.assertEqual([e.index for e in result.groups[0].reactions], [14, 40])

    def test_median_odd(self):
        result = label_window(peaks([(10, 100), (20, 101), (30, 104)]))
        self.assertEqual(result.groups[0].level, D(101))

    def test_extreme_first_A(self):
        members = (E(10, D(100), "H"), E(14, D(103), "H"), E(18, D(101), "H"))
        kept, suppressed = independent_reactions(members, D(101))
        self.assertEqual([e.index for e in kept], [14])
        self.assertEqual(len(suppressed), 2)

    def test_extreme_first_B(self):
        members = (E(10, D(103), "H"), E(14, D(100), "H"), E(18, D(101), "H"))
        self.assertEqual([e.index for e in independent_reactions(members, D(101))[0]], [10, 18])

    def test_integrated_A_B_valid_120_candles(self):
        a = label_window(peaks([(10, 100), (14, 103), (18, 101)]))
        b = label_window(peaks([(10, 103), (14, 100), (18, 101)]))
        self.assertEqual(a.target_json().strip(), '{"supports": [], "resistances": []}')
        self.assertEqual(b.resistances[0].level, D(101))
        self.assertEqual(len(a.groups[0].reactions), 1)
        self.assertEqual(len(b.groups[0].reactions), 2)

    def test_distance_4_vs_5(self):
        for distance, expected in ((4, 1), (5, 2)):
            members = (E(10, D(100), "H"), E(10+distance, D(101), "H"))
            self.assertEqual(len(independent_reactions(members, D(100))[0]), expected)

    def test_minima_lowest_first(self):
        members = (E(10, D(99), "L"), E(14, D(97), "L"), E(18, D(98), "L"))
        self.assertEqual([e.index for e in independent_reactions(members, D(98))[0]], [14])

    def test_mixed_signed_strength_not_absolute_distance(self):
        members = (E(10, D(96), "H"), E(14, D(101), "H"), E(18, D(103), "L"))
        self.assertEqual([e.index for e in independent_reactions(members, D(101))[0]], [14])

    def test_reaction_ties_later_then_H(self):
        members = (E(10, D(101), "H"), E(14, D(99), "L"))
        self.assertEqual(independent_reactions(members, D(100))[0], (members[1],))
        same = (E(14, D(101), "H"), E(14, D(99), "L"))
        self.assertEqual(independent_reactions(same[::-1], D(100))[0], (same[0],))

    def test_close_boundary_inclusive(self):
        # Stały TR=20: delta=10, a dwa szczyty H=100 leżą dokładnie na granicy.
        candles = fixture()
        candles = [replace(c, high=D(100), low=D(80)) for c in candles]
        for i in (10, 20):
            candles[i] = replace(candles[i], high=D(101), low=D(81))
        for close, expected in (("91", 0), ("91.0001", 0), ("90.9999", 1)):
            candidate = candles.copy()
            candidate[-1] = replace(candidate[-1], open=D(close), close=D(close), high=D(close)+10, low=D(close)-10)
            result = label_window(candidate)
            self.assertEqual(len(result.supports)+len(result.resistances), expected)

    def test_support_close_boundary_inclusive(self):
        candles = [replace(c, high=D(100), low=D(80)) for c in fixture()]
        for i in (10, 20):
            candles[i] = replace(candles[i], high=D(99), low=D(79))
        for close, expected in (("89", 0), ("88.9999", 0), ("89.0001", 1)):
            candidate = candles.copy()
            candidate[-1] = replace(candidate[-1], open=D(close), close=D(close), high=D(close)+10, low=D(close)-10)
            result = label_window(candidate)
            self.assertEqual(len(result.supports), expected)

    def test_ranking_priorities_and_limit(self):
        groups = [group(0, "105", (10, 20, 30)), group(1, "101", (10, 40)),
                  group(2, "102", (10, 50)), group(3, "103", (10, 50)), group(4, "102", (10, 50))]
        self.assertEqual([g.id for g in rank_groups(groups, D(90))], [0, 2, 4, 3, 1])
        selected, collisions = select_groups(groups, D(90))
        self.assertEqual([g.id for g in selected['resistances']], [0, 2, 3])
        self.assertEqual(collisions[0]['discarded_group'], 4)

    def test_rounding_collisions_both_sides(self):
        groups = [group(0, "100.001", side="supports"), group(1, "100.004"), group(2, "101.005")]
        selected, collisions = select_groups(groups, D("100.002"))
        self.assertEqual(len(collisions), 1)
        self.assertEqual(len(selected['supports'])+len(selected['resistances']), 2)

    def test_json_half_up_numbers_and_diagnostic_precision(self):
        result = label_window(peaks([(10, "101.005"), (20, "101.005")]))
        self.assertIn('101.01', result.target_json())
        self.assertIsInstance(json.loads(result.target_json())['resistances'][0], float)
        self.assertEqual(result.diagnostics()['resistances'][0]['level'], '101.005')
        self.assertEqual(set(json.loads(result.target_json())), {'supports', 'resistances'})

    def test_flat_zero_atr_empty(self):
        candles = [replace(c, open=D(90), high=D(90), low=D(90), close=D(90)) for c in fixture()]
        result = label_window(candles)
        self.assertEqual(result.delta, 0)
        self.assertEqual(result.extrema, ())
        self.assertEqual(json.loads(result.target_json()), {'supports': [], 'resistances': []})

    def test_determinism_context_and_metadata_independence(self):
        candles = peaks([(10, 101), (20, 102)])
        result = label_window(candles)
        with localcontext() as context:
            context.prec = 6
            context.rounding = 'ROUND_DOWN'
            self.assertEqual(label_window(candles), result)
        self.assertEqual(label_window([replace(c, source_archive='other-generator-secret') for c in candles]), result)

    def test_invalid_count_ohlc_gap_order_and_type(self):
        original = fixture()
        invalid = [original[:119], original+[original[-1]],
                   [replace(c, high=D(1)) if i == 10 else c for i, c in enumerate(original)],
                   [replace(c, timestamp=c.timestamp+timedelta(hours=4)) if i >= 10 else c for i, c in enumerate(original)],
                   original[::-1], [replace(c, close=float(c.close)) for c in original],
                   [replace(c, low=D('NaN')) for c in original]]
        for candles in invalid:
            with self.subTest(case=invalid.index(candles)):
                with self.assertRaises(ValueError):
                    label_window(candles)


if __name__ == '__main__':
    unittest.main()

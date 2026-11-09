"""Hand-computed parsing/matching/count/error conventions; no VLM results."""
from decimal import Decimal, localcontext
import unittest

from market_levels.core.ohlc.model import Candle, UTC, CANDLE_DELTA
from datetime import datetime
from market_levels.evaluation.protocol import dumps, loads
from market_levels.evaluation.domain.models import Levels, Reference
from market_levels.evaluation.domain.responses import parse_response
from market_levels.evaluation.domain.matching import match_levels
from market_levels.evaluation.domain.scoring import score_example, final_atr
from market_levels.evaluation.domain.metrics import aggregate

D = Decimal


def ref(supports=(), resistances=(), atr='3', identity='fixture', symbol='BTCUSDT'):
    return Reference(identity, symbol, 'validation', Levels(tuple(map(D, supports)), tuple(map(D, resistances))), D(atr))


def score(reference, response):
    return score_example(reference, parse_response(response))


class ResponseValidationTests(unittest.TestCase):
    def test_valid_numbers_preserve_decimal_precision_and_raw_text(self):
        text = ' \n{"supports":[60123.40, 1e2],"resistances":[]} \t'
        response = parse_response(text)
        self.assertIsNone(response.error)
        self.assertEqual(response.raw, text)
        self.assertEqual(response.levels.supports, (D('60123.40'), D('100')))
        self.assertTrue(all(isinstance(x, D) for x in response.levels.supports))

    def test_missing_and_extra_keys(self):
        for text in ('{"supports":[]}', '{"supports":[],"resistances":[],"note":1}'):
            self.assertEqual(parse_response(text).error, 'keys')

    def test_wrong_structure_and_types(self):
        for text in ('[]', 'null', '42', '"{}"', '{"supports":{},"resistances":[]}',
                     '{"supports":null,"resistances":[]}', '{"supports":[],"resistances":false}'):
            self.assertIsNone(parse_response(text).levels)

    def test_price_strings_rejected(self):
        self.assertEqual(parse_response('{"supports":["100"],"resistances":[]}').error, 'invalid_price')

    def test_more_than_three_prices_rejected_even_if_repeated(self):
        self.assertEqual(parse_response('{"supports":[1,1,1,1],"resistances":[]}').error, 'too_many_prices')

    def test_nonfinite_null_boolean_zero_and_negative_prices_rejected(self):
        for token in ('NaN','Infinity','-Infinity','null','true','false','0','-1','-0.0'):
            with self.subTest(token=token):
                self.assertIsNone(parse_response('{"supports":['+token+'],"resistances":[]}').levels)

    def test_duplicate_keys_including_escaped_spelling(self):
        for text in ('{"supports":[],"supports":[],"resistances":[]}',
                     '{"supports":[],"\\u0073upports":[],"resistances":[]}'):
            self.assertEqual(parse_response(text).error, 'duplicate_key')

    def test_json_is_never_extracted_or_repaired(self):
        for text in ('```json\n{"supports":[],"resistances":[]}\n```',
                     'Answer: {"supports":[],"resistances":[]}',
                     '{"supports":[],"resistances":[]} thanks',
                     '{"supports":[],"resistances":[],}', '', '   ',
                     '{"supports":[],/*comment*/"resistances":[]}'):
            response = parse_response(text)
            self.assertIsNone(response.levels)
            self.assertEqual(response.raw, text)

    def test_exact_numeric_serialization_does_not_use_float(self):
        value = D('12345678901234567890.12345678901234567890')
        text = dumps({'price': value, 'undefined': None})
        self.assertIn(str(value), text)
        self.assertEqual(loads(text)['price'], value)


class MatchingTests(unittest.TestCase):
    def match(self, predicted, references, tolerance='1.5', atr='3'):
        return match_levels(tuple(map(D,predicted)), tuple(map(D,references)), D(tolerance), D(atr))

    def test_required_greedy_counterexample_has_two_matches(self):
        result = self.match(['101','99'], ['100','102'])
        self.assertEqual((result['tp'],result['fp'],result['fn']), (2,0,0))
        self.assertEqual([(p.predicted_index,p.reference_index) for p in result['matches']], [(0,1),(1,0)])

    def test_one_prediction_cannot_match_two_references(self):
        result = self.match(['101'], ['100','102'])
        self.assertEqual((result['tp'],result['fp'],result['fn']), (1,0,1))
        self.assertEqual(result['matches'][0].reference_index, 0)

    def test_maximum_cardinality_precedes_minimum_cost(self):
        result = self.match(['100','99'], ['100','101'], tolerance='1')
        # Greedy exact pair would have zero error but only one match; optimum has two.
        self.assertEqual(result['tp'], 2)
        self.assertEqual(sum(p.absolute_error for p in result['matches']), D(2))

    def test_minimum_distance_precedes_input_order(self):
        result = self.match(['102.1'], ['100','102'], tolerance='3')
        self.assertEqual(result['matches'][0].reference_index, 1)
        self.assertEqual(result['matches'][0].absolute_error, D('.1'))

    def test_full_tie_uses_original_indices_deterministically(self):
        for _ in range(3):
            result = self.match(['101'], ['102','100'])
            self.assertEqual(result['matches'][0].reference_index, 0)

    def test_exact_boundary_and_just_outside(self):
        self.assertEqual(self.match(['101.5'], ['100'])['tp'], 1)
        self.assertEqual(self.match(['101.500000000000000000000000000000000000000000000000001'], ['100'])['tp'], 0)

    def test_repeated_numeric_price_is_fp_and_only_first_is_eligible(self):
        result = self.match(['100','100.00','102'], ['100','102'])
        self.assertEqual((result['tp'],result['fp'],result['fn']), (2,1,0))
        self.assertEqual(result['duplicate_indices'], [1])
        self.assertEqual([p.predicted_index for p in result['matches']], [0,2])

    def test_all_combinations_of_empty_sides(self):
        for pred, actual, expected in (([],[],(0,0,0)), (['100'],[],(0,1,0)), ([],['100'],(0,0,1))):
            r = self.match(pred,actual)
            self.assertEqual((r['tp'],r['fp'],r['fn']),expected)

    def test_zero_atr_allows_only_exact_match_and_no_normalized_error(self):
        result = self.match(['100','100.01'],['100'],tolerance='0',atr='0')
        self.assertEqual((result['tp'],result['fp']), (1,1))
        self.assertEqual(result['matches'][0].absolute_error,0)
        self.assertIsNone(result['matches'][0].atr_error)
        self.assertEqual(result['matches'][0].atr_error_reason,'zero_atr')


class MetricTests(unittest.TestCase):
    def test_support_as_resistance_is_fp_and_fn(self):
        r = score(ref(['100']),'{"supports":[],"resistances":[100]}')['scores']['0.5']
        self.assertEqual((r['tp'],r['fp'],r['fn'],r['example_f1']), (0,1,1,0))

    def test_three_atr_tolerances(self):
        r = score(ref(['100'],atr='4'),'{"supports":[101.5],"resistances":[]}')
        self.assertEqual([r['scores'][k]['tp'] for k in ('0.25','0.5','1.0')], [0,1,1])

    def test_valid_empty_and_invalid_empty_example_conventions(self):
        rows = [score(ref(identity='a'),'{"supports":[],"resistances":[]}'), score(ref(identity='b'),'{bad')]
        self.assertEqual([r['scores']['0.5']['example_f1'] for r in rows], [1,0])
        overall = aggregate(rows)['tolerances']['0.5']['overall']
        self.assertIsNone(overall['micro_f1'])
        self.assertEqual(overall['mean_example_f1'],D('.5'))
        self.assertEqual(overall['valid_json_percent'],50)
        self.assertEqual(overall['correct_empty_examples'],1)

    def test_invalid_response_loses_all_reference_levels_without_fictitious_fp(self):
        r = score(ref(['100','101'],['110']),'{"supports":[100],"resistances":"bad"}')['scores']['0.5']
        self.assertEqual((r['tp'],r['fp'],r['fn'],r['example_f1']), (0,0,3,0))

    def test_micro_is_not_mean_example_f1(self):
        rows = [score(ref(['100'],identity='a'),'{"supports":[100],"resistances":[]}'),
                score(ref(['100','102','104'],identity='b'),'{"supports":[],"resistances":[]}')]
        s = aggregate(rows)['tolerances']['0.5']['overall']
        self.assertEqual((s['tp'],s['fp'],s['fn']),(1,0,3))
        self.assertEqual(s['micro_f1'],D('.4'))
        self.assertEqual(s['mean_example_f1'],D('.5'))

    def test_price_errors_known_mae_by_symbol_and_normalized(self):
        rows = [score(ref(['100'],atr='4'),'{"supports":[101],"resistances":[]}'),
                score(ref(['200'],atr='4',identity='b'),'{"supports":[202],"resistances":[]}')]
        s = aggregate(rows)['tolerances']['0.5']
        self.assertEqual(s['by_symbol']['BTCUSDT']['price_error']['mae_usdt'],D('1.5'))
        self.assertEqual(s['overall']['price_error']['mae_atr'],D('.375'))
        self.assertEqual(s['overall']['price_error']['matched_pairs'],2)
        self.assertNotIn('mae_usdt',s['overall']['price_error'])

    def test_no_matches_gives_undefined_mae_not_zero(self):
        s = aggregate([score(ref(['100']),'{"supports":[10],"resistances":[]}')])['tolerances']['0.5']
        self.assertIsNone(s['by_symbol']['BTCUSDT']['price_error']['mae_usdt'])
        self.assertIsNone(s['overall']['price_error']['mae_atr'])
        self.assertEqual(s['overall']['price_error']['matched_pairs'],0)

    def test_zero_atr_matched_price_has_zero_usdt_and_undefined_normalization(self):
        s = aggregate([score(ref(['100'],atr='0'),'{"supports":[100],"resistances":[]}')])['tolerances']['0.5']
        self.assertEqual(s['by_symbol']['BTCUSDT']['price_error']['mae_usdt'],0)
        self.assertIsNone(s['overall']['price_error']['mae_atr'])
        self.assertEqual(s['overall']['price_error']['zero_atr_excluded_pairs'],1)

    def test_global_decimal_context_does_not_change_scoring(self):
        r = ref(['100'])
        expected = dumps(aggregate([score(r,'{"supports":[101],"resistances":[]}')]))
        with localcontext() as context:
            context.prec = 4
            self.assertEqual(dumps(aggregate([score(r,'{"supports":[101],"resistances":[]}')])),expected)

    def test_atr_reuses_wilder_initialization_recurrence_and_zero_case(self):
        start = datetime(2024,1,1,tzinfo=UTC)
        for delta, expected in ((D('1.5'),D(3)),(D(0),D(0))):
            cs = [Candle(start+i*CANDLE_DELTA,D(100),D(100)+delta,D(100)-delta,D(100),'fixture') for i in range(120)]
            self.assertEqual(final_atr(cs),expected)
        # First 119 true ranges=2; last=4 => final ATR=(13*2+4)/14=15/7.
        cs = [Candle(start+i*CANDLE_DELTA,D(100),D(101),D(99),D(100),'fixture') for i in range(119)]
        cs.append(Candle(start+119*CANDLE_DELTA,D(100),D(102),D(98),D(100),'fixture'))
        self.assertTrue(abs(final_atr(cs)-D('2.142857142857142857142857143')) < D('1e-26'))

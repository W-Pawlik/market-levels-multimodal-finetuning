"""Post-build descriptive similarity of centered log-Close paths, same symbol."""
import argparse
from itertools import combinations
import json
import math
from pathlib import Path

from market_levels.datasets.packaging import verify_files
from market_levels.data_processing.storage import read_candles_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = verify_files(args.dataset)
    normalized = []
    for entry in manifest['entries']:
        candles = read_candles_csv(args.dataset/entry['ohlc'], source='similarity-audit')
        values = [math.log(float(c.close)) for c in candles]
        mean = math.fsum(values)/len(values)
        centered = [v-mean for v in values]
        norm = math.sqrt(math.fsum(v*v for v in centered))
        normalized.append((entry, [v/norm for v in centered] if norm else None))
    pairs, count = [], 0
    for (a, x), (b, y) in combinations(normalized, 2):
        if a['symbol'] != b['symbol'] or x is None or y is None:
            continue
        count += 1
        correlation = math.fsum(p*q for p, q in zip(x, y))
        if correlation >= .995:
            pairs.append({'a': {k:a[k] for k in ('id','symbol','split','source')},
                          'b': {k:b[k] for k in ('id','symbol','split','source')},
                          'log_close_correlation': correlation})
    report = {'threshold': .995, 'compared_same_symbol_pairs': count,
              'similar_pairs': pairs, 'similar_pair_count': len(pairs),
              'method': 'Pearson correlation of 120 log-Close values, centered and normalized independently, same symbol. Ignores wicks and absolute price scale.',
              'purpose': 'audit_only; correlation is not duplication or market independence; no regeneration or reselection'}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(f'{count} par; podobnych przy r>=0.995: {len(pairs)}')


if __name__ == '__main__':
    main()

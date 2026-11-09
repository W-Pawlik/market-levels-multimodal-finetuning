"""Descriptive dataset audits without selection or parameter feedback."""
from __future__ import annotations

from collections import Counter
from itertools import combinations

from ...core.numeric.statistics import distribution


def audit_dataset(metadata: list[dict]) -> dict:
    groups = {}
    for name in ("train/real", "train/synthetic", "validation/real", "test/real"):
        split, source = name.split('/')
        records = [r for r in metadata if r['split'] == split and r['source'] == source]
        group = summarize(records)
        group['symbols'] = {s: summarize([r for r in records if r['symbol'] == s])
                            for s in ('BTCUSDT', 'ETHUSDT')}
        group['full_support_limit_share'] = sum(r['support_count'] == 3 for r in records)/len(records) if records else None
        group['full_resistance_limit_share'] = sum(r['resistance_count'] == 3 for r in records)/len(records) if records else None
        groups[name] = group
    close_levels = []
    regimes, transitions, shares = Counter(), Counter(), Counter()
    for r in metadata:
        levels = [float(v) for side in r['answer'].values() for v in side]
        atr = float(r['label_audit']['atr'])
        pairs = [(a, b) for a, b in combinations(levels, 2) if abs(a-b) <= atr/2]
        if pairs:
            close_levels.append({'id': r['id'], 'pairs': pairs, 'threshold': atr/2})
        if r['source'] == 'synthetic':
            declared = r['generator_metadata']['regimes']
            regimes.update(x['kind'] for x in declared)
            transitions.update(a['kind']+'->'+b['kind'] for a, b in zip(declared, declared[1:]))
            for x in declared:
                shares[x['kind']] += x['length']
    return {'count': len(metadata), 'by_split': dict(Counter(r['split'] for r in metadata)),
            'by_symbol': dict(Counter(r['symbol'] for r in metadata)),
            'by_source': dict(Counter(r['source'] for r in metadata)), 'groups': groups,
            'close_level_examples': close_levels,
            'close_level_definition': 'Odległość między dowolnymi dwiema cenami odpowiedzi <= końcowy Wilder ATR(14)/2. Wyłącznie opis.',
            'synthetic_regimes': dict(regimes), 'synthetic_transitions': dict(transitions),
            'synthetic_regime_candles': dict(shares),
            'synthetic_phase_counts': dict(Counter(str(len(r['generator_metadata']['regimes'])) for r in metadata if r['source'] == 'synthetic')),
            'exact_ohlc_duplicates': len(metadata)-len({r['ohlc_sha256'] for r in metadata}),
            'purpose': 'audit_only; validation/test never feed generator or training selection',
            'dependence': 'Train overlaps intentionally; BTC/ETH from the same dates are correlated market observations.'}


def summarize(records: list[dict]) -> dict:
    """Audit only; no split-dependent thresholds or selection feedback."""
    signatures = Counter((r["symbol"], r["metrics"]["observed_motion"],
                          round(r["metrics"]["log_return_std"], 3),
                          r["support_count"], r["resistance_count"]) for r in records)
    n = len(records)
    return {"count": n,
            "by_symbol_source": dict(Counter(r["symbol"]+"/"+r["source"] for r in records)),
            "real_years_by_start": dict(Counter(r["start_utc"][:4] for r in records if r["source"] == "real")),
            "direction": dict(Counter(r["metrics"]["observed_motion"] for r in records)),
            "net_change_direction": dict(Counter("up" if r["metrics"]["price_change"] > 0 else "down" if r["metrics"]["price_change"] < 0 else "flat" for r in records)),
            "volatility": distribution([r["metrics"]["log_return_std"] for r in records]) if n else None,
            "price_change": distribution([r["metrics"]["price_change"] for r in records]) if n else None,
            "supports": dict(Counter(str(r["support_count"]) for r in records)),
            "resistances": dict(Counter(str(r["resistance_count"]) for r in records)),
            "without_supports_share": sum(r["support_count"] == 0 for r in records)/n if n else None,
            "without_resistances_share": sum(r["resistance_count"] == 0 for r in records)/n if n else None,
            "similar_characteristic_groups": [{"signature": list(key), "count": count} for key, count in sorted(signatures.items()) if count > 1],
            "similarity_definition": "Ten sam symbol, observed_motion, std log-zwrotów zaokrąglone do 0.001, liczba supports/resistances. Opis przybliżony, bez progu doboru próbek.",
            "purpose": "audit_only; no feedback into selection, generator or test tuning"}

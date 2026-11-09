"""Window aggregation and descriptive generator comparison metrics."""
from __future__ import annotations

import math

from ....core.numeric.statistics import distribution
from ....core.ohlc.model import Candle
from .quality import series_observations, series_statistics
from ....core.ohlc.validation import validate_values


POOLED_METRICS = ("log_returns", "absolute_log_returns", "relative_range", "relative_body",
                  "body_fraction", "upper_wick_fraction", "lower_wick_fraction")


COMPARISON_VERSION = 1


def tail_diagnostics(values: list[float]) -> dict:
    """Kurtoza Pearsona (normalna=3) i częstości abs(r)>2/3 próbnego sigma."""
    dist = distribution(values)
    mean = dist["mean"]
    m2 = math.fsum((v - mean) ** 2 for v in values) / len(values)
    kurtosis = (math.fsum((v - mean) ** 4 for v in values) / len(values) / (m2 * m2)) if m2 else None
    return {"pearson_kurtosis": kurtosis, "kurtosis_reason": None if m2 else "zero_variance",
            "sample_sigma": dist["std"], "exceedance_abs_2sigma": sum(abs(v) > 2 * dist["std"] for v in values) / len(values),
            "exceedance_abs_3sigma": sum(abs(v) > 3 * dist["std"] for v in values) / len(values)}


def lag1_absolute_correlation(return_windows: list[list[float]]) -> dict:
    """Pearson dla par abs(r_t), abs(r_t-1) wyłącznie wewnątrz okien."""
    pairs = [(abs(a), abs(b)) for returns in return_windows for a, b in zip(returns, returns[1:])]
    if len(pairs) < 2:
        return {"value": None, "pair_count": len(pairs), "reason": "insufficient_pairs"}
    xs, ys = zip(*pairs)
    mx, my = math.fsum(xs) / len(xs), math.fsum(ys) / len(ys)
    vx, vy = math.fsum((x - mx) ** 2 for x in xs), math.fsum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return {"value": None, "pair_count": len(pairs), "reason": "zero_variance"}
    value = math.fsum((x - mx) * (y - my) for x, y in pairs) / math.sqrt(vx * vy)
    return {"value": max(-1.0, min(1.0, value)), "pair_count": len(pairs), "reason": None}


def aggregate_windows(windows: list[list[Candle]]) -> dict:
    """Łącz surowe obserwacje, a statystyki całych okien opisuj osobno."""
    if not windows:
        raise ValueError("Brak okien do porównania")
    pooled = {name: [] for name in POOLED_METRICS}
    returns, per_window = [], []
    for index, window in enumerate(windows):
        report = validate_values(window)
        if len(window) != 120 or report["missing_total"]:
            raise ValueError("Porównanie wymaga ciągłych okien po 120 świec")
        observations = series_observations(window)
        stats = series_statistics(window)
        for name in POOLED_METRICS:
            pooled[name].extend(observations[name])
        returns.append(observations["log_returns"])
        per_window.append({"index": index, "return_std": stats["log_returns"]["std"],
                           "close_change": stats["window_close_change"],
                           "relative_range": stats["window_relative_range"],
                           "absolute_return_lag1": lag1_absolute_correlation([observations["log_returns"]])})
    return {"window_count": len(windows), "candle_count": len(windows) * 120,
            "pooled_observations": {name: distribution(values) for name, values in pooled.items()},
            "window_distributions": {name: distribution([row[name] for row in per_window])
                                     for name in ("return_std", "close_change", "relative_range")},
            "absolute_return_lag1": lag1_absolute_correlation(returns), "per_window": per_window,
            "return_diagnostics": tail_diagnostics([r for window in returns for r in window])}


def statistical_differences(real: dict, synthetic: dict) -> dict:
    """Różnice signed synthetic-minus-real; brak dzielenia przez bliskie zera."""
    result = {}
    for section in ("pooled_observations", "window_distributions"):
        result[section] = {}
        for name, reference in real[section].items():
            observed = synthetic[section][name]
            difference = {key: observed[key] - reference[key] for key in ("mean", "std", "min", "max")}
            difference["quantiles"] = {q: observed["quantiles"][q] - value
                                       for q, value in reference["quantiles"].items()}
            result[section][name] = difference
    a, b = real["absolute_return_lag1"]["value"], synthetic["absolute_return_lag1"]["value"]
    result["absolute_return_lag1"] = b - a if a is not None and b is not None else None
    if "return_diagnostics" in real and "return_diagnostics" in synthetic:
        result["return_diagnostics"] = {}
        for name in ("pearson_kurtosis", "exceedance_abs_2sigma", "exceedance_abs_3sigma"):
            a, b = real["return_diagnostics"][name], synthetic["return_diagnostics"][name]
            result["return_diagnostics"][name] = b-a if a is not None and b is not None else None
    return result


def metric_values(stats: dict) -> dict:
    """Wspólne metryki raportów v1/v2; podstawowe statystyki nie są liczone ponownie."""
    pooled, windows = stats["pooled_observations"], stats["window_distributions"]
    metrics = {"return_mean": pooled["log_returns"]["mean"], "return_std": pooled["log_returns"]["std"],
               "abs_ac1": stats["absolute_return_lag1"]["value"]}
    for q in ("0.95", "0.99"):
        metrics[f"abs_return_q{q}"] = pooled["absolute_log_returns"]["quantiles"][q]
    for name in ("relative_range", "body_fraction", "upper_wick_fraction", "lower_wick_fraction"):
        metrics[f"{name}_mean"] = pooled[name]["mean"]
    for q, value in pooled["relative_range"]["quantiles"].items():
        metrics[f"relative_range_q{q}"] = value
    for name in ("return_std", "close_change", "relative_range"):
        for metric in ("mean", "std"):
            metrics[f"window_{name}_{metric}"] = windows[name][metric]
    return metrics


REFINEMENT_METRICS = dict(abs_ac1="abs_ac1", window_std_mean="window_return_std_mean",
    window_std_std="window_return_std_std", abs_q95="abs_return_q0.95", abs_q99="abs_return_q0.99",
    range_mean="relative_range_mean", body_fraction="body_fraction_mean",
    upper_wick="upper_wick_fraction_mean", lower_wick="lower_wick_fraction_mean")


def refinement_review(report: dict, profiles: dict) -> dict:
    """Opis tolerancji i ablacji; bez wskazywania zwycięzcy lub akceptacji."""
    from ..config.refinement import RefinementSettings, PRIORITY
    from .calibration.objectives import error_scale
    required = {"V1", "V2-full-original", "V2-full-refined", "V2-bridge_volatility-refined"}
    if not required <= set(report["variants"]):
        raise ValueError("Porównanie refinement wymaga V1, full-original i obu osobno dostrojonych profili")
    parent_hashes = {p["calibration"]["source_profile_sha256"] for p in profiles.values()}
    originals = {r["profile_sha256"] for r in report["reports"] if r["variant"] == "V2-full-original"}
    if len(parent_hashes) != 1 or parent_hashes != originals:
        raise ValueError("Profile refinement muszą pochodzić z porównywanego full-original")
    policies = [p["calibration"]["search"] for p in profiles.values()]
    if any(p != policies[0] for p in policies):
        raise ValueError("Porównanie refinement wymaga jednakowej polityki diagnostycznej")
    policy = RefinementSettings(**policies[0])
    # Ocena parami wymaga takich samych seedów i liczby przykładów.
    seed_sets = [{(r["master_seed"], len(r["example_seeds"])) for r in report["reports"] if r["variant"] == label}
                 for label in sorted(required)]
    if any(s != seed_sets[0] for s in seed_sets) or any(seed is None for seed, _ in seed_sets[0]):
        raise ValueError("Bezpośrednie porównanie wymaga tych samych seedów i liczności we wszystkich czterech grupach")
    groups, mixture = {}, {}
    for label in sorted(required):
        rows, counts = {}, {"improved": 0, "worsened": 0, "practically_unchanged": 0, "undefined": 0}
        priority_counts = dict(counts)
        for feature, metric_name in REFINEMENT_METRICS.items():
            target = report["real_metrics"][metric_name]
            metric = report["variants"][label]["metrics"][metric_name]
            baseline = report["variants"]["V2-full-original"]["metrics"][metric_name]
            if target is None or "mean_absolute_error" not in metric or "mean_absolute_error" not in baseline:
                rows[feature] = {"direction_vs_original": "undefined"}
                counts["undefined"] += 1
                if feature in PRIORITY:
                    priority_counts["undefined"] += 1
                continue
            scale = error_scale(feature, target, policy)
            delta = metric["mean_absolute_error"]-baseline["mean_absolute_error"]
            direction = _error_direction(delta, scale*policy.practical_equivalence_fraction)
            values = [r["metrics"][metric_name] for r in report["reports"] if r["variant"] == label]
            rows[feature] = {"tolerance_absolute": scale, "mean_absolute_error_exceeds_tolerance": metric["mean_absolute_error"]>scale,
                "seeds_exceeding_tolerance": sum(v is not None and abs(v-target)>scale for v in values),
                "undefined_seeds": sum(v is None for v in values), "error_change_vs_original": delta,
                "direction_vs_original": direction}
            counts[direction] += 1
            if feature in PRIORITY:
                priority_counts[direction] += 1
        groups[label] = {"metrics": rows, "metric_counts": counts, "priority_metric_counts": priority_counts}
    for feature, metric_name in REFINEMENT_METRICS.items():
        a = report["variants"]["V2-full-refined"]["metrics"][metric_name]
        b = report["variants"]["V2-bridge_volatility-refined"]["metrics"][metric_name]
        target = report["real_metrics"][metric_name]
        delta = b.get("mean_absolute_error", 0)-a.get("mean_absolute_error", 0)
        mixture[feature] = ({"direction": "undefined"} if target is None or "mean_absolute_error" not in a or "mean_absolute_error" not in b
            else {"error_change_without_mixture": delta,
                  "direction": _error_direction(delta, error_scale(feature, target, policy)*policy.practical_equivalence_fraction)})
    return {"groups": groups, "mixture_ablation": mixture, "source_profile_sha256": next(iter(parent_hashes)),
        "tolerances": policy.tolerances, "practical_equivalence_fraction": policy.practical_equivalence_fraction,
        "notes": ["Zmiana mieszanki obejmuje również osobne dostrojenie zmienności; nie izoluje efektu samej mieszanki.",
                  "Progi są diagnostyczne; nie wybrano zwycięzcy ani nie zaakceptowano profili.",
                  "Kontrola stabilności na treningu nie jest niezależnym testem rynkowym."]}


def _error_direction(change: float, threshold: float) -> str:
    return "practically_unchanged" if abs(change)<=threshold else ("improved" if change<0 else "worsened")

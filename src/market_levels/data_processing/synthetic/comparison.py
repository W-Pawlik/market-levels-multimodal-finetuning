"""Statystyki okien i sprawdzony odczyt istniejących partii syntetycznych."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path

from ...core.candles import Candle
from ..storage import read_candles_csv
from .calibration import profile_hash, validate_generator_profile
from .quality import (canonical_hash, distribution, series_observations,
                      series_statistics, validate_synthetic, validate_values)
from .settings import KINDS, SYMBOLS, positive_int
from .training_period import ChronologicalSplit

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


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Oczekiwano obiektu JSON: {path}")
    return value


def _batch_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value.strip() or Path(value).is_absolute():
        raise ValueError("Manifest wymaga względnych ścieżek plików")
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Ścieżka pliku wychodzi poza katalog partii")
    return path


def load_synthetic_windows(manifest_path: Path, *, symbol: str, count: int,
                           split: ChronologicalSplit) -> tuple[list[list[Candle]], dict]:
    """Sprawdź manifest, profil, metadane, OHLC i statystyki zapisanych plików."""
    positive_int(count, "window_count")
    if symbol not in SYMBOLS:
        raise ValueError("Nieobsługiwany instrument")
    path = Path(manifest_path).resolve()
    try:
        manifest = _load_json(path)
        identity = manifest["identity"]
        if manifest["origin"] != "synthetic" or manifest["status"] not in ("diagnostic", "candidate"):
            raise ValueError("Niepoprawne pochodzenie lub status manifestu")
        expected_id = hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False).encode()).hexdigest()[:24]
        if manifest["run_id"] != expected_id:
            raise ValueError("Identyfikator partii nie zgadza się z jej konfiguracją/profilami")
        entries = manifest["examples"]
        if (not isinstance(entries, list) or type(manifest["accepted_count"]) is not int
                or manifest["accepted_count"] != len(entries)):
            raise ValueError("Niezgodna liczba przykładów manifestu")
        if type(manifest["rejected_count"]) is not int or manifest["rejected_count"] < 0:
            raise ValueError("Niepoprawna liczba odrzuconych przykładów")
        for key in ("id", "seed", "ohlc_sha256", "csv", "metadata"):
            values = [entry[key] for entry in entries]
            if len(set(values)) != len(values):
                raise ValueError(f"Duplikaty w manifeście: {key}")
        if any(entry["symbol"] not in SYMBOLS for entry in entries):
            raise ValueError("Niepoprawny instrument w manifeście")
        selected = [entry for entry in entries if entry["symbol"] == symbol]
        if len(selected) != count:
            raise ValueError(f"{symbol}: wymagano dokładnie {count} przykładów, manifest zawiera {len(selected)}")
        profile = identity["profiles"][symbol]
        generator_version = {"1.0.0": "v1", "2.0.0": "v2"}.get(identity["generator_version"])
        if generator_version is None:
            raise ValueError("Nieobsługiwana wersja generatora w manifeście")
        validate_generator_profile(profile, symbol=symbol, generator_version=generator_version)
        if (profile.get("calibration", {}).get("method") == "volatility_refinement_v1"
                and profile["calibration"]["variant"] != identity["configuration"].get("v2_variant")):
            raise ValueError("Manifest używa profilu refinement dla innego wariantu")
        if profile["status"] == "diagnostic" or profile.get("estimation_kind") == "diagnostic":
            raise ValueError("Porównanie wymaga empirycznego profilu treningowego, nie parametrów ręcznych")
        split.require_training(*(datetime.fromisoformat(profile["period"][key])
                                 for key in ("allowed_start", "allowed_end")))
        declared_split = profile["source"].get("chronological_split")
        if declared_split is not None and declared_split != split.document():
            raise ValueError("Profil odnosi się do innego podziału chronologicznego")
        digest = profile_hash(profile)
        windows, details = [], []
        regime_counts = Counter({kind: 0 for kind in KINDS})
        regime_candles = Counter({kind: 0 for kind in KINDS})
        counts_per_example = []
        for entry in selected:
            csv_path, metadata_path = (_batch_path(path.parent, entry[key]) for key in ("csv", "metadata"))
            metadata = _load_json(metadata_path)
            for key in ("id", "seed", "symbol", "csv", "ohlc_sha256"):
                if metadata[key] != entry[key]:
                    raise ValueError(f"Niezgodne metadane i manifest: {key}")
            if (metadata["origin"] != "synthetic" or metadata["status"] != manifest["status"]
                    or metadata["generator_version"] != identity["generator_version"]
                    or metadata["profile_sha256"] != digest or metadata["calibration_profile"] != profile):
                raise ValueError("Niezgodne pochodzenie, wersja lub profil przykładu")
            config = dict(metadata["configuration"])
            config.pop("output")
            if config != identity["configuration"]:
                raise ValueError("Niezgodna konfiguracja przykładu")
            if generator_version == "v2":
                from .v2_parameters import mechanisms, effective_parameters, V2Parameters
                from .stochastic_processes import stream_seed
                from .generator_v2 import STREAMS
                if (config["generator_version"] != "v2" or metadata["profile_version"] != 2
                        or metadata["v2_variant"] != config["v2_variant"]
                        or metadata["experiment_id"] != config["experiment_id"]
                        or metadata["mechanisms"] != mechanisms(config["v2_variant"])
                        or metadata["configured_parameters"] != profile["v2_parameters"]
                        or metadata["effective_parameters"] != effective_parameters(V2Parameters(**profile["v2_parameters"]),config["v2_variant"])
                        or metadata["rng_stream_seeds"] != {name: stream_seed(entry["seed"], name) for name in STREAMS}
                        or profile["regime_configuration"] != {key: config[key] for key in ("regimes", "min_regimes", "max_regimes")}):
                    raise ValueError("Niespójne mechanizmy lub profil generatora v2")
                import random
                from .stochastic_processes import volatility_states, volatility_multiplier
                parameters = profile["v2_parameters"]
                enabled = metadata["mechanisms"]["volatility"]
                sd = parameters["volatility_stationary_std"]
                states = (volatility_states(random.Random(metadata["rng_stream_seeds"]["volatility"]), 120,
                                           parameters["volatility_phi"], sd) if enabled else [0.0] * 120)
                trace = metadata["volatility_trace"]
                if len(trace) != 120:
                    raise ValueError("Niepełny przebieg zmienności v2")
                regime_sigmas = [r["sigma"] for r in metadata["regimes"] for _ in range(r["length"])]
                if len(regime_sigmas) != 120:
                    raise ValueError("Niepoprawna długość reżimów w przebiegu v2")
                for i, state in enumerate(states):
                    multiplier = volatility_multiplier(state, sd) if enabled else 1.0
                    if trace[i] != {"index": i, "h": state, "sigma_4h": regime_sigmas[i]*multiplier, "multiplier": multiplier}:
                        raise ValueError("Niezgodny przebieg zmienności v2")
            if metadata["internal_steps_per_candle"] != 12 or metadata["total_internal_steps"] != 1440:
                raise ValueError("Niezgodna liczba kroków symulacji")
            source = f"synthetic:{metadata['generator_version']}:{symbol}:{entry['seed']}"
            candles = read_candles_csv(csv_path, source=source)
            validation = validate_synthetic(candles, metadata["regimes"], entry["seed"])
            if validation != metadata["validation"] or not metadata["roundtrip_valid"]:
                raise ValueError("Niezgodny wynik walidacji przykładu")
            if canonical_hash(candles) != entry["ohlc_sha256"]:
                raise ValueError("Niepoprawny hash OHLC przykładu")
            stats = series_statistics(candles)
            if stats != metadata["statistics"] or stats != entry["statistics"]:
                raise ValueError("Statystyki pliku nie zgadzają się z metadanymi")
            regimes = metadata["regimes"]
            shares = {kind: sum(r["length"] for r in regimes if r["kind"] == kind) / 120 for kind in KINDS}
            if shares != metadata["regime_shares"] or shares != entry["regime_shares"]:
                raise ValueError("Niezgodne udziały reżimów")
            regime_counts.update(r["kind"] for r in regimes)
            for regime in regimes:
                regime_candles[regime["kind"]] += regime["length"]
            counts_per_example.append(len(regimes))
            windows.append(candles)
            details.append({"id": entry["id"], "seed": entry["seed"], "csv": entry["csv"],
                            "metadata": entry["metadata"], "ohlc_sha256": entry["ohlc_sha256"],
                            "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                            "metadata_sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest()})
        return windows, {"manifest": str(path), "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "run_id": manifest["run_id"], "status": manifest["status"],
                         "generator_version": identity["generator_version"],
                         "variant": identity["configuration"].get("v2_variant", "v1"),
                         "experiment_id": identity["configuration"].get("experiment_id"),
                         "master_seed": identity["configuration"]["seed"],
                         "invalid_examples": manifest["rejected_count"], "duplicate_examples": 0,
                         "profile": profile, "profile_sha256": digest, "profile_status": profile["status"],
                         "examples": details, "regimes": {
                             "occurrences": dict(regime_counts), "candle_counts": dict(regime_candles),
                             "candle_shares": {k: regime_candles[k] / (count * 120) for k in KINDS},
                             "regimes_per_example": distribution(counts_per_example),
                             "regimes_per_example_counts": dict(Counter(map(str, counts_per_example)))}}
    except (KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError(f"Uszkodzony manifest lub metadane: {exc}") from exc

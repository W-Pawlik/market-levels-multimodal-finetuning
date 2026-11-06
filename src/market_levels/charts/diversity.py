"""Read-only diversity diagnostics; declared regimes are not observed labels."""
from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import statistics

from ..core.candles import Candle, CANDLE_DELTA
from ..data_processing.storage import read_candles_csv
from ..data_processing.synthetic.calibration import profile_hash
from ..data_processing.synthetic.generator import example_seed
from ..data_processing.synthetic.profile_v2 import validate_profile_v2
from ..data_processing.synthetic.quality import (canonical_hash, distribution, validate_synthetic,
                                                  validate_values)
from .renderer import validate_window

SEEDS = (20261105, 20261115, 20261125, 20261201, 20261211)
SYMBOLS = ("BTCUSDT", "ETHUSDT")
KINDS = ("uptrend", "downtrend", "consolidation", "breakout")


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()


class SourceLedger:
    """Byte hashes of inputs before reading and after analysis; never writes them."""
    def __init__(self):
        self.files: dict[str, str] = {}

    def track(self, path: Path) -> Path:
        path = Path(path).resolve()
        key = str(path)
        digest = sha256_file(path)
        if key in self.files and self.files[key] != digest:
            raise ValueError(f"Źródło zmieniło się podczas analizy: {path}")
        self.files[key] = digest
        return path

    def verify(self) -> dict:
        changed = [p for p, digest in self.files.items() if sha256_file(Path(p)) != digest]
        if changed:
            raise ValueError(f"Zmienione źródła: {changed}")
        return {"unchanged": True, "file_count": len(self.files), "sha256": dict(self.files)}


def read_training_csv(path: Path, start: datetime, end: datetime) -> list[Candle]:
    """Parse only training OHLC; first later timestamp is a stop sentinel.

    Whole-file byte hashes are integrity checks, not analytical access. CSV is
    chronological: a strictly increasing training prefix is required.
    """
    result = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["open_time_utc", "open", "high", "low", "close"]:
            raise ValueError("Niepoprawny nagłówek CSV")
        previous = None
        for row in reader:
            stamp = datetime.fromisoformat(row["open_time_utc"])
            if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
                raise ValueError("Wymagany UTC")
            if previous is not None and stamp <= previous:
                raise ValueError("Niechronologiczny CSV treningu")
            previous = stamp
            if stamp > end:
                break
            if stamp < start:
                continue
            result.append(Candle(stamp, *(Decimal(row[k]) for k in ("open", "high", "low", "close")), str(path)))
    validate_values(result)
    if result[0].timestamp != start or result[-1].timestamp != end:
        raise ValueError("Niepełne pokrycie granic treningu")
    return result


def training_windows(candles: list[Candle], stride: int = 120) -> tuple[list[tuple[int, list[Candle]]], int]:
    """Fixed positions in each continuous run; no windows cross a gap."""
    validate_values(candles)
    if type(stride) is not int or stride <= 0:
        raise ValueError("stride musi być dodatni")
    windows, runs = [], []
    for index, candle in enumerate(candles):
        if not runs or candle.timestamp - runs[-1][-1][1].timestamp != CANDLE_DELTA:
            runs.append([])
        runs[-1].append((index, candle))
    for run in runs:
        for offset in range(0, len(run)-119, stride):
            windows.append((run[offset][0], [c for _, c in run[offset:offset+120]]))
    return windows, len(runs)-1


def quantile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("Brak danych do progu")
    ordered = sorted(values)
    position = (len(ordered)-1)*q
    a, b = math.floor(position), math.ceil(position)
    return ordered[a] + (ordered[b]-ordered[a])*(position-a)


def movement(candles: list[Candle]) -> dict:
    """Open-to-last-Close net/path, including the first candle and real gaps in price."""
    prices = [float(candles[0].open)] + [float(c.close) for c in candles]
    path = sum(abs(b-a) for a, b in zip(prices, prices[1:]))
    return {"price_change": prices[-1]/prices[0]-1,
            "directionality": abs(prices[-1]-prices[0])/path if path else 0.0}


def observed_motion(metrics: dict) -> str:
    if metrics["directionality"] >= 0.18:
        return "upward" if metrics["price_change"] > 0 else "downward"
    return "low_directionality" if metrics["directionality"] <= 0.08 else "intermediate"


def window_metrics(candles: list[Candle], thresholds: dict | None = None) -> dict:
    validate_window(candles)
    changes = [math.log(float(b.close))-math.log(float(a.close)) for a, b in zip(candles, candles[1:])]
    spans = [float((c.high-c.low)/c.open) for c in candles]
    fractions = [(float(abs(c.close-c.open)/(c.high-c.low)),
                  float((c.high-max(c.open,c.close))/(c.high-c.low)),
                  float((min(c.open,c.close)-c.low)/(c.high-c.low)))
                 for c in candles if c.high > c.low]
    # Flat bars have no defined proportions: report count, average nonflat bars only.
    result = dict(movement(candles),
                  relative_range=float((max(c.high for c in candles)-min(c.low for c in candles))/candles[0].open),
                  log_return_std=statistics.stdev(changes),
                  body_fraction=statistics.mean(f[0] for f in fractions) if fractions else None,
                  upper_wick_fraction=statistics.mean(f[1] for f in fractions) if fractions else None,
                  lower_wick_fraction=statistics.mean(f[2] for f in fractions) if fractions else None,
                  flat_candles=120-len(fractions))
    result["observed_motion"] = observed_motion(result)
    # Breakout proxy is local only: 20 preceding bars, no target S/R calculation.
    events = []
    for i in range(20, 120):
        preceding = candles[i-20:i]
        baseline = statistics.stdev(changes[i-20:i-1])
        outside = candles[i].close > max(c.high for c in preceding) or candles[i].close < min(c.low for c in preceding)
        if outside and abs(changes[i-1]) > 2*baseline:
            events.append(i+1)
    first, second = movement(candles[:60]), movement(candles[60:])
    result.update(breakout_proxy_positions=events,
                  reversal_proxy=(first["directionality"] >= 0.18 and second["directionality"] >= 0.18
                                  and first["price_change"]*second["price_change"] < 0))
    if thresholds is not None:
        std = result["log_return_std"]
        result.update(volatility_band="low" if std <= thresholds["volatility_q33"] else "high" if std > thresholds["volatility_q67"] else "medium",
                      large_candle_share=sum(v >= thresholds["range_q95"] for v in spans)/120,
                      extreme_move_share=sum(abs(v) >= thresholds["abs_return_q99"] for v in changes)/119)
    return result


def fit_thresholds(candles: list[Candle]) -> dict:
    windows, _ = training_windows(candles)
    stds = [window_metrics(w)["log_return_std"] for _, w in windows]
    returns = [abs(math.log(float(b.close))-math.log(float(a.close))) for a,b in zip(candles,candles[1:]) if b.timestamp-a.timestamp == CANDLE_DELTA]
    return {"method": "train_only_linear_quantiles_v1", "window_stride": 120,
            "reference_window_count": len(stds), "volatility_q33": quantile(stds, 1/3),
            "volatility_q67": quantile(stds, 2/3),
            "range_q95": quantile([float((c.high-c.low)/c.open) for c in candles], .95),
            "abs_return_q99": quantile(returns, .99)}


def _child(root: Path, relative: str) -> Path:
    path = (root/relative).resolve()
    if root.resolve() not in path.parents:
        raise ValueError("Ścieżka manifestu wychodzi poza partię")
    return path


def discover_batches(root: Path, ledger: SourceLedger) -> tuple[list[tuple[Path, dict]], dict]:
    candidates = {seed: [] for seed in SEEDS}
    issues = []
    for path in sorted(root.rglob("manifest.json")):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        try:
            manifest = json.loads(ledger.track(path).read_text(encoding="utf-8"))
            identity = manifest.get("identity", {})
            config = identity.get("configuration", {})
            profiles = identity.get("profiles", {})
            if (config.get("generator_version") != "v2" or config.get("v2_variant") != "full"
                    or config.get("seed") not in SEEDS):
                continue
            if set(profiles) != set(SYMBOLS) or not all(p.get("calibration", {}).get("method") == "volatility_refinement_v1" and p["calibration"].get("variant") == "full" for p in profiles.values()):
                continue
            candidates[config["seed"]].append((path, manifest))
        except (ValueError, KeyError, TypeError) as error:
            issues.append({"path": str(path), "error": str(error)})
    selected, excluded = [], []
    for seed, options in candidates.items():
        if not options:
            continue
        maximum = max(len(m.get("examples", [])) for _,m in options)
        largest = [(p,m) for p,m in options if len(m.get("examples", [])) == maximum]
        if len(largest) != 1:
            raise ValueError(f"Niejednoznaczne partie seeda {seed}; wskaż węższy katalog źródeł")
        selected.extend(largest)
        excluded.extend({"path": str(p), "seed": seed, "count": len(m["examples"]),
                         "reason": "smaller_existing_batch_not_pooled"} for p,m in options if p != largest[0][0])
    return selected, {"expected_seeds": list(SEEDS), "missing_seeds": [s for s in SEEDS if not candidates[s]],
                       "excluded_batches": excluded, "discovery_issues": issues}


def read_synthetic(batches: list[tuple[Path, dict]], ledger: SourceLedger) -> tuple[list[dict], list[dict], list[dict]]:
    records, errors, completeness = [], [], []
    for path, manifest in batches:
        config = manifest["identity"]["configuration"]
        profiles = manifest["identity"]["profiles"]
        master = config["seed"]
        batch_errors = []
        for symbol, profile in profiles.items():
            try:
                validate_profile_v2(profile, symbol=symbol)
            except ValueError as error:
                batch_errors.append(f"Niepoprawny profil {symbol}: {error}")
        if manifest.get("status") != "diagnostic" or not config.get("diagnostic") or manifest.get("origin") != "synthetic":
            batch_errors.append("Partia nie ma statusu diagnostic/synthetic")
        if manifest.get("run_id") != path.parent.name:
            batch_errors.append("Niezgodny run_id")
        if manifest.get("accepted_count") != len(manifest["examples"]) or manifest.get("rejected_count") != 0:
            batch_errors.append("Niezgodne liczniki partii")
        expected = {(s,i) for s in SYMBOLS for i in range(config["count"])}
        found = set()
        for entry in manifest["examples"]:
            try:
                if batch_errors:
                    raise ValueError("; ".join(batch_errors))
                symbol, seed = entry["symbol"], entry["seed"]
                index = int(entry["id"].split("_")[1])
                if symbol not in SYMBOLS or (symbol,index) not in expected or (symbol,index) in found:
                    raise ValueError("Niepoprawny symbol/indeks lub duplikat wpisu")
                if type(seed) is not int or seed != example_seed(master, symbol, index) or entry["id"] != f"{symbol}_{index:06d}_{seed:064x}":
                    raise ValueError("Niezgodny seed/id")
                csv_path = ledger.track(_child(path.parent, entry["csv"]))
                meta_path = ledger.track(_child(path.parent, entry["metadata"]))
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                profile = profiles[symbol]
                if (profile.get("symbol") != symbol or profile.get("status") != "unapproved"
                        or profile.get("version") != 2 or profile.get("generator_version") != "2.0.0"
                        or profile.get("estimation_kind") != "training"):
                    raise ValueError("Niezgodny profil refined/unapproved/training")
                if (meta.get("calibration_profile") != profile or meta.get("profile_sha256") != profile_hash(profile)
                        or meta.get("symbol") != symbol or meta.get("seed") != seed or meta.get("id") != entry["id"]
                        or meta.get("status") != "diagnostic" or meta.get("origin") != "synthetic"
                        or meta.get("generator_version") != "2.0.0" or meta.get("v2_variant") != "full"
                        or {k:v for k,v in meta.get("configuration", {}).items() if k != "output"} != config
                        or meta.get("effective_parameters") != profile["v2_parameters"]
                        or not meta.get("roundtrip_valid")):
                    raise ValueError("Niezgodna tożsamość metadanych/profilu/konfiguracji")
                profile_path = Path(config["profiles"][symbol])
                profile_file_hash = None
                if profile_path.is_file():
                    profile_file_hash = sha256_file(ledger.track(profile_path))
                    if json.loads(profile_path.read_text(encoding="utf-8")) != profile:
                        raise ValueError("Profil lokalny różni się od osadzonego")
                candles = read_candles_csv(csv_path, source=f"synthetic:2.0.0:{symbol}:{seed}")
                validate_synthetic(candles, meta["regimes"], seed)
                digest = canonical_hash(candles)
                shares = {k: sum(r["length"] for r in meta["regimes"] if r["kind"] == k)/120 for k in KINDS}
                if (digest != entry["ohlc_sha256"] or digest != meta["ohlc_sha256"]
                        or shares != meta.get("regime_shares") or shares != entry.get("regime_shares")):
                    raise ValueError("Niezgodny hash OHLC lub udziały reżimów")
                segments = []
                for regime in meta["regimes"]:
                    segment = candles[regime["start"]:regime["end_exclusive"]]
                    observed = movement(segment)
                    observed["motion"] = observed_motion(observed)
                    segments.append(dict(regime, observed=observed,
                                         declared_direction_matches=(observed["price_change"] > 0 if regime["kind"] == "uptrend" else observed["price_change"] < 0 if regime["kind"] == "downtrend" else None)))
                records.append({"id": entry["id"], "symbol": symbol, "source": "synthetic",
                                "master_seed": master, "seed": seed, "variant": "V2-full-refined",
                                "profile": profile, "profile_path": str(profile_path),
                                "profile_sha256": profile_hash(profile), "profile_file_sha256": profile_file_hash,
                                "manifest": str(path.resolve()), "source_csv": str(csv_path),
                                "source_csv_sha256": ledger.files[str(csv_path)],
                                "csv_record_indices": list(range(120)), "ohlc_sha256": digest,
                                "regimes": segments, "candles": candles})
                found.add((symbol,index))
            except (ValueError, KeyError, TypeError, OSError, IndexError, ArithmeticError) as error:
                errors.append({"manifest": str(path), "id": entry.get("id"), "error": str(error)})
        completeness.append({"manifest": str(path), "master_seed": master, "expected": len(expected),
                             "analyzed": len(found), "batch_errors": batch_errors,
                             "missing_symbol_indices": sorted(expected-found)})
    return records, errors, completeness


def summarize(records: list[dict]) -> dict:
    """All segments count; each chart contributes exactly 120 candle assignments."""
    count = Counter(str(len(r["regimes"])) for r in records)
    occurrences, candles, transitions, sequences = Counter(), Counter(), Counter(), Counter()
    lengths = {k: [] for k in KINDS}
    agreement = {k: Counter() for k in ("uptrend", "downtrend")}
    observed_segments = {k: Counter() for k in KINDS}
    for record in records:
        regimes = record["regimes"]
        kinds = [r["kind"] for r in regimes]
        sequences[" -> ".join(kinds)] += 1
        for a,b in zip(kinds,kinds[1:]):
            transitions[f"{a} -> {b}"] += 1
        for regime in regimes:
            k = regime["kind"]
            occurrences[k] += 1
            candles[k] += regime["length"]
            lengths[k].append(regime["length"])
            if "observed" in regime:
                observed_segments[k][regime["observed"]["motion"]] += 1
            if k in agreement:
                agreement[k]["matches" if regime["declared_direction_matches"] else "opposite_or_flat"] += 1
    total = len(records)*120
    metrics = [r["metrics"] for r in records]
    return {"charts": len(records), "master_seeds": dict(Counter(str(r["master_seed"]) for r in records)),
            "regime_count": {str(i): count[str(i)] for i in (1,2,3)},
            "regime_occurrences": {k: occurrences[k] for k in KINDS},
            "candle_counts": {k: candles[k] for k in KINDS},
            "candle_shares": {k: candles[k]/total if total else 0 for k in KINDS},
            "regime_lengths": {k: {"histogram": dict(sorted(Counter(lengths[k]).items())),
                                    "distribution": distribution(lengths[k]) if lengths[k] else None} for k in KINDS},
            "transitions": dict(transitions.most_common()), "sequences": dict(sequences.most_common()),
            "consolidation_breakout_trend": sum(v for k,v in sequences.items() if k in ("consolidation -> breakout -> uptrend", "consolidation -> breakout -> downtrend")),
            "declared_segment_direction_agreement": {k: dict(v) for k,v in agreement.items()},
            "declared_vs_observed_segments": {k:dict(v) for k,v in observed_segments.items()},
            "volatility_bands": dict(Counter(m["volatility_band"] for m in metrics)),
            "observed_motion": dict(Counter(m["observed_motion"] for m in metrics)),
            "breakout_proxy_charts": sum(bool(m["breakout_proxy_positions"]) for m in metrics),
            "metric_distributions": {k: distribution([m[k] for m in metrics if m[k] is not None])
                                     for k in ("price_change", "relative_range", "log_return_std", "directionality",
                                               "large_candle_share", "extreme_move_share", "body_fraction",
                                               "upper_wick_fraction", "lower_wick_fraction") if any(m[k] is not None for m in metrics)}}

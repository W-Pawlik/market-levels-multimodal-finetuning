"""Discover and verify existing refined diagnostic batches."""
from __future__ import annotations

import json
from pathlib import Path

from ...data_processing.io.candles import read_candles_csv
from ...data_processing.synthetic.domain.profiles.v1 import profile_hash
from ...data_processing.synthetic.domain.generation.seeds import example_seed
from ...data_processing.synthetic.domain.profiles.validation import validate_profile_v2
from ...core.ohlc.identity import canonical_hash
from ...data_processing.synthetic.domain.quality import validate_synthetic
from ..config import SEEDS, SYMBOLS, KINDS
from ...shared.integrity import SourceLedger, sha256_file
from ..domain.metrics import movement, observed_motion
from ...shared.paths import _child


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

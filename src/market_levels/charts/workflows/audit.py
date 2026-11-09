"""charts / workflows / audit."""
from __future__ import annotations

import hashlib
import platform
from datetime import datetime
from pathlib import Path

from ...shared.publication import publication_workspace, publish_directory
from ...data_processing.io.candles import write_candles_csv
from ...shared.json_io import write_json
from ...core.ohlc.identity import canonical_hash
from ...core.numeric.statistics import distribution
from ...data_processing.io.chronology import load_chronological_split
from ..config import SEEDS, SYMBOLS
from ...shared.integrity import SourceLedger
from ..io.audit_sources import discover_batches, read_synthetic
from ..domain.metrics import fit_thresholds, window_metrics
from ...data_processing.windows.io.training_csv import read_training_csv
from ..domain.diversity import summarize
from ...data_processing.windows.domain.candidates import training_windows
from ..io.rendering import render_window
from ...shared.paths import require_short_path
from ..domain.selection import SELECTION_VERSION, tags, select_pilot
from ..reporting.audit import _audit_markdown


def _public(record: dict) -> dict:
    return {k:v for k,v in record.items() if k not in ("candles", "profile")}


def run_audit(*, synthetic_root: Path, real_csv: dict[str, Path], config: Path,
              output: Path, selection_seed: int = 20261106, per_group: int = 8) -> Path:
    """Publish a new audit directory with a 24–32 image pilot; no source writes."""
    if per_group not in (6, 7, 8):
        raise ValueError("Pilotaż wymaga 6–8 obrazów na symbol i źródło (24–32 łącznie)")
    if type(selection_seed) is not int or selection_seed < 0:
        raise ValueError("Seed selekcji musi być nieujemny")
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"Odmowa nadpisania: {output}")
    # A diagnostic output cannot live in any source tree or final chart dataset.
    protected = [Path(synthetic_root).resolve(), Path("data").resolve()]
    if any(output == p or p in output.parents for p in protected):
        raise ValueError("Wynik umieść poza źródłami i data/, np. results/diagnostics")
    for name in ("AUDYT_ROZNORODNOSCI.json", "SOURCE_INTEGRITY.json", "pilot/031.json", "pilot/031.csv"):
        require_short_path(output/name)
        require_short_path(output.parent/(".charts-"+"x"*8)/"batch"/name)
    ledger = SourceLedger()
    split = load_chronological_split(ledger.track(config), ledger=ledger)
    start, end = split.periods["train"]
    if start.year != 2020 or end.year != 2023:
        raise ValueError("Ten pilotaż wymaga treningu 2020–2023")
    batches, discovery = discover_batches(Path(synthetic_root), ledger)
    synthetic, errors, completeness = read_synthetic(batches, ledger)
    thresholds, real, reference = {}, [], {}
    for symbol in SYMBOLS:
        path = ledger.track(real_csv[symbol])
        candles = read_training_csv(path, start, end)
        thresholds[symbol] = fit_thresholds(candles)
        # Profiles must demonstrably use only this training interval.
        for record in [r for r in synthetic if r["symbol"] == symbol]:
            period = record["profile"]["period"]
            if not (start <= datetime.fromisoformat(period["allowed_start"]) <= datetime.fromisoformat(period["allowed_end"]) <= end):
                raise ValueError("Profil poza treningiem")
            record["metrics"] = window_metrics(record["candles"], thresholds[symbol])
        windows, gaps = training_windows(candles, 60)
        for index, window in windows:
            real.append({"id": f"{symbol}_train_{index:05d}", "symbol": symbol, "source": "real",
                         "variant": None, "profile_sha256": None, "profile_file_sha256": None,
                         "profile_path": None, "master_seed": None, "seed": None, "regimes": [],
                         "start_utc": window[0].timestamp.isoformat(), "end_utc": window[-1].timestamp.isoformat(),
                         "source_csv": str(path), "source_csv_sha256": ledger.files[str(path)],
                         "training_record_indices": list(range(index,index+120)), "ohlc_sha256": canonical_hash(window),
                         "candles": window, "metrics": window_metrics(window, thresholds[symbol])})
        disjoint, _ = training_windows(candles)
        reference[symbol] = {"window_count": len(disjoint), "training_candles": len(candles), "gaps": gaps,
                             "std_distribution": distribution([window_metrics(w)["log_return_std"] for _,w in disjoint])}
    summaries = {symbol: summarize([r for r in synthetic if r["symbol"] == symbol]) for symbol in SYMBOLS}
    for symbol in SYMBOLS:
        d = summaries[symbol]["metric_distributions"].get("log_return_std")
        denominator = reference[symbol]["std_distribution"]["std"]
        reference[symbol]["window_std_dispersion_ratio"] = d["std"]/denominator if d and denominator else None
    digest_ids: dict[str, list[str]] = {}
    for record in synthetic:
        digest_ids.setdefault(record["ohlc_sha256"], []).append(record["id"])
    duplicates = {d:ids for d,ids in digest_ids.items() if len(ids)>1}
    selected, coverage = [], []
    for symbol in SYMBOLS:
        for source, pool in (("synthetic",synthetic),("real",real)):
            group = [r for r in pool if r["symbol"] == symbol]
            # Report duplicates without silently rendering repeated trajectories.
            unique = {r["ohlc_sha256"]:r for r in reversed(group)}
            chosen = select_pilot(list(unique.values()), per_group, selection_seed)
            selected.extend(chosen)
            available = set().union(*(tags(r) for r in group)) if group else set()
            covered = set().union(*(tags(r) for r in chosen)) if chosen else set()
            wanted = {"motion:upward", "motion:downward", "motion:low_directionality",
                      "observed:breakout_proxy", "volatility:low", "volatility:high"}
            if source == "synthetic":
                wanted |= {"declared:mixed", "declared:consolidation", "declared:breakout"}
                wanted |= {"seed:"+str(seed) for seed in SEEDS}
            coverage.append({"symbol": symbol, "source": source, "available_count": len(group),
                             "selected_count": len(chosen), "covered": sorted(covered),
                             "missing_in_source": sorted(wanted-available),
                             "available_but_not_selected": sorted(available-covered)})
    findings = []
    for symbol, summary in summaries.items():
        if not summary["charts"]:
            findings.append(f"{symbol}: brak poprawnych serii syntetycznych; nie zastąpiono ich nowymi.")
            continue
        agreement = summary["declared_segment_direction_agreement"]
        mismatches = sum(v.get("opposite_or_flat",0) for v in agreement.values())
        findings.append(f"{symbol}: consolidation obejmuje {summary['candle_shares']['consolidation']:.1%} świec, breakout tylko {summary['candle_shares']['breakout']:.1%}. Złożona sekwencja consolidation → breakout → trend występuje {summary['consolidation_breakout_trend']} razy na {summary['charts']} wykresów. To słabiej reprezentowane krótkie sytuacje, nie brak całej kategorii.")
        findings.append(f"{symbol}: {mismatches} segmentów uptrend/downtrend ma znak netto przeciwny do deklaracji lub płaski ruch. Proxy wybicia wykrywa {summary['breakout_proxy_charts']}/{summary['charts']} okien; jest mało selektywne i nie wystarcza jako etykieta wybicia.")
        absent = [band for band in ("low","medium","high") if not summary['volatility_bands'].get(band)]
        if absent:
            findings.append(f"{symbol}: brak pasm zmienności {absent}.")
    findings.append("Strukturalnie nie ma wykresów zaczynających się od breakout ani więcej niż trzech faz; nie są to możliwości obecnego harmonogramu. Syntetyki nie odwzorowują luk czasu ani nieciągłości Open/Close rzeczywistych danych.")
    report = {"schema_version": 1, "status": "diagnostic_unapproved", "analyzed_count": len(synthetic),
              "methodology": "Netto: ostatnie Close / pierwsze Open − 1. Zakres: (max High − min Low) / pierwsze Open. Zmienność: próbne std 119 log-zwrotów Close–Close. Kierunkowość: |Close końcowe − Open początkowe| / suma |zmian| ścieżki Open0, Close0…Close119. Ruch upward/downward przy kierunkowości ≥0.18, low_directionality ≤0.08; pozostałe intermediate. To wskaźniki diagnostyczne, nie prawda o trendzie/konsolidacji. Proxy wybicia: Close poza ekstremami poprzednich 20 świec i |log-zwrot| > 2× próbne std poprzednich 19 zwrotów. Duża świeca: (H−L)/O ≥ treningowe q95; skrajny ruch: |log-zwrot| ≥ treningowe q99. Średnie korpusów/knotów względem H−L wyłącznie dla niepłaskich świec. Zmienność low ≤ treningowe q(1/3), medium ≤ q(2/3), high powyżej; progi osobno dla BTC/ETH z rozłącznych 120-świecowych okien. Kwantyle z interpolacją liniową. Brak etykietowania S/R.",
              "discovery": discovery, "completeness": completeness, "quality_errors": errors,
              "duplicate_ohlc": duplicates, "symbols": summaries, "thresholds": thresholds,
              "training_reference": reference, "training_bounds": {"start": start.isoformat(), "end": end.isoformat()},
              "data_access": {"analytical_ohlc": "train_only", "validation_test_ohlc_parsed": False,
                              "whole_source_bytes_hashed_for_integrity": True,
                              "note": "Czytane są bajty całego źródłowego CSV do SHA; parser kończy na pierwszym znaczniku czasu po treningu, bez analizy jego OHLC. Chronologiczny prefiks jest weryfikowany."},
              "runtime": {"python": platform.python_version(), "platform": platform.platform()},
              "findings": findings + ["Zróżnicowanie deklarowanych faz nie dowodzi różnorodności obserwowanych trajektorii. Sprawdź zgodność segmentów i statystyki ruchu.",
                           "Zmienność między oknami pozostaje ograniczeniem kandydata; wyliczony stosunek zależy od jawnej siatki referencji, więc nie musi być identyczny z poprzednimi raportami 48%/37%.",
                           "Rzadkość faz i sekwencji oceniaj po licznikach JSON, a luki selekcji po pilot.coverage. Kategorie proxy wymagają oceny wzrokowej; nie są etykietami modelu.",
                           "Pilotaż celowo pokrywa sytuacje i skrajności; nie reprezentuje częstości rynku ani finalnego zbioru. Sąsiednie realne okna kandydackie mają krok 60 i mogą się nakładać.",
                           "Żaden profil ani pilotaż nie został zatwierdzony. Nie odczytywano analitycznie OHLC validation/test i nie wykonano nowej generacji."],
              "missing_local_profile_files": sorted({r['profile_path'] for r in synthetic if r['profile_file_sha256'] is None}),
              "examples": [_public(r) for r in synthetic]}
    output.parent.mkdir(parents=True, exist_ok=True)
    with publication_workspace(output.parent, prefix=".charts-") as temporary:
        stage = temporary/"batch"
        pilot = stage/"pilot"
        pilot.mkdir(parents=True)
        images = []
        for i, record in enumerate(selected):
            filename = f"{i:03d}"
            metadata = dict(_public(record), selection_seed=selection_seed,
                            selection_version=SELECTION_VERSION, selection_tags=sorted(tags(record)),
                            png=f"{filename}.png", window_csv=f"{filename}.csv",
                            **render_window(record["candles"], pilot/f"{filename}.png"))
            write_candles_csv(pilot/f"{filename}.csv", record["candles"])
            metadata["window_csv_sha256"] = hashlib.sha256((pilot/f"{filename}.csv").read_bytes()).hexdigest()
            write_json(pilot/f"{filename}.json", metadata)
            images.append(metadata)
        report["pilot"] = {"selection_seed": selection_seed, "selection_version": SELECTION_VERSION,
                           "requested_count": 4*per_group, "actual_count": len(images), "coverage": coverage,
                           "images": images}
        report["source_integrity"] = ledger.verify()
        write_json(stage/"SOURCE_INTEGRITY.json", report["source_integrity"])
        write_json(pilot/"manifest.json", report["pilot"])
        write_json(stage/"AUDYT_ROZNORODNOSCI.json", report)
        (stage/"AUDYT_ROZNORODNOSCI.md").write_text(_audit_markdown(report), encoding="utf-8")
        write_json(stage/"run.json", {"status": "diagnostic_unapproved", "selection_seed": selection_seed,
                                     "synthetic_root": str(Path(synthetic_root).resolve()),
                                     "real_csv": {s:str(p.resolve()) for s,p in real_csv.items()},
                                     "config": str(config.resolve()), "output": str(output)})
        publish_directory(stage, output)
    return output

"""Koordynacja opisowego porównania z treningiem i zapisu raportów."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile

from ..storage import read_candles_csv, write_json
from ..synthetic.comparison import (COMPARISON_VERSION, aggregate_windows,
                                    load_synthetic_windows, statistical_differences)
from ..synthetic.selection import select_real_windows
from ..synthetic.training_period import ChronologicalSplit


def build_comparison(*, symbol: str, real_csv: Path, synthetic_manifest: Path,
                     start: datetime, end: datetime, count: int, selection_seed: int,
                     split: ChronologicalSplit) -> dict:
    """Zbuduj raport z rzeczywistych plików, bez zmieniania danych wejściowych."""
    split.require_training(start, end)
    candles = read_candles_csv(real_csv, source=str(real_csv))
    real, selection = select_real_windows(candles, symbol=symbol, start=start, end=end,
        count=count, seed=selection_seed, split=split)
    synthetic, provenance = load_synthetic_windows(synthetic_manifest, symbol=symbol, count=count, split=split)
    real_stats, synthetic_stats = aggregate_windows(real), aggregate_windows(synthetic)
    real_digest = hashlib.sha256(Path(real_csv).read_bytes()).hexdigest()
    warnings = ["Porównanie opisowe z treningiem użytym do kalibracji; nie jest niezależną walidacją.",
                "Parametry generatora nie zostały automatycznie zatwierdzone.",
                "Kontrola wizualna: oczekuje na implementację modułu wykresów.",
                "Profil kalibracyjny i porównanie odczytują pełny CSV; obliczenia cen dotyczą tylko treningu."]
    if provenance["profile"]["source"].get("sha256") != real_digest:
        warnings.append("Hash referencyjnego CSV różni się od źródła profilu; sprawdź pochodzenie obu plików.")
    report = {"version": COMPARISON_VERSION, "symbol": symbol, "split": split.document(),
              "real_source": {"path": str(Path(real_csv).resolve()), "sha256": real_digest},
              "selection": selection, "synthetic_source": provenance,
              "real": real_stats, "synthetic": synthetic_stats,
              "differences": statistical_differences(real_stats, synthetic_stats),
              "difference_definition": "synthetic_minus_real; signed, bez procentów i ilorazów",
              "aggregation": "pooled_observations: surowe wartości tylko wewnątrz okien; window_distributions: statystyki całych okien; kwantyle nigdy nie są uśredniane",
              "warnings": warnings, "visual_review": "pending_chart_renderer"}
    identity = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)
    report["comparison_id"] = hashlib.sha256(identity.encode()).hexdigest()[:24]
    return report


def comparison_summary(report: dict) -> str:
    """Zwięzła tabela do terminala i udostępnienia autorowi pracy."""
    lines = [f"# {report['symbol']} — opisowe porównanie z treningiem",
             f"Porównanie: {report['comparison_id']}; podział: {report['split']['split_id']}",
             f"Okna rzeczywiste: {report['real']['window_count']}; syntetyczne: {report['synthetic']['window_count']}",
             "", "| Metryka | Rzeczywiste | Syntetyczne | Różnica S-R |",
             "| --- | ---: | ---: | ---: |"]
    def row(label, a, b):
        if a is None or b is None:
            show = lambda value: "nieokreślona" if value is None else f"{value:.8g}"
            lines.append(f"| {label} | {show(a)} | {show(b)} | nieokreślona |")
        else:
            lines.append(f"| {label} | {a:.8g} | {b:.8g} | {b-a:.8g} |")
    for name in report["real"]["pooled_observations"]:
        a, b = (report[side]["pooled_observations"][name] for side in ("real", "synthetic"))
        row(f"{name}: średnia", a["mean"], b["mean"])
        if name == "log_returns":
            for metric in ("std", "min", "max"):
                row(f"{name}: {metric}", a[metric], b[metric])
    for name in report["real"]["window_distributions"]:
        a, b = (report[side]["window_distributions"][name] for side in ("real", "synthetic"))
        for metric in ("mean", "std"):
            row(f"okna/{name}: {metric}", a[metric], b[metric])
    row("abs(r): korelacja lag 1", report["real"]["absolute_return_lag1"]["value"],
        report["synthetic"]["absolute_return_lag1"]["value"])
    lines.extend(["", "Pełne kwantyle i statystyki są w JSON. Reżimy wyłącznie syntetyczne:",
                  json.dumps(report["synthetic_source"]["regimes"]["occurrences"], ensure_ascii=False), ""])
    lines.extend(f"- {warning}" for warning in report["warnings"])
    return "\n".join(lines) + "\n"


def save_comparison(output: Path, report: dict) -> Path:
    """Opublikuj JSON i Markdown razem, z odmową nadpisania istniejącej partii."""
    output = Path(output)
    resolved = output.resolve()
    protected = {Path("data/processed").resolve(), Path(__file__).resolve().parents[4] / "data/processed"}
    if any(resolved == p or p in resolved.parents for p in protected):
        raise ValueError("Raporty syntetyczne nie mogą być zapisywane w data/processed")
    final = output / report["comparison_id"]
    if final.exists():
        raise FileExistsError(f"Porównanie już istnieje (odmowa nadpisania): {final}")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".comparison-", dir=output) as temporary:
        stage = Path(temporary) / "report"
        stage.mkdir()
        write_json(stage / f"{report['symbol']}_comparison.json", report)
        (stage / f"{report['symbol']}_summary.md").write_text(comparison_summary(report), encoding="utf-8")
        stage.rename(final)
    return final

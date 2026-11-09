"""data_processing / synthetic / workflows / comparison."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from ...io.candles import read_candles_csv
from ..domain.diagnostics import COMPARISON_VERSION, aggregate_windows, statistical_differences
from ..io.batches import load_synthetic_windows
from ...windows.domain.selection import select_real_windows
from ....core.time.periods import ChronologicalSplit
from ....shared.json_io import write_json
from ....shared.publication import publication_workspace, publish_directory
from ..reporting.comparison import comparison_summary


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


def save_comparison(output: Path, report: dict, *, summary_text: str | None = None) -> Path:
    """Opublikuj JSON i Markdown razem, z odmową nadpisania istniejącej partii."""
    output = Path(output)
    resolved = output.resolve()
    protected = {Path("data/processed").resolve(), Path(__file__).resolve().parents[5] / "data/processed"}
    if any(resolved == p or p in resolved.parents for p in protected):
        raise ValueError("Raporty syntetyczne nie mogą być zapisywane w data/processed")
    final = output / report["comparison_id"]
    if final.exists():
        raise FileExistsError(f"Porównanie już istnieje (odmowa nadpisania): {final}")
    output.mkdir(parents=True, exist_ok=True)
    with publication_workspace(output, prefix=".comparison-") as temporary:
        stage = temporary / "report"
        stage.mkdir()
        write_json(stage / f"{report['symbol']}_comparison.json", report)
        (stage / f"{report['symbol']}_summary.md").write_text(
            comparison_summary(report) if summary_text is None else summary_text, encoding="utf-8")
        publish_directory(stage, final)
    return final

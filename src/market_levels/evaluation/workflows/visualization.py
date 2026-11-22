"""Read-only verification of existing test examples before visualization."""
from __future__ import annotations

from pathlib import Path

from ...charts.io.rendering import render_window
from ...data_processing.io.candles import read_candles_csv
from ...shared.integrity import sha256_file
from ...shared.paths import child
from ..domain.responses import parse_response
from ..domain.scoring import score_example
from ..io.inputs import read_references, read_predictions
from ..protocol import dumps, loads
from .verification import read_evaluation


def load_visualization_examples(dataset: Path, predictions: Path, evaluation: Path,
                                identities: list[str], verification: Path) -> tuple[list[dict], dict]:
    """Bind original OHLC, labels, raw predictions and official per-example scores."""
    if len(set(identities)) != len(identities):
        raise ValueError("Powtórzone ID wizualizacji")
    refs, binding, ledger = read_references(dataset, split="test")
    ledger.track(predictions)
    for path in evaluation.rglob("*"):
        if path.is_file():
            ledger.track(path)
    official = read_evaluation(evaluation)
    if loads(dumps(binding)) != official["binding"] or official["run"]["variant"] != "finetuned":
        raise ValueError("Wynik nie odpowiada testowi dostrojonego modelu dla wskazanego zbioru")
    raw = read_predictions(predictions, refs, binding)
    if predictions.read_bytes() != (evaluation/"predictions.jsonl").read_bytes():
        raise ValueError("Predykcje różnią się od oficjalnie ocenionego pliku")
    reference_by_id = {r.id: r for r in refs}
    rows = {r["id"]: r for r in official["rows"]}
    entries = {r["id"]: r for r in loads((dataset/"manifest.json").read_text(encoding="utf-8"))["entries"]}
    if set(identities)-reference_by_id.keys():
        raise ValueError("ID nie należy do zbioru testowego")
    verification.mkdir(parents=True, exist_ok=True)
    examples, checks = [], []
    for identity in identities:
        ref = reference_by_id[identity]
        response = parse_response(raw[identity])
        if response.levels is None:
            raise ValueError(f"Niepoprawny JSON modelu: {identity}")
        score = score_example(ref, response)
        if score != rows[identity]:
            raise ValueError(f"Metryki nie odpowiadają oficjalnemu wynikowi: {identity}")
        entry = entries[identity]
        candles = read_candles_csv(child(dataset, entry["ohlc"]), source="thesis-visualization")
        original = child(dataset, entry["image"])
        regenerated = verification/f"{identity}_original.png"
        render_window(candles, regenerated)
        original_hash, regenerated_hash = sha256_file(original), sha256_file(regenerated)
        check = {"id": identity, "symbol": ref.symbol, "reference": ref.levels,
                 "predicted": response.levels, "raw_response": response.raw,
                 "score_at_0.5_atr": score["scores"]["0.5"],
                 "original_png_sha256": original_hash, "regenerated_png_sha256": regenerated_hash,
                 "original_png_byte_identical": original_hash == regenerated_hash}
        checks.append(check)
        if original_hash != regenerated_hash:
            raise ValueError(f"Odtworzony PNG różni się od oryginału {identity}; "
                             f"porównaj {original} i {regenerated} oraz wersję Matplotlib")
        examples.append({"reference": ref, "predicted": response.levels, "candles": candles,
                         "score": score})
    return examples, {"examples": checks, "sources": ledger.verify()}

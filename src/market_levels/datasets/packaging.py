"""Portable diagnostic examples, exact JSON labels, replay and integrity."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import tempfile

from ..charts.diversity import window_metrics
from ..charts.renderer import render_window, require_short_path, VISUALIZATION, RENDERER_VERSION
from ..data_processing.staging import publication_workspace, publish_directory
from ..data_processing.storage import read_candles_csv, write_candles_csv, write_json
from ..data_processing.synthetic.quality import canonical_hash, distribution
from ..data_processing.synthetic.v2_parameters import V2_VERSION
from ..labeling.algorithm import label_window, VERSION
from ..labeling.pilot import child, read_pilot, sha256
from .planning import SYMBOLS

INSTRUCTION_VERSION = "pl-sr-v1"
INSTRUCTION = ("Przeanalizuj przedstawiony wykres świecowy. Wskaż maksymalnie trzy poziomy wsparcia "
               "i trzy poziomy oporu. Zwróć wyłącznie obiekt JSON z polami supports i resistances, "
               "zawierającymi listy wartości cenowych.")


def diagnostic_records(pilot: Path, per_group: int = 2) -> tuple[list, dict]:
    """Reuse already generated pilot OHLC; never generate new synthetic data."""
    if type(per_group) is not int or not 1 <= per_group <= 2:
        raise ValueError("Mała próba: 1–2 przykłady na symbol i źródło")
    loaded, ledger = read_pilot(pilot)
    selected = []
    for symbol in SYMBOLS:
        for source in ("real", "synthetic"):
            group = sorted([(r, c) for r, c in loaded if r["symbol"] == symbol and r["source"] == source],
                           key=lambda pair: pair[0]["id"])
            if len(group) < per_group:
                raise ValueError("Brak wymaganej grupy pilotażu")
            selected.extend(group[:per_group])
    return selected, ledger


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


def _example_line(identity: str, image: str, answer: str) -> str:
    # Insert the algorithm's exact numeric JSON directly, retaining two decimal places.
    fields = {"id": identity, "split": None, "image": image, "instruction": INSTRUCTION}
    return json.dumps(fields, ensure_ascii=False)[:-1]+', "answer": '+answer.strip()+'}\n'


def _metadata(record: dict, candles: list, result, rendering: dict, identity: str) -> dict:
    answer = json.loads(result.target_json())
    return {"id": identity, "symbol": record["symbol"], "source": record["source"],
            "split": None, "diagnostic_only": True, "source_metadata": record,
            "start_utc": candles[0].timestamp.isoformat() if record["source"] == "real" else None,
            "end_utc": candles[-1].timestamp.isoformat() if record["source"] == "real" else None,
            "generator_version": V2_VERSION if record["source"] == "synthetic" else None,
            "profile_id": record.get("profile_sha256"), "seed": record.get("seed"),
            "master_seed": record.get("master_seed"), "ohlc_sha256": canonical_hash(candles),
            "support_count": len(answer["supports"]), "resistance_count": len(answer["resistances"]),
            "metrics": window_metrics(candles), "rendering": rendering,
            "algorithm_version": VERSION, "instruction_version": INSTRUCTION_VERSION,
            "source_reproduction": "Pinned source pilot metadata, copied exact OHLC; same renderer and labeling versions. No overlays."}


def seal(stage: Path, payload: dict) -> None:
    files = {p.relative_to(stage).as_posix(): sha256(p) for p in sorted(stage.rglob("*")) if p.is_file()}
    write_json(stage/"manifest.json", dict(payload, files=files))
    (stage/"manifest.sha256").write_text(sha256(stage/"manifest.json")+"\n", encoding="ascii")


def verify_files(output: Path) -> dict:
    manifest_path = output/"manifest.json"
    if (output/"manifest.sha256").read_text(encoding="ascii").strip() != sha256(manifest_path):
        raise ValueError("Niezgodny hash manifestu")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
    if actual != set(manifest["files"]) | {"manifest.json", "manifest.sha256"}:
        raise ValueError("Niezgodny inwentarz plików")
    for name, digest in manifest["files"].items():
        if sha256(child(output, name)) != digest:
            raise ValueError(f"Niezgodny hash pliku: {name}")
    return manifest


def publish_plan(plan: dict, output: Path) -> Path:
    output = diagnostic_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with publication_workspace(output.parent, prefix=".ds-") as temporary:
        stage = temporary/"batch"
        stage.mkdir()
        write_json(stage/"plan.json", plan)
        seal(stage, {"schema_version": 1, "kind": "preflight_plan", "status": "plan_only_not_dataset"})
        verify_files(stage)
        publish_directory(stage, output)
    return output


def diagnostic_output(output: Path, *, source: Path | None = None) -> Path:
    output = Path(output).resolve()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Odmowa nadpisania: {output}")
    allowed = Path("results/diagnostics").resolve()
    if allowed not in output.parents or (source is not None and source.resolve() in output.parents):
        raise ValueError("Wynik wymaga nowego katalogu results/diagnostics poza źródłem")
    for root in (output, output.parent/(".ds-"+"x"*8)/"batch"):
        require_short_path(root/"metadata/007.json")
        require_short_path(root/"SOURCE_INTEGRITY.json")
    return output


def run_smoke(pilot: Path, output: Path, *, per_group: int = 2) -> Path:
    output = diagnostic_output(output, source=pilot)
    selected, ledger = diagnostic_records(pilot, per_group)
    output.parent.mkdir(parents=True, exist_ok=True)
    with publication_workspace(output.parent, prefix=".ds-") as temporary:
        stage = temporary/"batch"
        for name in ("images", "ohlc", "labels", "metadata"):
            (stage/name).mkdir(parents=True)
        entries, metadata, seen, lines = [], [], set(), []
        for i, (record, candles) in enumerate(selected):
            digest = canonical_hash(candles)
            if digest in seen:
                raise ValueError("Duplikat OHLC próby technicznej")
            seen.add(digest)
            if record["visualization"] != VISUALIZATION or record["renderer_version"] != RENDERER_VERSION:
                raise ValueError("Wejście musi być oryginalnym wykresem bez poziomów")
            result = label_window(candles)
            names = {"image": f"images/{i:03d}.png", "ohlc": f"ohlc/{i:03d}.csv",
                     "label": f"labels/{i:03d}.json", "metadata": f"metadata/{i:03d}.json"}
            rendering = render_window(candles, stage/names["image"])
            if rendering["png_sha256"] != record["png_sha256"]:
                raise ValueError("Obraz nie odtwarza oryginalnego pilotażu; sprawdź środowisko")
            write_candles_csv(stage/names["ohlc"], candles)
            (stage/names["label"]).write_text(result.target_json(), encoding="utf-8")
            identity = hashlib.sha256((record["symbol"]+":"+record["source"]+":"+record["id"]+":"+digest).encode()).hexdigest()[:24]
            meta = _metadata(record, candles, result, rendering, identity)
            meta.update(csv_sha256=sha256(stage/names["ohlc"]), label_sha256=sha256(stage/names["label"]))
            write_json(stage/names["metadata"], meta)
            entries.append(dict(id=identity, **names))
            metadata.append(meta)
            lines.append(_example_line(identity, names["image"], result.target_json()))
        (stage/"examples.jsonl").write_text("".join(lines), encoding="utf-8")
        write_json(stage/"summary.json", summarize(metadata))
        if any(sha256(Path(p)) != digest for p, digest in ledger.items()):
            raise ValueError("Źródło zmieniło się podczas próby")
        write_json(stage/"SOURCE_INTEGRITY.json", {"unchanged": True, "files": ledger})
        seal(stage, {"schema_version": 1, "kind": "diagnostic_smoke", "status": "diagnostic_only_not_final_splits",
                     "count": len(entries), "entries": entries, "runtime": {"python": platform.python_version()},
                     "algorithm_version": VERSION, "instruction_version": INSTRUCTION_VERSION})
        verify_smoke(stage, re_render=True)
        publish_directory(stage, output)
    return output


def verify_smoke(output: Path, *, re_render: bool = True) -> dict:
    """Replay from copied OHLC without original large files; verify every binding."""
    manifest = verify_files(output)
    if (manifest["kind"] != "diagnostic_smoke" or manifest["status"] != "diagnostic_only_not_final_splits"
            or manifest["algorithm_version"] != VERSION or manifest["instruction_version"] != INSTRUCTION_VERSION):
        raise ValueError("Niezgodny schemat/status/wersja próby")
    rows = [json.loads(line) for line in (output/"examples.jsonl").read_text(encoding="utf-8").splitlines()]
    entries = manifest["entries"]
    if manifest["count"] != len(rows) or len(rows) != len(entries) or not 4 <= len(rows) <= 8:
        raise ValueError("Niepoprawna liczba przykładów")
    integrity = json.loads((output/"SOURCE_INTEGRITY.json").read_text(encoding="utf-8"))
    if integrity["unchanged"] is not True or not integrity["files"]:
        raise ValueError("Brak kontroli integralności źródła")
    source_hashes = set(integrity["files"].values())
    seen, ids, metadata, lines = set(), set(), [], []
    expected_files = {"examples.jsonl", "summary.json", "SOURCE_INTEGRITY.json"}
    with tempfile.TemporaryDirectory(prefix="ds-verify-") as temporary:
        for i, (row, entry) in enumerate(zip(rows, entries)):
            names = {"image": f"images/{i:03d}.png", "ohlc": f"ohlc/{i:03d}.csv",
                     "label": f"labels/{i:03d}.json", "metadata": f"metadata/{i:03d}.json"}
            if set(entry) != {"id", *names} or any(entry[k] != v for k, v in names.items()):
                raise ValueError("Niezgodne ścieżki przykładów")
            expected_files.update(names.values())
            meta = json.loads(child(output, entry["metadata"]).read_text(encoding="utf-8"))
            record = meta["source_metadata"]
            candles = read_candles_csv(child(output, entry["ohlc"]), source="dataset-replay")
            result = label_window(candles)
            digest = canonical_hash(candles)
            identity = hashlib.sha256((record["symbol"]+":"+record["source"]+":"+record["id"]+":"+digest).encode()).hexdigest()[:24]
            if digest in seen or identity in ids:
                raise ValueError("Duplikat przykładu")
            seen.add(digest)
            ids.add(identity)
            if record["symbol"] not in SYMBOLS or record["source"] not in ("real", "synthetic") or not record["id"].startswith(record["symbol"]+"_"):
                raise ValueError("Niezgodny symbol/źródło")
            if (record["source"] == "real" and (record["start_utc"] != candles[0].timestamp.isoformat()
                    or record["end_utc"] != candles[-1].timestamp.isoformat())):
                raise ValueError("Niezgodny zakres czasowy źródła")
            if record["source"] == "synthetic" and (record.get("variant") != "V2-full-refined" or type(record.get("seed")) is not int or not record.get("profile_sha256")):
                raise ValueError("Brak pochodzenia syntetyka")
            if record["visualization"] != VISUALIZATION or record["renderer_version"] != RENDERER_VERSION:
                raise ValueError("Niedozwolony obraz wejściowy")
            if digest != record["ohlc_sha256"] or sha256(child(output, entry["image"])) != record["png_sha256"]:
                raise ValueError("Niezgodne wiązanie obrazu/OHLC ze źródłem")
            if record["png_sha256"] not in source_hashes or record["window_csv_sha256"] not in source_hashes or sha256(child(output, entry["ohlc"])) != record["window_csv_sha256"]:
                raise ValueError("Brak wiązania z inwentarzem źródłowym")
            rendering = meta["rendering"]
            if re_render:
                rendering = render_window(candles, Path(temporary)/f"{i:03d}.png")
                if rendering != meta["rendering"]:
                    raise ValueError("Niezgodny odtworzony PNG; kontrola braku linii")
            expected = _metadata(record, candles, result, rendering, identity)
            expected.update(csv_sha256=sha256(child(output, entry["ohlc"])), label_sha256=sha256(child(output, entry["label"])))
            if expected != meta or entry["id"] != identity:
                raise ValueError("Niezgodne metadane")
            if child(output, entry["label"]).read_text(encoding="utf-8") != result.target_json():
                raise ValueError("Niezgodna etykieta")
            line = _example_line(identity, entry["image"], result.target_json())
            if row != json.loads(line):
                raise ValueError("Niezgodny przykład modelu")
            lines.append(line)
            metadata.append(meta)
    if set(manifest["files"]) != expected_files:
        raise ValueError("Niekompletny manifest")
    if (output/"examples.jsonl").read_text(encoding="utf-8") != "".join(lines):
        raise ValueError("Niezgodna serializacja JSONL")
    summary = summarize(metadata)
    if json.loads((output/"summary.json").read_text(encoding="utf-8")) != summary:
        raise ValueError("Niezgodny audyt struktury")
    if set(summary["by_symbol_source"]) != {s+"/"+source for s in SYMBOLS for source in ("real", "synthetic")}:
        raise ValueError("Niekompletne grupy instrument/źródło")
    return {"verified": True, "count": len(rows), "re_rendered": re_render, "final_dataset": False}

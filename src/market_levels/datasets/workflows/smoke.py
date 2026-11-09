"""datasets / workflows / smoke."""
from __future__ import annotations

import hashlib
import platform
from pathlib import Path

from ...charts.io.pilot import read_pilot
from ..config import SYMBOLS
from ...charts.io.rendering import render_window
from ...charts.config import VISUALIZATION, RENDERER_VERSION
from ...shared.publication import publication_workspace, publish_directory
from ...data_processing.io.candles import write_candles_csv
from ...shared.json_io import write_json
from ...core.ohlc.identity import canonical_hash
from ...labeling.domain.algorithm import label_window
from ...labeling.domain.models import VERSION
from ...shared.integrity import sha256_file as sha256
from ..domain.examples import INSTRUCTION_VERSION, _example_line, _metadata
from ..domain.audit import summarize
from ...shared.manifests import seal
from ..io.outputs import diagnostic_output
from .verification import verify_smoke


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

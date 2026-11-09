"""labeling / workflows / pilot."""
from __future__ import annotations

import platform
from pathlib import Path

from ...shared.paths import require_short_path
from ...shared.publication import publication_workspace, publish_directory
from ...shared.json_io import write_json
from ..domain.models import VERSION
from ..domain.algorithm import label_window
from ...shared.integrity import sha256_file as sha256
from ...charts.io.pilot import read_pilot
from ..io.overlays import render_levels
from ..reporting.pilot import summarize, report_markdown


def run_labeling(*, pilot: Path, output: Path) -> Path:
    pilot, output = Path(pilot).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"Odmowa nadpisania: {output}")
    allowed = Path("results/diagnostics").resolve()
    if allowed not in output.parents or pilot == output or pilot in output.parents:
        raise ValueError("Wynik musi być nowym katalogiem pod results/diagnostics poza źródłowym pilotażem")
    for name in ("diagnostics/031.json", "SOURCE_INTEGRITY.json", "overlays/031.png"):
        require_short_path(output/name)
        require_short_path(output.parent/(".labels-"+"x"*8)/"batch"/name)
    loaded, ledger = read_pilot(pilot)
    results = [(record, label_window(candles)) for record, candles in loaded]
    output.parent.mkdir(parents=True, exist_ok=True)
    with publication_workspace(output.parent, prefix=".labels-") as temporary:
        stage = temporary/"batch"
        for name in ("labels", "diagnostics", "overlays"):
            (stage/name).mkdir(parents=True)
        images = []
        for i, ((record, candles), (_, result)) in enumerate(zip(loaded, results)):
            names = {"label": f"labels/{i:03d}.json", "diagnostic": f"diagnostics/{i:03d}.json",
                     "overlay": f"overlays/{i:03d}.png"}
            (stage/names["label"]).write_text(result.target_json(), encoding="utf-8")
            write_json(stage/names["diagnostic"], dict(result.diagnostics(), source_metadata=record,
                                                     overlay_is_vlm_input=False))
            render_levels(candles, result, stage/names["overlay"])
            images.append(dict(id=record["id"], source_png=record["png"], source_csv=record["window_csv"],
                               source_png_sha256=record["png_sha256"], source_csv_sha256=record["window_csv_sha256"],
                               ohlc_sha256=record["ohlc_sha256"], **names))
        summary = summarize(results)
        write_json(stage/"summary.json", summary)
        (stage/"RAPORT.md").write_text(report_markdown(results, summary), encoding="utf-8")
        if any(sha256(Path(p)) != digest for p, digest in ledger.items()):
            raise ValueError("Zmiana źródła w trakcie etykietowania")
        write_json(stage/"SOURCE_INTEGRITY.json", {"unchanged": True, "files": ledger})
        files = {p.relative_to(stage).as_posix(): sha256(p) for p in sorted(stage.rglob("*")) if p.is_file()}
        import matplotlib
        write_json(stage/"manifest.json", {"schema_version": 1, "algorithm_version": VERSION,
                                          "status": "diagnostic_unapproved", "overlay_is_vlm_input": False,
                                          "pilot": str(pilot), "count": 32, "images": images, "files": files,
                                          "runtime": {"python": platform.python_version(), "matplotlib": matplotlib.__version__}})
        publish_directory(stage, output)
    return output

"""datasets / workflows / approval."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ...data_processing.synthetic.domain.profiles.v1 import approve_profile, profile_hash
from ...data_processing.synthetic.domain.profiles.validation import validate_profile_v2
from ...core.time.periods import ChronologicalSplit
from ...shared.integrity import SourceLedger
from ...shared.publication import publication_workspace, publish_directory
from ...shared.json_io import write_json
from ...data_processing.synthetic.io.profiles import load_profile
from ...data_processing.io.chronology import load_chronological_split
from ..config import SYMBOLS
from .planning import build_plan
from ...shared.manifests import seal


def approve_refined(profile: dict, split: ChronologicalSplit, *, decision_date: str,
                    original_file_sha256: str) -> dict:
    validate_profile_v2(profile)
    if (profile["status"] != "unapproved" or profile["estimation_kind"] != "training"
            or profile["calibration"]["method"] != "volatility_refinement_v1"
            or profile["calibration"]["variant"] != "full"
            or profile["source"]["chronological_split"] != split.document()):
        raise ValueError("Zatwierdzenie wymaga treningowego V2-full-refined unapproved")
    datetime.strptime(decision_date, "%Y-%m-%d")
    # Reuse the existing explicit approval procedure for the common empirical schema.
    result = approve_profile(dict(profile, version=1), training_start=split.periods["train"][0],
                             training_end=split.periods["train"][1], split_id=split.split_id,
                             reviewed_by="autor pracy")
    result["version"] = 2
    result["approval"].update(decision_date=decision_date, scope="pierwszy zbiór 800 przykładów, etap 3.5 część 2",
        original_profile_sha256=profile_hash(profile), original_file_sha256=original_file_sha256,
        basis="Jawna decyzja autora pracy z 2026-11-07; audyty V2-full-refined i kontrola pochodzenia na treningu")
    if {k: v for k, v in result.items() if k not in ("status", "approval")} != {k: v for k, v in profile.items() if k not in ("status", "approval")}:
        raise ValueError("Zatwierdzenie zmieniło dane kalibracji")
    validate_profile_v2(result)
    return result


def approve_configured_profiles(config: Path, real_csv: dict[str, Path], output: Path,
                                *, audit: Path, decision_date: str) -> Path:
    """Verify selected profile identities against the existing 600-series audit."""
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"Odmowa nadpisania: {output}")
    ledger = SourceLedger()
    ledger.track(config)
    ledger.track(audit)
    plan = build_plan(config, real_csv)
    if not plan["real_feasible"]:
        raise ValueError("Preflight przed zatwierdzeniem nie potwierdził danych")
    report = json.loads(audit.read_text(encoding="utf-8"))
    if report["analyzed_count"] != len(report["examples"]) or report["quality_errors"] or report["duplicate_ohlc"]:
        raise ValueError("Niekompletny lub niepoprawny wcześniejszy audyt")
    approved, rows = {}, []
    split = load_chronological_split(config)
    for symbol in SYMBOLS:
        entry = plan["synthetic"]["profiles"][symbol]
        path = ledger.track(Path(entry["path"]))
        original = load_profile(path, symbol=symbol)
        matches = [r for r in report["examples"] if r["symbol"] == symbol]
        if not matches or any(r["profile_sha256"] != profile_hash(original) or r["variant"] != "V2-full-refined" for r in matches):
            raise ValueError("Audyt nie dotyczy wskazanego profilu")
        approved[symbol] = approve_refined(original, split, decision_date=decision_date,
                                           original_file_sha256=ledger.files[str(path)])
        rows.append({"symbol": symbol, "original_path": str(path), "original_profile_id": profile_hash(original),
                     "original_file_sha256": ledger.files[str(path)], "approved_profile_id": profile_hash(approved[symbol]),
                     "audit_examples": len(matches), "parameters_unchanged": True})
    output.parent.mkdir(parents=True, exist_ok=True)
    with publication_workspace(output.parent, prefix=".approve-") as tmp:
        stage = tmp/"batch"
        stage.mkdir()
        for symbol in SYMBOLS:
            write_json(stage/f"{symbol}_full_refined_approved.json", approved[symbol])
        write_json(stage/"approval.json", {"decision_date": decision_date, "reviewed_by": "autor pracy",
            "profiles": rows, "preapproval_plan": plan, "source_integrity": ledger.verify(),
            "limitations": report["findings"]})
        seal(stage, {"kind": "approved_profiles", "schema_version": 1})
        publish_directory(stage, output)
    return output

"""data_processing / synthetic / workflows / summary."""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from ....core.numeric.statistics import distribution
from ..domain.profiles.v1 import profile_hash
from ..domain.diagnostics import metric_values, refinement_review


def build_variant_summary(paths: list[Path], *, symbol: str) -> dict:
    """Łącz tylko raporty z identyczną referencją i zapisz rozrzut między seedami."""
    if not paths:
        raise ValueError("Brak raportów wariantów")
    reports, identities, groups = [], set(), defaultdict(list)
    reference_identity, reference_metrics = None, None
    loaded = [(Path(path), json.loads(Path(path).read_text(encoding="utf-8-sig"))) for path in paths]
    refinement_mode = any(r.get("synthetic_source", {}).get("profile", {}).get("calibration", {}).get("method")
                          == "volatility_refinement_v1" for _, r in loaded)
    refinement_profiles = {}
    for path, report in loaded:
        if not isinstance(report, dict) or report.get("symbol") != symbol:
            raise ValueError("Raport ma niewłaściwy instrument lub format")
        without_id = {k: v for k, v in report.items() if k != "comparison_id"}
        digest = hashlib.sha256(json.dumps(without_id, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()[:24]
        if digest != report["comparison_id"] or digest in identities:
            raise ValueError("Niepoprawny hash raportu lub powtórzony raport")
        identities.add(digest)
        reference = {"sha256": report["real_source"]["sha256"], "split": report["split"],
                     "selection": report["selection"]}
        metrics = metric_values(report["real"])
        if reference_identity is None:
            reference_identity, reference_metrics = reference, metrics
        elif reference != reference_identity or metrics != reference_metrics:
            raise ValueError("Warianty wymagają identycznych rzeczywistych okien i statystyk referencyjnych")
        source = report["synthetic_source"]
        if profile_hash(source["profile"]) != source["profile_sha256"]:
            raise ValueError("Hash profilu nie zgadza się z zawartością raportu")
        version = source.get("generator_version", source["profile"].get("generator_version", "1.0.0"))
        if version == "1.0.0" and source["profile"]["version"] == 1:
            label = "V1"
        elif version == "2.0.0" and source["profile"]["version"] == 2:
            from ..domain.parameters import VARIANTS
            if source["variant"] not in VARIANTS:
                raise ValueError("Nieznany wariant w raporcie v2")
            label = "V2-" + source["variant"]
            if source["profile"].get("calibration", {}).get("method") == "volatility_refinement_v1":
                from ..domain.profiles.validation import validate_profile_v2
                validate_profile_v2(source["profile"], symbol=symbol)
                if source["profile"]["calibration"]["variant"] != source["variant"]:
                    raise ValueError("Wariant raportu nie odpowiada profilowi refinement")
                label += "-refined"
                refinement_profiles[label] = source["profile"]
            elif refinement_mode and source["variant"] == "full":
                label += "-original"
        else:
            raise ValueError("Niespójna wersja raportu generatora")
        item = {"path": str(Path(path).resolve()), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                "comparison_id": digest, "run_id": source["run_id"],
                "master_seed": source.get("master_seed"), "variant": label,
                "profile_sha256": source["profile_sha256"], "profile_status": source["profile_status"],
                "example_seeds": [entry["seed"] for entry in source["examples"]],
                "metrics": metric_values(report["synthetic"]), "regimes": source["regimes"],
                "invalid_examples": source.get("invalid_examples", 0),
                "duplicate_examples": source.get("duplicate_examples", 0)}
        if refinement_mode:
            item.update(mechanism_variant=source.get("variant", "v1"),
                        calibration_method=source["profile"].get("calibration", {}).get("method", "v1"),
                        profile_family="refined" if label.endswith("-refined") else "original")
        if any(previous["run_id"] == item["run_id"] for previous in groups[label]):
            raise ValueError("Powtórzona partia nie może udawać niezależnego seeda")
        if groups[label] and any(previous["profile_sha256"] != item["profile_sha256"] for previous in groups[label]):
            raise ValueError("Powtórzenia wariantu muszą używać tego samego profilu")
        if item["master_seed"] is not None and any(previous["master_seed"] == item["master_seed"] for previous in groups[label]):
            raise ValueError("Powtórzenia wariantu wymagają różnych seedów głównych")
        if any(set(previous["example_seeds"]) & set(item["example_seeds"]) for previous in groups[label]):
            raise ValueError("Powtórzenia wariantu nie mogą współdzielić seedów przykładów")
        groups[label].append(item)
        reports.append(item)
    if "V1" not in groups:
        raise ValueError("Raport zbiorczy wymaga V1 jako jawnego punktu odniesienia")
    variants = {}
    for label, items in groups.items():
        metrics = {}
        for name, target in reference_metrics.items():
            values = [r["metrics"][name] for r in items if r["metrics"][name] is not None]
            if not values or target is None:
                metrics[name] = {"value": None, "reason": "undefined_metric", "count": len(values)}
                continue
            metrics[name] = {"value": distribution(values)["mean"], "std_between_seeds": distribution(values)["std"],
                             "difference": distribution(values)["mean"] - target,
                             "mean_absolute_error": math.fsum(abs(v-target) for v in values)/len(values),
                             "count": len(values)}
        variants[label] = {"run_count": len(items), "metrics": metrics,
                           "invalid_examples": sum(item["invalid_examples"] for item in items),
                           "duplicate_examples": sum(item["duplicate_examples"] for item in items)}
    for label, variant in variants.items():
        for name, metric in variant["metrics"].items():
            baseline = variants["V1"]["metrics"][name]
            if "mean_absolute_error" in metric and "mean_absolute_error" in baseline:
                change = metric["mean_absolute_error"] - baseline["mean_absolute_error"]
                metric["absolute_error_change_vs_v1"] = change
                metric["error_direction"] = "unchanged" if math.isclose(change, 0, abs_tol=1e-15) else ("decreased" if change < 0 else "increased")
    result = {"version": 1, "report_kind": "variant_summary", "symbol": symbol,
              "reference": reference_identity, "real_metrics": reference_metrics, "variants": variants,
              "reports": reports, "warnings": ["Opisowe porównanie z treningiem; nie jest niezależną walidacją.",
                  "Co najmniej trzy niezależne seedy są zalecane do właściwej oceny.",
                  "Nie wybrano automatycznie najlepszego wariantu i nie zatwierdzono profili.",
                  "Błędy to średnie błędy bezwzględne po seedach; rozrzut po seedach zapisano osobno.",
                  "Zera odrzuceń/duplikatów dotyczą zaakceptowanych partii; błędy fail-fast nie publikują partii."]}
    if refinement_mode:
        result["refinement_review"] = refinement_review(result, refinement_profiles)
    result["comparison_id"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()[:24]
    return result

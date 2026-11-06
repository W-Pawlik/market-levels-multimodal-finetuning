"""Zbiorcza ocena wariantów na identycznych oknach, bez automatycznej akceptacji."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

from .quality import distribution
from .calibration import profile_hash


def metric_values(stats: dict) -> dict:
    """Wspólne metryki raportów v1/v2; podstawowe statystyki nie są liczone ponownie."""
    pooled, windows = stats["pooled_observations"], stats["window_distributions"]
    metrics = {"return_mean": pooled["log_returns"]["mean"], "return_std": pooled["log_returns"]["std"],
               "abs_ac1": stats["absolute_return_lag1"]["value"]}
    for q in ("0.95", "0.99"):
        metrics[f"abs_return_q{q}"] = pooled["absolute_log_returns"]["quantiles"][q]
    for name in ("relative_range", "body_fraction", "upper_wick_fraction", "lower_wick_fraction"):
        metrics[f"{name}_mean"] = pooled[name]["mean"]
    for q, value in pooled["relative_range"]["quantiles"].items():
        metrics[f"relative_range_q{q}"] = value
    for name in ("return_std", "close_change", "relative_range"):
        for metric in ("mean", "std"):
            metrics[f"window_{name}_{metric}"] = windows[name][metric]
    return metrics


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
            from .v2_parameters import VARIANTS
            if source["variant"] not in VARIANTS:
                raise ValueError("Nieznany wariant w raporcie v2")
            label = "V2-" + source["variant"]
            if source["profile"].get("calibration", {}).get("method") == "volatility_refinement_v1":
                from .profile_v2 import validate_profile_v2
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


def variant_summary_markdown(report: dict) -> str:
    preferred = ("V1", "V2-base", "V2-bridge", "V2-tails", "V2-volatility", "V2-full",
                 "V2-full-original", "V2-full-refined", "V2-bridge_volatility-refined")
    order = [name for name in preferred if name in report["variants"]]
    order += sorted(set(report["variants"]) - set(order))
    lines = [f"# {report['symbol']}: V1 i warianty V2", "",
             "| Metryka | Realne | " + " | ".join(order) + " |",
             "| --- | ---: | " + " | ".join("---:" for _ in order) + " |"]
    fmt = lambda v: "nieokreślona" if v is None else f"{v:.7g}"
    for name, target in report["real_metrics"].items():
        lines.append("| " + name + " | " + fmt(target) + " | " + " | ".join(
            fmt(report["variants"][variant]["metrics"][name]["value"]) for variant in order) + " |")
    lines.extend(["", "| Wariant / metryka | Śr. błąd bezwzględny | Zmiana błędu względem V1 | Ocena kierunku |",
                  "| --- | ---: | ---: | --- |"])
    for label in order:
        for name, metric in report["variants"][label]["metrics"].items():
            lines.append(f"| {label}/{name} | {fmt(metric.get('mean_absolute_error'))} | "
                         f"{fmt(metric.get('absolute_error_change_vs_v1'))} | {metric.get('error_direction', 'undefined')} |")
    lines.extend(["", "| Wariant / metryka | Odchylenie standardowe między seedami |",
                  "| --- | ---: |"])
    for label in order:
        for name, metric in report["variants"][label]["metrics"].items():
            lines.append(f"| {label}/{name} | {fmt(metric.get('std_between_seeds'))} |")
    if "refinement_review" in report:
        lines.extend(["", "## Diagnostyka refinement", "", "```json",
                      json.dumps(report["refinement_review"], ensure_ascii=False, indent=2), "```"])
    lines.extend(["", "Liczba powtórzeń: " + ", ".join(f"{v}={report['variants'][v]['run_count']}" for v in order), ""])
    lines.extend("- " + warning for warning in report["warnings"])
    return "\n".join(lines) + "\n"


REFINEMENT_METRICS = dict(abs_ac1="abs_ac1", window_std_mean="window_return_std_mean",
    window_std_std="window_return_std_std", abs_q95="abs_return_q0.95", abs_q99="abs_return_q0.99",
    range_mean="relative_range_mean", body_fraction="body_fraction_mean",
    upper_wick="upper_wick_fraction_mean", lower_wick="lower_wick_fraction_mean")


def refinement_review(report: dict, profiles: dict) -> dict:
    """Opis tolerancji i ablacji; bez wskazywania zwycięzcy lub akceptacji."""
    from .refinement import RefinementSettings, PRIORITY, error_scale
    required = {"V1", "V2-full-original", "V2-full-refined", "V2-bridge_volatility-refined"}
    if not required <= set(report["variants"]):
        raise ValueError("Porównanie refinement wymaga V1, full-original i obu osobno dostrojonych profili")
    parent_hashes = {p["calibration"]["source_profile_sha256"] for p in profiles.values()}
    originals = {r["profile_sha256"] for r in report["reports"] if r["variant"] == "V2-full-original"}
    if len(parent_hashes) != 1 or parent_hashes != originals:
        raise ValueError("Profile refinement muszą pochodzić z porównywanego full-original")
    policies = [p["calibration"]["search"] for p in profiles.values()]
    if any(p != policies[0] for p in policies):
        raise ValueError("Porównanie refinement wymaga jednakowej polityki diagnostycznej")
    policy = RefinementSettings(**policies[0])
    # Ocena parami wymaga takich samych seedów i liczby przykładów.
    seed_sets = [{(r["master_seed"], len(r["example_seeds"])) for r in report["reports"] if r["variant"] == label}
                 for label in sorted(required)]
    if any(s != seed_sets[0] for s in seed_sets) or any(seed is None for seed, _ in seed_sets[0]):
        raise ValueError("Bezpośrednie porównanie wymaga tych samych seedów i liczności we wszystkich czterech grupach")
    groups, mixture = {}, {}
    for label in sorted(required):
        rows, counts = {}, {"improved": 0, "worsened": 0, "practically_unchanged": 0, "undefined": 0}
        priority_counts = dict(counts)
        for feature, metric_name in REFINEMENT_METRICS.items():
            target = report["real_metrics"][metric_name]
            metric = report["variants"][label]["metrics"][metric_name]
            baseline = report["variants"]["V2-full-original"]["metrics"][metric_name]
            if target is None or "mean_absolute_error" not in metric or "mean_absolute_error" not in baseline:
                rows[feature] = {"direction_vs_original": "undefined"}
                counts["undefined"] += 1
                if feature in PRIORITY:
                    priority_counts["undefined"] += 1
                continue
            scale = error_scale(feature, target, policy)
            delta = metric["mean_absolute_error"]-baseline["mean_absolute_error"]
            direction = _error_direction(delta, scale*policy.practical_equivalence_fraction)
            values = [r["metrics"][metric_name] for r in report["reports"] if r["variant"] == label]
            rows[feature] = {"tolerance_absolute": scale, "mean_absolute_error_exceeds_tolerance": metric["mean_absolute_error"]>scale,
                "seeds_exceeding_tolerance": sum(v is not None and abs(v-target)>scale for v in values),
                "undefined_seeds": sum(v is None for v in values), "error_change_vs_original": delta,
                "direction_vs_original": direction}
            counts[direction] += 1
            if feature in PRIORITY:
                priority_counts[direction] += 1
        groups[label] = {"metrics": rows, "metric_counts": counts, "priority_metric_counts": priority_counts}
    for feature, metric_name in REFINEMENT_METRICS.items():
        a = report["variants"]["V2-full-refined"]["metrics"][metric_name]
        b = report["variants"]["V2-bridge_volatility-refined"]["metrics"][metric_name]
        target = report["real_metrics"][metric_name]
        delta = b.get("mean_absolute_error", 0)-a.get("mean_absolute_error", 0)
        mixture[feature] = ({"direction": "undefined"} if target is None or "mean_absolute_error" not in a or "mean_absolute_error" not in b
            else {"error_change_without_mixture": delta,
                  "direction": _error_direction(delta, error_scale(feature, target, policy)*policy.practical_equivalence_fraction)})
    return {"groups": groups, "mixture_ablation": mixture, "source_profile_sha256": next(iter(parent_hashes)),
        "tolerances": policy.tolerances, "practical_equivalence_fraction": policy.practical_equivalence_fraction,
        "notes": ["Zmiana mieszanki obejmuje również osobne dostrojenie zmienności; nie izoluje efektu samej mieszanki.",
                  "Progi są diagnostyczne; nie wybrano zwycięzcy ani nie zaakceptowano profili.",
                  "Kontrola stabilności na treningu nie jest niezależnym testem rynkowym."]}


def _error_direction(change: float, threshold: float) -> str:
    return "practically_unchanged" if abs(change)<=threshold else ("improved" if change<0 else "worsened")

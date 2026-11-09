"""data_processing / synthetic / domain / calibration / objectives."""
from __future__ import annotations

import math

from .....core.numeric.validation import finite_number
from ...config.refinement import METRIC_KINDS, RefinementSettings, PRIORITY


def objective(observed: dict, reference: dict) -> tuple[float, dict]:
    """Wspólny wielometryczny błąd; brak progów automatycznego zatwierdzenia."""
    terms = {}
    for name, target in reference.items():
        value = observed[name]
        if target is None or value is None:
            continue
        if name == "pearson_kurtosis":
            error = 0.25 * (math.log1p(value) - math.log1p(target))
        elif name in ("body_fraction", "upper_wick", "lower_wick", "abs_ac1"):
            error = (value - target) / 0.25
        elif name.startswith("exceedance"):
            error = (value - target) / 0.05
        else:
            error = (value - target) / max(abs(target), 1e-5)
        terms[name] = error * error
    return math.fsum(terms.values()) / len(terms), terms


def error_scale(metric: str, reference: float, settings: RefinementSettings) -> float:
    return settings.tolerances[metric] * (max(abs(reference), settings.relative_floor)
                                         if METRIC_KINDS[metric] == "relative" else 1)


def refinement_objective(observed: dict, reference: dict, settings: RefinementSettings,
                         *, baseline: dict | None = None) -> dict:
    """Ważone błędy w jednostkach tolerancji oraz kara pogorszenia kontroli."""
    terms, guards, errors = {}, {}, {}
    for key in METRIC_KINDS:
        target = finite_number(reference[key], f"reference/{key}")
        value = finite_number(observed[key], f"observed/{key}")
        scale = error_scale(key, target, settings)
        error = abs(value-target)/scale
        errors[key] = error
        terms[key] = settings.weights[key]*error*error
        if key not in PRIORITY and baseline is not None:
            base_error = abs(finite_number(baseline[key], key)-target)/scale
            guards[key] = max(0, error-max(1.0, base_error))**2
    loss = math.fsum(terms.values())/math.fsum(settings.weights.values())
    loss += settings.guard_penalty*math.fsum(guards.values())/max(1, len(guards))
    if not math.isfinite(loss):
        raise ValueError("Niefinitywny błąd refinement")
    return {"loss": loss, "weighted_terms": terms, "control_guard_terms": guards,
            "normalized_absolute_errors": errors,
            "tolerance_exceeded": {key: error>1 for key, error in errors.items()}}


def _trial_score(features_by_seed: list[dict], reference: dict, settings: RefinementSettings,
                  baseline_by_seed: list[dict]) -> tuple[float, list[dict]]:
    scores = [refinement_objective(f, reference, settings, baseline=b)
              for f, b in zip(features_by_seed, baseline_by_seed)]
    losses = [s["loss"] for s in scores]
    loss = ((1-settings.worst_seed_weight)*math.fsum(losses)/len(losses)
            + settings.worst_seed_weight*max(losses))
    return loss, scores

"""Jawne dostrojenie wyłącznie dwóch parametrów zmienności v2 na treningu."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
import hashlib
from itertools import product
import json
import math
from pathlib import Path

from ...core.candles import CANDLE_DELTA
from ..storage import read_candles_csv
from .calibration import profile_hash, validate_profile
from .calibration_v2 import calibration_features
from .comparison import aggregate_windows
from .generator import example_seed
from .generator_v2 import generate_example_v2
from .profile_v2 import regime_configuration, validate_profile_v2
from .selection import select_real_windows
from .settings import SyntheticSettings, finite_number, positive_int
from .training_period import ChronologicalSplit, split_from_document
from .v2_parameters import V2Parameters

METHOD = "volatility_refinement_v1"
REFINEMENT_VARIANTS = ("full", "bridge_volatility")
VOLATILITY_KEYS = ("volatility_phi", "volatility_stationary_std")
PRIORITY = ("abs_ac1", "window_std_mean", "window_std_std")
METRIC_KINDS = {"abs_ac1": "absolute", "window_std_mean": "relative", "window_std_std": "relative",
                "abs_q95": "relative", "abs_q99": "relative", "range_mean": "relative",
                "body_fraction": "absolute", "upper_wick": "absolute", "lower_wick": "absolute"}
FROZEN_FIELDS = ("symbol", "source", "period", "observations", "skipped_noncontiguous_transitions",
                 "statistics", "generator_parameters", "regime_configuration", "estimation_kind")
CRITERION = "per-seed weighted normalized squared errors + control deterioration guard; mean/worst-seed blend"
SELECTION_RULE = "minimum_loss_then_input_order; baseline included first"


@dataclass(frozen=True)
class RefinementSettings:
    volatility_phi: list[float] = field(default_factory=lambda: [.65, .75, .85, .90, .94, .97, .99])
    volatility_stationary_std: list[float] = field(default_factory=lambda: [.25, .35, .45, .55, .65])
    simulation_seeds: list[int] = field(default_factory=lambda: [73001, 73002, 73003])
    diagnostic_seeds: list[int] = field(default_factory=lambda: [20261105, 20261115, 20261125, 20261205, 20261215])
    selection_seed: int = 73004
    examples_per_seed: int = 12
    max_candidates: int = 64
    max_simulated_windows: int = 2304
    tolerances: dict[str, float] = field(default_factory=lambda: dict(
        abs_ac1=.05, window_std_mean=.10, window_std_std=.20, abs_q95=.15,
        abs_q99=.15, range_mean=.10, body_fraction=.03, upper_wick=.03, lower_wick=.03))
    weights: dict[str, float] = field(default_factory=lambda: {key: 3.0 if key in PRIORITY else 1.0 for key in METRIC_KINDS})
    guard_penalty: float = 4.0
    worst_seed_weight: float = .25
    relative_floor: float = 1e-8
    practical_equivalence_fraction: float = .10

    def validate(self) -> None:
        for name, minimum in (("simulation_seeds", 3), ("diagnostic_seeds", 2)):
            values = getattr(self, name)
            if (not isinstance(values, list) or len(values) < minimum
                    or any(type(s) is not int or s < 0 for s in values) or len(set(values)) != len(values)):
                raise ValueError(f"{name}: wymagane co najmniej {minimum} różne nieujemne seedy")
        if set(self.simulation_seeds) & set(self.diagnostic_seeds):
            raise ValueError("Seedy kalibracyjne i diagnostyczne muszą być rozłączne")
        if type(self.selection_seed) is not int or self.selection_seed < 0:
            raise ValueError("Niepoprawny seed selekcji refinement")
        for name in ("examples_per_seed", "max_candidates", "max_simulated_windows"):
            positive_int(getattr(self, name), name)
        for name in VOLATILITY_KEYS:
            values = getattr(self, name)
            if not isinstance(values, list) or not values or len(values) > 20 or len(set(values)) != len(values):
                raise ValueError(f"{name}: wymagana niepusta siatka maksymalnie 20 różnych wartości")
            for value in values:
                replace(V2Parameters(), **{name: value}).validate()
        for name in ("tolerances", "weights"):
            values = getattr(self, name)
            if not isinstance(values, dict) or set(values) != set(METRIC_KINDS):
                raise ValueError(f"{name}: wymagany komplet metryk refinement")
            for key, value in values.items():
                finite_number(value, key, positive=True)
        for name in ("guard_penalty", "relative_floor", "practical_equivalence_fraction"):
            finite_number(getattr(self, name), name, positive=True)
        if not 0 <= finite_number(self.worst_seed_weight, "worst_seed_weight") <= 1:
            raise ValueError("worst_seed_weight musi mieścić się w [0,1]")


def load_refinement_settings(path: Path) -> RefinementSettings:
    options = json.loads(Path(path).read_text(encoding="utf-8-sig")).get("volatility_refinement_v1", {})
    if not isinstance(options, dict) or set(options) - set(RefinementSettings.__dataclass_fields__):
        raise ValueError("Nieobsługiwane ustawienia volatility_refinement_v1")
    settings = RefinementSettings(**options)
    settings.validate()
    return settings


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


def _candidate_parameters(source: dict, settings: RefinementSettings) -> list[dict]:
    parameters = [deepcopy(source["v2_parameters"])]
    for phi, sd in product(settings.volatility_phi, settings.volatility_stationary_std):
        candidate = dict(source["v2_parameters"], volatility_phi=phi, volatility_stationary_std=sd)
        if candidate not in parameters:
            parameters.append(candidate)
    windows = len(settings.simulation_seeds)*settings.examples_per_seed
    if len(parameters)>settings.max_candidates or len(parameters)*windows>settings.max_simulated_windows:
        raise ValueError("Siatka refinement przekracza jawny budżet kandydatów lub symulowanych okien")
    return parameters


def refine_v2_volatility(real_csv: Path, source_profile_path: Path, *, symbol: str, variant: str,
                          start: datetime, end: datetime, split: ChronologicalSplit,
                          settings: SyntheticSettings, search: RefinementSettings,
                          expected_source_sha256: str | None = None) -> dict:
    split.require_training(start, end)
    search.validate()
    settings.validate()
    if variant not in REFINEMENT_VARIANTS or settings.generator_version != "v2":
        raise ValueError("Refinement wymaga v2 i wariantu full albo bridge_volatility")
    raw_source = Path(source_profile_path).read_bytes()
    file_hash = hashlib.sha256(raw_source).hexdigest()
    if expected_source_sha256 is not None and expected_source_sha256.lower() != file_hash:
        raise ValueError("SHA-256 pliku profilu źródłowego nie odpowiada oczekiwanej wartości")
    source = json.loads(raw_source.decode("utf-8-sig"))
    if source.get("calibration", {}).get("method") == METHOD:
        raise ValueError("Ta iteracja wymaga oryginalnego profilu v2, nie kolejnego refinement")
    validate_profile_v2(source, symbol=symbol)
    if source["estimation_kind"] != "training" or source["source"]["chronological_split"] != split.document():
        raise ValueError("Wymagany empiryczny profil v2 z obecnego zatwierdzonego treningu")
    if source["regime_configuration"] != regime_configuration(settings):
        raise ValueError("Refinement nie może zmieniać konfiguracji reżimów")
    split.require_training(*(datetime.fromisoformat(source["period"][k]) for k in ("allowed_start", "allowed_end")))
    if not (datetime.fromisoformat(source["period"]["allowed_start"]) <= start < end
            <= datetime.fromisoformat(source["period"]["allowed_end"])):
        raise ValueError("Okres refinement wychodzi poza źródłowy okres kalibracji")
    candidates = _candidate_parameters(source, search)
    raw_csv = Path(real_csv).read_bytes()
    if hashlib.sha256(raw_csv).hexdigest() != source["source"]["sha256"]:
        raise ValueError("CSV nie odpowiada SHA-256 źródła oryginalnego profilu; nie zmieniono danych ani profilu")
    candles = read_candles_csv(Path(real_csv), source=str(real_csv))
    count = len(search.simulation_seeds)*search.examples_per_seed
    reference_windows, selection = select_real_windows(candles, symbol=symbol, start=start, end=end,
        count=count, seed=search.selection_seed, split=split)
    reference = calibration_features(aggregate_windows(reference_windows))
    # Cel wymaga określonych metryk; nie zastępujemy null arbitralnymi zerami.
    refinement_objective(reference, reference, search)
    profile = deepcopy(source)
    profile["status"] = "unapproved"
    profile.pop("approval", None)
    profile["calibration"] = {"method": METHOD, "phase": "evaluation", "status": "unapproved",
        "variant": variant, "source_profile": source, "source_profile_sha256": profile_hash(source),
        "source_profile_file_sha256": file_hash, "source_profile_path": str(Path(source_profile_path).resolve()),
        "search": asdict(search), "simulation_seeds": search.simulation_seeds,
        "requested_period": {"start": start.isoformat(), "end": end.isoformat()},
        "reference_selection": selection, "reference_features": reference,
        "changed_parameters": list(VOLATILITY_KEYS),
        "criterion": CRITERION,
        "profile_family": "refined", "selection_rule": SELECTION_RULE}
    trials = []
    baseline_features = None
    for parameters in candidates:
        candidate = deepcopy(profile)
        candidate["v2_parameters"] = parameters
        windows, by_seed = [], []
        for seed in search.simulation_seeds:
            config = replace(settings, diagnostic=True, seed=seed, count=search.examples_per_seed,
                             v2_variant=variant, experiment_id=METHOD+"-evaluation")
            seed_windows = [generate_example_v2(symbol, example_seed(seed, symbol, i), candidate, config,
                            calibration_evaluation=True).candles for i in range(search.examples_per_seed)]
            windows.extend(seed_windows)
            by_seed.append(calibration_features(aggregate_windows(seed_windows)))
        if baseline_features is None:
            baseline_features = by_seed
        loss, seed_scores = _trial_score(by_seed, reference, search, baseline_features)
        trials.append({"parameters": parameters, "loss": loss, "features_by_seed": by_seed,
                       "seed_objectives": seed_scores, "pooled_features": calibration_features(aggregate_windows(windows))})
    best = min(trials, key=lambda trial: trial["loss"])
    profile["v2_parameters"] = deepcopy(best["parameters"])
    profile["calibration"].update(phase="complete", trials=trials,
        baseline_features_by_seed=baseline_features, baseline_loss=trials[0]["loss"],
        selected_parameters=deepcopy(best["parameters"]), selected_loss=best["loss"],
        selection_reason="Najmniejszy wieloseedowy błąd z karą pogorszenia kontroli; remisy zachowują pierwszy punkt, w tym baseline.")
    for key in VOLATILITY_KEYS:
        profile["parameter_provenance"][key] = METHOD+"; training only; unapproved"
    validate_profile_v2(profile, symbol=symbol)
    return profile


def _objective_results_match(stored: object, computed: object) -> bool:
    """Tylko wyniki celu: floaty rel_tol=1e-12, abs_tol=1e-18; reszta dokładnie.

    Tolerancja pokrywa różnice zaokrągleń między platformami. Nie dotyczy
    parametrów, seedów, pochodzenia ani SHA. Typy, klucze, długości i kolejność
    list muszą być identyczne; NaN/Inf są odrzucane nawet przy równych bitach.
    """
    if type(stored) is not type(computed):
        return False
    if isinstance(computed, float):
        return (math.isfinite(stored) and math.isfinite(computed)
                and math.isclose(stored, computed, rel_tol=1e-12, abs_tol=1e-18))
    if isinstance(computed, dict):
        return (stored.keys() == computed.keys()
                and all(_objective_results_match(stored[key], value) for key, value in computed.items()))
    if isinstance(computed, list):
        return (len(stored) == len(computed)
                and all(_objective_results_match(a, b) for a, b in zip(stored, computed)))
    return stored == computed


def validate_refinement_audit(profile: dict, *, allow_evaluation: bool = False) -> None:
    """Sprawdź pełne pochodzenie, zamrożenie i odtwarzalność wyniku celu."""
    audit = profile["calibration"]
    source = audit["source_profile"]
    if source.get("calibration", {}).get("method") == METHOD:
        raise ValueError("Niedozwolone zagnieżdżenie refinement")
    validate_profile_v2(source, symbol=profile["symbol"])
    if profile["status"] == "approved":
        # Approval is new metadata; the immutable calibration audit remains unapproved.
        validate_profile(dict(profile, version=1), symbol=profile["symbol"])
        split = split_from_document(profile["source"]["chronological_split"])
        approval = profile["approval"]
        if (approval["split_id"] != split.split_id or
                tuple(datetime.fromisoformat(approval[k]) for k in ("training_start", "training_end")) != split.periods["train"]):
            raise ValueError("Zatwierdzenie refinement wymaga dokładnego podziału treningowego")
    if (profile["status"] not in ("unapproved", "approved") or audit["status"] != "unapproved"
            or source["estimation_kind"] != "training" or audit["variant"] not in REFINEMENT_VARIANTS
            or audit["source_profile_sha256"] != profile_hash(source)
            or audit["profile_family"] != "refined" or audit["changed_parameters"] != list(VOLATILITY_KEYS)):
        raise ValueError("Niepoprawny status, wariant lub pochodzenie refinement")
    if audit["criterion"] != CRITERION or audit["selection_rule"] != SELECTION_RULE:
        raise ValueError("Nieobsługiwane kryterium lub reguła wyboru refinement")
    raw_hash = audit["source_profile_file_sha256"]
    if not isinstance(raw_hash, str) or len(raw_hash)!=64 or any(c not in '0123456789abcdef' for c in raw_hash):
        raise ValueError("Niepoprawny SHA-256 źródłowego pliku profilu")
    if not isinstance(audit["source_profile_path"], str) or not audit["source_profile_path"]:
        raise ValueError("Brak ścieżki pochodzenia profilu")
    for key in FROZEN_FIELDS:
        if profile[key] != source[key]:
            raise ValueError(f"Refinement zmienił zamrożone pole {key}")
    for key in V2Parameters.__dataclass_fields__:
        if key not in VOLATILITY_KEYS and profile["v2_parameters"][key] != source["v2_parameters"][key]:
            raise ValueError(f"Refinement zmienił zamrożony parametr {key}")
    settings = RefinementSettings(**audit["search"])
    settings.validate()
    if audit["simulation_seeds"] != settings.simulation_seeds:
        raise ValueError("Niezgodne seedy refinement")
    split = split_from_document(source["source"]["chronological_split"])
    start, end = (datetime.fromisoformat(audit["requested_period"][k]) for k in ("start", "end"))
    split.require_training(start, end)
    if not (datetime.fromisoformat(source['period']['allowed_start']) <= start < end
            <= datetime.fromisoformat(source['period']['allowed_end'])):
        raise ValueError("Refinement poza okresem źródłowego profilu")
    selection = audit["reference_selection"]
    count = len(settings.simulation_seeds)*settings.examples_per_seed
    if (selection["window_count"] != count or len(selection["windows"]) != count
            or selection["selection_seed"] != settings.selection_seed or selection["symbol"] != profile["symbol"]
            or selection["start"] != start.isoformat() or selection["end"] != end.isoformat()
            or selection["windows_with_gaps_allowed"] is not False):
        raise ValueError("Niezgodna próbka referencyjna refinement")
    used_indices, used_starts = set(), []
    for index, window in enumerate(selection["windows"]):
        first, last = (datetime.fromisoformat(window[k]) for k in ("start", "end"))
        indices = window["csv_record_indices"]
        if (window["index"] != index or window["count"] != 120 or len(indices) != 120
                or any(type(i) is not int or i < 0 for i in indices)
                or indices != list(range(indices[0], indices[0]+120))
                or used_indices.intersection(indices) or not start <= first <= last <= end
                or last-first != 119*CANDLE_DELTA
                or any(abs(first-previous)<120*CANDLE_DELTA for previous in used_starts)):
            raise ValueError("Niepoprawne lub pokrywające się okna refinement")
        used_indices.update(indices)
        used_starts.append(first)
    refinement_objective(audit["reference_features"], audit["reference_features"], settings)
    candidates = _candidate_parameters(source, settings)
    if profile["v2_parameters"] not in candidates:
        raise ValueError("Parametry spoza ocenianej siatki refinement")
    if audit["phase"] == "evaluation":
        if not allow_evaluation:
            raise ValueError("Wewnętrzny kandydat refinement nie jest kompletnym profilem do zapisu/odczytu")
        return
    if audit["phase"] != "complete":
        raise ValueError("Niepoprawna faza audytu refinement")
    trials = audit["trials"]
    if [t["parameters"] for t in trials] != candidates:
        raise ValueError("Dziennik refinement nie odpowiada pełnej siatce i baseline")
    baseline = audit["baseline_features_by_seed"]
    if baseline != trials[0]["features_by_seed"] or len(baseline) != len(settings.simulation_seeds):
        raise ValueError("Niezgodny wynik źródłowej zmienności")
    for trial in trials:
        if len(trial["features_by_seed"]) != len(settings.simulation_seeds):
            raise ValueError("Niepełne wyniki seedów refinement")
        loss, terms = _trial_score(trial["features_by_seed"], audit["reference_features"], settings, baseline)
        if (not _objective_results_match(trial["loss"], loss)
                or not _objective_results_match(trial["seed_objectives"], terms)):
            raise ValueError("Niezgodny wynik funkcji celu refinement")
    best = min(trials, key=lambda t: t["loss"])
    if (profile["v2_parameters"] != best["parameters"] or audit["selected_parameters"] != best["parameters"]
            or audit["selected_loss"] != best["loss"] or audit["baseline_loss"] != trials[0]["loss"]
            or not audit["selection_reason"]):
        raise ValueError("Niespójny wybór parametrów refinement")

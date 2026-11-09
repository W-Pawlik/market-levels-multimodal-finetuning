"""Composed profile and refinement-audit validation without simulation."""
from __future__ import annotations

import math
from datetime import datetime

from .v1 import profile_hash, validate_profile
from ...config.generation import SyntheticSettings
from ..parameters import V2Parameters, V2_VERSION
from .....core.ohlc.model import CANDLE_DELTA
from .....core.time.periods import split_from_document
from ...config.refinement import (
    METHOD,
    REFINEMENT_VARIANTS,
    VOLATILITY_KEYS,
    FROZEN_FIELDS,
    CRITERION,
    SELECTION_RULE,
    RefinementSettings,
)
from ..calibration.objectives import refinement_objective, _trial_score
from ..calibration.candidates import _candidate_parameters


def validate_generator_profile(profile: dict, *, symbol: str | None = None,
                               generator_version: str | None = None) -> None:
    """Rozróżnij schematy bez zmiany historycznego validate_profile v1."""
    if not isinstance(profile, dict):
        raise ValueError("Profil musi być obiektem JSON")
    version = profile.get("version")
    if generator_version is not None and (generator_version, version) not in (("v1", 1), ("v2", 2)):
        raise ValueError("Wersja profilu nie odpowiada wybranemu generatorowi")
    if version == 2:
        validate_profile_v2(profile, symbol=symbol)
    else:
        validate_profile(profile, symbol=symbol)


def validate_profile_v2(profile: dict, *, symbol: str | None = None, allow_evaluation: bool = False) -> None:
    try:
        if (type(profile["version"]) is not int or profile["version"] != 2
                or profile["generator_version"] != V2_VERSION
                or profile["status"] not in ("unapproved", "approved")
                or profile["estimation_kind"] not in ("diagnostic", "training")):
            raise ValueError("Niezgodna wersja lub status profilu v2")
        view = dict(profile, version=1)
        if profile["estimation_kind"] == "diagnostic":
            if profile["status"] != "unapproved":
                raise ValueError("Ręczne parametry v2 nie mogą być zatwierdzone")
            view["status"] = "diagnostic"
        validate_profile(view, symbol=symbol)
        parameters = profile["v2_parameters"]
        if set(parameters) != set(V2Parameters.__dataclass_fields__):
            raise ValueError("Profil v2 wymaga kompletu parametrów matematycznych")
        V2Parameters(**parameters).validate()
        regime = profile["regime_configuration"]
        from ...config.regimes import RegimeSettings
        SyntheticSettings(regimes=RegimeSettings(**regime["regimes"]),
                          min_regimes=regime["min_regimes"], max_regimes=regime["max_regimes"]).validate()
        required = set(parameters) | {"sigma_4h", "initial_price_range", "regime_configuration"}
        if not required <= set(profile["parameter_provenance"]) or any(
                not isinstance(profile["parameter_provenance"][key], str)
                or not profile["parameter_provenance"][key].strip() for key in required):
            raise ValueError("Brak pochodzenia parametrów v2")
        if not isinstance(profile["calibration"], dict) or not profile["calibration"].get("method"):
            raise ValueError("Brak opisu kalibracji v2")
        if profile["calibration"]["method"] == "volatility_refinement_v1":
            validate_refinement_audit(profile, allow_evaluation=allow_evaluation)
        if profile["calibration"]["method"] == "bounded_coordinate_grid_full_model_v1":
            audit = profile["calibration"]
            from .....core.numeric.validation import finite_number
            from ...config.calibration import CalibrationV2Settings
            search = CalibrationV2Settings(**audit["search"])
            search.validate()
            if (audit["selected_parameters"] != parameters or not isinstance(audit["trials"], list)
                    or not audit["trials"] or len(set(audit["simulation_seeds"])) < 2
                    or audit["simulation_seeds"] != search.simulation_seeds
                    or audit["reference_selection"]["window_count"] != len(search.simulation_seeds)*search.examples_per_seed
                    or finite_number(audit["selected_loss"], "selected_loss") < 0):
                raise ValueError("Niespójny audyt kalibracji v2")
            selected_trials = [t for t in audit["trials"] if t["parameters"] == parameters]
            if not selected_trials or selected_trials[0]["loss"] != audit["selected_loss"]:
                raise ValueError("Wybrane parametry nie mają zgodnego wyniku kalibracyjnego")
        if profile["estimation_kind"] == "training":
            from .....core.time.periods import split_from_document
            declared = profile["source"]["chronological_split"]
            # Weryfikacja granic treningu bez stałych dat w walidatorze.
            split_from_document(declared).require_training(
                *(datetime.fromisoformat(profile["period"][key]) for key in ("allowed_start", "allowed_end")))
        profile_hash(profile)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Niekompletny profil v2: {exc}") from exc


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

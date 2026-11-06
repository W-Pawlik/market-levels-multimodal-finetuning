"""Osobny schemat v2, współdzielący walidację części empirycznej v1."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json

from .calibration import diagnostic_profile, profile_hash, validate_profile
from .settings import SyntheticSettings
from .v2_parameters import V2Parameters, V2_VERSION


def regime_configuration(settings: SyntheticSettings) -> dict:
    config = settings.document()
    return json.loads(json.dumps({key: config[key] for key in ("regimes", "min_regimes", "max_regimes")}))


def make_profile_v2(base: dict, settings: SyntheticSettings, *, diagnostic: bool) -> dict:
    validate_profile(base)
    params = V2Parameters(**settings.v2_parameters)
    params.validate()
    result = deepcopy(base)
    result.update(version=2, generator_version=V2_VERSION, status="unapproved",
                  estimation_kind="diagnostic" if diagnostic else "training",
                  v2_parameters=params.document(), regime_configuration=regime_configuration(settings),
                  parameter_provenance={"sigma_4h": "diagnostic" if diagnostic else "direct_training_estimate",
                      "initial_price_range": "diagnostic" if diagnostic else "training_quantiles_05_95",
                      **{name: "diagnostic" for name in params.document()},
                      "regime_configuration": "design; unchanged v1 scheduling"},
                  calibration={"method": "not_calibrated", "status": "diagnostic"})
    return result


def diagnostic_profile_v2(symbol: str, settings: SyntheticSettings) -> dict:
    return make_profile_v2(diagnostic_profile(symbol), settings, diagnostic=True)


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
        from .settings import RegimeSettings
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
            from .refinement import validate_refinement_audit
            validate_refinement_audit(profile, allow_evaluation=allow_evaluation)
        if profile["calibration"]["method"] == "bounded_coordinate_grid_full_model_v1":
            audit = profile["calibration"]
            from .settings import finite_number
            from .calibration_v2 import CalibrationV2Settings
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
            from .training_period import split_from_document
            declared = profile["source"]["chronological_split"]
            # Weryfikacja granic treningu bez stałych dat w walidatorze.
            split_from_document(declared).require_training(
                *(datetime.fromisoformat(profile["period"][key]) for key in ("allowed_start", "allowed_end")))
        profile_hash(profile)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Niekompletny profil v2: {exc}") from exc

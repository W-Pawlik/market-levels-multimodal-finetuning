"""data_processing / synthetic / domain / profiles / v2."""
from __future__ import annotations

import json
from copy import deepcopy

from ...config.generation import SyntheticSettings
from .v1 import validate_profile, diagnostic_profile
from ..parameters import V2Parameters, V2_VERSION


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

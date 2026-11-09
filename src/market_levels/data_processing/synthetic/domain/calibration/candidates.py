"""data_processing / synthetic / domain / calibration / candidates."""
from __future__ import annotations

from copy import deepcopy
from itertools import product

from ...config.refinement import RefinementSettings


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

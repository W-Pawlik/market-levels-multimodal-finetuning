"""data_processing / synthetic / domain / generation / dispatch."""

from .v1 import generate_example as generate_example_v1
from .models import SyntheticExample
from .v2 import generate_example_v2
from ...config.generation import SyntheticSettings


def generate_example(symbol: str, seed: int, profile: dict, settings: SyntheticSettings) -> SyntheticExample:
    if settings.generator_version == "v1":
        return generate_example_v1(symbol, seed, profile, settings)
    if settings.generator_version == "v2":
        return generate_example_v2(symbol, seed, profile, settings)
    raise ValueError("Nieobsługiwana wersja generatora")

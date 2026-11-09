# data_processing/synthetic

Generowanie v1/v2, profile, kalibracja, refinement i diagnostyka.

[Architektura i reguły zależności](../../../../docs/ARCHITECTURE.md).

Domain zawiera obliczenia i modele, workflows koordynuje wykonanie, io obsługuje pliki, reporting składa raporty, a config zawiera ustawienia. W core i shared podział odpowiada wspólnym odpowiedzialnościom bibliotecznym.

| Moduł | Definicje i punkty wejścia |
| --- | --- |
| [config/calibration.py](config/calibration.py) | `CalibrationV2Settings`, `load_calibration_v2_settings` |
| [config/generation.py](config/generation.py) | `SyntheticSettings`, `load_synthetic_settings` |
| [config/refinement.py](config/refinement.py) | `RefinementSettings`, `load_refinement_settings` |
| [config/regimes.py](config/regimes.py) | `RegimeSettings` |
| [domain/calibration/candidates.py](domain/calibration/candidates.py) |  |
| [domain/calibration/features.py](domain/calibration/features.py) | `calibration_features`, `training_volatility_diagnostics` |
| [domain/calibration/objectives.py](domain/calibration/objectives.py) | `objective`, `error_scale`, `refinement_objective` |
| [domain/diagnostics.py](domain/diagnostics.py) | `tail_diagnostics`, `lag1_absolute_correlation`, `aggregate_windows`, `statistical_differences`, `metric_values`, `refinement_review` |
| [domain/generation/dispatch.py](domain/generation/dispatch.py) | `generate_example` |
| [domain/generation/models.py](domain/generation/models.py) | `SyntheticExample` |
| [domain/generation/processes.py](domain/generation/processes.py) | `stream_seed`, `normal_mixture`, `mixture_value`, `volatility_states`, `volatility_multiplier`, `brownian_bridge` |
| [domain/generation/regimes.py](domain/generation/regimes.py) | `feasible_sequences`, `plan_regimes` |
| [domain/generation/seeds.py](domain/generation/seeds.py) | `example_seed` |
| [domain/generation/v1.py](domain/generation/v1.py) | `generate_example` |
| [domain/generation/v2.py](domain/generation/v2.py) | `generate_example_v2` |
| [domain/parameters.py](domain/parameters.py) | `V2Parameters`, `mechanisms`, `effective_parameters` |
| [domain/profiles/v1.py](domain/profiles/v1.py) | `profile_hash`, `diagnostic_profile`, `approve_profile`, `validate_profile` |
| [domain/profiles/v2.py](domain/profiles/v2.py) | `regime_configuration`, `make_profile_v2`, `diagnostic_profile_v2` |
| [domain/profiles/validation.py](domain/profiles/validation.py) | `validate_generator_profile`, `validate_profile_v2`, `validate_refinement_audit` |
| [domain/quality.py](domain/quality.py) | `validate_synthetic`, `series_observations`, `series_statistics`, `compare_statistics` |
| [io/batches.py](io/batches.py) | `load_synthetic_windows` |
| [io/profiles.py](io/profiles.py) | `prepare_profiles`, `save_profile`, `load_profile` |
| [reporting/comparison.py](reporting/comparison.py) | `comparison_summary` |
| [reporting/variants.py](reporting/variants.py) | `variant_summary_markdown` |
| [workflows/calibration.py](workflows/calibration.py) | `calibrate`, `calibrate_csv`, `calibrate_v2_csv` |
| [workflows/comparison.py](workflows/comparison.py) | `build_comparison`, `save_comparison` |
| [workflows/generation.py](workflows/generation.py) | `run` |
| [workflows/refinement.py](workflows/refinement.py) | `refine_v2_volatility` |
| [workflows/summary.py](workflows/summary.py) | `build_variant_summary` |

Testy z katalogu projektu: `.\.venv\Scripts\python.exe -m unittest discover -s tests`. Jednostkowe i integracyjne przypadki są pogrupowane według tych samych obszarów; wspólne fixture znajdują się w tests/support.

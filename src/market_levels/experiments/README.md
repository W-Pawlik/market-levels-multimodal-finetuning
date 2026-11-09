# experiments

Koordynacja istniejących eksperymentów refinement; bez nowego treningu lub inferencji.

[Architektura i reguły zależności](../../../docs/ARCHITECTURE.md).

Domain zawiera obliczenia i modele, workflows koordynuje wykonanie, io obsługuje pliki, reporting składa raporty, a config zawiera ustawienia. W core i shared podział odpowiada wspólnym odpowiedzialnościom bibliotecznym.

| Moduł | Definicje i punkty wejścia |
| --- | --- |
| [refinement/config.py](refinement/config.py) | `SYMBOLS`, `VARIANTS`, `SEEDS`, `FRESH_SEEDS`, `FRESH_EXPERIMENT`, `SELECTION_SEED`, `WINDOWS_MAX_PATH` |
| [refinement/domain/plan.py](refinement/domain/plan.py) | `experiment_tasks` |
| [refinement/io.py](refinement/io.py) | `resolve`, `checked_report`, `cli`, `exclusive_json`, `unique_file`, `incomplete_stage`, `run_lock` |
| [refinement/paths.py](refinement/paths.py) | `longest_output_path`, `validate_output_paths` |
| [refinement/reporting.py](refinement/reporting.py) | `fresh_summary_markdown` |
| [refinement/workflows/preflight.py](refinement/workflows/preflight.py) | `check_environment`, `preflight` |
| [refinement/workflows/runner.py](refinement/workflows/runner.py) | `execute`, `run_comparison` |

Testy z katalogu projektu: `.\.venv\Scripts\python.exe -m unittest discover -s tests`. Jednostkowe i integracyjne przypadki są pogrupowane według tych samych obszarów; wspólne fixture znajdują się w tests/support.

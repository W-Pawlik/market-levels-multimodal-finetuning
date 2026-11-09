# datasets

Planowanie, budowa, weryfikacja i diagnostyka zbioru.

[Architektura i reguły zależności](../../../docs/ARCHITECTURE.md).

Domain zawiera obliczenia i modele, workflows koordynuje wykonanie, io obsługuje pliki, reporting składa raporty, a config zawiera ustawienia. W core i shared podział odpowiada wspólnym odpowiedzialnościom bibliotecznym.

| Moduł | Definicje i punkty wejścia |
| --- | --- |
| [config.py](config.py) | `load_plan_config`, `synthetic_settings` |
| [domain/audit.py](domain/audit.py) | `audit_dataset`, `summarize` |
| [domain/examples.py](domain/examples.py) | `json_line`, `names_for`, `synthetic_id`, `source_metadata` |
| [io/outputs.py](io/outputs.py) | `diagnostic_output`, `production_output` |
| [workflows/approval.py](workflows/approval.py) | `approve_refined`, `approve_configured_profiles` |
| [workflows/planning.py](workflows/planning.py) | `publish_plan`, `require_production_ready`, `inspect_synthetic`, `build_plan` |
| [workflows/production.py](workflows/production.py) | `build_dataset` |
| [workflows/review.py](workflows/review.py) | `create_review` |
| [workflows/smoke.py](workflows/smoke.py) | `diagnostic_records`, `run_smoke` |
| [workflows/verification.py](workflows/verification.py) | `verify_smoke`, `verify_dataset` |

Testy z katalogu projektu: `.\.venv\Scripts\python.exe -m unittest discover -s tests`. Jednostkowe i integracyjne przypadki są pogrupowane według tych samych obszarów; wspólne fixture znajdują się w tests/support.

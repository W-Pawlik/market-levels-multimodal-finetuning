# charts

Metryki okien, selekcja pilotażu, renderer i odczyt danych pilotażu.

[Architektura i reguły zależności](../../../docs/ARCHITECTURE.md).

Domain zawiera obliczenia i modele, workflows koordynuje wykonanie, io obsługuje pliki, reporting składa raporty, a config zawiera ustawienia. W core i shared podział odpowiada wspólnym odpowiedzialnościom bibliotecznym.

| Moduł | Definicje i punkty wejścia |
| --- | --- |
| [config.py](config.py) | `SEEDS`, `SYMBOLS`, `KINDS`, `RENDERER_VERSION`, `VISUALIZATION` |
| [domain/diversity.py](domain/diversity.py) | `summarize` |
| [domain/metrics.py](domain/metrics.py) | `quantile`, `movement`, `observed_motion`, `window_metrics`, `fit_thresholds` |
| [domain/selection.py](domain/selection.py) | `tags`, `select_pilot` |
| [domain/validation.py](domain/validation.py) | `validate_window` |
| [io/audit_sources.py](io/audit_sources.py) | `discover_batches`, `read_synthetic` |
| [io/pilot.py](io/pilot.py) | `read_pilot` |
| [io/rendering.py](io/rendering.py) | `build_figure`, `render_window` |
| [reporting/audit.py](reporting/audit.py) |  |
| [workflows/audit.py](workflows/audit.py) | `run_audit` |

Testy z katalogu projektu: `.\.venv\Scripts\python.exe -m unittest discover -s tests`. Jednostkowe i integracyjne przypadki są pogrupowane według tych samych obszarów; wspólne fixture znajdują się w tests/support.

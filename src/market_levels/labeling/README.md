# labeling

Etykietowanie S/R, wynik algorytmu i osobne nakładki diagnostyczne.

[Architektura i reguły zależności](../../../docs/ARCHITECTURE.md).

Domain zawiera obliczenia i modele, workflows koordynuje wykonanie, io obsługuje pliki, reporting składa raporty, a config zawiera ustawienia. W core i shared podział odpowiada wspólnym odpowiedzialnościom bibliotecznym.

| Moduł | Definicje i punkty wejścia |
| --- | --- |
| [domain/algorithm.py](domain/algorithm.py) | `find_extrema`, `price_groups`, `independent_reactions`, `rank_groups`, `select_groups`, `label_window` |
| [domain/models.py](domain/models.py) | `Extremum`, `Group`, `LabelResult` |
| [io/overlays.py](io/overlays.py) | `render_levels` |
| [reporting/pilot.py](reporting/pilot.py) | `summarize`, `report_markdown` |
| [workflows/pilot.py](workflows/pilot.py) | `run_labeling` |
| [workflows/verification.py](workflows/verification.py) | `verify_labeling` |

Testy z katalogu projektu: `.\.venv\Scripts\python.exe -m unittest discover -s tests`. Jednostkowe i integracyjne przypadki są pogrupowane według tych samych obszarów; wspólne fixture znajdują się w tests/support.

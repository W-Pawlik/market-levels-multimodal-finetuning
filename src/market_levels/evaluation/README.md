# evaluation

Ocena zapisanych odpowiedzi, metryki i porównania według sr-eval-v1.

[Architektura i reguły zależności](../../../docs/ARCHITECTURE.md).

Domain zawiera obliczenia i modele, workflows koordynuje wykonanie, io obsługuje pliki, reporting składa raporty, a config zawiera ustawienia. W core i shared podział odpowiada wspólnym odpowiedzialnościom bibliotecznym.

| Moduł | Definicje i punkty wejścia |
| --- | --- |
| [domain/comparison.py](domain/comparison.py) |  |
| [domain/matching.py](domain/matching.py) | `match_levels` |
| [domain/metrics.py](domain/metrics.py) | `aggregate` |
| [domain/models.py](domain/models.py) | `Levels`, `Response`, `Reference`, `Match` |
| [domain/responses.py](domain/responses.py) | `parse_response` |
| [domain/scoring.py](domain/scoring.py) | `final_atr`, `score_example` |
| [io/inputs.py](io/inputs.py) | `InputError`, `read_references`, `read_predictions`, `read_run_manifest` |
| [io/reports.py](io/reports.py) |  |
| [protocol.py](protocol.py) | `ratio`, `dumps`, `reject_constant`, `unique_object`, `loads` |
| [reporting/markdown.py](reporting/markdown.py) |  |
| [workflows/compare.py](workflows/compare.py) | `compare` |
| [workflows/evaluate.py](workflows/evaluate.py) | `evaluate` |
| [workflows/verification.py](workflows/verification.py) | `read_evaluation`, `read_comparison` |

Testy z katalogu projektu: `.\.venv\Scripts\python.exe -m unittest discover -s tests`. Jednostkowe i integracyjne przypadki są pogrupowane według tych samych obszarów; wspólne fixture znajdują się w tests/support.

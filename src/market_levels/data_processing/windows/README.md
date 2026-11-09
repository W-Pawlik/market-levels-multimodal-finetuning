# data_processing/windows

Okna produkcyjne i diagnostyczne; odrębne reguły selekcji.

[Architektura i reguły zależności](../../../../docs/ARCHITECTURE.md).

Domain zawiera obliczenia i modele, workflows koordynuje wykonanie, io obsługuje pliki, reporting składa raporty, a config zawiera ustawienia. W core i shared podział odpowiada wspólnym odpowiedzialnościom bibliotecznym.

| Moduł | Definicje i punkty wejścia |
| --- | --- |
| [domain/candidates.py](domain/candidates.py) | `training_windows`, `candidates`, `validate_selection`, `coverage` |
| [domain/models.py](domain/models.py) | `Window` |
| [domain/selection.py](domain/selection.py) | `select_real_windows`, `select_training` |
| [io/training_csv.py](io/training_csv.py) | `read_training_csv` |

Testy z katalogu projektu: `.\.venv\Scripts\python.exe -m unittest discover -s tests`. Jednostkowe i integracyjne przypadki są pogrupowane według tych samych obszarów; wspólne fixture znajdują się w tests/support.

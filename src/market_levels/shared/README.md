# shared

Integralność plików, publikacja, manifesty, JSON i kontrola ścieżek.

[Architektura i reguły zależności](../../../docs/ARCHITECTURE.md).

Domain zawiera obliczenia i modele, workflows koordynuje wykonanie, io obsługuje pliki, reporting składa raporty, a config zawiera ustawienia. W core i shared podział odpowiada wspólnym odpowiedzialnościom bibliotecznym.

| Moduł | Definicje i punkty wejścia |
| --- | --- |
| [integrity.py](integrity.py) | `sha256_file`, `SourceLedger` |
| [json_io.py](json_io.py) | `write_json`, `read_json` |
| [configuration.py](configuration.py) | `read_configuration`, `configuration_sources`, `track_configuration`, `configuration_snapshot` |
| [manifests.py](manifests.py) | `seal`, `verify_files` |
| [paths.py](paths.py) | `require_short_path`, `child` |
| [publication.py](publication.py) | `publish_directory`, `publication_workspace` |

Testy z katalogu projektu: `.\.venv\Scripts\python.exe -m unittest discover -s tests`. Jednostkowe i integracyjne przypadki są pogrupowane według tych samych obszarów; wspólne fixture znajdują się w tests/support.

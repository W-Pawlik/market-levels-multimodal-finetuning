# data_processing

Pozyskiwanie danych, CSV, okna oraz osobny generator syntetyczny.

[Architektura i reguły zależności](../../../docs/ARCHITECTURE.md).

Domain zawiera obliczenia i modele, workflows koordynuje wykonanie, io obsługuje pliki, reporting składa raporty, a config zawiera ustawienia. W core i shared podział odpowiada wspólnym odpowiedzialnościom bibliotecznym.

Osobne obszary: [syntetyki](synthetic/README.md), [okna](windows/README.md).

| Moduł | Definicje i punkty wejścia |
| --- | --- |
| [io/candles.py](io/candles.py) | `write_candles_csv`, `read_candles_csv` |
| [io/chronology.py](io/chronology.py) | `load_chronological_split` |
| [real/binance_vision/archives.py](real/binance_vision/archives.py) | `acquire_archive`, `acquire_month` |
| [real/binance_vision/client.py](real/binance_vision/client.py) | `DownloadError` |
| [real/binance_vision/parsing.py](real/binance_vision/parsing.py) | `decode_binance_timestamp`, `parse_candle`, `read_spot_klines_zip`, `verify_archive_period` |
| [real/workflows/download.py](real/workflows/download.py) | `run` |

Testy z katalogu projektu: `.\.venv\Scripts\python.exe -m unittest discover -s tests`. Jednostkowe i integracyjne przypadki są pogrupowane według tych samych obszarów; wspólne fixture znajdują się w tests/support.

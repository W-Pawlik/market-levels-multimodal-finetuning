# core

Wspólne modele OHLC, czas, walidacja i obliczenia numeryczne.

[Architektura i reguły zależności](../../../docs/ARCHITECTURE.md).

Domain zawiera obliczenia i modele, workflows koordynuje wykonanie, io obsługuje pliki, reporting składa raporty, a config zawiera ustawienia. W core i shared podział odpowiada wspólnym odpowiedzialnościom bibliotecznym.

| Moduł | Definicje i punkty wejścia |
| --- | --- |
| [numeric/atr.py](numeric/atr.py) | `true_ranges`, `wilder_atr` |
| [numeric/statistics.py](numeric/statistics.py) | `distribution` |
| [numeric/validation.py](numeric/validation.py) | `positive_int`, `finite_number` |
| [ohlc/identity.py](ohlc/identity.py) | `canonical_hash` |
| [ohlc/model.py](ohlc/model.py) | `DataValidationError`, `Candle` |
| [ohlc/validation.py](ohlc/validation.py) | `check_series`, `validate_candle_timestamp`, `validate_ohlc`, `validate_values` |
| [time/calendar.py](time/calendar.py) | `iter_months` |
| [time/periods.py](time/periods.py) | `validate_period`, `ChronologicalSplit`, `split_from_document` |

Testy z katalogu projektu: `.\.venv\Scripts\python.exe -m unittest discover -s tests`. Jednostkowe i integracyjne przypadki są pogrupowane według tych samych obszarów; wspólne fixture znajdują się w tests/support.

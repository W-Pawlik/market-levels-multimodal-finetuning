# data_processing/synthetic

Generator niezależnych serii 120 świec OHLC z 12 krokami na świecę, reżimami,
lokalnym RNG, kalibracją z jawnym okresem i kontrolą jakości.

`settings.py` — konfiguracja, `regimes.py` — plan faz, `generator.py` — ścieżka,
`calibration.py` — profile i jawne zatwierdzenie, `quality.py` — walidacja/statystyki.
Pipeline zapisu: `../pipelines/synthetic.py`; CLI: `market-levels-generate-synthetic`.

Dokumentacja: [generator](../../../../docs/SYNTHETIC_GENERATOR.md),
[architektura](../../../../docs/ARCHITECTURE.md).

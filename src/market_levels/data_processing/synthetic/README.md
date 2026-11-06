# data_processing/synthetic

Generator niezależnych serii 120 świec OHLC z 12 krokami na świecę, reżimami,
lokalnym RNG, kalibracją z jawnym okresem i kontrolą jakości.

`settings.py` — konfiguracja, `regimes.py` — plan faz, `generator.py` — ścieżka,
`calibration.py` — profile i jawne zatwierdzenie, `quality.py` — walidacja/statystyki.
`training_period.py` — zatwierdzony podział z konfiguracji, `selection.py` —
rozłączne okna diagnostyczne, `comparison.py` — sprawdzenie partii i agregacja.
Pipeline zapisu: `../pipelines/synthetic.py`; CLI: `market-levels-generate-synthetic`.

Dokumentacja: [generator](../../../../docs/SYNTHETIC_GENERATOR.md),
[architektura](../../../../docs/ARCHITECTURE.md).
Proces kalibracji CLI i porównania z treningiem:
[instrukcja](../../../../docs/SYNTHETIC_CALIBRATION_COMPARISON.md).

V1 zachowano w `generator.py`; `dispatch.py` wybiera implementację.
V2: `generator_v2.py`, `stochastic_processes.py`, `v2_parameters.py`,
`profile_v2.py`, `calibration_v2.py`. `experiments.py` zestawia warianty/seedowe
powtórzenia na identycznej referencji. [Matematyka i status](../../../../docs/SYNTHETIC_GENERATOR_V2.md).

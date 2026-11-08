# evaluation

Działa protokół `sr-eval-v1`: ścisła walidacja surowego JSON, ATR Wildera
z istniejącego etykietowania, optymalne dopasowanie 1:1, micro-P/R/F1,
MAE/ATR i MAE USDT osobno BTC/ETH, kontrola ID, raporty i sparowane porównanie.
CLI: `python -m market_levels.cli.evaluate evaluate|compare|verify`.
Domyślnie validation; test wymaga jawnego wskazania. Nie wykonuje inferencji,
treningu ani porównania algorytmu etykietującego z własnymi referencjami.
[Protokół](../../../docs/evaluation/PROTOKOL_3_6.md),
[PowerShell](../../../docs/evaluation/INSTRUKCJA_POWERSHELL.md).

# charts

Renderer Matplotlib Agg: 120 ciągłych świec → PNG 1024 × 768, pozycja w oknie,
oryginalna liniowa oś ceny, bez pochodzenia, reżimów i poziomów S/R na obrazie.
`diversity.py` analizuje istniejące V2-full-refined; `pilot.py` publikuje audyt
i deterministyczny pilotaż poza finalnymi zbiorami danych.

Instalacja: `pip install -e ".[charts]"`.
Instrukcja: [PowerShell](../../../docs/charts/INSTRUKCJA_POWERSHELL.md).

Ten sam renderer jest używany w produkcyjnym etapie 3.5; styl pozostał
niezmieniony. Obrazy wejściowe modelu nie zawierają poziomów S/R.
Oddzielne overlays przeglądowe tworzy moduł `datasets/review.py`.

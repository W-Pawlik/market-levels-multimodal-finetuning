# Działający moduł etykietowania — etap 3.4

`algorithm.py` udostępnia `label_window(list[Candle]) -> LabelResult`.
Wejście: dokładnie 120 kolejnych poprawnych świec 4h, ceny `Decimal`.
Nie przyjmuje metadanych generatora. `target_json()` serializuje wyłącznie
`supports` i `resistances` jako liczby; `diagnostics()` zachowuje wszystkie cyfry
obliczeń jako tekst JSON. `pilot.py` weryfikuje istniejący pilotaż i publikuje
oddzielną diagnostykę, obrazy z liniami i manifest SHA-256.

Aktualna instrukcja: [PowerShell](../../../docs/labeling/INSTRUKCJA_POWERSHELL.md).

Etap 3.5 używa tego samego `label_window` i serializacji cen z dwoma miejscami
po przecinku. Produkcja etykietuje dokładnie te świece, które renderuje;
algorytmu ani rankingu nie zmieniono. Overlays są poza zbiorem wejściowym.

# Wykonana weryfikacja refinement v2 — 2026-11-05

Środowisko: Windows, Windows PowerShell, CPython 3.13.15,
lokalna `.venv`, bez nowych zależności wykonawczych.

## Zestaw testów

```powershell
./.venv/Scripts/python.exe -m pip install -e .
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Wynik pełnego zestawu: **116 testów, OK**, 20.511 s, bez pominięć.
Punkt odniesienia przed tą iteracją: **106 testów, OK**.

Nowe testy:

- `tests/unit/test_refinement_v2.py`: 5 testów. Aktywacje mostu/AR(1), brak
  wywołania mieszanki, brak wpływu p/k, aktywny wpływ gamma/phi/std,
  deterministyczność, precyzyjne błędy ważone i kara kontroli, średnia/najgorszy
  seed, odmowa null/NaN/Inf i nieprawidłowej konfiguracji. Fixture sprzed zmiany
  potwierdza identyczne OHLC oraz pełne metadane wszystkich pięciu dawnych
  wariantów v2, BTC i ETH. Stara regresja v1 również przechodzi.
- `tests/integration/test_refinement_v2_pipeline.py`: 5 testów. Sztuczny CSV,
  mała siatka, trzy seedy, po jednym przykładzie. Powtarzalność, zamrożone pola,
  baseline, dwa osobne warianty, zapis/odczyt, odmowa nadpisania, zmienionego SHA,
  validation/test, zbyt dużego budżetu, rekurencyjnego źródła i niedokończonego
  audytu. Celowe uszkodzenia score, wyboru, hash, okien i kryterium są odrzucane.
  Pełna ścieżka obejmuje V1/original/oba refined, dwa seedy i po dwa syntetyki.
  Raport odmawia brakujących grup, różnych seedów i mieszania profili.
  CLI jest wykonywane jako subprocess, także dry-run i kolizja wyjścia.
- Dwa istniejące testy rozszerzono o szósty wariant zamiast zachowywać stałe
  oczekiwanie pięciu wariantów. Testy matematyczne mostu, normalizacji mieszanki
  i AR(1) pozostały aktywne.

Wszystkie 10 testów poprawki Windows również przeszło: blokada przejściowa,
trwała blokada po publikacji, prawdziwe błędy przed publikacją oraz natywna
blokada uchwytu katalogu Windows po rename. Kod sprzątania nie wymagał nowej zmiany.

## Natywny PowerShell

Sprawdzono parserem PowerShell wszystkie bloki poleceń nowej instrukcji.
W osobnym katalogu tymczasowym wykonano następnie rzeczywiste nowe CLI
i funkcje instrukcji na sztucznej referencji obu symboli:

- cztery nowe profile (BTC/ETH × full/bridge_volatility);
- mała siatka jednego punktu plus baseline, trzy seedy kalibracyjne, po jednej serii;
- cztery grupy × dwa seedy diagnostyczne × dwa symbole × dwie serie = **32 serie**;
- **16 raportów porównawczych** i **dwa zbiorcze raporty czterech grup**;
- polecenia zakończone kodem 0, poprawne liczności i identyfikacja grup.

Wykorzystano funkcje `Invoke-RefinementDiagnostic`, `Save-RefinementSummary`
i pętlę kalibracji z instrukcji; podmieniono wyłącznie wejścia/wyjścia, małą
konfigurację i seedy. Duże pętle 60 przykładów sprawdzono składniowo, bez wykonania.
Log PowerShell dołączono do handoffu. Instalacja nowego entry point i `--help`
zostały sprawdzone osobno.

## Ochrona wyników i zakres

Porównanie SHA-256 przed/po obejmuje 4808 istniejących plików w
`data/processed` i `data/synthetic`: dane, profile, metadane, manifesty i raporty.
Paczka zawiera wynik tej kontroli i pełny log testów uruchomionych na jej kopii
źródeł. Nowe dane testowe i natywny smoke powstawały wyłącznie w katalogach temp.

Nie wykonywano ponownej kalibracji rynku, diagnostyki po 60 przykładów,
docelowych 440 syntetyków, PNG, etykietowania ani treningu. Testy techniczne
nie stanowią oceny dopasowania generatora do rynku.

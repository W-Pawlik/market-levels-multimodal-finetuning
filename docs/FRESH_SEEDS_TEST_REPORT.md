# Testy nowej próby stabilności — 2026-11-06

Pełny zestaw: **141 testów OK**, bez pominięć, 76.656 s.
Windows PowerShell, CPython 3.13.15; brak nowych zależności.

```powershell
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

136 wcześniejszych testów pozostało aktywnych: regresja v1/v2, procesy
matematyczne, przenośność audytu, publikacja/sprzątanie Windows, MAX_PATH,
integralność i wznowienie poprzedniego koordynatora.

Pięć nowych testów w `test_refinement_fresh_seeds.py` obejmuje:

- jawny plan: osiem partii, tylko 20261201/20261211, cztery grupy, 960 serii;
  test planu nie uruchamia pełnej generacji; smoke ma 32 serie;
- osiem wczytywanych profili, zgodność baseline z zamrożonymi raportami,
  odmowę podmiany original na refined oraz nieznanych opcji starego trybu;
- budżet ścieżek Windows, w tym odrzucenie 260 jednostek UTF-16;
- natywny skrypt fresh CheckOnly z innego katalogu terminala;
- całą małą ścieżkę, symulowane przerwanie po publikacji, odzyskanie partii,
  16 raportów, dwie tabele czterech grup, sześć priorytetowych metryk,
  odmowę domieszania starego seeda oraz ponowne wznowienie bez wywołania CLI.

Testy korzystają z małych sztucznych fixture. Jak w poprzednich testach
koordynatora, referencyjne historyczne JSON są kontrolowanymi fixture,
nie wynikami dużego eksperymentu rynkowego. Nie powielono dawnych dziewięciu
testów przez dziedziczenie klasy fixture.

## Mała próba na istniejących profilach

Oddzielnie uruchomiono rzeczywisty `run_refinement_fresh_seeds.ps1` z obcego
katalogu terminala, z wyjściem wyłącznie w temp:

- CheckOnly — OK: istniejące profile i raporty, SHA, split i referencja;
- SmokeTest — OK: 32 serie, osiem manifestów, 16 raportów indywidualnych,
  dwa podsumowania z dokładnie czterema grupami i wyłącznie dwoma nowymi seedami;
- ResumeDirectory — OK: ukończony smoke ponownie zweryfikowany;
- obie tabele STABILITY.md istnieją i zawierają wskazane metryki.

Log pełnego zestawu i log natywnego PowerShell znajdują się w handoffie.
Nie dołączono rynkowych profili ani pochodnych raportów liczbowych z tej próby.
Wynik smoke potwierdza działanie procedury, nie przewagę żadnego wariantu.

Kontrola przed/po obejmuje SHA-256 6384 istniejących plików data/processed
i data/synthetic; wynik jest w handoffie. `git diff --check` nie zgłosił
błędów whitespace. Seedy 20261201/20261211 nie występowały w lokalnych
manifestach przed rozpoczęciem zadania.

Nie wykonywano kalibracji rynku, pełnych 960 serii, nowych 720 serii,
renderowania, etykietowania ani treningu. Nie zatwierdzono generatora.
Nie testowano macierzy innych systemów i wersji Pythona. Dwa seedy są
kontrolą stabilności symulacji na treningu, nie niezależnym testem rynku.

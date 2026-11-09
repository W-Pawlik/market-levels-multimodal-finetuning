# Testy

Podział unit/integration zachowano, a wewnątrz testy odpowiadają obszarom src:
dane rzeczywiste, synthetic, windows, charts, labeling, datasets, evaluation,
experiments i shared. Architecture sprawdza zależności, regression wzorce wyników.

- support/: wspólne konstruktory fixture i ścieżki niezależne od głębokości testu;
- fixtures/: zapisane oczekiwania, bez automatycznego nadpisywania;
- unit/: obliczenia, walidacja, kontrakty i granice zależności;
- integration/: izolowane pliki, CLI, publikacja, wznowienie i renderowanie.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_behavior.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_boundaries.py
```

Uruchamiaj z katalogu projektu. Wszystkie katalogi testów mają inicjalizatory,
więc dotychczasowe discover zbiera cały zestaw. Wspólnych fixture nie importuj
z plików test_*.py. Użyj support; [architektura](../docs/ARCHITECTURE.md).

Testy nie wymagają sieci. Wzorce generatora i PNG wskazują wersje środowiska,
na których je zapisano; pominięcie na innej wersji nie potwierdza zgodności.
Nowy [wzorzec refaktoryzacji](fixtures/README.md) pochodzi ze starej implementacji.

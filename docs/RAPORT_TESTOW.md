# Weryfikacja naprawy importu i skryptu porównania

Pełny zestaw: **130 testów OK**, bez pominięć, 41.246 s.
Windows, Windows PowerShell 5.1, CPython 3.13.15.

```powershell
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

121 dotychczasowych testów pozostało aktywnych, w tym golden v1/v2,
przenośność audytu oraz rzeczywista blokada katalogu Windows.
Dziewięć nowych testów `tests/integration/test_refinement_runner.py` obejmuje:

- brak modułu i konflikt miejsca importu;
- prawidłowy preflight, brak profilu, brak raportu i duplikat raportu;
- natywny PowerShell CheckOnly wywołany z innego katalogu, także prawidłowe
  raportowanie błędu wejścia z zachowaniem pełnego tracebacku;
- przerwanie po publikacji partii przed checkpointem, odzyskanie tej partii,
  brak ponownego generowania oraz poprawny smoke z czterema raportami;
- ponowne wznowienie bez uruchamiania CLI i bez zmiany wyników;
- odmowę nadpisania istniejącego katalogu i zmian tożsamości wznowienia;
- zwalnianie blokady po błędzie i odmowę równoczesnego wznowienia;
- odmowę uznania częściowego katalogu i manifestu o złej liczności;
- zachowanie oryginalnego tracebacku CLI w logu UTF-8;
- wykrywanie zmienionego CSV przez checkpoint/walidację.

Testy tworzą wyłącznie małe partie sztuczne w temp. Historyczne raporty fixture
korzystają z powtarzanych sztucznych okien i jawnie skonstruowanych metadanych
60-oknowych, żeby sprawdzić preflight bez generowania setek serii. Nie są wynikami
eksperymentu rynku. Rozróżnienie czterech grup i kompletność agregacji sprawdzają
również dotychczasowe testy refinement/experiments.

## Sprawdzenie rzeczywistego środowiska i wejść

Przed naprawą odtworzono traceback importu, potwierdzono brak całego katalogu
synthetic i właściwą lokalizację interpretera/importu market_levels.
Po przywróceniu 18 plików sprawdzono SHA każdego z odzyskanej kompletnej migawki,
metadane editable, importy oraz `--help` obu CLI (.exe i python -m).

Oficjalny CheckOnly przeszedł na wszystkich czterech istniejących profilach
i 12 rzeczywistych raportach historycznych. Nie wykonuje generowania.
Oficjalny SmokeTest uruchomiono z obcego katalogu terminala i z wyjściem temp:
**8 nowych serii, dwa manifesty, cztery raporty porównawcze** na istniejących
profilach BTC/ETH. Jawne wznowienie zakończyło się sukcesem bez zmiany plików.
Logi tej próby są dołączone do handoffu.

`git diff --check` nie zgłosił błędów whitespace; ostrzeżenia CRLF wynikają
z ustawień Git na Windows. Kontrola przed/po obejmuje SHA-256 4822 istniejących
plików data/processed i data/synthetic; wynik znajduje się w handoffie.

Nie wykonano RunFull, nowej kalibracji rynku, zmiany parametrów, docelowych
440 przykładów, wykresów, etykietowania ani treningu. Nie badano działania
na innych systemach/wersjach Pythona. Testy nie oznaczają akceptacji generatora.

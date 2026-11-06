# Audyt i pilotaż — PowerShell

Uruchamiaj z głównego katalogu projektu, w istniejącym środowisku Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[charts]"
.\scripts\run_chart_audit.ps1
```

Domyślnie tworzy nowy `results/diagnostics/dc-<12 hex>` i 32 PNG. Można jawnie
ustawić nowy krótki katalog, seed selekcji oraz 6/7/8 obrazów na grupę
(BTC real, BTC synthetic, ETH real, ETH synthetic):

```powershell
.\scripts\run_chart_audit.ps1 -OutputDirectory results/diagnostics/review-01 -SelectionSeed 20261106 -PerGroup 8
```

Ponowne uruchomienie na istniejącym katalogu odmawia zapisu. Nie usuwaj
dotychczasowych wyników w celu ponowienia; wybierz nowy katalog. Ścieżki końcowe
i staging muszą mieć mniej niż 260 jednostek UTF-16. Przy blokadach Windows
publikacja ponawia sam rename, wykorzystując istniejący moduł staging projektu.
Nie regeneruje danych ani nie pomija błędów źródłowych po cichu.

Równoważny CLI z jawnymi źródłami:

```powershell
.\.venv\Scripts\python.exe -m market_levels.cli.audit_charts `
  --config configs/experiment.json `
  --synthetic-root data/synthetic `
  --btc-csv data/processed/BTCUSDT_4h_2020-01_2026-10.csv `
  --eth-csv data/processed/ETHUSDT_4h_2020-01_2026-10.csv `
  --output results/diagnostics/review-02 --selection-seed 20261106 --per-group 8
```

Po instalacji dostępny jest też `market-levels-audit-charts.exe`.
Nie uruchamiaj generatorów ani kalibracji, aby zastąpić brakujące wejścia.
Audyt wybiera największą opublikowaną partię refined na seed. Mniejsze próby
są wyliczane jako pominięte; dwie jednakowo duże partie powodują błąd
niejednoznaczności. W takim przypadku wskaż węższy katalog źródeł.
Braki i niepoprawne przykłady są raportowane i nie są naprawiane nową generacją;
pilotaż może mieć mniej obrazów. Kod sukcesu oznacza utworzenie diagnostyki,
a nie zatwierdzenie jakości — sprawdź `quality_errors`, `completeness`,
`duplicate_ohlc` oraz `pilot.coverage` w JSON.

Źródła lokalnego wykonania:

- `data/synthetic/rc-4e06cde3da05/full-20261105|20261115|20261125/diagnostics/…`.
- `data/synthetic/rf-73945c52e28b/full-20261201|20261211/diagnostics/…`.
- Dwa pełne CSV `data/processed/*USDT_4h_2020-01_2026-10.csv`.
- Profile przypięte manifestami, w `data/synthetic/refinement-81150be97c7448dc94ce6004d3514832/profiles/`.

Pełne ścieżki są w `run.json`, `SOURCE_INTEGRITY.json` i metadanych. Numery
seedów nie są datami notowań. Parser rzeczywisty konwertuje tylko treningowe
OHLC i zatrzymuje się po odczycie pierwszego późniejszego znacznika czasu.
SHA ochrony źródeł obejmuje bajty całych CSV, także nieanalizowanych okresów;
nie jest estymacją ani wyborem parametrów na validation/test.

Sprawdzenie przenośnego pilotażu wymaga tylko paczki i zainstalowanego kodu:

```powershell
.\.venv\Scripts\python.exe scripts/verify_chart_pilot.py results/diagnostics/review-01/pilot --re-render
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

W rozpakowanym handoffie zamiast ścieżki `results/.../pilot` podaj `pilot`.
Weryfikator nie potrzebuje pełnej historii ani oryginalnych profili: sprawdza
PNG, SHA, boczne JSON i eksportowane okna. `--re-render` dodatkowo odtwarza PNG
w katalogu tymczasowym i porównuje hashe. Identyczność bajtowa wymaga tej samej
wersji renderera, Matplotlib, fontów i zgodnego środowiska; wersje zapisano w
metadanych i `CHART_ENVIRONMENT.txt` w handoffie. Przy innych wersjach można
sprawdzić integralność bez `--re-render`, ale nie deklarować równych bajtów.

Przekazuj lokalny ZIP pilotażu lub cały handoff, bez pakowania `data/`, `.venv/`,
historycznych paczek i cache. Paczka zawiera pochodne danych Binance na prośbę
autora; zachowaj `docs/LICENCJA_DANYCH.md` i nie traktuj MIT kodu jako licencji
na dane. To nie jest publiczna publikacja danych ani akceptacja eksperymentu.

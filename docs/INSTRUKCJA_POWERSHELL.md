# Oficjalna procedura porównania refinement

Domyślny katalog ma krótką nazwę `data/synthetic/rc-<12 hex>`; pełny UUID jest
w run.json. Przed generowaniem sprawdzane są długości ścieżek obu wariantów,
także po publikacji. CheckOnly może otrzymać OutputDirectory do sprawdzenia
wybranej lokalizacji. [Poprawka MAX_PATH](WINDOWS_REFINEMENT_PATH_FIX.md).

Projekt musi zawierać cały `src/market_levels/data_processing/synthetic/`.
Rozpakuj aktualny handoff do osobnego katalogu/przejrzyj zmiany źródeł. Zachowaj
lokalne data/ z oryginalnymi CSV, profilami i raportami; nie ma ich w ZIP-ie.
Nie kopiuj samych zmienionych plików z pominięciem całego nowego pakietu synthetic.

Z katalogu głównego projektu, Windows PowerShell 5.1 lub nowszy:

```powershell
./.venv/Scripts/python.exe -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw 'Instalacja nieudana' }
./.venv/Scripts/python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Testy nieudane' }
```

## Kontrola bez generowania

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_refinement_comparison.ps1 -CheckOnly
```

Domyślnie skrypt znajduje po jednym profilu
`data/synthetic/*/profiles/{SYMBOL}_{VARIANT}_refined_unapproved.json`
i 12 indywidualnych raportów V1/full-original w
`data/synthetic/v2-evaluation/comparisons/`. Inne warianty pomija.
Kilka pasujących profili lub duplikaty raportów są błędem, nie wybieramy najnowszego.
Wszystkie ścieżki względne są rozwiązywane względem projektu ustalonego ze skryptu.
Można wywołać skrypt pełną ścieżką z dowolnego katalogu terminala.

## Mała próba — 8 nowych serii

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_refinement_comparison.ps1 -SmokeTest
```

Zapisz wypisaną ścieżkę katalogu przebiegu. Powstaną dwa manifesty i cztery raporty
JSON/Markdown. Ponowne wywołanie bez ResumeDirectory stworzy osobny nowy przebieg.

## Pełne porównanie — uruchamia autor świadomie, osobno

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_refinement_comparison.ps1 -RunFull
```

To 720 nowych serii, nie 2160: tylko full-refined i bridge_volatility-refined,
60 BTC + 60 ETH na wariant/seed 20261105, 20261115, 20261125.
Referencja: train z chronological_v1, 60 okien po 120 świec, selection_seed=20261106.
Stare dane nie są generowane ponownie. Po zakończeniu przekaż pliki
`summary/**/{SYMBOL}_comparison.json` i `{SYMBOL}_summary.md` dla obu instrumentów.
Tabele mają V1, V2-full-original, V2-full-refined i V2-bridge_volatility-refined.
Nie jest to niezależny test rynkowy ani automatyczne zatwierdzenie.

## Wznowienie

Wpisz rzeczywisty wypisany wcześniej katalog; zachowaj ten sam tryb:

```powershell
$previousRun = 'data/synthetic/rc-TUTAJ_IDENTYFIKATOR'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_refinement_comparison.ps1 -RunFull -ResumeDirectory $previousRun
```

Dla przerwanego smoke użyj `-SmokeTest -ResumeDirectory $previousRun`.
Nie kasuj checkpointów ani plików danych. Zmiana wejść, kodu, interpretera,
profilu lub konfiguracji wymaga osobnego przebiegu. Niekompletne/uszkodzone
pliki powodują odmowę, nie są automatycznie naprawiane przez nadpisanie.
`-OutputDirectory 'data/synthetic/moja-nowa-proba'` wybiera nowy katalog,
który musi jeszcze nie istnieć. Nie łącz OutputDirectory i ResumeDirectory.

## Inne lokalizacje wejść

Podaj `-InputsFile configs/refinement_inputs.local.json` we wszystkich trybach,
także podczas wznowienia. Plik JSON obsługuje wyłącznie pola `config`,
`profiles`, `real_csv`, `historical_reports`; wszystkie ścieżki są względem
projektu, można również użyć ścieżek absolutnych. Przykładowa struktura:

```json
{
  "config": "configs/experiment.json",
  "profiles": {
    "BTCUSDT|full": "data/synthetic/MOJ_KATALOG/profiles/BTCUSDT_full_refined_unapproved.json",
    "BTCUSDT|bridge_volatility": "data/synthetic/MOJ_KATALOG/profiles/BTCUSDT_bridge_volatility_refined_unapproved.json",
    "ETHUSDT|full": "data/synthetic/MOJ_KATALOG/profiles/ETHUSDT_full_refined_unapproved.json",
    "ETHUSDT|bridge_volatility": "data/synthetic/MOJ_KATALOG/profiles/ETHUSDT_bridge_volatility_refined_unapproved.json"
  }
}
```

Opcjonalne `real_csv` mapuje BTCUSDT/ETHUSDT na źródłowe pliki CSV.
`historical_reports` to lista dokładnie 12 istniejących raportów indywidualnych
V1/full-original z trzech znanych seedów i obu symboli, nie raportów zbiorczych.
Te pola można pominąć, aby korzystać z domyślnego wyszukiwania.
Nie podawaj nowych wag ani parametrów kalibracji — skrypt nie prowadzi kalibracji.

Przy błędzie przeczytaj wskazany log w katalogu temp lub `logs/` i `error-*.log`
w przebiegu. Nie uruchamiaj starszego `run_refinement_known_seeds.ps1`.

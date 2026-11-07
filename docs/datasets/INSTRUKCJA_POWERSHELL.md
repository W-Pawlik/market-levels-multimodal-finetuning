# Etap 3.5 — PowerShell

## Część 2: aktualna ścieżka produkcyjna

Decyzją autora z 2026-11-07 dopuszczono pierwsze 800 przykładów. Wykonane
zatwierdzone profile są w `data/synthetic/approved-ds35-20261107`;
konfiguracja już na nie wskazuje. Nie ponawiaj zatwierdzania ani generacji
z tym samym master seedem. Oryginalne profile pozostają `unapproved`.
Używaj istniejącej `.venv` i uruchamiaj polecenia z katalogu głównego.

Oddzielne polecenia wykonania (nazwy odnoszą się do zapisanych wyników):

```powershell
# Preflight wykonany po zmianie ścieżek na approved, przed pierwszą produkcją:
.\.venv\Scripts\python.exe -m market_levels.cli.build_dataset preflight `
  --output results/diagnostics/ds35-prod-pre-20261107-a

# Budowa: nowy katalog, kontrola aktualności planu, brak nadpisywania:
.\.venv\Scripts\python.exe -m market_levels.cli.build_dataset build `
  --plan results/diagnostics/ds35-prod-pre-20261107-a `
  --output data/datasets/ds35-800-20261107-a

# Weryfikacja istniejącego zbioru, bez modyfikowania danych:
.\.venv\Scripts\python.exe -m market_levels.cli.build_dataset verify `
  --output data/datasets/ds35-800-20261107-a --check-sources
```

Dwa pierwsze polecenia dokumentują ukończone wykonanie; **nie uruchamiaj ich
ponownie pod tymi nazwami**. Po publikacji zbioru jego master seed jest
zarezerwowany. Nowy preflight z tym samym seedem celowo zgłosi kolizję także
wobec opublikowanych zbiorów w `data/datasets`, poza historią generatora
w `data/synthetic`. To zabezpieczenie przed uznaniem tej samej symulacji za
nowy eksperyment. Nie zmieniaj seeda ani liczebności w celu obejścia kontroli.
Do odtworzenia całej zapisanej partii służy trzecie polecenie: regeneruje
440 syntetycznych OHLC, odtwarza 800 PNG i etykiet z zapisanych wejść.

Na innym komputerze bez dużych CSV pomiń `--check-sources`; nadal sprawdzane są
plan, kopie 120 świec, wszystkie profile, seedy, etykiety, obrazy, JSONL i hashe.
Flaga `--allow-renderer-difference` pozwala jawnie raportować różnice bajtów PNG
przy innej wersji renderera/Matplotlib/fontów. Nie pomija kontroli etykiet,
OHLC, źródeł, formatu PNG i manifestu. W środowisku produkcyjnym użyto
domyślnej ścisłej kontroli bajtowej.

Procedura zatwierdzania, użyta jednorazowo przed zmianą konfiguracji:

```powershell
# config-before wskazuje oryginały; poniższy cel już istnieje, więc nie ponawiaj:
.\.venv\Scripts\python.exe -m market_levels.cli.build_dataset approve `
  --config results/diagnostics/ds35p-20261107-a/config-before.json `
  --decision-date 2026-11-07 `
  --audit results/diagnostics/dc-20261106-c/AUDYT_ROZNORODNOSCI.json `
  --output data/synthetic/approved-ds35-20261107
```

`approve` weryfikuje źródła, okresy, audyt i niezmienione parametry; tworzy
nowe pliki i nie edytuje oryginałów. Konfigurację zaktualizowano jawnie po
zatwierdzeniu. `require_production_ready()` nadal uruchamia istniejącą bramkę
`prepare_profiles()` z `diagnostic=False`. Nie ma produkcji na `unapproved`.

Do późniejszego treningu wybierz wyłącznie `splits/train.jsonl`;
validation i test mają osobne pliki. Ścieżki obrazów są względem katalogu
głównego zbioru, nie względem podkatalogu splits. Nie używaj rekurencyjnego
wczytywania wszystkich JSONL jako treningu. Obrazy z poziomami są tylko
w `results/diagnostics/ds35-review-20261107-a/overlays`.

Pełne testy offline:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Nowe dane: [raport części 2](RAPORT_3_5_CZ2.md). Poniżej pozostawiono
historyczną procedurę części 1; domyślna konfiguracja wskazuje już profile
zatwierdzone, a seed produkcyjny jest zarezerwowany.

## Część 1: historyczna próba diagnostyczna

Uruchamiaj z katalogu głównego projektu, używając istniejącego środowiska.
Jeżeli brakuje zależności renderera, zainstaluj `.[charts]` według głównego README.
CLI modułowe działa bez ponownej instalacji. Aby odświeżyć entry point
`market-levels-build-dataset`, wykonaj `python -m pip install -e .` interpreterem
projektu. Poniższe polecenia nie pobierają danych ani nie generują syntetycznych OHLC.

```powershell
$run = [guid]::NewGuid().ToString('N').Substring(0, 8)
$pre = "results/diagnostics/ds35-pre-$run"
$smoke = "results/diagnostics/ds35-smoke-$run"
$check = "results/diagnostics/ds35-check-$run"
$testLog = Join-Path $env:TEMP "ds35-tests-$run.txt"

.\.venv\Scripts\python.exe -m market_levels.cli.build_dataset preflight --output $pre
if ($LASTEXITCODE -ne 0) { throw 'Nieudany preflight: przeczytaj błąd lub problems w plan.json' }

.\.venv\Scripts\python.exe -m market_levels.cli.build_dataset smoke --output $smoke
if ($LASTEXITCODE -ne 0) { throw 'Nieudana mała próba' }

.\.venv\Scripts\python.exe -m market_levels.cli.build_dataset verify --output $smoke
if ($LASTEXITCODE -ne 0) { throw 'Nieudana weryfikacja próby' }

.\.venv\Scripts\python.exe -m unittest discover -s tests -v *> $testLog
if ($LASTEXITCODE -ne 0) { Get-Content $testLog -Tail 40; throw 'Testy niezaliczone' }

.\.venv\Scripts\python.exe scripts/verify_dataset_stage.py `
  --preflight $pre --smoke $smoke `
  --pilot results/diagnostics/dc-20261106-c/pilot `
  --labeling results/diagnostics/sr-20261106-a `
  --test-log $testLog --check-local-sources --output $check
if ($LASTEXITCODE -ne 0) { throw 'Nieudana zbiorcza kontrola' }
```

`preflight` domyślnie korzysta z dwóch CSV
`data/processed/{BTCUSDT,ETHUSDT}_4h_2020-01_2026-10.csv`. Dostępne są
`--config`, `--real-root`, `--btc-csv`, `--eth-csv`. Profil musi wskazywać hash
tego samego źródła. Brak danych lub niedobór okien jest raportowany jako
`real_feasible: false`, `problems`; po zapisaniu planu CLI zwraca kod 2.
Błąd struktury, profilu albo kolizja wyjścia daje kod 1. Nie ma pobierania,
interpolacji ani automatycznej korekty liczebności/przesunięć.

`smoke --per-group 1` daje 4 przykłady, domyślne 2 daje 8. Cały źródłowy pilotaż
32 okien jest sprawdzany przed wyborem. Próba bierze pierwsze ID w każdej grupie,
bez nowej oceny atrakcyjności. To kontrola techniczna, a nie selekcja docelowa.
`verify` odtwarza PNG i etykiety z kopii 120 świec oraz weryfikuje wszystkie
wiązania, JSONL, inwentarz i SHA-256. Nie nadpisuje sprawdzanego katalogu.

Liczebności zmienia się **wyłącznie w `dataset_build.targets`**.
Sumy i udziały plan wylicza automatycznie; starsze pola `target_total_charts`
i `target_*_share` są historycznym opisem założenia, nie drugim sterownikiem
budowy. Aktualne 800/45%/55% są z nimi zgodne. Granice `chronological_v1`
pozostają zatwierdzone. Przesunięcia czytane są z dotychczasowych pól JSON.

`dataset_build.profiles` przypina dwa profile full-refined. Ich lokalizacje
mogą wymagać dostosowania na innym komputerze. `synthetic_history_root` musi
zawierać lokalną historię manifestów, aby skontrolować seedy. Kontrola obejmuje
także seedy zapisane w konfiguracji i profilach. Brak danych innych komputerów
nie stanowi dowodu braku kolizji w tych środowiskach.

Profile pozostają `unapproved`. `synthetic_settings()` zwraca ustawienia v2/full
z `diagnostic=False`; `require_production_ready()` deleguje kontrolę do obecnego
`prepare_profiles()`. **Nie używaj `--diagnostic` jako sposobu obejścia blokady.**
W tym etapie nie ma komendy produkcyjnej ani automatycznej budowy 800 obrazów.

Wykonane artefakty:

- `results/diagnostics/ds35-pre-20261107-b`: aktualny preflight (a zachowano jako wcześniejszy przebieg).
- `results/diagnostics/ds35-smoke-20261107-a`: 8 przykładów i audyt.
- `results/diagnostics/ds35-check-20261107-a`: zbiorcza kontrola i pełny log testów.

Handoff obecnego wykonania, bez nadpisania:

```powershell
.\.venv\Scripts\python.exe scripts/create_dataset_handoff.py --output handoff/etap-3-5-cz1-20261107.zip
```

Skrypt pakuje aktualne źródła, instrukcje, testy, konfigurację, dwa małe profile,
nową diagnostykę i źródłowy pilotaż 3.3/3.4 do odtworzenia kontroli. Pomija pełne
CSV rynku, pełne serie audytów, `.venv`, cache, build i egg-info. ZIP zawiera
`HANDOFF_SHA256.json`; obok ZIP powstaje `.sha256`. Po przeniesieniu paczki
można zweryfikować małą próbę i wcześniejszy pilotaż bez danych rynku.
Pełny preflight wymaga oryginalnych dwóch CSV i kompletnej lokalnej historii
manifestów; nie pobieraj ich automatycznie. `--check-local-sources` w kontroli
zbiorczej pomiń, jeżeli oryginalne absolutne ścieżki nie istnieją.

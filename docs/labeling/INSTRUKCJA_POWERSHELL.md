# Etykietowanie pilotażu — PowerShell

Wykonuj polecenia z głównego katalogu projektu. Korzystaj z istniejącego środowiska.
Jeżeli dopiero przygotowujesz środowisko po otrzymaniu paczki, wykonaj
`py -3 -m venv .venv`. Instalacja z dodatkiem `charts` udostępnia Matplotlib:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[charts]"
```

Nie uruchamiaj generatora ani audytu 600 serii. Wejściem są wyłącznie istniejące
32 okna z pilotażu 3.3. Nazwa wyjścia musi być nowa; katalog już istniejący,
także pusty, powoduje odmowę. Wyniki można zapisać tylko pod `results/diagnostics/`.

```powershell
$pilot = 'results/diagnostics/dc-20261106-c/pilot'
$output = 'results/diagnostics/sr-' + [guid]::NewGuid().ToString('N').Substring(0,12)
.\.venv\Scripts\market-levels-label-pilot.exe --pilot $pilot --output $output
if ($LASTEXITCODE -ne 0) { throw 'Etykietowanie nie powiodło się' }
.\.venv\Scripts\market-levels-label-pilot.exe --pilot $pilot --output $output --verify --re-render
if ($LASTEXITCODE -ne 0) { throw 'Weryfikacja nie powiodła się' }
```

Równoważnie użyj `python.exe -m market_levels.cli.label_pilot` zamiast entry pointu.
Parametry matematyczne są zatwierdzoną definicją, a nie opcjami CLI. CLI nie
wczytuje konfiguracji generatora ani metadanych do algorytmu.

Sprawdzenie dostarczonych wyników bez nowego zapisu:

```powershell
.\.venv\Scripts\python.exe -m market_levels.cli.label_pilot --pilot results/diagnostics/dc-20261106-c/pilot --output results/diagnostics/sr-20261106-a --verify --re-render
.\.venv\Scripts\python.exe scripts/verify_chart_pilot.py results/diagnostics/dc-20261106-c/pilot --re-render
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`--verify` sprawdza komplet plików, SHA-256, powiązanie źródeł, ponownie liczy
etykiety, diagnostykę i statystyki. `--re-render` dodatkowo porównuje bajty PNG.
Identyczność PNG zależy od środowiska: wykonanie lokalne Python 3.13.15,
Matplotlib 3.11.2, Windows, DejaVu Sans. Inna wersja może renderować inaczej mimo
identycznych poziomów; wówczas weryfikację matematyki uruchom bez `--re-render`.

W nowym katalogu:

- `labels/000.json`…`031.json`: tylko odpowiedź VLM, liczby JSON w kolejności rankingu.
- `diagnostics/`: pełne ceny Decimal zapisane jako tekst, TR/ATR, ekstrema, grupy,
  reakcje i odrzucenia, zachowane metadane źródła.
- `overlays/`: osobne obrazy z liniami i legendą. **Wyłącznie diagnostyka; nie
  wolno używać tych PNG jako wejść przyszłego VLM.** Oryginały pozostają w pilotażu.
- `manifest.json`: mapowanie ID/CSV/PNG → wyniki i SHA wszystkich pozostałych plików.
- `SOURCE_INTEGRITY.json`: hashe wejść i potwierdzenie braku zmian podczas przebiegu.
- `summary.json`, `RAPORT.md`: rozkłady i tabela wszystkich 32 odpowiedzi.

Manifest nie uwierzytelnia samego siebie; paczka handoff ma dodatkowo inwentarz
SHA-256 wewnątrz ZIP oraz osobny hash całego ZIP. Absolutne ścieżki pochodzenia
wewnątrz metadanych są historycznym zapisem; po przeniesieniu paczki weryfikator
korzysta ze wskazanego `--pilot`, a nie z dużych danych źródłowych.

Nowa paczka (bez nadpisywania istniejącej):

```powershell
.\.venv\Scripts\python.exe scripts/create_labeling_handoff.py --output handoff/labeling-3-4-new.zip
Get-FileHash handoff/labeling-3-4-new.zip -Algorithm SHA256
```

Paczka zawiera kod, testy, konfigurację, dokumentację, instrukcje AI, źródłowy mały
pilotaż i nowe wyniki. Nie zawiera środowiska, cache ani dużej historii danych.
Nie jest publikowana; licencja MIT dotyczy kodu, zastrzeżenia do danych pozostają
w `docs/LICENCJA_DANYCH.md`.

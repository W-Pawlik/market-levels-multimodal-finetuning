# Raport refaktoryzacji — 2026-11-03

## Aktualny stan

Logika projektu znajduje się w pakiecie `market_levels`, w układzie src-layout.
Na późniejszą prośbę autora usunięto moduły zgodności `src/download_data.py`,
`src/validate_data.py` i `src/__init__.py`. Kod z `market_levels/data` przeniesiono
do `market_levels/data_processing`, aby odróżnić go od artefaktów w głównym `data/`.
Stare polecenie `python -m src.download_data` zostało zastąpione instalowanym CLI.
Zasady pobierania, walidacji i format wyników pozostały takie same.

Następnie na prośbę autora podłączono `configs/experiment.json` do CLI.
Daty i symbole są pobierane z istniejących pól; nowa sekcja `download` określa
katalog wyników, offline, kontrolę luk i fallback. Argumenty CLI nadpisują JSON.
`--config` pozwala wskazać inny plik. Nie zmieniono zatwierdzonych parametrów.

## Struktura

Pominięto `__init__.py`, lokalne cache i wygenerowane metadane instalacji.
Przyszłe obszary kodu zawierają wyłącznie README.

```text
.
├── README.md
├── pyproject.toml
├── .gitignore
├── configs/experiment.json
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DECYZJE_3_3.md
│   ├── LICENCJA_DANYCH.md
│   └── REFACTORING_REPORT.md
├── src/market_levels/
│   ├── configuration.py
│   ├── cli/download.py
│   ├── core/
│   │   ├── candles.py
│   │   └── periods.py
│   ├── data_processing/
│   │   ├── validation.py
│   │   ├── storage.py
│   │   ├── pipelines/download.py
│   │   ├── real/binance_vision/
│   │   │   ├── client.py
│   │   │   ├── archives.py
│   │   │   └── parsing.py
│   │   ├── synthetic/README.md
│   │   └── windows/README.md
│   ├── charts/README.md
│   ├── labeling/README.md
│   ├── datasets/README.md
│   ├── modeling/README.md
│   ├── training/README.md
│   ├── inference/README.md
│   ├── evaluation/README.md
│   └── experiments/README.md
├── tests/
│   ├── unit/
│   │   ├── test_validation.py
│   │   └── test_contracts.py
│   ├── integration/
│   │   ├── test_configuration.py
│   │   ├── test_offline.py
│   │   ├── test_pipeline_contracts.py
│   │   └── test_transfer.py
│   └── fixtures/
│       ├── README.md
│       └── pipeline_baseline.json
├── data/
│   ├── raw/
│   ├── processed/
│   ├── reports/
│   ├── synthetic/
│   ├── charts/
│   ├── labels/
│   └── splits/
└── results/
    ├── predictions/
    ├── metrics/
    ├── figures/
    ├── logs/
    ├── checkpoints/
    └── adapters/
```

Dokładną mapę przeniesionych funkcji i uzasadnienie podziału opisuje
[architektura](ARCHITECTURE.md). Nie dodano klas usług, interfejsów ani zależności
uruchomieniowych. Setuptools jest zależnością budowania. Nie zaimplementowano
żadnego przyszłego etapu, nie zmieniono parametrów eksperymentu ani licencji.

## Weryfikacja

Środowisko: Windows PowerShell, Python 3.13.15.

| Kontrola | Wynik |
| --- | --- |
| Przed pierwszą refaktoryzacją | 6/6 testów OK |
| Po pierwszej refaktoryzacji z warstwą zgodności | 25/25 testów OK |
| Po usunięciu warstwy zgodności i zmianie nazwy katalogu | 24/24 testy OK; usunięto tylko test dawnych reeksportów |
| Po podłączeniu JSON do CLI | 30/30 testów OK, w tym konfiguracja, nadpisania, błędy i pełny lokalny pipeline |
| Sześć pierwotnych przypadków testowych | zachowane, importy skierowane do właściwych modułów |
| ZIP → CSV, raport, manifest i stdout względem wzorca oryginału | OK |
| Ceny Decimal, UTC, ms/µs, duplikaty, luki, okresy i SHA-256 | OK |
| Offline, cache, strict-gaps, niepoprawny ZIP i suma | OK |
| Fallback ostatniego zamkniętego miesiąca, 404, offline i ograniczenia | OK, mocki pozyskiwania, bez sieci |
| HTTP: retry, timeout, User-Agent, cache, `.part`, 404/403/429/503 | OK, mock HTTP |
| Nowe CLI: wartości domyślne, flagi, dry-run i błąd offline | OK |
| Oryginalne archiwa styczniowe, oba instrumenty | po 186 świec, bez braków |
| Wyniki nowej struktury względem wzorca sprzed refaktoryzacji na tych samych kopiach archiwów | CSV identyczne bajtowo; wszystkie pola raportów i manifestu zgodne poza czasem utworzenia |
| SHA-256 14 chronionych plików przed integracją konfiguracji | bez zmian; później JSON celowo rozszerzono o download, zachowując zatwierdzone parametry |
| Instalacja edytowalna w lokalnym `.venv` i nowe polecenie konsolowe | OK |

W pierwszej fazie dodatkowo porównano 38 rekordów starego i nowego parsera
(wartości lub pełne komunikaty i nazwy typów błędów), stdout help/dry-run
oraz błąd niepoprawnej daty CLI. Wyniki były zgodne. Sprawdzono też zwykłą
instalację wheel poza projektem i brak zależności `Requires-Dist`.
Reguły `.gitignore` zweryfikowano w osobnym repozytorium tymczasowym.

Nie pobierano notowań z sieci ani całej historii. Rzeczywistego fallbacku
na serwerze Binance nie sprawdzano. Nie wykonywano testów na Pythonie 3.10–3.12.
Polecenie CLI i ścieżki importów zmieniono świadomie na prośbę autora;
formaty, nazwy i lokalizacje artefaktów danych nie zmieniły się.

## Celowo pozostawione ograniczenia

- Lokalny CHECKSUM jest ponownie używany bez odświeżania go z serwera.
- `iter_months` wykorzystuje `assert`, więc `-O` może zmienić walidację wejścia.
- Ponowne uruchomienie nadpisuje CSV/raporty; strict-gaps przerywa przed zapisem
  nowego manifestu, więc wcześniejszy manifest może pozostać.
- Fallback zależy od lokalnej daty komputera.

Przy integracji konfiguracji zmieniono obsługę błędów wejścia: niepoprawny JSON,
brak pliku i błędne daty kończą się czytelnym komunikatem `BŁĄD:` zamiast
tracebacka. Pola przyszłych etapów eksperymentu pozostają nieaktywne do czasu
implementacji tych etapów.

Projekt nie zawiera `.git`; nie tworzono commita. Automatyczna kontrola
w pierwszej fazie odrzuciła usunięcie wygenerowanych artefaktów budowania.
`build/`, `.venv/` i `*.egg-info/` są ignorowane. `egg-info` zawiera metadane
instalacji, nie kod źródłowy; narzędzia instalacji generują je automatycznie.

## Uruchomienie w PowerShell

Jednorazowo:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Następnie:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\market-levels-download.exe --start 2020-01 --end 2020-01 --dry-run
```

Pozostałe opcje i rzeczywiste pobieranie opisuje [README](../README.md).

## Nazwa projektu i przekazanie

Aktualna nazwa katalogu: market-levels-multimodal-finetuning.
Pakiet Python: market_levels; dystrybucja: market-levels.
Po zmianie nazwy potwierdzono działanie 30 testów i CLI dry-run
oraz niezmienność SHA-256 16 lokalnych plików w data/.
Paczka przekazania zawiera kod, konfigurację, testy i dokumentację.
Dane rynkowe, lokalne raporty, środowisko i artefakty budowania pominięto.

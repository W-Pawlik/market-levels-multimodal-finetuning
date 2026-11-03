# Market Levels — projekt pracy inżynierskiej

Projekt służy badaniu dostrajania modelu multimodalnego do znajdowania poziomów
wsparcia i oporu na wykresach finansowych. Docelowy proces obejmuje dane OHLC,
wykresy, etykiety, zbiory treningowe, dostrajanie, inferencję i ewaluację.

**Działają pobieranie i walidacja rzeczywistych OHLC oraz generator syntetyczny
z kalibracją, diagnostyką i osobnym CLI.** Renderowanie, etykiety i modele pozostają
do implementacji. Lokalnie potwierdzono pełny zakres 2020-01–2026-10: po 14 975
świec BTCUSDT i ETHUSDT; w obu brak 2020-02-19 12:00 UTC. Nie interpolowano luk.

## Przygotowanie — Windows PowerShell

Python 3.10+ (zalecany 3.11+). Aktualny proces używa tylko biblioteki standardowej,
bez klucza API. Jednorazowo przygotuj środowisko i zainstaluj lokalny pakiet:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Następnie uruchamiaj testy i pobieranie z katalogu głównego projektu:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\market-levels-download.exe --start 2020-01 --end 2020-01 --dry-run
.\.venv\Scripts\market-levels-download.exe --start 2020-01 --end 2020-01
```

Ostatnie polecenie wykorzystuje istniejące archiwa lub pobiera brakujące pliki
z Binance Vision. Aby wymusić pracę lokalną:

```powershell
.\.venv\Scripts\market-levels-download.exe --start 2020-01 --end 2020-01 --offline
```

Ponowne uruchomienie zapisuje CSV i raporty pod tymi samymi nazwami. Do prób
używaj osobnego `--output`; offline szuka wtedy archiwów w `<output>/raw/`.

To samo CLI można uruchamiać jako moduł Pythona:

```powershell
.\.venv\Scripts\python.exe -m market_levels.cli.download --start 2020-01 --end 2020-01 --dry-run
```

Pakietowanie wymaga setuptools; nie dodaje zależności uruchomieniowych.
Przyszłych bibliotek ML i wykresów nie trzeba obecnie instalować.
Ścieżki danych są liczone względem bieżącego katalogu.
Stare moduły `src.download_data` i `src.validate_data` zostały usunięte.
`src` jest katalogiem źródeł, a importowany pakiet nazywa się `market_levels`.

Instalacja edytowalna tworzy `src/market_levels.egg-info/`: metadane pakietu
(nazwa, wersja, pliki, polecenia). Katalog jest generowany automatycznie przez
narzędzia instalacji i ignorowany przez Git. Nie edytuje się go ręcznie.

## CLI

| Argument | Wartość domyślna / znaczenie |
| --- | --- |
| `--config` | `configs/experiment.json`, plik ustawień |
| `--start` | `history_start_month` z JSON; obecnie `2020-01` |
| `--end` | `history_end_month` z JSON; obecnie `2026-10` |
| `--output` | `download.output` z JSON; obecnie `data` |
| `--symbols` | `symbols` z JSON; obecnie `BTCUSDT ETHUSDT` |
| `--offline` / `--no-offline` | nadpisz `download.offline`; obecnie `false` |
| `--strict-gaps` / `--no-strict-gaps` | nadpisz `download.strict_gaps`; obecnie `false` |
| `--daily-fallback` / `--no-daily-fallback` | nadpisz `download.daily_fallback`; obecnie `true` |
| `--dry-run` | wyłączony; wypisz URL-e bez pobierania i zapisu |

Program pobiera miesięczne archiwa spot `4h` z `.CHECKSUM`, weryfikuje SHA-256
i odczytuje CSV bez wypakowywania ZIP. Zachowuje ceny `Decimal`, czas UTC
i obsługę milisekund/mikrosekund. Odrzuca niepoprawne OHLC, duplikaty i nieregularne
odstępy. Raportuje luki, również na brzegach, bez interpolacji. Fallback dzienny
dotyczy tylko ostatniego zakończonego miesiąca według lokalnej daty komputera,
przy 404 albo braku lokalnego pliku offline. Błędna suma nie uruchamia fallbacku.

## Struktura

```text
configs/experiment.json          zatwierdzone ustalenia
src/market_levels/
    configuration.py            odczyt i walidacja konfiguracji
    cli/                        argumenty i obsługa błędów
    core/                       model świecy i operacje na okresach
    data_processing/real/binance_vision/   HTTP, archiwa i parser Binance
    data_processing/validation.py          walidacja świec i szeregów
    data_processing/storage.py             zapis CSV i JSON
    data_processing/pipelines/             koordynacja procesu
    ...                         przyszłe etapy, opisane w README katalogów
data/                           lokalne dane i raporty
results/                        przyszłe wyniki eksperymentów
tests/unit/                     testy jednostkowe
tests/integration/              testy offline i CLI
tests/fixtures/                 wynik oryginalnej implementacji na próbce
docs/                           architektura, decyzje, licencja, raport
pyproject.toml                  src-layout i polecenie pakietu
```

Szczegóły: [ARCHITECTURE.md](docs/ARCHITECTURE.md).
Testy nie wymagają Internetu; zachowano sześć pierwotnych przypadków testowych.

## Konfiguracja i plan rozwoju

**CLI automatycznie wczytuje `configs/experiment.json`.** Zmiana zakresu dat,
listy symboli lub sekcji `download` zmienia pobieranie. Argumenty CLI mają
pierwszeństwo przed JSON. Plik jest wymagany również przy `--dry-run`;
błędna konfiguracja przerywa działanie przed pobieraniem i zapisem.
Ścieżka konfiguracji oraz `download.output` są względne wobec katalogu uruchomienia.
Spoza projektu podaj `--config` z odpowiednią ścieżką.

```json
"download": {
  "output": "data",
  "offline": false,
  "strict_gaps": false,
  "daily_fallback": true
}
```

Na przykład zmień `symbols` na `["BTCUSDT"]` i oba pola `history_*_month`
na `2020-01`, aby domyślnie przetwarzać tylko BTCUSDT ze stycznia 2020.
Obecny plik zachowuje cały zatwierdzony zakres. Plan można obejrzeć bez pobierania:

```powershell
.\.venv\Scripts\market-levels-download.exe --dry-run
.\.venv\Scripts\market-levels-download.exe --config configs/experiment.json --start 2020-01 --end 2020-01 --symbols BTCUSDT --dry-run
```

Źródło, rynek i interwał są sprawdzane: obecna implementacja obsługuje Binance
Vision spot, BTCUSDT/ETHUSDT i `4h`. Inna wartość powoduje błąd zamiast cichego
zignorowania ustawienia. Zatwierdzony zakres to 2020-01–2026-10.
Parametry przyszłego eksperymentu: 120 świec na wykres,
przesunięcie treningowe 60, walidacyjne/testowe 120, roboczo 800 wykresów,
45% danych rzeczywistych i 55% syntetycznych, początkowo 1024 × 768 px.
Te parametry nie są używane przez pobieranie; będą odczytywane przez kolejne
etapy po ich implementacji.

Planowane są: okna cenowe, wykresy Matplotlib/mplfinance,
etykiety, przygotowanie zbiorów zgodnie z podziałem, pary obraz–instrukcja–JSON, obsługa modeli,
trening, osobna inferencja i ewaluacja. Model i hiperparametry wymagają osobnej
decyzji; struktura nie narzuca rodziny modeli.

## Generator syntetyczny OHLC

Sekcja `synthetic` steruje osobnym CLI; nie zmienia pobierania Binance.
Domyślnie `diagnostic=false`, a brak zatwierdzonych profili zatrzymuje wykonanie.
Do kontroli działania jawnie włącz diagnostykę:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\market-levels-generate-synthetic.exe --diagnostic --count 5 --symbols BTCUSDT ETHUSDT --seed 20261103 --dry-run
.\.venv\Scripts\market-levels-generate-synthetic.exe --diagnostic --count 5 --symbols BTCUSDT ETHUSDT --seed 20261103 --output data/synthetic
```

`--count` oznacza liczbę **na instrument**: powyższy przykład zapisuje 10
niezależnych serii po 120 świec. Ponowne identyczne uruchomienie odmawia zapisu.
Inny `--seed` tworzy nową partię. `--output` nie może wskazywać `data/processed`.
Równoważnie: `python -m market_levels.cli.generate_synthetic`.

Każda świeca powstaje z 12 kroków logarytmicznego ruchu ceny. Obsługiwane fazy:
trend wzrostowy/spadkowy, konsolidacja z powrotem do środka i krótkie wybicie.
Wyniki zawierają CSV, metadane JSON, statystyki i manifest. Data od 2000-01-01 UTC
jest wyłącznie indeksem symulacji. Nie przypisujemy przykładów do train/validation/test.

Kalibracja wymaga jawnego dozwolonego okresu, osobno dla BTC i ETH; pomija
przejścia przez luki. Podział `chronological_v1` jest zatwierdzony: trening 2020–2023,
walidacja 2024, test 2025–2026-10. Parametry i profile generatora wymagają osobnej
oceny i zatwierdzenia. Nie wykonano końcowej kalibracji ani generowania
docelowego zbioru. Kontrola wizualna czeka na renderer.

Opis parametrów, API kalibracji, format wyników i ograniczenia:
[SYNTHETIC_GENERATOR.md](docs/SYNTHETIC_GENERATOR.md).
Wyniki wykonanej weryfikacji: [raport wdrożenia](docs/SYNTHETIC_IMPLEMENTATION_REPORT.md).

## Kalibracja i opisowe porównanie z treningiem

Nowe polecenia po `pip install -e .`:

- `market-levels-calibrate`: jawne `--symbol`, `--input`, `--start`, `--end`,
  `--output`, opcjonalne `--config` i `--dry-run`; zakres musi należeć do treningu.
  Profil zawsze pozostaje `unapproved`.
- `market-levels-compare-synthetic`: odczyt rzeczywistych OHLC i istniejącego
  manifestu syntetycznego, losowanie nienakładających się okien bez luk,
  statystyki zbiorcze/okienne, autokorelacja i raport JSON/Markdown.

Granice w `chronological_split` odnoszą się do otwarcia świecy UTC i są włącznie.
Potwierdzono lokalnie po 8765/2196/4014 świec w treningu/walidacji/teście dla obu
instrumentów. Z treningu można wybrać maksymalnie 72 rozłączne okna po 120 świec;
selekcja 60 jest wykonalna mimo luki. Nie używamy walidacji/testu do kalibracji
ani dopasowania generatora. Odczytywany jest pełny CSV; ceny poza treningiem nie
wchodzą do obliczeń diagnostycznych.

Pełne polecenia PowerShell: kalibracja BTC i ETH, generowanie 60+60 ze seedem
20261105, przechwycenie ścieżki automatycznej partii i porównania osobno dla
instrumentów: [instrukcja procesu](docs/SYNTHETIC_CALIBRATION_COMPARISON.md).
Właściwe uruchomienie pozostawiono autorowi. Wyniki są opisowym porównaniem
z treningiem użytym do kalibracji, nie niezależną walidacją generatora.

## Dane i licencja

Zachowano ścieżki i schematy:
`data/raw/<symbol>/4h/<monthly|daily>/`,
`data/processed/<symbol>_4h_<start>_<end>.csv`,
`data/reports/<symbol>_<start>_<end>.json` oraz `manifest_<start>_<end>.json`.
Nagłówek CSV: `open_time_utc,open,high,low,close`. Manifest zachowuje źródła,
SHA-256 i metadane licencji. Dane, raporty i wyniki są ignorowane przez Git.

Zastrzeżenia: [LICENCJA_DANYCH.md](docs/LICENCJA_DANYCH.md).
Ustalenia: [DECYZJE_3_3.md](docs/DECYZJE_3_3.md).
Pełnych danych i wag nie publikujemy automatycznie. Kod projektu jest udostępniony na [licencji MIT](LICENSE). MIT nie obejmuje
danych Binance ani nie zastępuje ich warunków licencyjnych. Wykonane kontrole i ograniczenia opisuje
[raport refaktoryzacji](docs/REFACTORING_REPORT.md).

## Instrukcje dla AI

Punkt wejścia dla agentów to [AGENTS.md](AGENTS.md).
Katalog [.ai/](.ai/README.md) przechowuje trwałe zasady, aktualny stan projektu
i sposób weryfikacji zmian. Czytaj go przed pracą nad kodem.

Repozytorium: [GitHub](https://github.com/W-Pawlik/market-levels-multimodal-finetuning).

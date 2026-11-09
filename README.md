# Market Levels — projekt pracy inżynierskiej

Aktualny etap: 3.5, część 2 — zatwierdzone kopie V2-full-refined i produkcyjny
proces zbioru 800 przykładów. Działają okna, renderer, etykietowanie,
planowanie, budowa oraz pełne odtworzenie. Trening VLM nie został rozpoczęty.
[Raport części 2](docs/datasets/RAPORT_3_5_CZ2.md),
[aktualne polecenia PowerShell](docs/datasets/INSTRUKCJA_POWERSHELL.md).
Etap 3.6, część 1 dodaje ewaluator zapisanych odpowiedzi `sr-eval-v1`;
wykonano wyłącznie ręczne fixture, bez inferencji ani treningu VLM.
[Protokół](docs/evaluation/PROTOKOL_3_6.md),
[raport i testy](docs/evaluation/RAPORT_3_6_CZ1.md),
[PowerShell ewaluacji](docs/evaluation/INSTRUKCJA_POWERSHELL.md).
Poniższe opisy wcześniejszych eksperymentów nie są poleceniem ich ponawiania.

Publikacja partii i raportów ponawia krótkotrwałe blokady Windows bez regeneracji
danych. [Poprawka, testy i polecenia końcowego eksperymentu](docs/WINDOWS_PUBLICATION_RETRY_FIX.md).

Nowa oddzielna próba stabilności na 20261201/20261211:
[`run_refinement_fresh_seeds.ps1`](scripts/run_refinement_fresh_seeds.ps1),
[polecenia PowerShell](docs/FRESH_SEEDS_POWERSHELL.md).
Autor ukończył historyczne porównania; raporty nie łączą się z poprzednimi seedami.

Po kalibracji refinement używaj oficjalnego
[`scripts/run_refinement_comparison.ps1`](scripts/run_refinement_comparison.ps1):
CheckOnly, SmokeTest, jawny RunFull oraz wznowienie bez nadpisywania.
[Instrukcja](docs/INSTRUKCJA_POWERSHELL.md),
[naprawa brakującego pakietu](docs/RAPORT_NAPRAWY_IMPORTU.md).

Nowość: `bridge_volatility` i osobne dostrojenie dwóch parametrów AR(1),
z audytem pochodzenia i porównaniem full-original/full-refined/bez mieszanki.
[Raport refinement](docs/RAPORT_REFINEMENT_V2.md) oraz
[procedura PowerShell](docs/INSTRUKCJA_REFINEMENT_POWERSHELL.md).
Historyczne profile refinement pozostają `unapproved`. Nowe kopie dwóch profili
full zatwierdzono decyzją autora z 2026-11-07, bez ponownej kalibracji.

Projekt służy badaniu dostrajania modelu multimodalnego do znajdowania poziomów
wsparcia i oporu na wykresach finansowych. Docelowy proces obejmuje dane OHLC,
wykresy, etykiety, zbiory treningowe, dostrajanie, inferencję i ewaluację.

**Działają pobieranie i walidacja OHLC, generator V2-full-refined z profilami
zatwierdzonymi do pierwszego zbioru, renderer świecowy oraz przetestowany algorytm
etykietowania wsparć i oporów.** Przygotowano i zweryfikowano pełny zbiór 800
przykładów. Wybór, dostrajanie i ewaluacja modelu VLM pozostają do wykonania.
Lokalnie potwierdzono pełny zakres 2020-01–2026-10: po 14 975
świec BTCUSDT i ETHUSDT; w obu brak 2020-02-19 12:00 UTC. Nie interpolowano luk.

## Przygotowanie — Windows PowerShell

Python 3.10+ (zalecany 3.11+). Pobieranie i walidacja OHLC używają tylko biblioteki
standardowej, bez klucza API. Jednorazowo przygotuj środowisko i zainstaluj lokalny pakiet:

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

Pakietowanie wymaga setuptools; podstawowa instalacja nie dodaje zależności
uruchomieniowych. Renderer korzysta z Matplotlib dostępnego przez dodatek
`[charts]`: `pip install -e ".[charts]"`. Biblioteki do treningu VLM nie zostały
jeszcze wybrane.
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
configs/experiment.json          wejście konfiguracji i odwołania do sekcji
src/market_levels/
    configuration.py            konfiguracja pobierania
    cli/                        stabilne polecenia i argumenty
    core/                       OHLC, czas, walidacja, statystyki i ATR
    shared/                     integralność, ścieżki, manifesty i publikacja
    data_processing/
        real/                   Binance i workflow pobierania
        synthetic/              generatory, profile, kalibracja i diagnostyka
        windows/                okna oraz odrębne reguły selekcji
        io/                     wspólny CSV i odczyt chronologii
    charts/                     metryki, renderer i pilotaż
    labeling/                   algorytm S/R i nakładki diagnostyczne
    datasets/                   plan, budowa, audyt i odtworzenie zbioru
    evaluation/                 zapisane odpowiedzi, metryki i porównania
    experiments/refinement/     istniejący runner i wznowienie
    modeling/, training/, inference/       planowane etapy z README
data/                           lokalne dane i raporty
results/                        wyniki diagnostyki i ewaluacji
tests/unit/                     testy jednostkowe według obszarów
tests/integration/              testy offline i CLI według obszarów
tests/support/                  współdzielone fixture i ścieżki testów
tests/fixtures/                 niezmienne wzorce wyników
docs/                           architektura, decyzje, licencja, raport
pyproject.toml                  src-layout i polecenie pakietu
```

Szczegóły: [ARCHITECTURE.md](docs/ARCHITECTURE.md).
W obszarach powtarzają się `domain`, `workflows`, `io`, `reporting` i `config`,
stosownie do istniejących odpowiedzialności. README obszarów zawierają mapy
plików i punktów wejścia. Refaktoryzacja zachowała polecenia, konfigurację
i wyniki algorytmów; [raport i zakres kontroli](docs/refactoring/RAPORT_REFAKTORYZACJI_SRC.md).
Testy nie wymagają Internetu; zachowano sześć pierwotnych przypadków testowych.

## Konfiguracja i plan rozwoju

**CLI automatycznie wczytuje `configs/experiment.json`.** Zmiana zakresu dat,
listy symboli lub sekcji `download` zmienia pobieranie. Argumenty CLI mają
pierwszeństwo przed JSON. Plik jest wymagany również przy `--dry-run`;
błędna konfiguracja przerywa działanie przed pobieraniem i zapisem.
Ścieżka konfiguracji oraz `download.output` są względne wobec katalogu uruchomienia.
Spoza projektu podaj `--config` z odpowiednią ścieżką.

Ustawienia generatora, kalibracji, refinementu, chronologii i budowy zbioru są
w pięciu fragmentach wskazanych z `experiment.json`. Odwołania `$file` są
względne wobec tego pliku; ścieżki danych i wyjścia nadal wobec CWD.
Dotychczasowe pełne JSON-y i zapisane konfiguracje wyników nadal działają.
[Mapa plików i zasady konfiguracji](configs/README.md).

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
przesunięcie treningowe 60, walidacyjne/testowe 120, zatwierdzone 800 wykresów,
45% danych rzeczywistych i 55% syntetycznych, początkowo 1024 × 768 px.
Te parametry nie są używane przez pobieranie; są aktywne w budowie zbioru.

Działają okna cenowe, wykresy Matplotlib, etykiety i przygotowanie zbiorów
obraz–instrukcja–JSON. Planowane są obsługa modeli,
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
jest wyłącznie indeksem symulacji. Sam generator nie przypisuje splitów;
proces budowy zbioru umieszcza syntetyki wyłącznie w train.

Kalibracja wymaga jawnego dozwolonego okresu, osobno dla BTC i ETH; pomija
przejścia przez luki. Podział `chronological_v1` jest zatwierdzony: trening 2020–2023,
walidacja 2024, test 2025–2026-10. Autor wykonał kalibrację v1 i diagnostykę
60+60, a następnie audyty V2-full-refined i pilotaż renderera/etykietowania.
Dwa profile V2-full-refined zatwierdzono w nowych plikach do zbioru 800 przykładów.

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
Autor wykonał kalibrację v1 i porównania. Wyniki są opisowym porównaniem
z treningiem użytym do kalibracji, nie niezależną walidacją generatora.

## Generator v2 i kontrolowane warianty

Dodano wersję `2.0.0`: model zamknięcia 4h, skalowany most Browna, mieszankę
normalną o wariancji jednostkowej i stacjonarną log-zmienność AR(1).
Domyślnie nadal działa v1; jego algorytm, seedy i historyczne metadane zachowano.

```powershell
.\.venv\Scripts\market-levels-generate-synthetic.exe --generator-version v2 --v2-variant full --diagnostic --count 2 --symbols BTCUSDT ETHUSDT --seed 20261107 --output data/synthetic/v2-manual-smoke --dry-run
```

Warianty v2: `base`, `bridge`, `tails`, `volatility`, `full`.
`market-levels-calibrate --generator-version v2` tworzy osobny profil schematu 2
na treningu, przez ograniczoną łączną kalibrację na kilku seedach. Profile
pozostają `unapproved`. Sekcje `synthetic_v2` i `synthetic_v2_calibration`
przechowują robocze ustawienia i siatki; nie zmieniają domyślnej matematyki v1.

Istniejący CLI porównania obsługuje oba schematy i tryb `--reports` do tabeli
Realne/V1/V2-* oraz oceny zmiany błędów na identycznych oknach rzeczywistych.
Autor wykonał wcześniej kalibrację i porównanie 60+60 dla v1; lokalne raporty
potwierdzają problemy, które uzasadniają v2. Nie przeprowadzono jeszcze empirycznej
oceny poprawy v2 w ramach pierwotnego wdrożenia. Mała próba v2 korzystała
wyłącznie ze sztucznej referencji. Później autor ukończył porównanie na pięciu
seedach i wskazał V2-full-refined do dalszej pracy. Historyczne profile
pozostają `unapproved`; zatwierdzone kopie opisano w raporcie części 2.

[Matematyka i kalibracja v2](docs/SYNTHETIC_GENERATOR_V2.md),
[pełna instrukcja PowerShell](docs/SYNTHETIC_V2_POWERSHELL.md),
[raport wdrożenia i testów](docs/SYNTHETIC_V2_IMPLEMENTATION_REPORT.md).

## Audyt różnorodności i pilotaż wykresów

Etap diagnostyczny analizuje istniejące V2-full-refined z pięciu seedów oraz
renderuje 24–32 PNG 1024 × 768. Rzeczywiste okna i progi zmienności pochodzą
wyłącznie z train 2020–2023. Nie generuje nowych OHLC ani nie zatwierdza profili.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[charts]"
.\scripts\run_chart_audit.ps1
```

Nowy katalog `results/diagnostics/dc-<id>` zawiera audyt Markdown/JSON i `pilot/`
z PNG, bocznymi JSON oraz dokładnymi 120 świecami CSV dla każdego obrazu.
Te same zasady rysowania obowiązują obie grupy; PNG nie zawierają źródła ani S/R.
[Raport renderera](docs/charts/RAPORT_RENDERERA.md),
[polecenia i odtwarzalność](docs/charts/INSTRUKCJA_POWERSHELL.md),
[testy](docs/charts/RAPORT_TESTOW.md).

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
## Etap 3.4 — etykietowanie poziomów

Działa deterministyczny algorytm S/R i osobne CLI `market-levels-label-pilot`.
Przygotowano 32 etykiety i oddzielne obrazy diagnostyczne z pilotażu 3.3.
[Raport](docs/labeling/RAPORT_3_4.md) i [instrukcja PowerShell](docs/labeling/INSTRUKCJA_POWERSHELL.md).
Obrazy z liniami służą wyłącznie diagnostyce. Ręczna ocena autora pozostaje otwarta.

## Etap 3.5, część 1 — historyczny plan i mała próba danych

`python -m market_levels.cli.build_dataset` udostępnia `preflight`, `smoke`,
`verify`. Plan: 698 train, 36 validation, 66 test; syntetyki wyłącznie w train.
Lokalne dane pozwalają wybrać po 129/18/33 rzeczywiste okna BTC i ETH.
Próba obejmuje 8 diagnostycznych przykładów JSONL z `split: null`.
W części 1 profile pozostały `unapproved`; nie budowano wówczas finalnych 800 obrazów.
[Raport](docs/datasets/RAPORT_3_5_CZ1.md),
[PowerShell](docs/datasets/INSTRUKCJA_POWERSHELL.md),
[format](docs/datasets/FORMAT.md).

## Etap 3.5, część 2 — zatwierdzenie i produkcja

Nowe polecenia CLI: `approve`, `build`; `verify` rozpoznaje zbiór produkcyjny
i odtwarza wszystkie obrazy, etykiety oraz syntetyczne OHLC.
Liczebności określa wyłącznie `dataset_build.targets`: train 698 (258 realnych
i 440 syntetycznych), validation 36 realnych, test 66 realnych. Udział syntetyków
w train to 63,04%, w całym zbiorze 55%. `splits/train.jsonl`, `validation.jsonl`
i `test.jsonl` są oddzielne. Metadane pozostają poza wejściem modelu.
Nowe profile są w `data/synthetic/approved-ds35-20261107`;
oryginalne pliki i audyty zachowano. Przeglądowe PNG z poziomami są wyłącznie
w oddzielnej diagnostyce. [Raport](docs/datasets/RAPORT_3_5_CZ2.md).

# Końcowa kontrola refaktoryzacji i integralności danych

Data wykonania: 2026-11-09T20:16:54+01:00. Audyt lokalny na Windows, na zlecenie autora.
Identyfikator izolowanego przebiegu: `mlv-q9b_9lbi`.

## Werdykt

**Nie wykryto regresji w sprawdzonym zakresie.** Aktualny kod zachowuje wyniki
generatorów, etykietowania, ewaluacji i renderowania w poniższych kontrolach.
Wszystkie 800 istniejących przykładów przeszło ponowną ścisłą weryfikację.
Nie poprawiano implementacji, testów, fixture, konfiguracji, profili ani danych.
Zmiany kompatybilności wewnętrznych importów opisano osobno; nie oznacza to
zachowania wszystkich dawnych ścieżek API.

**Pod względem sprawdzonej stabilności kodu i danych projekt jest gotowy do
rozpoczęcia etapu wyboru VLM.** Nie dokonano wyboru modelu, nie uruchomiono
inferencji ani treningu. Audyt nie ocenia skuteczności przyszłego VLM.

## Referencja, bieżący kod i zabezpieczenie pracy

- Referencja: Git `092059aa5dd49e260b762cc6ccc0c660acebc166`.
- ZIP `handoff/refactor-review-20261109-a.zip`: zweryfikowano **612/612** plików
  względem manifestu oraz SHA całego archiwum:
  `f6cb0af9432a132a681b8d8619960045396d8d7e56f8c3a684c3f6b0570e11ff`.
- Wszystkie **224** pliki before porównano z tą rewizją Git; dopuszczono wyłącznie
  różnicę CRLF/LF pochodzącą z zachowanej referencji. Nie przywracano ich do repozytorium.
- **359 plików** aktualnej kopii kodu/testów/configów/dokumentacji/skryptów,
  włącznie z nieśledzonymi, jest bajtowo zgodnych z current w handoffie.
  Nie stwierdzono dodatkowych zmian tych plików od utworzenia paczki.
- Przed testami zapisano status Git z pełnymi ścieżkami nieśledzonymi, binary diff
  względem HEAD, staged diff, stan indeksu i hashe **444** ścieżek śledzonych oraz
  nieśledzonych, w tym informację o wcześniej usuniętych plikach.
  Stan początkowy: **307 wpisów zmian**. Nie wykonano commit/stash/checkout/reset/
  clean/rebase ani publikacji.
- Osobne before/.venv i current/.venv z instalacjami editable utworzono wyłącznie
  w nowym katalogu `C:\Users\wojte\AppData\Local\Temp\mlv-q9b_9lbi`. Aktualny kod skopiowano z żywego drzewa roboczego.
  Produkcyjnych danych nie kopiowano. Historyczne dane czytano w oryginalnym miejscu;
  odtworzenia, cache renderera, wyniki A/B i nowe fixture mieściły się pod tym
  katalogiem tymczasowym. Nie instalowano referencji w głównym środowisku projektu.

## Środowisko

Windows 10.0.19045, AMD64, CPython **3.13.15**, Matplotlib **3.11.2**.
Biblioteki: matplotlib 3.11.2, numpy 2.5.4, pillow 13.0.0, contourpy 1.4.0, cycler 0.12.1, fonttools 4.68.0, kiwisolver 1.5.1, packaging 26.3, pyparsing 3.3.3, python-dateutil 4.0.0, tzdata 2026.6.
Biblioteki renderera w obu nowych środowiskach przypięto do tych samych wersji.
Nie używano GPU/CUDA; nie są wymagane do wykonanych kontroli CPU.
Przygotowanie bibliotek wymagało instalacji pip; testy i weryfikatory nie
pobierały historii rynku. Głównego venv nie zmieniono.

## Testy faktycznie uruchomione w tej kontroli

| Zestaw | Wykonane | Zaliczone | Pominięte | Błędy/niezaliczone | Czas unittest |
| --- | ---: | ---: | ---: | ---: | ---: |
| Before | 277 | 277 | 0 | 0 | 148.000 s |
| Current | 286 | 286 | 0 | 0 | 159.615 s |

Polecenie w każdej osobnej kopii: `.venv/Scripts/python.exe -B -m unittest discover -s tests -v`.
Testy wykonywano z CWD danej kopii i własnym TEMP/TMP. Kontrole Windows nie były pomijane.

Zachowano **277/277** historycznych metod testowych. Porównano **945 wywołań
asercji self.assert***: po jawnym rozwiązaniu przeniesionych importów i aliasów
nie ma różnic asercji. Oryginalne fixture poza README są bajtowo identyczne.
Przejrzano pozostałe różnice ciał 13 metod: dotyczą celów patchowania przeniesionych
modułów i odnajdywania tych samych plików fixture/config. Nie zmieniają oczekiwań.
Dziesięć wydzielonych funkcji pomocniczych ma identyczny surowy AST;
przeniesiony konstruktor fixture runnera zachowuje instrukcje po zmianie aliasów stałych.
Dodano wcześniej 9 testów, obecnie również zaliczonych; podczas audytu nie dopisywano
testów do repozytorium i nie zmieniano wzorców.

SHA logu before: `38481151985135e7027150fe9e42c4d66500f22c8744355e15f25c29a17d022c`.
SHA logu current: `8719f793e54eca32c4b481dedf007ab8773982e4ff63f38230df2da86cc1a022`.
Logi robocze usunięto razem z izolowanym środowiskiem zgodnie ze zleceniem.

## Porównania zachowania przed/po

1. Narzędzie handoffu wykonano ponownie z **nowymi seedami 982451653, 32452843,
   49979687**. **44 przypadki**: BTC/ETH × V1 i sześć wariantów V2 × trzy seedy,
   dodatkowo płaskie i ręczne okno. Zgodne pełne metadane, daty i kanoniczne OHLC,
   etykiety, diagnostyka, metryki, hashe CSV, PNG 1024×768 i nakładek oraz dokładne
   linie JSONL diagnostyki/produkcji. Porównano też pełne wyniki małej kalibracji,
   refinementu i selekcji na sztucznej referencji z luką. Nie kalibrowano danych rynku.
   SHA obu raportów: `47dffcce46695926a9c605d794aa5e07d100956b5eae240b0dcbf4af43f2fdc3`. Brak normalizacji i tolerancji.
2. Osobny harness, niezależny od macierzy handoffu: **20 wygenerowanych przypadków**,
   w tym 14 śladów V1/sześciu V2 dla BTC/ETH i 6 przypadków V2-full-refined
   na istniejących zatwierdzonych profilach z nowymi seedami. Delegujący wrapper
   Random zapisał kolejność tworzenia strumieni oraz wywołań i wyników losowań:
   **66344 zdarzenia identyczne**. Wrapper nie zmienia metod Random.
3. Bezpośrednio porównano **14 przypadków** mostu Browna, normal_mixture,
   AR(1) i granicy wyboru składnika mieszanki. Dodatkowe **12 przypadków** etykietowania
   obejmuje odstępy reakcji 4/5/6, delta ±1e-25, remisy cen, równe ekstrema,
   graniczne indeksy okna, płaskie ceny i okolice zaokrągleń Decimal.
   Istniejące testy dodatkowo obejmują ATR Wildera, mediany, ranking, kolizje i JSON.
4. Uruchomiono pełną ścieżkę ewaluatora sr-eval-v1 na tych samych ręcznych fixture
   A/B dla obu wersji: evaluate A, evaluate B i sparowane compare. **49/49 plików**
   wynikowych jest bajtowo identycznych, w tym per_example, summary, trzy tolerancje,
   TP/FP/FN, precision/recall/F1, MAE/MAE-ATR, raporty Markdown, bindingi i manifesty.
   Nie były to predykcje rzeczywistego modelu ani produkcyjnego testu.
5. Cały dodatkowy raport (OHLC/metadane/ślady RNG/przypadki graniczne/hashe ewaluacji)
   ma w obu wersjach identyczne **5 682 071 bajtów**, SHA:
   `74836f2ae10ae232e06b227fa057a3a2dd5b83ff4683bfc71a3b6b042834e118`.
   Nie zwiększano tolerancji float ani nie normalizowano tych wyników.

Równość obserwowanych wyników wspiera przegląd kodu: ciała algorytmów, operacje
float/Decimal, kolejność RNG, wyprowadzanie seedów, sekwencje reżimów, dopasowanie
max TP/min błąd/remisy i kolejność rysowania pozostały zgodne strukturalnie.
Nie jest to dowód dla wszystkich możliwych wejść lub środowisk.

## Przegląd struktury, importów i API

Skaner bez whitelisty wskazał **297 definicji: 275 identycznych, 9 różniących się
wyłącznie importami i 13 REVIEW_REQUIRED**. Każdą z poniższych różnic przejrzano:

| Nr | Dawna definicja | Obecna lokalizacja | Ocena |
| --- | --- | --- | --- |
| 1 | `market_levels.charts.diversity.sha256_file` | `src/market_levels/shared/integrity.py:8` | SHA-256 liczony porcjami tych samych bajtów; bez zmiany kanonizacji cen/profili. |
| 2 | `market_levels.charts.diversity._child` | `src/market_levels/shared/paths.py:29` | Delegacja do child; identyczny resolve, warunek potomka i komunikat manifestu. |
| 3 | `market_levels.cli.refinement_comparison.sha` | `src/market_levels/shared/integrity.py:8` | Wspólny SHA-256 zamiast read_bytes; ten sam wynik dla plików wejściowych. |
| 4 | `market_levels.cli.refinement_comparison.check_environment` | `src/market_levels/experiments/refinement/workflows/preflight.py:18` | Sprawdzana aktualna ścieżka workflows.refinement; pozostałe kontrole instalacji zachowane. |
| 5 | `market_levels.cli.refinement_comparison.main` | `src/market_levels/cli/refinement_comparison.py:10` | Parser i delegacja; osobno potwierdzono identyczny AST parsera i całego przeniesionego cyklu przebiegu. |
| 6 | `market_levels.data_processing.pipelines.compare_synthetic.save_comparison` | `src/market_levels/data_processing/synthetic/workflows/comparison.py:49` | parents[4] → parents[5] wskazuje ten sam katalog projektu po przeniesieniu o poziom głębiej. |
| 7 | `market_levels.data_processing.pipelines.synthetic.prepare_profiles` | `src/market_levels/data_processing/synthetic/io/profiles.py:17` | Druga korekta parents[4] → parents[5]; zachowana ochrona data/processed także z innego CWD. |
| 8 | `market_levels.data_processing.real.binance_vision.archives._sha256_file` | `src/market_levels/shared/integrity.py:8` | Ta sama implementacja porcjowanego SHA; nowy właściciel i docstring. |
| 9 | `market_levels.data_processing.staging.LOGGER` | `src/market_levels/shared/publication.py:14` | Jawny historyczny identyfikator loggera market_levels.data_processing.staging. |
| 10 | `market_levels.datasets.packaging._example_line` | `src/market_levels/datasets/domain/examples.py:60` | Wrapper podaje split=None; zachowano pola, liczbowy JSON odpowiedzi i końcowy newline. |
| 11 | `market_levels.datasets.production.json_line` | `src/market_levels/datasets/domain/examples.py:36` | Adnotacja split rozszerzona o None; ciało serializera identyczne. |
| 12 | `market_levels.labeling.pilot.sha256` | `src/market_levels/shared/integrity.py:8` | Wspólny porcjowany SHA-256; bajty wejściowe i wynik zgodne. |
| 13 | `market_levels.labeling.pilot.child` | `src/market_levels/shared/paths.py:13` | Dodano opcjonalny komunikat; domyślny tekst i warunek potomka pozostają identyczne. |

Osobne rozwiązanie statycznych powiązań globalnych dla odpowiadających sobie
definicji objęło **1249 odniesień**, bez różnic po uwzględnieniu mapy przenosin.
Nie utożsamiano zgodności samej składni importów z poprawnością powiązań.
Przejrzano inicjalizatory: poza docstringami aktywne eksporty mają labeling
(LabelResult, label_window) i windows (Window, candidates, coverage,
validate_selection, select_training). Nie dodają nowych skutków wykonawczych.
Test grafu importów, także lokalnych, potwierdza brak cykli; testy granic
core/shared/domain/CLI i importu obliczeń bez Matplotlib przeszły.

**10/10 kontraktów CLI --help** ma identyczne kody zakończenia, stdout i stderr.
Parser runnera i instrukcje przeniesionego cyklu main są identyczne według AST.
pyproject.toml i entry pointy pozostają bajtowo niezmienione.

**Zmiana kompatybilności API:** zniknęło 40 dawnych plików modułów (lista na końcu).
Importy klientów używających np. synthetic.generator, labeling.algorithm,
datasets.production albo cli.refinement_comparison.preflight wymagają aktualizacji.
Zmieniają się także __module__, ścieżki tracebacków i adnotacja split serializera.
Nie przywracano modułów zgodności. Historyczne checkpointy przypinające SHA kodu
mają nadal odrzucać wznowienie po zmianie źródeł; nie migrowano ani nie uruchamiano
historycznych pełnych przebiegów. To ograniczenie kompatybilności, nie zmiana
wyników matematycznych; nowe wznowienia sprawdzono testami.

## Istniejące dane produkcyjne i historia

Wykonano z nowej instalacji aktualnego kodu, przy oryginalnym CWD projektu:

```powershell
python -B -m market_levels.cli.build_dataset verify --output data/datasets/ds35-800-20261107-a --check-sources
python -B scripts/verify_chart_pilot.py results/diagnostics/dc-20261106-c/pilot --re-render
python -B -m market_levels.cli.label_pilot --pilot results/diagnostics/dc-20261106-c/pilot --output results/diagnostics/sr-20261106-a --verify --re-render
```

- **800/800** przykładów; podział **698/36/66**, 120 świec na przykład,
  dokładne liczebności real/synthetic i instrumentów. **440/440** syntetyków
  odtworzonych w pamięci z przypiętych profili i seedów. **800/800** PNG odtworzonych
  z identycznym SHA, 0 różnic renderera. Etykiety, JSONL, metadane, manifesty,
  źródłowe CSV, przypięte źródła, profile, duplikaty i brak niedozwolonych okien
  między splitami sprawdzone przez ścisły weryfikator.
- Manifest zbioru SHA: `0f9093fbdcbd39243fcf802bfdd723cb913b15838aa4a3cc469787d5e7e462d0`.
- Pilotaż c: **32 oryginalne PNG** odtworzone bajtowo; **32 etykiety, pełna diagnostyka
  i 32 osobne nakładki PNG** zgodne. Pilotaże a i b dodatkowo sprawdzono odczytowo:
  po 32 obrazy, wymiary, SHA, CSV i sidecary, bez ich ponownego renderowania.
- Historia: **54 manifesty partii / 4050 zapisanych serii**. Reader porównań
  zweryfikował empiryczne partie: profile, hashe OHLC, pliki metadanych,
  statystyki i przebiegi zmienności. Dla 10 ręcznych przykładów diagnostycznych,
  których ten reader celowo nie przyjmuje jako empirycznej referencji, wykonano
  osobny odczyt CSV/profili/hashy/statystyk/walidacji. Nie generowano nowej partii.
- **16 plików profili**, 16 unikalnych osadzonych lub zewnętrznych profili
  sprawdzonych walidatorami i powiązaniami ze źródłami. **98 raportów porównania**:
  zgodne identyfikatory treści, profile, SHA wskazanych manifestów i źródłowych CSV
  oraz **4024 odwołania** do CSV/metadanych przykładów. To liczba odwołań,
  nie twierdzenie o tylu dodatkowych niezależnych seriach.
- **15 zapieczętowanych manifestów katalogowych** przeszło kontrolę inwentarza
  i hashy. Pozostałe cztery manifesty pilotaży sprawdzono kontrolami powyżej.
  Łącznie objęto wszystkie **73 istniejące manifest.json** w data/results.

Nie użyto build, approve ani allow-renderer-difference. Nie ponawiano kalibracji
rynku, audytu 600 serii, eksperymentu 960 serii ani produkcji zbioru.
Odtworzenie istniejących przykładów wykonywał weryfikator do TEMP, bez publikacji.

## Bezpieczeństwo Windows

Pełne testy faktycznie uruchomiły kontrolowane WinError 5/32/33, ograniczone retry,
atomowe publikowanie, odmowę nadpisania, awarie przed/po publikacji, zachowanie
pierwotnego wyjątku, realną blokadę katalogu Windows, blokady runnera,
wznowienie/reużycie etapów i odrzucenie zmienionych wejść. Przeszły testy MAX_PATH,
uruchamiania CLI z innego CWD, ochrony source data/processed, importów -I
i natywnych skryptów PowerShell. Wszystkie wymuszone awarie dotyczyły sztucznych
fixture w izolacji. Oryginalne dane nie były poligonem dla testów błędów.

## Integralność i sprzątanie

Przed testami zapisano pełne względne ścieżki, rozmiary i SHA-256 wszystkich
plików data/results/handoff, również zatwierdzonych profili i historii audytów.
Ścieżki historyczne >260 znaków odczytywano przez rozszerzony zapis Windows,
bez przenoszenia lub skracania nazw.

| Chroniony katalog | Pliki przed kontrolą | Dodane / usunięte / zmienione przed sprzątaniem |
| --- | ---: | --- |
| data | 12140 | 0 / 0 / 0 |
| results | 639 | 0 / 0 / 0 |
| handoff | 24 | 0 / 0 / 0 |

Bieżąca referencja data/results obejmuje **12 779** plików. Liczba 12 771 z
raportu wcześniejszej sesji jest historyczna; nie użyto jej do kasowania plików
ani do zastąpienia aktualnego pomiaru. W tym audycie: 0 nowych produkcyjnych
przykładów, 0 nowych partii i 0 nowych manifestów symulacji w repozytorium.

Nowe pliki robocze: kopie before/current, dwa venv, zależności/cache pip i renderera,
fixture, porównawcze CSV/PNG/nakładki/JSON/JSONL, raporty ewaluacji A/B,
ślady RNG, narzędzia audytu, logi i inwentarze. Wszystkie utworzono pod nowym,
oznaczonym OWNER.json katalogiem `C:\Users\wojte\AppData\Local\Temp\mlv-q9b_9lbi`. Przed sprzątaniem zapisano
szczegółowy inwentarz **11344 pozostałych plików** (włącznie z plikiem
inwentarza), około **385578623 bajtów**, oraz 1551 podkatalogów.
Wcześniej automatycznie usunięte pliki TemporaryDirectory nie są doliczane
do tej liczby. Fingerprint inwentarza pozostałych plików, z wyłączeniem jego
własnego pliku: `c0da83e7e825c182edc4257843ba0cb5e5046bc145d31521f2c4d2ae56a9bb37`.

Przed usuwaniem sprawdzono pełną ścieżkę, marker właściciela, położenie poza
projektem i brak symlinków/junctionów. Sprzątanie dotyczy wyłącznie całego
tego katalogu. Nie usuwano wcześniejszych katalogów, globalnego cache, danych,
wyników, środowiska projektu ani wcześniejszych paczek.

**Sprzątanie zakończone:** usunięto wyłącznie cały wskazany katalog audytu wraz z kopiami, dwoma venv, cache, fixture, wynikami i logami. Katalog już nie istnieje.

Po sprzątaniu ponownie obliczono pełne inwentarze. Wynik:

```json
{
  "data": {
    "files": 12140,
    "added": [],
    "removed": [],
    "changed": []
  },
  "results": {
    "files": 639,
    "added": [],
    "removed": [],
    "changed": []
  },
  "handoff": {
    "files": 24,
    "added": [],
    "removed": [],
    "changed": []
  },
  "working_tree": {
    "added": [],
    "removed": [],
    "changed": []
  },
  "index_unchanged": true,
  "head_unchanged": true,
  "prior_status_unchanged": true,
  "git_status_entries": 308,
  "only_new_report": true
}
```

Stan Git: **307 dotychczasowych zmian zachowanych + 1 nowy raport = 308 wpisów**. Jedyny nowy plik repozytorium to ten raport. Indeks i HEAD nie zmieniły się. Brak nowych artefaktów testowych w data/results/handoff.

## Ograniczenia i rozróżnienie wyników

Wszystkie liczby w tym raporcie poza jawnie nazwanym kontekstem historycznym
pochodzą z tej kontroli, a nie z VALIDATION.json poprzedniej sesji. Nie stwierdzono
niezaliczonych testów ani nowej regresji wymagającej poprawy implementacji.
Pomocnicze skrypty audytu wymagały korekty odczytu długich ścieżek, jawnego UTF-8
i właściwego znacznika source przy walidacji ręcznych syntetyków. Były to błędy
harnessu, a nie aplikacji; końcowe porównania powtórzono po korekcie, bez zmiany
źródeł projektu i bez osłabiania walidatorów.

Nie weryfikowano rzeczywistego HTTP/fallbacku na serwerze (testy offline i mocki),
innych systemów lub wersji Pythona, GPU/CUDA, zachowania po realnej utracie
zasilania ani jakości przyszłego modelu. Istniejące ograniczenia opisane w .ai
nie zostały przy okazji zmienione. Niezależna kontrola na CPython 3.13.5 z zadania
autora jest wynikiem historycznym, nie wykonaniem tej sesji. Jej odchylenia
liczbowe nie wymagały tutaj zmiany tolerancji: oryginalne Windows/3.13.15
przeszło kontrolę danych i dokładne porównania.

## Usunięte ścieżki modułów — informacja dla użytkowników API

Są to przeniesione wewnętrzne moduły, nie usunięte algorytmy. Odpowiedniki
definicji wskazuje [SYMBOL_MAP.json](SYMBOL_MAP.json).

- `market_levels/charts/diversity.py`
- `market_levels/charts/pilot.py`
- `market_levels/charts/renderer.py`
- `market_levels/core/candles.py`
- `market_levels/core/periods.py`
- `market_levels/data_processing/pipelines/__init__.py`
- `market_levels/data_processing/pipelines/compare_synthetic.py`
- `market_levels/data_processing/pipelines/download.py`
- `market_levels/data_processing/pipelines/synthetic.py`
- `market_levels/data_processing/staging.py`
- `market_levels/data_processing/storage.py`
- `market_levels/data_processing/synthetic/calibration.py`
- `market_levels/data_processing/synthetic/calibration_v2.py`
- `market_levels/data_processing/synthetic/comparison.py`
- `market_levels/data_processing/synthetic/dispatch.py`
- `market_levels/data_processing/synthetic/experiments.py`
- `market_levels/data_processing/synthetic/generator.py`
- `market_levels/data_processing/synthetic/generator_v2.py`
- `market_levels/data_processing/synthetic/profile_v2.py`
- `market_levels/data_processing/synthetic/quality.py`
- `market_levels/data_processing/synthetic/refinement.py`
- `market_levels/data_processing/synthetic/regimes.py`
- `market_levels/data_processing/synthetic/selection.py`
- `market_levels/data_processing/synthetic/settings.py`
- `market_levels/data_processing/synthetic/stochastic_processes.py`
- `market_levels/data_processing/synthetic/training_period.py`
- `market_levels/data_processing/synthetic/v2_parameters.py`
- `market_levels/data_processing/validation.py`
- `market_levels/datasets/approval.py`
- `market_levels/datasets/audit.py`
- `market_levels/datasets/packaging.py`
- `market_levels/datasets/planning.py`
- `market_levels/datasets/production.py`
- `market_levels/datasets/review.py`
- `market_levels/evaluation/inputs.py`
- `market_levels/evaluation/metrics.py`
- `market_levels/evaluation/pipeline.py`
- `market_levels/evaluation/scoring.py`
- `market_levels/labeling/algorithm.py`
- `market_levels/labeling/pilot.py`

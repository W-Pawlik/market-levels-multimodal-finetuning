# Architektura Market Levels

Docelowo system obsłuży odtwarzalny eksperyment dostrajania modelu multimodalnego
do poziomów wsparcia i oporu. Działają pozyskiwanie i walidacja
rzeczywistych OHLC oraz generowanie syntetycznych serii z kalibracją.
Jest to jeden pakiet, bez mikroserwisów, bazy danych i MLOps.

## Podział istniejącej implementacji

| Moduł w `src/market_levels/` | Odpowiedzialność i przeniesione elementy |
| --- | --- |
| `configuration.py` | wczytanie JSON, sprawdzenie obsługiwanego źródła i ustawień pobierania |
| `core/candles.py` | `Candle`, `DataValidationError`, UTC i odstęp 4h; niezależność od Binance |
| `core/periods.py` | `iter_months`, `_last_closed_month`, `_days_in_month` |
| `data_processing/real/binance_vision/client.py` | `_remote_url`, `_get`, retry, `.part`, `DownloadError`, parametry źródła |
| `data_processing/real/binance_vision/archives.py` | `_expected_sha256`, `_sha256_file`, `acquire_archive`, `acquire_month`, fallback |
| `data_processing/real/binance_vision/parsing.py` | `decode_binance_timestamp`, `parse_candle`, `read_spot_klines_zip`, `verify_archive_period` |
| `data_processing/validation.py` | `_positive_decimal`, granica 4h, relacje OHLC i `check_series` |
| `data_processing/storage.py` | zapis CSV i JSON wyodrębniony z `run` |
| `data_processing/pipelines/download.py` | `run`: koordynacja, brzegi zakresu, składanie raportów i manifestu |
| `cli/download.py` | `main`: argumenty, dry-run, prezentacja błędów |
| `data_processing/synthetic/settings.py` | oddzielny loader sekcji synthetic, walidacja i robocze parametry |
| `data_processing/synthetic/regimes.py` | wykonalne sekwencje 1–3 faz, ważenie przejść, długości i parametry |
| `data_processing/synthetic/generator.py` | lokalny RNG, seedy przykładów, logarytmiczna ścieżka i świece |
| `data_processing/synthetic/calibration.py` | jawny okres, statystyki, profile, jawne zatwierdzenie podziału |
| `data_processing/synthetic/quality.py` | wspólna walidacja + kontrola syntetyczna, hash, statystyki i porównania |
| `data_processing/pipelines/synthetic.py` | niezależne przykłady, kontrola duplikatów, round-trip, atomowa partia |
| `cli/generate_synthetic.py` | nowe CLI i nadpisania sekcji synthetic |
| `data_processing/synthetic/training_period.py` | zatwierdzony podział z JSON i kontrola przynależności okresu do treningu |
| `data_processing/synthetic/selection.py` | nienakładające się rzeczywiste okna wyłącznie do diagnostyki |
| `data_processing/synthetic/comparison.py` | odczyt i weryfikacja partii, agregacja obserwacji/okien, korelacja lag 1 |
| `data_processing/pipelines/compare_synthetic.py` | koordynacja porównania i atomowy zapis JSON/Markdown |
| `cli/calibrate_synthetic.py`, `cli/compare_synthetic.py` | dwa nowe entry pointy, bez zmiany interfejsów pobierania/generowania |
| `charts/diversity.py` | odczyt istniejących refined, reżimy, metryki i progi wyłącznie z treningu |
| `charts/renderer.py` | 120 poprawnych świec → PNG Agg 1024 × 768, bez metadanych wejściowych i S/R na obrazie |
| `charts/pilot.py`, `cli/audit_charts.py` | deterministyczny dobór, raporty, kopie okien i atomowa publikacja diagnostyki |

Przepływ: CLI → konfiguracja JSON + nadpisania CLI → pipeline → archiwa i SHA-256 → parser ZIP → walidacja okresu
i szeregu → kontrola brzegów → CSV → raport → manifest. Przy `strict_gaps`
przerwanie następuje po CSV i raporcie, przed manifestem, jak w oryginale.

Model i okresy nie zależą od wejścia/wyjścia. Walidacja zależy od modelu,
parser Binance od walidacji. HTTP nie zna świec ani raportów, zapis nie pobiera
i nie waliduje danych. Pipeline składa funkcje niższych warstw. Nie dodano
hierarchii klas, interfejsów ani ogólnego mechanizmu wstrzykiwania zależności.

`Candle.source_archive` pozostaje wymagane. Model nie importuje Binance.
Dla syntetycznych danych pole ma wartość `synthetic:<wersja>:<symbol>:<seed>`.
Nie zmieniono kontraktu modelu. Wspólny storage rozszerzono o odczyt CSV;
dotychczasowych funkcji zapisu i walidacji nie zmieniono.

Przepływ syntetyczny: CLI → osobne ustawienia + jawne profile → wykonalne reżimy
→ 12 kroków na świecę → wspólna walidacja + kontrola 120 świec i ciągłości ceny
→ hash duplikatów → CSV w katalogu tymczasowym → odczyt kontrolny → metadane
i manifest → rename całego katalogu partii. Błąd zatrzymuje całą partię,
bez cichych ponowień losowania i bez częściowo opublikowanych przykładów.
Kalibracja jest osobną operacją API i nigdy nie uruchamia się automatycznie.
Szczegóły: [generator](SYNTHETIC_GENERATOR.md).

Kalibracja CLI korzysta z istniejących `calibrate_csv` i `save_profile`, po
kontroli jawnego okresu przez `ChronologicalSplit.require_training`. Odczytuje
pełny CSV, a estymacja wybiera tylko wskazaną część treningu. Profil v1 ma
dodatkowe metadane podziału w `source.chronological_split`; status `unapproved`.
Funkcje podstawowego API kalibracji i ich format nie uległy zmianie.

Porównanie: CSV → ograniczenie do treningu → ciągłe odcinki → pojemność okien
→ deterministyczny wybór rozłącznych pozycji; osobno manifest → metadane/profil
→ CSV → weryfikacja hasha, walidacji i zapisanych statystyk. Dopiero potem
agregujemy surowe obserwacje wewnątrz okien. `series_observations` udostępnia
te same wzory, których używa `series_statistics`, bez zmiany dotychczasowych
wyników. Nie wprowadzono osobnych definicji zwrotów/knotów. Porównanie nie tworzy
zwrotów ani par korelacyjnych między oknami. JSON i Markdown publikowane są
razem przez rename katalogu. Nie jest to moduł końcowego podziału zbioru.
Instrukcja: [kalibracja i porównanie](SYNTHETIC_CALIBRATION_COMPARISON.md).

## Wersja v2

`generator.py` jest zachowaną implementacją v1. `dispatch.py` wybiera ją lub
`generator_v2.py`; domyślnie v1. `SyntheticSettings.document()` zachowuje
historyczną reprezentację konfiguracji v1, bez dodatkowych kluczy.
`stochastic_processes.py` zawiera most, mieszankę i AR(1), a `v2_parameters.py`
ich parametry, ograniczenia i przełączniki wariantów. Planowanie faz jest wspólne.

`profile_v2.py` definiuje schemat 2 i pochodzenie parametrów; część empiryczną
sprawdza wspólnym walidatorem pól v1. `calibration_v2.py` korzysta z istniejącej
kalibracji bazowej, wyboru okien i agregacji oraz ograniczonej siatki na kilku
seedach. Wspólne load/save_profile rozróżnia schematy; stary validate_profile
nie zmienił kontraktu. Nie zapisujemy profili v2 do plików v1.

`comparison.py` sprawdza manifesty obu wersji i przebieg zmienności v2.
`experiments.py` zestawia zapisane porównania z identyczną referencją,
pokazuje rozrzut po seedach i zmianę błędów względem V1. `--reports` jest osobnym
trybem istniejącego CLI porównania; oba rodzaje raportów wykorzystują ten sam
atomowy zapis JSON/Markdown. Nie dodano frameworka eksperymentów ani zależności.

Szczegóły: [generator v2](SYNTHETIC_GENERATOR_V2.md).

Publikacje partii, profili i porównań używają `data_processing/staging.py`.
Kontekst `publication_workspace` ponawia blokady dostępu przy sprzątaniu,
zachowuje pierwotny błąd operacji, a po udanej publikacji zgłasza wyczerpaną
blokadę jako ostrzeżenie. Atomowe rename/hard link i formaty są niezmienione.
Szczegóły: [poprawka Windows](WINDOWS_STAGING_CLEANUP_FIX.md).

## Pakiet i uruchamianie

Setuptools odkrywa `market_levels*` w `src/`. Instalacja udostępnia
`market_levels.cli.download`, `market-levels-download` oraz
`market-levels-generate-synthetic` (moduł `market_levels.cli.generate_synthetic`). Python 3.10+,
bez zewnętrznych zależności uruchomieniowych.

Pozostałe entry pointy: `market-levels-calibrate` (`cli.calibrate_synthetic`)
i `market-levels-compare-synthetic` (`cli.compare_synthetic`). Wszystkie operacje
danych mogą działać offline. Instalacja pakietu wymaga dostępnego setuptools.

Na prośbę autora usunięto warstwę zgodności: `src/download_data.py`,
`src/validate_data.py` oraz `src/__init__.py`. `src` jest teraz wyłącznie
katalogiem źródeł. Po instalacji pakietu należy używać importów `market_levels`
i polecenia `market-levels-download` lub modułu `market_levels.cli.download`.
Wewnętrzne importy są względne, bez modyfikowania `sys.path`.
Instrukcja przygotowania środowiska znajduje się w głównym README.

Kod pozyskiwania i przetwarzania danych jest w `data_processing/`.
Główny katalog projektu `data/` zawiera wyłącznie artefakty danych.
`src/market_levels.egg-info/` to generowane metadane instalacji edytowalnej,
ignorowane przez Git. Nie należy edytować ich ręcznie.

## Stan modułów kolejnych etapów

| Katalog pakietu | Planowana odpowiedzialność |
| --- | --- |
| `data_processing/windows/` (działa, 3.5) | okna 120 świec, fragmenty ciągłe, selekcja chronologiczna i walidacja |
| `charts/` (MVP działa) | Matplotlib Agg, styl, rozdzielczość, PNG i diagnostyka; bez etykietowania |
| `labeling/` (działa, etap 3.4) | model poziomów, deterministyczny algorytm, etykiety i diagnostyka pilotażu |
| `datasets/` (działa, 3.5 część 2) | zatwierdzanie kopii profili, preflight, produkcja, neutralny JSONL, pełne odtworzenie i audyty |
| `modeling/` | modele multimodalne bez narzuconej rodziny |
| `training/` | dostrajanie, adaptery, checkpointy, logi |
| `inference/` | obraz i instrukcja → JSON, niezależnie od treningu |
| `evaluation/` | porównanie modelu bazowego, dostrojonego i algorytmu; precision, recall, F1, błąd ceny, JSON, czas i analiza błędów |
| `experiments/` | identyfikatory, wersje danych, konfiguracje i wyniki |

Reguły etykietowania zaimplementowano w `labeling/algorithm.py`: ekstrema z trzema świecami po obu stronach,
minimum dwie niezależne reakcje oddalone o minimum pięć świec, Wilder ATR(14),
grupowanie 0,5 ATR i mediana ekstremów. Dalej: klasyfikacja względem ostatniego
zamknięcia, pomijanie poziomów zbyt bliskich, ranking według reakcji, aktualności
i odległości, maksymalnie trzy wsparcia i trzy opory. Mediana poprzedza filtrowanie
reakcji. Filtrowanie wybiera najsilniejsze ekstremum jako pierwsze, usuwa sąsiadów
bliższych niż pięć świec i powtarza; dla H siła to cena−mediana, dla L mediana−cena.
Stały kontekst Decimal ma 50 cyfr. Zaokrąglenie ROUND_HALF_UP do dwóch miejsc
dotyczy tylko odpowiedzi VLM; kolizje (również między stronami) rozstrzyga ranking.
`labeling/pilot.py` oraz `cli/label_pilot.py` czytają wyłącznie 32 istniejące okna,
sprawdzają SHA i publikują nowy katalog pod results/diagnostics przez wspólny staging.
Pełne dane diagnostyczne i PNG z poziomami są oddzielone od odpowiedzi VLM.
Nie wykonano niezależnej eksperckiej oceny. Stan etapu 3.5 opisano poniżej.

Etap 3.5, część 1: `windows.candidates` waliduje pełny CSV, dzieli według
zatwierdzonej chronologii, restartuje siatkę na każdym ciągłym fragmencie.
`select_training` dzieli chronologiczną pulę na N warstw o prawie równej
liczebności i losuje po jednym indeksie lokalnym RNG. Validation/test używają
chronologicznego prefiksu siatki, bez oceny cen i etykiet.
`datasets.planning` przypina źródła/profil/seedy i wylicza sumy wyłącznie z
`dataset_build.targets`. Historyczne pola sumy i udziałów nie sterują tym API.
`synthetic_settings` integruje obecne ustawienia v2/full z produkcyjnym
`diagnostic=False`; `require_production_ready` zachowuje dotychczasową blokadę
niezatwierdzonych profili. Planowanie nie wykonuje generacji ani kalibracji.
`datasets.packaging` składa obecny renderer i `label_window`, nie ma własnej
wersji tych algorytmów. Zapewnia oddzielne metadane, JSONL, etykiety, kopie CSV,
inwentarz, hash manifestu i odtworzenie. CLI `market-levels-build-dataset`
udostępnia preflight/smoke/verify oraz nowe approve/build z części 2. Publikacja używa wspólnego stagingu
i zabezpieczeń Windows. [Format](datasets/FORMAT.md), [raport](datasets/RAPORT_3_5_CZ1.md).

Część 2: `datasets.approval` sprawdza pierwotne profile i powiązanie z audytem,
deleguje wspólne zatwierdzenie do `approve_profile` i waliduje pełny schemat v2.
Walidator refinement dopuszcza kopię `approved` tylko z prawidłowym approval;
historyczny audyt pozostaje niezmieniony. `datasets.production` kontroluje
aktualność przypiętego planu, składa obecny generator/renderer/etykietowanie,
zapisuje osobne splity i publikuje katalog po pełnym odtworzeniu z dysku.
`verify_dataset` regeneruje wszystkie syntetyki oraz 800 obrazów/etykiet.
`audit` jest opisowy, `review` zapisuje oddzielne overlays. Nowy preflight
wyklucza master seedy także wobec opublikowanych zbiorów produkcyjnych.
[Raport części 2](datasets/RAPORT_3_5_CZ2.md).

## Dane, wyniki i konfiguracja

Zachowano `data/raw`, `processed`, `reports`. Generator używa `data/synthetic`,
a przyszłe artefakty mają katalogi `charts`, `labels`, `splits`. Wyniki mają miejsca
`results/predictions`, `metrics`, `figures`, `logs`, `checkpoints`, `adapters`.
`.gitkeep` utrzymuje strukturę; dane i wyniki są ignorowane.

`configs/experiment.json` jest domyślnie wczytywany przez CLI. Zachowano wszystkie
zatwierdzone parametry i dodano sekcję `download` dla katalogu wyników, offline,
kontroli luk i fallbacku. Zakres i symbole są pobierane z istniejących pól.
Argumenty CLI nadpisują JSON, także w obu kierunkach wartości logicznych.
`--config` wskazuje inny plik. Brak lub błąd pliku przerywa proces przed zapisem;
nie ma cichego powrotu do stałych w kodzie. Ścieżki są względne wobec katalogu
uruchomienia. Źródło, rynek, interwał i obsługiwane symbole są walidowane;
rozszerzenie obsługi poza Binance spot 4h wymaga zmian w istniejącym pipeline.
Koncepcyjnie oddzielamy pola źródła (`source`, rynek, symbole, interwał, zakres),
eksperymentu (okna, przesunięcia, liczba i udziały) oraz obrazów (wymiary).
Model i hiperparametry treningu nie są zatwierdzone. Pola przyszłych etapów
nie sterują jeszcze żadnym wykonaniem. Stałe źródła skupiono w kliencie Binance,
a wspólny odstęp 4h przy modelu świecy.

## Rozwój

`data_processing/staging.publish_directory` jest wspólną granicą atomowej
publikacji katalogów syntetyków i raportów. Ponawia tylko konflikty dostępu
rename, kontrolując kolizje celu; nie powtarza tworzenia zawartości.
Koordynator rozpoznaje tylko opublikowany układ katalogów, wykluczając staging.
[Opis poprawki](WINDOWS_PUBLICATION_RETRY_FIX.md).

`run_refinement_fresh_seeds.ps1` korzysta ze wspólnego koordynatora z flagą
`--fresh-seeds`. Jawny plan ośmiu partii używa istniejących ośmiu profili
i agreguje tylko nowo utworzone raporty 20261201/20261211. `STABILITY.md`
prezentuje sześć wskazanych metryk z wyników dotychczasowego agregatora;
nie zmienia definicji statystyk. [Opis próby](FRESH_SEEDS_EXPERIMENT.md).

Oficjalny `scripts/run_refinement_comparison.ps1` wskazuje interpreter projektu
i wywołuje `cli/refinement_comparison.py`. Koordynator sprawdza środowisko i dane,
wywołuje istniejące CLI generatora/porównania oraz walidatory wyników. Nie dodaje
matematyki OHLC. Przebieg przypina SHA wejść i źródeł; checkpointy po etapach
umożliwiają bezpieczne wznowienie. Szczegóły: [procedura](INSTRUKCJA_POWERSHELL.md).

`synthetic/refinement.py` implementuje oddzielne `volatility_refinement_v1`.
Jego CLI `refine_v2_volatility.py` dopasowuje tylko phi i stacjonarne std,
wywołując niezmienioną matematykę generatora v2. `profile_v2.py` deleguje
walidację pełnego audytu refinement; zapis zachowuje wspólny kontekst publikacji.
Jawna mapa mechanizmów zawiera dodatkowo `bridge_volatility`. `experiments.py`
oddziela wariant mechanizmów od rodziny profilu i nie miesza hashów w grupie.
Szczegóły celu i przepływu: [RAPORT_REFINEMENT_V2.md](RAPORT_REFINEMENT_V2.md).

Kolejny etap powinien otrzymać rzeczywiste funkcje, testy jednostkowe i lokalny
test integracyjny w przewidzianym katalogu. Nowy pipeline może składać te funkcje.
Nie ma atrap klas ani `NotImplementedError`. Biblioteki wykresów i ML należy
dodawać dopiero podczas implementacji, jako opcjonalne grupy zależności.
Aktualny proces danych pozostaje lekki; nie budujemy ogólnego frameworka giełd.

# Architektura Market Levels

Docelowo system obsłuży odtwarzalny eksperyment dostrajania modelu multimodalnego
do poziomów wsparcia i oporu. Działa wyłącznie pozyskiwanie i walidacja
rzeczywistych OHLC. Jest to jeden pakiet, bez mikroserwisów, bazy danych i MLOps.

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

Przepływ: CLI → konfiguracja JSON + nadpisania CLI → pipeline → archiwa i SHA-256 → parser ZIP → walidacja okresu
i szeregu → kontrola brzegów → CSV → raport → manifest. Przy `strict_gaps`
przerwanie następuje po CSV i raporcie, przed manifestem, jak w oryginale.

Model i okresy nie zależą od wejścia/wyjścia. Walidacja zależy od modelu,
parser Binance od walidacji. HTTP nie zna świec ani raportów, zapis nie pobiera
i nie waliduje danych. Pipeline składa funkcje niższych warstw. Nie dodano
hierarchii klas, interfejsów ani ogólnego mechanizmu wstrzykiwania zależności.

`Candle.source_archive` pozostaje wymagane. Model nie importuje Binance.
Wydzielenie metadanych pochodzenia można rozważyć wraz z danymi syntetycznymi;
obecnie nie ma migracji modelu i danych.

## Pakiet i uruchamianie

Setuptools odkrywa `market_levels*` w `src/`. Instalacja udostępnia
`market_levels.cli.download` i `market-levels-download`. Python 3.10+,
bez zewnętrznych zależności uruchomieniowych.

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

## Przyszłe etapy — wyłącznie katalogi z README

| Katalog pakietu | Planowana odpowiedzialność |
| --- | --- |
| `data_processing/synthetic/` | reżimy rynku, seed, konfiguracja, OHLC i metadane |
| `data_processing/windows/` | okna 120 świec, przesunięcia, luki i granice podziałów |
| `charts/` | Matplotlib/mplfinance, styl, rozdzielczość, PNG i diagnostyka |
| `labeling/` | model poziomów, deterministyczny algorytm, etykiety i audyt referencji |
| `datasets/` | chronologia, nakładanie okien, udziały źródeł, obraz–instrukcja–JSON, schematy i manifesty |
| `modeling/` | modele multimodalne bez narzuconej rodziny |
| `training/` | dostrajanie, adaptery, checkpointy, logi |
| `inference/` | obraz i instrukcja → JSON, niezależnie od treningu |
| `evaluation/` | porównanie modelu bazowego, dostrojonego i algorytmu; precision, recall, F1, błąd ceny, JSON, czas i analiza błędów |
| `experiments/` | identyfikatory, wersje danych, konfiguracje i wyniki |

Reguły etykietowania pozostają planem: ekstrema z trzema świecami po obu stronach,
minimum dwie niezależne reakcje oddalone o minimum pięć świec, Wilder ATR(14),
grupowanie 0,5 ATR i mediana ekstremów. Dalej: klasyfikacja względem ostatniego
zamknięcia, pomijanie poziomów zbyt bliskich, ranking według reakcji, aktualności
i odległości, maksymalnie trzy wsparcia i trzy opory. Nie implementowano tych reguł.

## Dane, wyniki i konfiguracja

Zachowano `data/raw`, `processed`, `reports`. Przyszłe artefakty mają katalogi
`data/synthetic`, `charts`, `labels`, `splits`. Wyniki mają miejsca
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

Kolejny etap powinien otrzymać rzeczywiste funkcje, testy jednostkowe i lokalny
test integracyjny w przewidzianym katalogu. Nowy pipeline może składać te funkcje.
Nie ma atrap klas ani `NotImplementedError`. Biblioteki wykresów i ML należy
dodawać dopiero podczas implementacji, jako opcjonalne grupy zależności.
Aktualny proces danych pozostaje lekki; nie budujemy ogólnego frameworka giełd.

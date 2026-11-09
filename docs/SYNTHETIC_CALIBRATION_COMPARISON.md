# Kalibracja i opisowe porównanie syntetycznych OHLC

To proces diagnostyczny etapu 3.3, korzystający z istniejącego generatora.
Nie zmienia jego mechanizmu ani parametrów. Nie buduje końcowego zbioru
multimodalnego, obrazów ani etykiet. Działa offline, bez nowych zależności.

Ta instrukcja dotyczy domyślnego v1. Kalibrację i porównanie 60+60 v1 autor już
wykonał. Nowe polecenia opcjonalne `--generator-version v2`, `--v2-variant`
i tryb porównania `--reports` opisuje [instrukcja v2](SYNTHETIC_V2_POWERSHELL.md).
Porównanie przyjmuje manifesty obu wersji i rozróżnia profile schematu 1/2.

## Zatwierdzony podział

Źródło ustawień: `configs/experiment.json`, sekcja `chronological_split`.
Identyfikator: **chronological_v1**, status **approved**. Obowiązuje dla BTC i ETH.
Granice dotyczą czasu **otwarcia** świecy 4h w UTC, **włącznie**.

| Zbiór | Początek | Koniec | Świece / instrument |
| --- | --- | --- | ---: |
| Trening | 2020-01-01 00:00 UTC | 2023-12-31 20:00 UTC | 8765 |
| Walidacja | 2024-01-01 00:00 UTC | 2024-12-31 20:00 UTC | 2196 |
| Test | 2025-01-01 00:00 UTC | 2026-10-31 20:00 UTC | 4014 |

Liczebności potwierdzono w lokalnych CSV. W treningu brakuje świecy
2020-02-19 12:00 UTC dla obu instrumentów. Nie interpolujemy.
Zatwierdzenie podziału **nie zatwierdza parametrów ani profili generatora**.

## Kalibracja

`market-levels-calibrate` przyjmuje wymagane `--symbol`, `--input`, `--start`,
`--end`, `--output`. Opcjonalne `--config` wskazuje plik konfiguracji, domyślnie
`configs/experiment.json`. `--dry-run` oblicza i sprawdza profil, bez zapisu.
Brak granic jest błędem. Wymagane UTC, granice 4h, początek < koniec i cały
okres mieszczący się w treningu. Nie ma flagi dopuszczającej walidację/test.

CLI wywołuje istniejące `calibrate_csv()` i `save_profile()`. Odczytuje i waliduje
**cały** CSV; do estymacji wybiera wyłącznie dozwolone obserwacje treningowe.
SHA-256 całego CSV identyfikuje źródło, nie jest parametrem generatora.
Zwroty liczymy wyłącznie między rzeczywiście sąsiednimi świecami 4h.
Profil v1 zachowuje dotychczasowy format; `source.chronological_split` dodaje
identyfikator i granice zatwierdzonego podziału. Status zawsze `unapproved`.
Zapis jest atomowy, bez nadpisywania; wymaga hard links, np. na lokalnym NTFS.
Dry-run także zgłasza kolizję istniejącego pliku, aby sprawdzać planowany zapis.

Podstawowe API kalibracji pozostaje ogólne i nie ładuje konfiguracji. Jeżeli
wywołujesz je poza CLI, sam odpowiadasz za dozwolony zakres. Nie używaj tego
do obejścia zatwierdzonego podziału. Kalibrację rynku v1 wykonał autor po
otrzymaniu pierwszego wdrożenia narzędzi.

## Selekcja rzeczywistych okien

`select_real_windows()` działa wyłącznie na zadeklarowanym okresie treningowym:

1. Zachowuje indeksy rekordów CSV i dzieli dane na ciągłe odcinki, przecinając je przy lukach.
2. Oblicza maksymalną liczbę rozłącznych okien jako sumę `floor(długość_odcinka/120)`.
3. Osobnym RNG wybiera żądaną liczbę miejsc pojemności odcinków, ustalając liczbę okien na odcinek.
4. Dla odcinka o N świecach i k oknach losuje k różnych uporządkowanych liczb y
   z `range(N − 120*k + k)`. Początek okna j to `y_j + j*119`.

Różnica kolejnych początków wynosi co najmniej 120, więc okna nie nakładają się.
Każde mieści się w swoim ciągłym odcinku. Nie ma zachłannego wyboru mogącego
przypadkowo uniemożliwić znalezienie wykonalnej liczby okien. Dla lokalnego treningu
maksimum wynosi 72, więc wybór 60 jest wykonalny. Za duże żądanie daje błąd
z rzeczywistym maksimum; nie zmniejszamy liczby po cichu.

Przydział jest losowy względem pojemności odcinków, a pozycje warunkowo jednostajne
w obrębie odcinka dla danej liczby okien. To **nie** jednostajny rozkład wszystkich
możliwych zestawów okien w całym treningu. Nie używamy cen, formacji ani etykiet
do wyboru. Efektywny seed pochodzi z `example_seed(selection_seed, symbol, 0)`.
Okna i ich lista są chronologiczne. Metadane zawierają metodę, oba seedy,
maksimum, luki, zakres i pełne indeksy rekordów każdego wybranego okna.

## Odczyt syntetyków

`market-levels-compare-synthetic` odczytuje **faktycznie zapisane CSV** wskazane
przez `--synthetic-manifest`. Nie zgaduje run_id, nie regeneruje danych i nie
porównuje samych profili. Wymaga dokładnie `--window-count` przykładów danego
instrumentu (domyślnie 60), bez cichego wybierania podzbioru większej partii.
BTC i ETH analizujemy osobno. Mniejsza liczba, np. 2, służy testom technicznym.

Sprawdzamy identyfikator partii z konfiguracji/profili, unikalność wpisów, zgodność
symbolu, seeda, plików i profilu z metadanymi, hash kanoniczny OHLC, walidację
120 świec i zakresów faz, liczbę kroków oraz zapisane statystyki i udziały faz.
Statystyki są ponownie liczone z CSV. Ścieżki muszą być względne i pozostać
w katalogu partii. Uszkodzone/brakujące pliki powodują błąd, nie pominięcie.

Profil musi być empiryczny (`unapproved` lub `approved`) i mieć zakres mieszczący
się w obecnym treningu. Ręczne parametry `diagnostic_profile()` są odrzucane.
Jeśli profil zawiera zapis podziału, musi on odpowiadać konfiguracji. Starszy
profil bez tej metadanej może być użyty po kontroli granic. Różny hash real-csv
i źródła profilu daje jawne ostrzeżenie o pochodzeniu, nie automatyczną akceptację
zgodności danych. Oznaczenie symbolu CSV opiera się na deklaracji użytkownika:
w dotychczasowym formacie OHLC nie ma kolumny symbolu.

## Statystyki i interpretacja

Wspólne `series_observations()`, `series_statistics()` i `distribution()`
zapewniają te same definicje co wcześniej. Wydzielono dostęp do surowych
obserwacji, bez zmiany wzorów i formatu dotychczasowych statystyk.

| Sekcja JSON | Metryka | Definicja |
| --- | --- | --- |
| pooled_observations | log_returns | log(Close_t) − log(Close_t-1), tylko wewnątrz okna |
| pooled_observations | absolute_log_returns | abs(r) |
| pooled_observations | relative_range | (High−Low)/Open |
| pooled_observations | relative_body | abs(Close−Open)/Open |
| pooled_observations | body_fraction | abs(Close−Open)/(High−Low) |
| pooled_observations | upper_wick_fraction | (High−max(Open,Close))/(High−Low) |
| pooled_observations | lower_wick_fraction | (min(Open,Close)−Low)/(High−Low) |
| window_distributions | return_std | próbne odchylenie zwrotów osobno w każdym oknie |
| window_distributions | close_change | ostatnie Close / pierwsze Open − 1 |
| window_distributions | relative_range | max(High)/min(Low) − 1 w oknie |
| absolute_return_lag1 | value | Pearson par abs(r_t-1), abs(r_t), bez łączenia granic okien |
| synthetic_source.regimes | occurrences, candle_shares, regimes_per_example | liczba wystąpień, udział świec i rozkład liczby faz |

Dla zerowego High−Low proporcje korpusu i knotów wynoszą 0, zgodnie ze starszym
kodem. Każdy rozkład zawiera count, mean, próbne std (dla jednej obserwacji 0),
min/max oraz kwantyle 1%, 5%, 50%, 95%, 99% z interpolacją liniową.

W `pooled_observations` najpierw liczymy wartości **w każdym oknie**, potem łączymy
obserwacje. Dla 60 okien jest 7140 zwrotów i 7200 obserwacji parametrów świec.
Kwantyle pochodzą z połączonych wartości; nie uśredniamy kwantyli okien.
`window_distributions` opisuje rozkłady 60 parametrów całych okien.
`per_window` zachowuje wartości pozwalające później dobrać przykłady do obejrzenia.

Autokorelacja lag 1 jest tu współczynnikiem Pearsona dla zbioru dozwolonych par
opóźnionych. Dla 60 pełnych okien są 7080 par. Nie ma par ani zwrotów między
oknami. Mniej niż dwie pary albo zerowa wariancja daje `value=null`, jawny reason
i pair_count. Dotyczy to również korelacji liczonej osobno dla okien.

Różnice są podpisane jako `synthetic_minus_real`, także dla kwantyli. Nie
stosujemy procentów ani ilorazów dla średnich bliskich zeru. Nie wyznaczamy
progu automatycznej akceptacji ani etykiet reżimów dla rzeczywistych danych.

Trening służy zarówno estymacji, jak i opisowi odniesienia. To porównanie opisowe,
**nie niezależna walidacja na niewidzianych danych**. Nie wykorzystujemy walidacji
i testu do strojenia generatora. Rozkład normalny, 12 kroków i ręczne parametry
faz nadal wymagają oceny; nie zmieniamy ich automatycznie w odpowiedzi na raport.

## PowerShell: kompletny przebieg

Uruchamiaj z głównego katalogu projektu. Polecenia operacji danych są offline;
do instalacji potrzebny jest dostępny setuptools. Autor wykonał już właściwą
kalibrację v1 i partię 60+60. Nie nadpisujemy istniejących profili ani raportów;
poniższe komendy służą do świadomego odtworzenia procesu w nowych lokalizacjach.

Przygotowanie, testy i odczyt zatwierdzonych granic:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

$experimentJson = & ./.venv/Scripts/python.exe -B -c 'import json, sys; from pathlib import Path; from market_levels.shared.configuration import read_configuration; print(json.dumps(read_configuration(Path(sys.argv[1]))))' configs/experiment.json
if ($LASTEXITCODE -ne 0) { throw 'Nie można wczytać konfiguracji' }
$experiment = $experimentJson | ConvertFrom-Json
$trainStart = $experiment.chronological_split.periods.train.start
$trainEnd = $experiment.chronological_split.periods.train.end
$symbols = @('BTCUSDT', 'ETHUSDT')
$profiles = @{
    BTCUSDT = 'data/synthetic/calibration/BTCUSDT_train_2020_2023_unapproved.json'
    ETHUSDT = 'data/synthetic/calibration/ETHUSDT_train_2020_2023_unapproved.json'
}
```

Najpierw dry-run kalibracji BTC i ETH (obliczenia bez zapisu):

```powershell
foreach ($symbol in $symbols) {
    .\.venv\Scripts\market-levels-calibrate.exe --symbol $symbol `
        --input "data/processed/${symbol}_4h_2020-01_2026-10.csv" `
        --start $trainStart --end $trainEnd --output $profiles[$symbol] --dry-run
    if ($LASTEXITCODE -ne 0) { throw "Błąd dry-run kalibracji $symbol" }
}
```

Właściwy zapis obu profili, nadal `unapproved`:

```powershell
foreach ($symbol in $symbols) {
    .\.venv\Scripts\market-levels-calibrate.exe --symbol $symbol `
        --input "data/processed/${symbol}_4h_2020-01_2026-10.csv" `
        --start $trainStart --end $trainEnd --output $profiles[$symbol]
    if ($LASTEXITCODE -ne 0) { throw "Błąd kalibracji $symbol" }
}
```

Generowanie diagnostyczne: najpierw dry-run, potem 60 na instrument. Przechwycenie
ścieżki z dotychczasowego komunikatu CLI usuwa potrzebę zgadywania run_id:

```powershell
$generationArgs = @(
    '--diagnostic', '--count', '60', '--symbols', 'BTCUSDT', 'ETHUSDT',
    '--seed', '20261105',
    '--profile', "BTCUSDT=$($profiles['BTCUSDT'])",
    '--profile', "ETHUSDT=$($profiles['ETHUSDT'])",
    '--output', 'data/synthetic'
)
.\.venv\Scripts\market-levels-generate-synthetic.exe @generationArgs --dry-run
if ($LASTEXITCODE -ne 0) { throw 'Błąd dry-run generatora' }

$generationOutput = @(& .\.venv\Scripts\market-levels-generate-synthetic.exe @generationArgs)
if ($LASTEXITCODE -ne 0) { throw 'Błąd generatora; poprzednia partia nie jest nadpisywana' }
$generationOutput | Write-Output
$batchPath = ($generationOutput[-1] -split ': ', 2)[1]
$manifestPath = Join-Path -Path $batchPath -ChildPath 'manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'Nie znaleziono manifestu nowej partii' }
Write-Output "Manifest: $manifestPath"
```

Powstaje łącznie 120 serii: 7200 świec BTC i 7200 ETH. Ponowne identyczne
uruchomienie generatora odmawia zapisu. Do istniejącej partii porównanie można
uruchomić ponownie, wskazując jej manifest; nie trzeba generować jej jeszcze raz.
Nie używaj „najnowszego katalogu” jako automatycznego zamiennika w razie błędu.

Dry-run obu porównań, następnie właściwe raporty:

```powershell
foreach ($symbol in $symbols) {
    .\.venv\Scripts\market-levels-compare-synthetic.exe --symbol $symbol `
        --real-csv "data/processed/${symbol}_4h_2020-01_2026-10.csv" `
        --synthetic-manifest $manifestPath --start $trainStart --end $trainEnd `
        --window-count 60 --selection-seed 20261106 --output data/synthetic/comparisons --dry-run
    if ($LASTEXITCODE -ne 0) { throw "Błąd dry-run porównania $symbol" }
}

$reportPaths = @()
foreach ($symbol in $symbols) {
    $comparisonOutput = @(& .\.venv\Scripts\market-levels-compare-synthetic.exe --symbol $symbol `
        --real-csv "data/processed/${symbol}_4h_2020-01_2026-10.csv" `
        --synthetic-manifest $manifestPath --start $trainStart --end $trainEnd `
        --window-count 60 --selection-seed 20261106 --output data/synthetic/comparisons)
    if ($LASTEXITCODE -ne 0) { throw "Błąd porównania $symbol" }
    $comparisonOutput | Write-Output
    $jsonLine = @($comparisonOutput | Where-Object { $_ -like 'Raport JSON:*' })[-1]
    $reportPaths += ($jsonLine -split ': ', 2)[1]
}
$reportPaths | ForEach-Object { Get-Item -LiteralPath $_ }
```

Równoważne moduły: `python -m market_levels.cli.calibrate_synthetic` oraz
`python -m market_levels.cli.compare_synthetic`, z tymi samymi argumentami.
`--selection-seed` jest niezależny od seeda generatora. Zmiana seeda selekcji
tworzy inne porównanie bez zmiany profili i syntetyków.

## Wyniki i dalsza ocena

```text
data/synthetic/calibration/BTCUSDT_train_2020_2023_unapproved.json
data/synthetic/calibration/ETHUSDT_train_2020_2023_unapproved.json
data/synthetic/diagnostics/<automatyczny_run_id>/manifest.json
data/synthetic/comparisons/<comparison_id_BTC>/BTCUSDT_comparison.json
data/synthetic/comparisons/<comparison_id_BTC>/BTCUSDT_summary.md
data/synthetic/comparisons/<comparison_id_ETH>/ETHUSDT_comparison.json
data/synthetic/comparisons/<comparison_id_ETH>/ETHUSDT_summary.md
```

JSON przechowuje źródła z hashami, profil i status, identyfikator podziału,
seedy, wybór okien, sprawdzone przykłady, statystyki, różnice, rozkład faz
i ostrzeżenia. comparison_id jest hashem kompletnego raportu bez samego ID;
nie zawiera czasu uruchomienia. Takie same wejścia/ścieżki, konfiguracja i wersja
implementacji/środowiska dają ten sam raport. Zmiana ścieżek w metadanych zmienia
ID, nawet gdy statystyki są identyczne. Brak gwarancji identyczności obliczeń
między dowolnymi wersjami Pythona; walidacja zapisanych statystyk jest ścisła.

JSON i Markdown publikowane są razem, bez nadpisania. Przy obsłużonym błędzie
katalog roboczy jest sprzątany. Awaria systemu może pozostawić nieopublikowany
`.comparison-*`. Sekwencyjny zapis do jednego output jest zalecany.

Do następnej oceny przekaż dwa `*_summary.md` oraz dwa `*_comparison.json`.
Profile i manifest mogą posłużyć do audytu pochodzenia; nie ma potrzeby przesyłać
całej historii ani wszystkich CSV. Nie publikuj danych automatycznie;
obowiązują dotychczasowe [zastrzeżenia licencyjne](LICENCJA_DANYCH.md).

Przed zatwierdzeniem generatora autor powinien ocenić różnice, sprawdzić ręczne
parametry faz i wpływ 12 kroków oraz obejrzeć reprezentatywne próbki po wdrożeniu
renderera. Profile pozostają `unapproved`. **Kontrola wizualna: oczekuje na
implementację modułu wykresów.** Nie wygenerowano docelowych 440 przykładów.

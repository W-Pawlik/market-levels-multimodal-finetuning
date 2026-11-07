# Generator syntetycznych OHLC

Generator służy przygotowaniu niezależnych przykładów dla późniejszego modułu
wykresów i eksperymentu multimodalnego. Nie tworzy obrazów, etykiet ani podziału
train/validation/test. Używa wyłącznie biblioteki standardowej Pythona.

Poniższa matematyka opisuje zachowaną wersję **v1**, nadal domyślną.
Jawne `--generator-version v2` wybiera nową wersję z osobnym profilem i wariantami.
Równania, status parametrów i ograniczenia: [generator v2](SYNTHETIC_GENERATOR_V2.md).

## Model ceny i świece

Symulacja zachodzi w skali logarytmu ceny `x = log(P)`. Dla każdego z 12 kroków:

```text
x_next = x + (mu - kappa * (x - center)) / 12 + sigma / sqrt(12) * epsilon
P_next = exp(x_next)
epsilon ~ N(0, 1)
```

`mu` i `sigma` opisują kierunek oraz zmienność w skali jednej świecy 4h.
`kappa` jest siłą rewersji w skali świecy; jej składnik dzielimy przez 12.
Jest to dyskretna symulacja z metodą Eulera, bez dodatkowej korekty `-sigma²/2`,
ponieważ modelujemy bezpośrednio logarytmiczne stopy, a nie dryf ceny arytmetycznej.

Open to ostatnia cena, Close to dwunasty krok. High/Low to maksimum/minimum
z Open i dwunastu kroków. Nie losujemy dodatkowych knotów. Obliczenia ścieżki
używają `float`; dopiero ceny gotowej świecy przechodzą przez `Decimal(str(value))`.
Nie ma kwantyzacji ani zaokrągleń po każdym kroku. Zapewnia to równość
`Open_t == Close_(t-1)` oraz zachowanie relacji OHLC. Nie oznacza to obliczeń
ścieżki z dowolną precyzją dziesiętną. Niefinitywne, niedodatnie i przepełnione
wyniki powodują błąd zamiast zastępowania ich arbitralną ceną.

## Reżimy

Trend wzrostowy ma dodatnie `mu`, spadkowy ujemne; oba zachowują losowy szum.
Konsolidacja ma `mu=0`, niższą zmienność i dodatnie `kappa`. Jej środek to
logarytm ceny na początku tej fazy. Nie ma sztywnych barier ani idealnych poziomów.
Wybicie ma losowy znak, silniejszy dryf i większą zmienność, bez skoku ceny.
W tej implementacji wybicie dopuszczamy wyłącznie po konsolidacji.

Najpierw wyliczamy wszystkie wykonalne sekwencje 1–3 faz. Liczbę faz losujemy
jednostajnie spośród liczebności mających wykonalne sekwencje. Sekwencję ważymy
iloczynem wagi początkowej i wag przejść. Są to wagi względne, nie bezwarunkowe
prawdopodobieństwa końcowe: ograniczenia długości zmieniają rozkład planów.
Nie dopuszczamy dwóch identycznych faz pod rząd. Wybicie nie może zajmować
samodzielnie całego przykładu.

Długości są losowane kolejno z przedziałów pozostawiających wykonalne minimum
i maksimum dla pozostałych faz. Ostatnia faza dostaje resztę. Zawsze uzyskujemy
dokładnie 120 świec, bez pustych segmentów. Brak wykonalnej sekwencji to błąd.
Indeksy `start` i `end_exclusive` w metadanych są liczone od zera.

## Parametry i ich status

Aktywne ustawienia znajdują się w `configs/experiment.json` w `synthetic`.
Poniższe wartości opisują stan początkowy, a nie drugi plik konfiguracji.

| Parametr | Wartość początkowa | Status |
| --- | --- | --- |
| Instrumenty, interwał | BTCUSDT/ETHUSDT, 4h | zatwierdzone |
| Świece, kroki | 120, 12 | zatwierdzone; inne wartości odrzucane |
| Liczba faz | 1–3 | zatwierdzony zakres; można go zawęzić |
| Seed główny | 20261103 | roboczy, konfigurowalny |
| Liczba przykładów | 5 na instrument | robocza; dowolna dodatnia liczba całkowita |
| Diagnostyczne sigma 4h | BTC 0,012; ETH 0,016 | ręczne, bez kalibracji |
| Diagnostyczne ceny początkowe | BTC 20 000–70 000; ETH 1000–4000 | ręczne, bez kalibracji |
| Ceny początkowe po kalibracji | kwantyle 5%–95% Close | empiryczne; wybór kwantyli projektowy |
| Sigma po kalibracji | odchylenie próbki log(Close_t/Close_(t-1)) | empiryczne, tylko sąsiednie 4h |
| Dryf trendu / sigma bazowe | jednostajnie 0,08–0,25 ze znakiem trendu | projektowe, niezatwierdzone |
| Dryf wybicia / sigma bazowe | jednostajnie 0,4–0,9, losowy znak | projektowe, niezatwierdzone |
| Sigma trendu / sigma bazowe | jednostajnie 0,8–1,2 | projektowe, niezatwierdzone |
| Sigma konsolidacji / sigma bazowe | jednostajnie 0,45–0,8 | projektowe, niezatwierdzone |
| Sigma wybicia / sigma bazowe | jednostajnie 1,2–1,8 | projektowe, niezatwierdzone |
| Kappa konsolidacji | jednostajnie 0,05–0,2 na świecę | projektowe, niezatwierdzone |
| Minimum długości | trendy/konsolidacja 24, wybicie 8 | robocze |
| Maksimum długości | trendy/konsolidacja 120, wybicie 24 | robocze |
| Wagi początkowe | wzrost 1, spadek 1, konsolidacja 2, wybicie 0 | robocze |
| Wagi przejść | trend→przeciwny trend 1, →konsolidacja 2; konsolidacja→trendy po 1, →wybicie 3; wybicie→pozostałe po 1 | robocze |
| Rozkład zaburzeń | standardowy normalny | projektowy; bez dodatkowego modelu skoków |
| Cena początkowa | jednostajnie w logarytmie dopuszczalnego zakresu | projektowe |
| Początek czasu | 2000-01-01 00:00 UTC | techniczny indeks symulacji |

Wagi, długości i zakresy parametrów faz są konfigurowalne w `synthetic.regimes`.
`profiles` to mapa symbol→plik JSON. Nieznane opcje powodują błąd; CLI nadpisuje
JSON przed walidacją. `--profile SYMBOL=PATH` można podać osobno dla obu symboli.
Ustawienia i ścieżki są liczone względem katalogu uruchomienia.

Udział 55%, robocze 800 wykresów i wynikające z nich 440 syntetycznych przykładów
nie sterują liczbą generowanych serii. Generator nie dobiera automatycznie
liczebności ani proporcji docelowego zbioru.

## Kalibracja i ochrona danych testowych

**Nie ma domyślnego okresu kalibracji ani automatycznego uznania całego pliku
historycznego za trening.** Nie uruchomiono końcowej kalibracji rynku.

Zatwierdzono podział `chronological_v1`: trening 2020–2023, walidacja 2024,
test 2025–2026-10, granice otwarcia świec UTC włącznie. Nowe CLI
`market-levels-calibrate` sprawdza jawne `--start`/`--end` względem treningu
z konfiguracji; nie udostępnia obejścia na dane walidacyjne/testowe. Podstawowe
API nadal wymaga okresu przekazanego przez wywołującego.
Krok po kroku: [kalibracja i porównanie](SYNTHETIC_CALIBRATION_COMPARISON.md).

API w `market_levels.data_processing.synthetic.calibration`:

```python
profile = calibrate_csv(
    input_csv, symbol,
    allowed_start=training_start,
    allowed_end=training_end,
)
save_profile(output_json, profile)
```

`input_csv` i `output_json` są obiektami `Path`, a granice muszą być jawnymi
`datetime` w UTC, na granicach 4h, początek < koniec. Granice są **włącznie**,
odnoszą się do czasu otwarcia świecy. `calibrate(candles, ...)` pozwala podać
już wybrany zbiór świec; nadal wymaga jawnych granic. Dane poza okresem nie są
uwzględniane w statystykach. Brakujące brzegi okresu są widoczne jako osobne
granice dozwolone i zaobserwowane. Potrzeba co najmniej trzech obserwacji,
sąsiadujących zwrotów i dodatniego oszacowania zmienności.

Odczyt pliku weryfikuje format i OHLC; nie korzysta z obserwacji spoza okresu do
doboru parametrów. SHA-256 całego wejściowego CSV jest wyłącznie identyfikatorem
pochodzenia i może zmienić się po zmianie rekordów poza zakresem. Gdy czas między
świecami wynosi 8h lub więcej, przejście nie tworzy stopy 4h. Nie interpolujemy.
Raport liczy pominięte **przejścia**, nie sumę brakujących świec.

Statystyki obejmują logarytmiczne i bezwzględne zwroty, średnią, próbne odchylenie
standardowe, min/max i kwantyle 1%, 5%, 50%, 95%, 99% (interpolacja liniowa).
Zakres i korpus są normalizowane przez Open, knoty i proporcja korpusu przez
High−Low. Dla zerowego zakresu proporcje wynoszą 0. Profil przechowuje źródło,
instrument, obie pary granic, liczbę obserwacji, pominięte przejścia, statystyki,
parametry generatora, status i wersję.

Nowa kalibracja zawsze daje `status="unapproved"`. Można jej użyć diagnostycznie,
ale kandydaci wymagają profilu `approved`. Podział jest już zatwierdzony;
po osobnym przeglądzie i zatwierdzeniu parametrów przez autora można jawnie wykonać:

```python
approved = approve_profile(
    profile,
    training_start=approved_training_start,
    training_end=approved_training_end,
    split_id=approved_split_id,
    reviewed_by=author_of_approval,
)
save_profile(new_approved_path, approved)
```

API sprawdza, czy cały dozwolony okres kalibracji mieści się w zatwierdzonym
treningu; wymaga identyfikatora podziału i autora decyzji. Nie ustala tych danych
samodzielnie. Ten zapis dokumentuje decyzję, nie jest systemem uwierzytelniania
ani dowodem niezależnego audytu. Nie ustawiaj zatwierdzenia bez rzeczywistej decyzji.
Profile zapisują się atomowo przez hard link kompletnego pliku tymczasowego
na tym samym systemie plików, z odmową nadpisania (wymagane wsparcie hard links,
np. lokalny NTFS). Nie ma zapisu do plików źródłowych.

## Losowość i odtwarzanie

Każdy przykład używa własnego `random.Random(seed)`. Seed przykładu jest liczbą
całkowitą z SHA-256 tekstu `master_seed:symbol:index`. Nie zależy od kolejności
symboli ani od liczby innych przykładów. Pipeline kontroluje kolizje seedów.
Generowanie 10 serii jest dziesięcioma niezależnymi symulacjami, bez wybierania
nakładających się okien z długiej ścieżki.

Metadane zapisują pełny profil, jego hash, konfigurację, seed, wersję generatora
i wersję/implementację Pythona. Funkcja `generate_example(symbol, seed, profile,
settings)` odtwarza przykład z tych danych. Do ponownego wczytania ustawień
można zapisać `{"synthetic": metadata["configuration"]}` i użyć
`load_synthetic_settings`. Zapisane `configuration` obejmuje także ścieżkę
wyjściową, mimo że nie wpływa ona na OHLC. Nie gwarantujemy zgodności wyników
między dowolnymi wersjami Pythona i platformami; sprawdzono Python 3.13.15/Windows.

## Uruchamianie w PowerShell

Z katalogu głównego projektu:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\market-levels-generate-synthetic.exe --diagnostic --count 5 --symbols BTCUSDT ETHUSDT --seed 20261103 --dry-run
.\.venv\Scripts\market-levels-generate-synthetic.exe --diagnostic --count 5 --symbols BTCUSDT ETHUSDT --seed 20261103 --output data/synthetic
.\.venv\Scripts\python.exe -m market_levels.cli.generate_synthetic --diagnostic --count 1 --symbols ETHUSDT --seed 20261104 --output data/synthetic
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Pierwsza generowana partia to 5 BTC + 5 ETH. Powtórzenie tego samego polecenia
odmawia nadpisania. Aby otrzymać inną próbkę, zmień seed. Aby odtworzyć OHLC,
wskaż nowy, pusty katalog wyjściowy. Identyczne dane wykryte względem poprzednich
partii w tym samym `--output` również powodują odmowę zapisu.

Dopiero gdy istnieją rzeczywiście zatwierdzone profile:

```powershell
.\.venv\Scripts\market-levels-generate-synthetic.exe --no-diagnostic --count 5 --symbols BTCUSDT ETHUSDT --profile BTCUSDT=data/synthetic/calibration/BTCUSDT_approved.json --profile ETHUSDT=data/synthetic/calibration/ETHUSDT_approved.json --dry-run
```

Usunięcie `--dry-run` zapisuje kandydatów, bez uznawania ich automatycznie
za końcowy zbiór treningowy. Domyślne `diagnostic=false` i puste profile
celowo blokują generowanie bez jawnego wyboru trybu lub profili.

## Format i bezpieczeństwo wyników

```text
data/synthetic/
  calibration/                       profile zapisywane jawnie przez użytkownika
  diagnostics/<run_id>/               partia diagnostyczna
    BTCUSDT/<example_id>.csv
    BTCUSDT/<example_id>.json
    ETHUSDT/<example_id>.csv
    ETHUSDT/<example_id>.json
    manifest.json
  candidates/<run_id>/                analogicznie, profile approved
```

Manifest jest wewnątrz partii, aby dane i manifest można było opublikować jednym
rename katalogu. Zawiera ścieżki względne, seedy, hashe, statystyki, udziały faz,
liczebność przyjętych/odrzuconych przykładów i status kontroli wizualnej.
Każdy JSON przykładu zawiera również parametry i zakresy faz, wynik walidacji,
pełny profil, wersję i potwierdzenie ponownego odczytu CSV.
CSV zachowuje `open_time_utc,open,high,low,close` i ceny Decimal.

Wszystkie przykłady mają czas od 2000-01-01 00:00 UTC co 4h. To wyłącznie indeks
symulacji; powtarzanie tych samych dat między seriami jest celowe. Nie wolno na
ich podstawie ustalać chronologicznego podziału rzeczywistych notowań.
`source_archive` zaczyna się od `synthetic:` i nie udaje archiwum Binance.

Identyfikator partii jest hashem konfiguracji, profili i wersji środowiska
(bez katalogu wyjściowego); identyfikator przykładu zawiera symbol, indeks i seed.
Hash OHLC obejmuje kanoniczne wartości cen, bez dat i pochodzenia. Zera końcowe
Decimal nie maskują identycznych przykładów. Kontrola duplikatów obejmuje partię
i manifesty poprzednich partii w tym samym katalogu wyjściowym.

Pipeline najpierw waliduje konfigurację/profil, a potem zapisuje do katalogu
tymczasowego. Przed publikacją odczytuje każde CSV i porównuje pełne obiekty
`Candle` oraz hash. Błąd wartości, kolizja, duplikat lub błąd zapisu przerywa
całą partię; katalog tymczasowy jest sprzątany przy obsłużonym wyjątku.
Nie losujemy cicho zamienników. Udana partia ma `rejected_count=0`; przy błędzie
nie publikuje się manifestu ani częściowych przykładów, CLI zwraca kod 1 i powód.
Awaria systemu/zasilania może pozostawić ukryty katalog roboczy `.synthetic-*`;
nie jest on opublikowaną partią. Nie zapewniamy transakcji między równoległymi
procesami sprawdzającymi duplikaty; uruchamiaj zapis do danego output sekwencyjnie.

## Kontrola jakości i ograniczenia

Kontrola techniczna używa wspólnych walidatorów OHLC, UTC/granic 4h oraz
`check_series`; dodatkowo sprawdza 120 świec, ciągłość Open/Close, reżimy,
parametry, seed, pochodzenie i round-trip. Statystyki obejmują zwroty, zakresy,
korpusy, proporcje knotów, zmianę pierwsze Open→ostatnie Close i zakres całego
okna `max(High)/min(Low)-1`. Dla zatwierdzonego profilu JSON podaje różnice
średnich i odchyleń względem treningu. Nie narzuca progów podobieństwa.

Rozkład normalny nie odtwarza automatycznie grubych ogonów, klastrów zmienności,
zależności BTC/ETH ani całej mikrostruktury rynku. Dwanaście kroków może zaniżać
ekstrema i zmieniać rozkład knotów. Nie skorygowano tego niezależnym losowaniem
knotów. Dodatkowe statystyki empiryczne są diagnostyką, a nie dowodem dopasowania
wszystkich aspektów generatora.

Powyższy opis dotyczy historycznego wdrożenia v1. Obecnie renderer i
etykietowanie działają, wykonano pilotaż i audyty V2-full-refined.
Decyzją autora z 2026-11-07 zatwierdzono nowe kopie dwóch profili v2/full
i skład pierwszego zbioru 800 przykładów; nie ponawiano kalibracji.
[Bieżący raport](datasets/RAPORT_3_5_CZ2.md). Dane kalibrowane na Binance nie stają się
automatycznie wolne od ograniczeń publikacji; zobacz [licencję danych](LICENCJA_DANYCH.md).

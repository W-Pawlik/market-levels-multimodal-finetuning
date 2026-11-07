# Etap 3.5, część 1 — mechanizm budowy zbioru

Data wykonania: 2026-11-07. Wdrożono planowanie, walidację i małą próbę
end-to-end. **Nie zbudowano finalnego zbioru 800 wykresów.** Nie generowano nowych
syntetycznych OHLC, nie pobierano danych, nie kalibrowano i nie zmieniano
matematyki generatora, stylu renderera, algorytmu S/R ani chronologii.
Istniejące niezacommitowane zmiany etapu 3.4 zachowano.

## 1. Wdrożony mechanizm

- `data_processing/windows`: walidacja pełnych wejść, rozdział według dokładnych
  granic UTC, ciągłe fragmenty, siatka 120 świec z krokiem 60/120/120,
  kontrola duplikatów, zakresów, indeksów i rozłączności validation/test.
- `datasets/planning.py`: plan 698/36/66, rzeczywista pojemność danych,
  selekcja treningowa, przypięcie źródeł/profili, rezerwacja seedów i kontrola
  zgodności z V2-full-refined. Brak automatycznej korekty założeń przy niedoborze.
- `datasets/packaging.py`: neutralny JSONL, oddzielne metadane, źródłowe CSV,
  oryginalne PNG, odpowiedzi JSON, statystyki audytowe, manifesty i ich hashe,
  odtworzenie i atomowa publikacja bez nadpisywania.
- CLI `market-levels-build-dataset` / `python -m market_levels.cli.build_dataset`:
  wyłącznie `preflight`, `smoke`, `verify`.
- Schemat JSON, [opis formatu](FORMAT.md), [PowerShell](INSTRUKCJA_POWERSHELL.md),
  zbiorczy weryfikator i skrypt paczkowania. Bez nowych zależności.

Docelowe liczebności są w jednym miejscu: `dataset_build.targets` w
`configs/experiment.json`. Plan wylicza z nich sumę 800, 360 realne / 440
syntetyczne, 400 BTC / 400 ETH. Historyczne pola sumy i udziałów zachowano jako
opis założenia; nie są drugim sterownikiem budowy. Nie wdrażano eksperymentu 1600.

## 2–3. Rzeczywista pojemność danych

Odczytano i zwalidowano lokalne pełne CSV, po **14 975 świec** każdego instrumentu.
Aktualny preflight: `results/diagnostics/ds35-pre-20261107-b/plan.json`.
Wcześniejszy przebieg `ds35-pre-20261107-a` pozostawiono bez nadpisania.

| Instrument | Split | Świece | Dostępne okna | Wybrane |
|---|---|---:|---:|---:|
| BTCUSDT | train | 8765 | 143 | 129 |
| ETHUSDT | train | 8765 | 143 | 129 |
| BTCUSDT | validation | 2196 | 18 | 18 |
| ETHUSDT | validation | 2196 | 18 | 18 |
| BTCUSDT | test | 4014 | 33 | 33 |
| ETHUSDT | test | 4014 | 33 | 33 |

**Planowane liczebności rzeczywiste są wykonalne.** Z 388 poprawnych kandydatów
obu instrumentów wybrano w planie 360; 28 niewybranych poprawnych kandydatów
train ma zapisane ID. Dla validation/test wykorzystano wszystkie dostępne okna.
Nie wyrenderowano ani nie etykietowano tych 360 planowanych okien.

Zakresy obejmowane przez wybrane okna, identyczne dla BTC i ETH, w UTC:

| Split | Pierwsze otwarcie | Ostatnie otwarcie |
|---|---|---|
| train | 2020-01-01 00:00 | 2023-12-30 12:00 |
| validation | 2024-01-01 00:00 | 2024-12-25 20:00 |
| test | 2025-01-01 00:00 | 2026-10-22 20:00 |

Granice zatwierdzonych okresów pozostały dokładnie jak w `chronological_v1`;
krótsze pokrycie końca okresów jest skutkiem długości okien i przesunięć.

## 4. Deterministyczny wybór treningu

Metoda `chronological_equal_count_strata_seeded_v1`, seed **20261107**:
143 kandydatów porządkujemy według czasu. Dzielimy indeksy na 129 kolejnych
warstw o prawie równej liczbie kandydatów: `[floor(i*M/N), floor((i+1)*M/N))`.
Z każdej wybieramy jeden indeks przez lokalny `random.Random(seed)`.
Nie używamy cen, etykiet, wyników ani informacji validation/test. Przy regularnej
siatce daje to równomierne rozłożenie w czasie bez optymalizatora.
Metoda jest deterministyczna dla tej samej konfiguracji i danych; testy
sprawdzają także niezależność od kolejności wejściowej i wpływ zmiany seeda.

Pokrycie lat według otwarcia pierwszej świecy, **na instrument**:

| Rok | Kandydaci train | Wybrany train | Validation | Test |
|---|---:|---:|---:|---:|
| 2020 | 35 | 32 | 0 | 0 |
| 2021 | 37 | 33 | 0 | 0 |
| 2022 | 36 | 33 | 0 | 0 |
| 2023 | 35 | 31 | 0 | 0 |
| 2024 | 0 | 0 | 18 | 0 |
| 2025 | 0 | 0 | 0 | 19 |
| 2026 | 0 | 0 | 0 | 14 |

Train świadomie dopuszcza nakładanie. BTC i ETH wybrano na tych samych
pozycjach czasowych; nie są całkowicie niezależnymi obserwacjami rynku.

## 5. Luki, duplikaty i granice

W obu źródłach brakuje **2020-02-19 12:00 UTC**. Train dzieli się na fragmenty
297 i 8468 świec. Siatka zaczyna się od pierwszej świecy każdego fragmentu,
więc żadne utworzone okno nie przechodzi przez lukę. Nie interpolowano.

Niekwalifikujące się początki siatki na instrument (nie są poprawnymi
kandydatami odrzuconymi w selekcji):

| Początek UTC | Dostępne kolejne świece | Powód |
|---|---:|---|
| 2020-01-31 00:00 | 117 | luka |
| 2020-02-10 00:00 | 57 | luka |
| 2023-12-20 16:00 | 68 | granica train |
| 2023-12-30 16:00 | 8 | granica train |
| 2024-12-26 00:00 | 36 | granica validation |
| 2026-10-23 00:00 | 54 | koniec test / danych |

Nie znaleziono duplikatów kanonicznego OHLC w wybranych 360 oknach ani w
8 przykładach próby. Nie ma nakładania validation/test w obrębie instrumentu,
przekroczenia granic ani niepoprawnego OHLC. Kanoniczny hash porównuje ceny,
nie maskuje duplikatów innymi datami lub pochodzeniem. Przypisanie symbolu
kontroluje nazwa źródła i zgodność SHA z profilem; sam CSV nie ma kolumny symbol.

## 6. Przykład przyszłego VLM

Obiekt JSONL ma `id`, `split`, względną ścieżkę `image`, jedną instrukcję
`pl-sr-v1` i `answer: {supports: [...], resistances: [...]}`. Do trzech poziomów
na stronę, także puste listy. Liczby zapisane są z dwoma miejscami po przecinku
bez konwersji Decimal → float przy serializacji; ranking nie zmienia kolejności.
Obliczenia pozostają w stałym 50-cyfrowym kontekście dotychczasowego algorytmu.

Symbol, źródło, zakres, profil, seed, indeksy i SHA-256 są w osobnym pliku
metadanych. Nie przekazujemy ich modelowi. Nie wybrano VLM, dostawcy ani API.
W obecnej próbie `split` jest `null`, status manifestu wyraźnie diagnostyczny.
[Szczegółowy schemat](FORMAT.md).

## 7–8. Renderer, etykietowanie i mała próba

`results/diagnostics/ds35-smoke-20261107-a` zawiera **8 przykładów**: po 2 realne
i 2 syntetyczne BTC/ETH, ponownie użyte z pilotażu 3.3. Nie generowano nowych
syntetyków, nie użyto obrazów diagnostycznych z liniami z 3.4.

Każdy obraz wygenerowano istniejącym rendererem i porównano z hashem
oryginalnego PNG pilotażu. Te same 120 świec przekazano do `label_window()`.
Zapisano 8 PNG 1024 × 768, 8 CSV, 8 etykiet JSON, 8 bocznych metadanych,
JSONL, podsumowanie i manifest. Ponowny odczyt odtworzył identyczne PNG i
etykiety, potwierdził ID, zakresy, pełne OHLC, metadane i hashe.
Weryfikacja odrzuca dodatkowe/brakujące pliki, zmieniony manifest i
etykietę niespójną z obliczeniem nawet po ponownym wyliczeniu hashy.

Wyniki audytu próby: **22 wsparcia i 12 oporów**. W 7 przykładach są 3 wsparcia,
w 1 jest jedno. Opory: 3 przykłady bez oporów, 3 z dwoma, 2 z trzema.
Brak wsparć: 0%; brak oporów: 37,5%. Ruch netto: 6 wzrostowych i 2 spadkowe;
std log-zwrotów min 0,009829 / mediana 0,015082 / max 0,025465.
Nie wykryto grup zbliżonej charakterystyki według jawnego klucza opisowego.
Wszystkie cztery realne przykłady zaczynają się w 2021: to wynik prostego
doboru technicznego z wcześniejszego pilotażu, nie pokrycie całego planu.
Próba nie służy ocenie jakości lub reprezentatywności przyszłego zbioru.

Weryfikację granic przeprowadzono na osobnych fixture przy rzeczywistych
przejściach 2023/2024 i 2024/2025 oraz ostatniej świecy testu. Nie nadawano
oknom dawnego pilotażu sztucznych splitów. Testy obejmują niedobór danych,
lukę, nakładanie, duplikaty między splitami, uszkodzone OHLC, UTC, seedy,
niezatwierdzony profil, nadpisanie i brak częściowej publikacji po awarii.

## 9. Rzeczywiste wyniki kontroli

- Przed zmianami: **199 testów OK**, 0 błędów, 96,785 s.
- Po zmianach: **221 testów OK**, 0 błędów, 107,517 s; 22 nowe testy.
- Istniejący pilotaż: 32 oryginalne PNG odtworzone bajtowo, poprawne CSV/JSON/SHA.
- Etykietowanie 3.4: 32 etykiety, pełna diagnostyka i 32 overlays odtworzone;
  oryginały zachowane bez zmian.
- Dry-run istniejącego downloadera: poprawny plan dwóch archiwów stycznia 2020,
  bez pobierania.
- Zbiorcza kontrola: `results/diagnostics/ds35-check-20261107-a/verification.json`,
  pełny `tests.log`, manifest i hash manifestu. Sprawdzono 156 przypiętych
  lokalnych wejść względem hashy z preflightu i źródłowego pilotażu.

Weryfikowano natywnie na Windows, Python 3.13.15, Matplotlib 3.11.2. Nie badano
pozostałych wersji Pythona deklarowanych przez pakiet. Powtarzalność PNG wymaga
zgodnego renderera, Matplotlib i fontów. SHA chroni integralność, nie stanowi
podpisu ani gwarancji semantycznej jakości etykiet.

## 10. Profile i warunki przed produkcją

Zweryfikowano dwa istniejące profile schematu 2, metodę
`volatility_refinement_v1`, wariant `full`, konfigurację reżimów, symbol,
okres kalibracji wyłącznie train, tożsamość chronologii i hash źródłowego CSV.
Nie zmieniono plików ani statusów:

| Symbol | Identyfikator profilu (początek SHA) | Status | phi / std |
|---|---|---|---|
| BTCUSDT | `d1db93b0929189da` | unapproved | 0,65 / 0,65 |
| ETHUSDT | `9f8f7fb90e4b2e8b` | unapproved | 0,65 / 0,55 |

Pełne identyfikatory, hashe plików, konfiguracje i parametry są w `plan.json`.
Ustawienia integracji używają **wartości profilu**, a nie roboczych domyślnych
parametrów v2. Zachowano istniejącą ochronę `prepare_profiles()`:
produkcja ma `diagnostic=False` i odmawia użycia `unapproved`. Komunikat starego
walidatora o `--diagnostic` zapisano w raporcie maszynowym jako przyczynę
blokady; nie jest zaleceniem użycia takiej flagi do tworzenia właściwego zbioru.

Nowy master seed planu to **2027013501**. Seedy 440 przyszłych przykładów
wyznacza dotychczasowe `example_seed(master_seed, symbol, index)` — SHA-256,
bez zależności od kolejności symboli i liczebności partii. Nie losowano OHLC.
Nie ma kolizji wewnętrznych ani kolizji z **54 lokalnymi manifestami**
obejmującymi **618 unikalnych seedów przykładów**. Wykluczono także seedy
z konfiguracji i audytów profili. To kontrola dostępnej historii lokalnej,
nie nieznanych eksperymentów na innych komputerach. Należy ją powtórzyć
bezpośrednio przed generacją i zachować przypięty plan.

Przed produkcją pozostają:

1. Ocena raportu i ośmiu przykładów przez autora; niezależna kontrola jakości
   referencji S/R pozostaje ograniczeniem z etapu 3.4.
2. **Jawna decyzja autora o zatwierdzeniu obu profili** i wykonanie istniejącej
   procedury ich zatwierdzania. Wskazanie V2-full-refined do dalszych prac
   nie zmieniło technicznego statusu profili.
3. Osobne polecenie autora przygotowania właściwych zbiorów, ponowny preflight,
   produkcyjna generacja 440 syntetyków przez istniejący pipeline z zatwierdzonymi
   profilami, renderowanie/etykietowanie planu i pełny audyt wynikowej partii.
   Obecny CLI celowo nie udostępnia operacji produkcyjnej.

Paczka: `handoff/etap-3-5-cz1-20261107.zip` z inwentarzem SHA-256 i sumą obok.
Zawiera aktualny kod, testy, dokumentację, dwa profile i małą diagnostykę
wraz ze źródłowym pilotażem; nie zawiera pełnych danych rynku, środowiska,
cache ani dużych historycznych audytów. Preflight pełnej historii po
przeniesieniu wymaga lokalnych CSV i historii manifestów; ich brak nie
powinien być zastępowany pobieraniem ani zgadywaniem pojemności.

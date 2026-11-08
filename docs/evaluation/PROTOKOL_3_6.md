# Zamrożony protokół oceny poziomów S/R

Wersja: **sr-eval-v1**, ustalona 2026-11-07, przed pierwszą oceną rzeczywistych
odpowiedzi VLM. SHA-256 kanonicznego zbioru reguł w kodzie:
`dafd622fc17e78fe9e095d0849b4a4ae1f8a748d203a3b8fa48a373e4b3ccf58`.
Każdy wynik zapisuje kopię reguł `protocol.json`, wersję i hash w manifeście.
Zmiany reguł wymagają nowej wersji; nie wolno dopasowywać ich do wyniku testu.

## Przedmiot oceny i dane

Oceniamy odtwarzanie referencji zgodnych z operacyjną definicją S/R na obrazach,
nie rentowność strategii ani prognozę przyszłych cen. Referencje utworzono
algorytmem etykietowania; nie stanowią niezależnej eksperckiej prawdy o rynku.
Nie przedstawiamy tego algorytmu jako konkurenta osiągającego idealny wynik
względem własnych etykiet.

Domyślnym splitem jest `validation` (36 realnych przykładów). `test` (66 realnych)
wymaga jawnego `--split test`. Train nie jest obsługiwanym celem ewaluacji.
W tej iteracji wynik demonstracyjny dotyczy wyłącznie osobnego ręcznego fixture,
nie produkcyjnego validation lub test. Żaden model nie był uruchamiany.

Neutralny plik predykcji JSONL zawiera dokładnie `id` i `response`, oba tekstowe:

```json
{"id":"example_id","response":"{\"supports\":[60123.45],\"resistances\":[62500.50]}"}
```

`response` zachowujemy bez usuwania whitespace, bloków kodu lub komentarzy.
Wynik zawiera `raw_response`, a plik wejściowy jest kopiowany bajtowo do wyniku.
Manifest wejściowy jest oddzielny od predykcji i zawiera `run_id`, `model_id`,
`checkpoint_id`, `variant`, `protocol_version`, `instruction_version`,
`inference`, `prediction_kind`, `dataset_manifest_sha256`, `split`.
Identyfikatory są tekstem, `inference` obiektem ustawień. Dodatkowe metadane są
zachowywane. Warianty modelowe: `base` i `finetuned`; `model_id` identyfikuje
wspólny model bazowy, `checkpoint_id` konkretny checkpoint. Te pola są deklaracją
pochodzenia odpowiedzi; bez adaptera inferencji nie dowodzą użycia wskazanych wag.

Każdy oczekiwany ID musi mieć jedną odpowiedź. Brakujące, nieznane, powtórzone,
pochodzące z innego splitu lub treningu ID blokują publikację całego wyniku.
Niepoprawny zewnętrzny wiersz JSONL również blokuje przebieg. CLI zwraca kod 2
i raportuje listy problemów; katalog kompletnego wyniku nie powstaje.
To inny przypadek niż błędna odpowiedź modelu w poprawnym rekordzie `response`:
taką odpowiedź uwzględniamy w wyniku i statystykach formatu.

Loader kontroluje hashe i inwentarz zbioru. Analitycznie czyta CSV/etykiety
wyłącznie wskazanego splitu; odczyt bajtów pozostałych plików służy SHA-256.
Nie uruchamia generatora, renderera ani pełnego produkcyjnego odtwarzania.
Fingerprint obejmuje manifest zbioru, ID, obrazy, instrukcję, etykiety i OHLC.

## Walidacja odpowiedzi

Wymagamy jednego obiektu JSON o dokładnie kluczach `supports`, `resistances`.
Obie wartości są tablicami 0–3 dodatnich, skończonych liczb JSON. Odrzucamy
stringi cen, NaN/Infinity, null, boole, zera, liczby ujemne, dodatkowe pola,
powtórzone klucze (także równoważne zapisy Unicode), obcy tekst i Markdown.
Zwykłe whitespace dozwolone przez składnię JSON jest poprawne.
`60123.4` i `60123.40` to ta sama cena; format dwóch cyfr nie jest wymogiem
dla predykcji. Odczyt używa `Decimal`, bez pośredniego float.

Nie wyciągamy JSON-a z tekstu i nie naprawiamy odpowiedzi. Cała odpowiedź
niespełniająca schematu jest niepoprawna, nawet gdy fragment da się odczytać.
Zapisujemy pierwszy deterministycznie wykryty błąd i jego przyczynę.
Kategorie: `invalid_json`, `duplicate_key`, `not_object`, `keys`, `not_array`,
`too_many_prices`, `invalid_price`. `valid_json` oznacza spełnienie pełnego
kontraktu odpowiedzi, a nie tylko poprawność składni parsera.

Dla niepoprawnej odpowiedzi: TP=0, FP=0, FN=wszystkie referencyjne poziomy.
Nie wymyślamy FP dla nieodczytanych cen. F1 całego przykładu wynosi 0 również
wtedy, gdy referencja ma obie listy puste. Dlatego micro-F1 nie pokazuje w pełni
błędów formatu; obok niego zawsze raportujemy liczbę i procent poprawnych
odpowiedzi oraz błędy według kategorii.

## ATR i tolerancja

Każda referencja korzysta z dokładnie swoich 120 kolejnych poprawnych świec 4h.
`final_atr()` wywołuje istniejące `labeling.algorithm.true_ranges` i `wilder_atr`:
TR pierwszej świecy to High−Low, potem max(High−Low, |High−poprzednie Close|,
|Low−poprzednie Close|); pierwszy ATR to średnia 14 TR, następne
`(13*ATR_previous+TR)/14`. Bierzemy ostatni ATR. Nie kopiujemy tych wzorów
do drugiej implementacji. Kontekst obliczeń ATR jest taki sam jak etykietowania:
50 cyfr, ROUND_HALF_UP. W produkcyjnych metadanych kontrolujemy zgodność ATR.

Tolerancja `T=k*ATR`: **0.5 główna**, 0.25 i 1.0 pomocnicze. Iloczyn oraz
różnice cen zachowują precyzję potrzebną do porównania granicy; nie zaokrąglamy
predykcji do centów. Dopasowanie jest dozwolone dla `abs(pred−ref) <= T`.
Granica jest włączona. ATR=0 daje T=0 i wyłącznie dokładne dopasowania.

## Optymalne dopasowanie

Wsparcia porównujemy tylko ze wsparciami, opory tylko z oporami. Każdy indeks
może uczestniczyć w najwyżej jednej parze. Rekurencja sprawdza wszystkie
wykonalne częściowe dopasowania (maksymalnie 3×3 na stronę), wybierając kolejno:

1. Maksymalną liczbę par TP.
2. Minimalną sumę bezwzględnych błędów cenowych.
3. Najmniejszą leksykograficznie listę par `(indeks_predykcji, indeks_referencji)`;
   pary są uporządkowane według pierwotnych indeksów predykcji, indeksy od zera.

Dla referencji [100,102], predykcji [101,99] i T=1.5 otrzymujemy 101→102 oraz
99→100, czyli 2 TP. Zachłanne 101→100 pozbawiłoby 99 dopasowania.
Bliskość dokładnej pary nigdy nie zastępuje maksymalizacji liczby trafień.

Duplikaty cen wewnątrz jednej tablicy są rozpoznawane przez równość Decimal,
więc 100 i 100.00 to powtórzenie. Tylko pierwsze wystąpienie jest kandydatem;
każde kolejne liczy się jako FP. Oryginalny tekst i indeksy duplikatów pozostają
w raporcie. Nie usuwamy duplikatów z surowej odpowiedzi. Równa cena po obu
stronach jest oceniana oddzielnie w każdej z tych stron.

## Metryki i puste listy

Na stronę i przykład: TP=liczba par, FP=liczba przewidzianych cen−TP
(w tym duplikaty), FN=liczba referencji−TP. Niepoprawna odpowiedź jest wyjątkiem
opisanym wyżej. Precision=TP/(TP+FP), Recall=TP/(TP+FN),
F1=2TP/(2TP+FP+FN).

**Micro** wyliczamy z sum TP/FP/FN wszystkich przykładów i obu stron.
Osobne agregacje obejmują supports/resistances, BTC/ETH oraz symbol×strona,
dla każdej tolerancji. Zerowy mianownik dowolnego ilorazu oznacza `null`.
W szczególności gdy w całym agregacie TP=FP=FN=0, micro-F1 jest niezdefiniowane.

Nie tworzymy sztucznego TP dla pustych list. Poprawne obie puste listy przy
całkowicie pustej referencji dają pomocniczy F1 przykładu równy 1.
Niepoprawna odpowiedź ma F1 przykładu 0. Inne przypadki korzystają z normalnego
wzoru łączącego strony. Średnia tych wartości jest `mean_example_f1`,
metryką pomocniczą odrębną od micro-F1. Nie jest podstawą głównej oceny.
Ilorazy, agregacja i pomocnicze kwantyle mają stały kontekst Decimal 50 cyfr.

Raport zawiera liczebności poziomów przewidzianych/referencyjnych, duplikaty,
pełne poprawne zestawy (poprawny JSON, FP=FN=0), min/q25/medianę/q75/max F1,
liczby zer i jedynek. `zero_tp_examples` obejmuje także poprawnie puste
referencje; `missed_all_nonempty_reference_examples` zlicza wyłącznie przypadki
z istniejącym poziomem referencyjnym. Osobno podajemy poprawne odpowiedzi
bez żadnego przewidzianego poziomu.

Puste listy raportujemy na stronę i dla całego przykładu, wraz z jawnym
mianownikiem: procent poprawnie pustych **wśród przypadków pustej referencji**.
Gdy takich referencji nie ma, procent jest niezdefiniowany. Procent poprawnych
pełnych zestawów i procent JSON mają mianownik równy liczbie wszystkich
przykładów danej grupy; poprawny JSON nie może być pominięty w tym mianowniku.

## Błąd ceny

Każda trafiona para zachowuje błąd bezwzględny w USDT i błąd/ATR.
MAE to średnia błędów wyłącznie poprawnie dopasowanych par. Podajemy liczbę
par; brak par daje null, nie zero. MAE USDT agregujemy osobno dla BTC/ETH,
także symbol×strona. Nie uśredniamy dolarowych skal BTC i ETH jako głównego
błędu globalnego. Ogólnie porównujemy przede wszystkim MAE/ATR.

Dla ATR=0 błąd USDT jest policzony (trafienie ma wtedy błąd 0),
a znormalizowany błąd jest null z powodem `zero_atr`. Takie pary są wyłączone
z mianownika MAE/ATR i jawnie policzone. Dobry MAE przy niewielu trafieniach
nie oznacza dobrego odtworzenia poziomów; zawsze należy czytać F1 i liczbę par.

## Sparowane porównanie i integralność

Najpierw oceniamy dwa kompletne pliki, następnie porównujemy gotowe wyniki.
Wymagamy identycznego fingerprintu zbioru (w tym tych samych obrazów,
instrukcji, OHLC i referencji), wersji i hasha protokołu, model_id, ustawień
inferencji oraz wersji instrukcji. Run ID muszą być różne. Dla prawdziwych
wyników warianty to base→finetuned. Porównanie technicznych zestawów A/B ma
`prediction_kind=technical_fixture` i nie jest nazwane wynikiem modelu.

Raport porównawczy zawiera oba wyniki, różnice candidate−baseline dla metryk
we wszystkich przekrojach i tolerancjach oraz sparowane różnice F1 przykładów.
Zmiana poprawności JSON jest w punktach procentowych; F1/P/R w skali 0–1.
Niezdefiniowany wynik po którejś stronie daje niezdefiniowaną różnicę.
Różnice MAE mogą dotyczyć różnych zbiorów trafionych par; ich liczebności
pozostają w obu raportach. Nie wykonujemy bootstrapu ani testu statystycznego.
66 wykresów nie stanowi 66 niezależnych sytuacji rynkowych.

Każdy katalog wyników ma pełny manifest SHA-256, hash manifestu, kopię reguł,
surowe predykcje, metadane, referencje w bindingu i kontrolę wejść przed/po.
Wyniki są odtwarzane przed atomową publikacją. Ponowne `verify` przelicza
wyniki z zapisanych referencji i odpowiedzi bez odwołania do dużych danych.
Porównanie zachowuje kompletne kopie obu małych raportów.
Nie nadpisujemy istniejących katalogów i nie modyfikujemy danych źródłowych.
Hashe kontrolują przypadkowe uszkodzenie; nie są podpisem autentyczności.

Nie ma metryk inwestycyjnych, inferencji, adaptera dostawcy, wyboru VLM
ani treningu. Referencje i test są chronione przed automatycznym dostrajaniem.

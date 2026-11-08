# Etap 3.6, część 1 — implementacja i kontrola ewaluatora

Data: 2026-11-07. Wdrożono deterministyczny mechanizm oceny zapisanych surowych
odpowiedzi. **Nie wybrano ani nie uruchomiono VLM; nie wykonywano inferencji,
treningu ani rzeczywistego porównania modelu przed i po dostrojeniu.**
Wyniki demonstracyjne poniżej są wyłącznie testem technicznym ręcznych fixture.

## Implementacja

Nowy pakiet `evaluation/` zawiera:

- `protocol.py`: zamrożone reguły `sr-eval-v1`, wersję, hash, ścisły odczyt JSON
  i serializację Decimal jako liczb JSON bez float.
- `scoring.py`: modele Levels/Reference/Response/Match, walidację odpowiedzi,
  końcowy ATR z istniejącego modułu etykietowania, optymalne dopasowanie
  oraz wynik pojedynczego przykładu.
- `metrics.py`: sumy TP/FP/FN, micro-P/R/F1, pomocniczą średnią F1, błędy cenowe,
  format i rozkłady w przekrojach tolerancja × instrument × strona.
- `inputs.py`: odczyt produkcyjnego formatu zbioru i ręcznych fixture,
  kontrolę integralności, pełnych ID, splitów i manifestów predykcji.
- `pipeline.py`: atomowy zapis raportu, odtworzenie wyniku, sparowane porównanie
  dwóch kompletnych zestawów oraz jego weryfikację.

CLI: `python -m market_levels.cli.evaluate evaluate|compare|verify`;
entry point `market-levels-evaluate`. Dodano wyłącznie ten entry point
do `pyproject.toml`, bez nowych zależności. Nie przebudowano istniejących modułów.

## Tolerancja i parowanie

Główny wynik to **micro-F1 przy 0.5 × końcowy Wilder ATR(14)**. Pomocniczo
liczymy 0.25 i 1.0 × ATR. ATR wylicza się ponownie z dokładnie tych samych
120 świec OHLC, wywołując istniejące `true_ranges` i `wilder_atr`, w tym samym
50-cyfrowym kontekście Decimal. Nie dodano drugiej definicji ATR.
Mnożenie tolerancji i różnice cen nie są zaokrąglane do centów. Granica
`abs(pred-ref) <= k*ATR` jest włączona. ATR=0 dopuszcza wyłącznie równość ceny.

Wsparcia i opory są dopasowywane oddzielnie, jeden indeks najwyżej raz.
Wyczerpujący przegląd małych dopasowań wybiera maksymalną liczbę TP,
następnie najmniejszy łączny błąd i leksykograficznie najmniejsze pary indeksów
predykcji/referencji. Brak SciPy i zachłannego wyboru pierwszej pary.
Wymagany kontrprzykład [101,99] względem [100,102], T=1.5, daje **2 TP**.
Testy sprawdzają też pierwszeństwo maksymalnej liczby par przed zerowym błędem
pojedynczej pary i deterministyczne remisy.

Powtórzona cena w jednej liście nie tworzy nowego rozpoznanego poziomu:
tylko pierwsza jest dopuszczana do dopasowania, a każda dodatkowa jest FP.
Równość Decimal obejmuje np. 100 i 100.00. Oryginalny tekst i indeksy powtórzeń
są zachowane; nie naprawiamy odpowiedzi.

## Wyniki liczbowe i konwencje

TP to liczba par, FP to liczba przewidzianych poziomów bez pary (w tym duplikaty),
FN to referencje bez pary. Micro-P/R/F1 liczymy z sum liczników całego zbioru,
nie jako średnią F1 przykładów. Oddzielne wyniki dotyczą BTC, ETH, supports,
resistances oraz symbol×strona dla wszystkich trzech tolerancji.

Poprawny kontrakt to obiekt o dokładnie dwóch tablicach `supports` i
`resistances`, po 0–3 skończone dodatnie liczby JSON. Decimal zachowuje precyzję;
nie wymagamy dwóch cyfr w zapisie predykcji. Tekst, Markdown, stringi cen,
null/boole/NaN/Infinity, dodatkowe lub powtórzone klucze są odrzucane.
Surowa odpowiedź jest kopiowana bez zmian, a przyczyna błędu zapisana.

Niepoprawna odpowiedź daje TP=FP=0, FN=wszystkie referencje i F1 przykładu=0,
także dla pustej referencji. Nie wymyślamy FP. Obowiązkowo podajemy procent
odpowiedzi spełniających cały format, bo micro-F1 nie odzwierciedla wszystkich
błędów formatu dla pustych etykiet.

Poprawnie puste odpowiedzi i referencje nie dają sztucznych TP; pomocniczy
F1 takiego przykładu wynosi 1. Jeśli całe sumy TP=FP=FN=0, micro-F1 jest null.
Osobno raportujemy poprawne puste strony i przykłady, mianowniki statystyk,
pełne zestawy, brak jakiegokolwiek trafienia i rozkład F1 między wykresami.

MAE dotyczy wyłącznie dopasowanych par, z jawną liczbą par. Brak dopasowań daje
null, nie zero. MAE USDT jest oddzielnie po BTC/ETH; ogólną miarą błędu jest
MAE/ATR. Parę z ATR=0 wyłączamy tylko z normalizacji, z podanym powodem
`zero_atr`. Małe MAE kilku trafień nie zastępuje F1 obejmującego pominięcia.

## Próba techniczna na ręcznych predykcjach

Źródło: `tests/fixtures/evaluation_v1`. Jest 12 ręcznych przypadków validation
oraz osobne rekordy train/test do kontroli pomylenia ID. To sztuczne OHLC
i referencje, nie produkcyjne wykresy testowe. Stałe świece mają ATR=3
lub ATR=0. Nie uzyskano referencji przez ocenę algorytmu na własnych etykietach.

Zestaw A obejmuje dokładne trafienia, granicę i punkt poza tolerancją,
pominięcia, dodatkowe ceny, powtórzenie, pomylenie strony, puste listy,
niepoprawny JSON i Markdown, przypadek greedy oraz ATR=0.
Ręcznie policzone oczekiwania przechowują README fixture i `expected-main.json`.

**Poniższa tabela opisuje wyłącznie test implementacji, nie wynik modelu AI.**

| Tolerancja | TP | FP | FN | Micro-F1 zestawu A | Średni F1 przykładu |
|---|---:|---:|---:|---:|---:|
| 0.25 ATR | 6 | 7 | 7 | 0,461538 | 0,416667 |
| 0.5 ATR | 9 | 4 | 4 | 0,692308 | 0,583333 |
| 1.0 ATR | 10 | 3 | 3 | 0,769231 | 0,666667 |

Dla 0.5 ATR micro-P=micro-R=micro-F1=9/13, a średni F1=7/12.
10/12 odpowiedzi spełnia format (83,333333%); są dwa błędy formatu i jeden
duplikat ceny. MAE USDT: BTC 0 na 3 parach, ETH 3.5/6 na 6 parach.
Globalne MAE/ATR obejmuje 8 par; jedną z ATR=0 jawnie wykluczono.

Zestaw B zawiera ręcznie przepisane dokładne odpowiedzi, jako kontrolę
oczekiwanego wyniku 1 i mechanizmu różnicowania dwóch raportów. Nie nazywamy
go wynikiem modelu dostrojonego. Oba manifesty mają
`prediction_kind=technical_fixture`, `variant=technical_fixture`,
model_id `manual-fixtures-no-vlm`. Sparowana różnica micro-F1 B−A przy 0.5 ATR
wynosi 4/13 (około 0,307692), a poprawność formatu rośnie o 16,666667 p.p.
Nie jest to dowód poprawy któregokolwiek modelu.

Zapisane wyniki:

- `results/diagnostics/ev36-20261107-a/manual-a/`
- `results/diagnostics/ev36-20261107-a/manual-b/`
- `results/diagnostics/ev36-20261107-a/comparison/`
- `results/diagnostics/ev36-20261107-a/checks/`

## Przyszłe porównanie modelu i ochrona testu

Oba zestawy rzeczywistych odpowiedzi będą wymagać identycznych ID, obrazów,
instrukcji, referencji, protokołu, model_id i ustawień inferencji. Checkpoint
i wariant base/finetuned zapisuje oddzielny manifest. Porównanie jest sparowane,
pokazuje oba wyniki, różnice wszystkich metryk/przekrojów i różnice F1 każdego
wykresu. Niezdefiniowane metryki nie są zastępowane zerami.

Nie ma bootstrapu ani założenia niezależności 66 obserwacji. BTC/ETH z tych
samych okresów oraz nakładające się okna są powiązane. Ewentualna przyszła
analiza niepewności musi uwzględniać tę strukturę.

CLI domyślnie wybiera validation; test wymaga jawnego wskazania.
Sprawdzono read-only adapter na **36 produkcyjnych referencjach validation**:
poprawne JSONL, ID, obrazy/CSV/etykiety, ich hashe i ATR zgodny z metadanymi.
Nie oceniano dla nich żadnych predykcji. Nie tworzono sztucznych odpowiedzi
dla 66 rzeczywistych przykładów testowych i nie analizowano ich OHLC.
Odczyt bajtów całego zbioru do SHA jest kontrolą integralności, nie ewaluacją.

## Wykonane testy i integralność

Końcowy pełny przebieg: **277 zaliczonych, 0 pominiętych, 0 błędów**,
124,393 s; log `checks/tests-full.log`. To 233 dotychczasowe i 44 nowe testy
(28 jednostkowych, 16 integracyjnych). Osobno uruchomiono oba nowe moduły.
W pierwszej próbie integracyjnej wystąpił WinError 32 podczas sprzątania
katalogu testowego na Windows. Użyto istniejącego wspólnego mechanizmu
sprzątania z ponowieniami; po poprawce testów wszystkie kontrole przeszły.
Nie zmieniano z tego powodu kodu źródłowych danych lub wspólnego stagingu.

Nowe testy obejmują wszystkie wymagane kategorie: format i typy JSON,
duplikaty kluczy/cen, poprawność trzech tolerancji i granic, ATR=0, optymalne
parowanie z remisami, strony, puste listy, FP/FN, micro vs średni F1, MAE/null,
niepełne/nieznane/powtórzone ID, zmieszane splity, powtarzalność, niezmienność
wejść, odmowę nadpisania, awarię zapisu, ponowne hashowanie błędnych wyników
i sparowane porównanie. Oczekiwania fixture są ręczne, nie wyliczane przez
tę samą funkcję, którą testujemy.

Środowisko: Windows, CPython 3.13.15, biblioteka standardowa dla ewaluacji.
Nie dodano bibliotek modeli, SciPy ani frameworków. Testy pozostałych modułów
wykorzystały istniejące zależności i małe sztuczne fixture zgodnie z projektem.

Sprawdzono SHA-256 **3245 chronionych plików** przed i po pracy: cały produkcyjny
zbiór, nowe approved, dotychczasowe moduły generatora/etykietowania/renderera
i `configs/experiment.json`. Pliki i definicje pozostają bez zmian.
Nowy ewaluator jedynie importuje kod ATR. Manifesty i kontrola wejść chronią
przypadkowe zmiany; nie są podpisem autentyczności danych ani wag modelu.

## Stan końcowy

Protokół jest opisany w [PROTOKOL_3_6.md](PROTOKOL_3_6.md), a rzeczywiste
polecenia w [instrukcji PowerShell](INSTRUKCJA_POWERSHELL.md).
Handoff: `handoff/etap-3-6-cz1-20261107.zip`, z inwentarzem i sumą SHA-256.
Zawiera aktualny kod, konfigurację, testy, ręczne fixture, dokumentację
i wyniki próby. Nie zawiera produkcyjnych 800 wykresów, środowiska ani cache.

Wynik tego etapu to sprawdzona implementacja i jawne konwencje oceny.
Nie ma jeszcze wyników eksperymentu z rzeczywistym VLM, metryk finansowych,
wyboru modelu ani treningu. Kolejne użycie do rzeczywistych odpowiedzi powinno
nastąpić po niezależnym audycie protokołu i raportu.

# Etap 4.6B — końcowa ewaluacja testowa Qwen3-VL

Data dokumentacji: 2026-11-12 (Europe/Warsaw). Status: końcowa ewaluacja
zakończona; raport opracowany offline na podstawie istniejących artefaktów.
W tabelach zastosowano kropkę dziesiętną i zaokrąglenie do 10 miejsc;
załączniki JSON zachowują precyzję ewaluatora.

## 1. Cel i zakres

Przedmiotem badania jest odtwarzanie algorytmicznie wyznaczonych poziomów
wsparcia i oporu na podstawie obrazu wykresu. Jednorazowo porównano bazowy
Qwen3-VL-2B-Instruct w NF4 z tym samym modelem i adapterem wybranym przed
testem. Ocena obejmuje 66 zamrożonych wykresów, główne micro-F1 przy 0.5 ATR
oraz pomocnicze tolerancje 0.25 i 1.0 ATR.

Etap dokumentacyjny obejmował odczyt i kontrolę sum plików, odtworzenie ocen,
agregację przekrojów oraz historyczną diagnostykę zdejmowania zewnętrznego
Markdown. Nie uruchomiono Qwen, treningu, nowej inferencji, CUDA ani nowych
eksperymentów. Oficjalne pliki wynikowe pozostały niezmienione.

## 2. Zamrożenie konfiguracji

Wybór z 2026-11-11 utrwala `FINAL_MODEL_SELECTION.json`. Wybrano adapter
`results/vlm44-part2-17554-5354/adapter`, lokalny krok 175 dodatkowego
eksperymentu po głównych 350 aktualizacjach. Dodatkowy eksperyment miał nowy
AdamW, scheduler i RNG; nie był prostym przedłużeniem jednego harmonogramu.
Test nie uczestniczył w wyborze checkpointu. Nie dokonano ponownego wyboru
po poznaniu wyników testowych.

| Element | Wartość zamrożona |
|---|---|
| Model bazowy | `Qwen/Qwen3-VL-2B-Instruct` |
| Rewizja | `89644892e4d85e24eaac8bacfd4f463576704203` |
| SHA-256 wag adaptera | `20cbbb8e39ca636108d9533e8e8cc4543371b48eb322fff97999a9b8454ebdf6` |
| SHA-256 manifestu adaptera | `cc11b18830876107d075b560d8abe37b718c46f22725e2d0cbf430b73bae1c83` |
| SHA-256 pliku wyboru | `287e45bd688de30293b129a536086133be380116202ca74a0fe69c6ab9bd921e` |
| SHA-256 efektywnej konfiguracji treningu | `b5c69a9a4820b892af669feca6b6f1090b431c8d8bd2861829148f924896f2ef` |
| Protokół / instrukcja | `sr-eval-v1` / `pl-sr-v1` |

Hash pliku wyboru jest zgodny z planem zapisanym w sesji testowej i raportem
4.6A. Historyczne pole `test_evaluation_run=false` w pliku wyboru opisuje
moment zamrożenia w etapie 4.5; zachowano je jako dowód pierwotnej decyzji.
Bieżący status zakończenia testu dokumentuje niniejszy raport.

## 3. Charakterystyka zbioru testowego

Źródło: `data/datasets/ds35-800-20261107-a`. Zbiór produkcyjny ma
698 train, 36 validation i 66 test. Test zawiera wyłącznie realne okna
Binance spot, po 33 BTCUSDT i ETHUSDT; syntetyki występują jedynie w train.
Każdy obraz ma 1024×768 pikseli i przedstawia 120 świec 4h bez linii
referencyjnych. Zatwierdzony podział `chronological_v1` obejmuje train
2020–2023, validation 2024 i test 2025–2026-10. Metadane faktycznie
wybranych testowych okien potwierdzają zakres od 2025-01-01 00:00 do
2026-10-22 20:00 UTC. Okna validation/test mają krok 120 świec i nie
przekraczają granic splitów; test jest prefiksem kandydatów.

| Instrument | Wykresy | Wsparcia referencyjne | Opory referencyjne | Poziomy razem |
|---|---|---|---|---|
| BTCUSDT | 33 | 70 | 60 | 130 |
| ETHUSDT | 33 | 69 | 58 | 127 |
| Razem | 66 | 139 | 118 | 257 |

Referencje wytworzono metodą `sr-extreme-first-1.0.0`: ścisłe ekstrema 3+3,
Wilder ATR(14), grupowanie w rozpiętości 0.5 końcowego ATR, minimum dwie
reakcje oddalone o co najmniej pięć świec, podział względem ostatniego Close
i maksymalnie trzy poziomy na stronę. Etykiety reprezentują operacyjną definicję
S/R, nie niezależny konsensus ekspertów ani obiektywną prawdę rynkową.

## 4. Warunki inferencji

Oba warianty wykonano w osobnych wywołaniach procesu Pythona, kolejno baza,
a następnie model dostrojony. Potwierdzają to dwa logi inferencji z kodem 0,
osobne zdarzenia ładowania i zakończenia oraz sposób uruchomienia w
`scripts/run_vlm_final_test.ps1`. Baza została wznowiona po blokadzie zasobów
przy `committed_answers=0`. Nie ma ponownego generowania zatwierdzonych ID.
Nie zachowano niezależnego rejestru PID; wniosek o oddzielnych procesach opiera
się na zapisanych wykonaniach i runnerze.

| Parametr | Oba warianty |
|---|---|
| Kwantyzacja | NF4, double quantization |
| Typ obliczeń / wizja | BF16 / BF16 |
| Inne zamrożone części niekwantyzowane | przygotowanie PEFT, FP32 |
| Attention / urządzenie | SDPA / cuda:0, bez CPU/disk offload |
| Obraz / budżet / minimum | 1024×768 / 786432 / 65536 pikseli |
| Tokeny obrazu / wejścia | 768 / 845 dla każdego z 132 rekordów |
| Generowanie | `do_sample=false`, `num_beams=1`, `max_new_tokens=256`, `use_cache=true` |
| Seed inferencji | 20261109 |
| Instrukcja | pl-sr-v1; bez few-shot |
| Dekodowanie | skip_special_tokens=True, clean_up_tokenization_spaces=False |

Sprawdzono identyczność zapisanych konfiguracji generowania, procesora,
tokenizera, środowiska oraz kolejności ID. Przy `do_sample=false` zapisane
domyślne temperature=0.7, top_k=20 i top_p=0.8 nie oznaczają próbkowania.
Model otrzymywał obraz i instrukcję; ID, symbol, OHLC i etykiety nie stanowiły
dodatkowego promptu. Inferencja nie parsowała referencji przed ukończeniem
obu wariantów.

Środowisko historyczne: Windows 10/19045, Python 3.12.12, RTX 3060 Ti
8192 MiB; torch 2.10.0+cu128, torchvision 0.25.0+cu128, transformers 5.3.0,
peft 0.18.1, bitsandbytes 0.49.2, accelerate 1.12.0, pillow 12.1.1.
Pełny wykaz wersji znajduje się w `final46b/execution_audit.json`.

Finetuned ładował adapter jako `is_trainable=False`, bez merge. Zapisana
kontrola potwierdza dokładną równość wszystkich 112 tensorów z eksportem.
Kod wykonania wymusza `requires_grad=False`, brak gradientów, `eval()`
i `torch.inference_mode()`; nie tworzy optymalizatora. Oba `result.json`
i zdarzenia ładowania potwierdzają `no_optimizer_updates=true`.

Poniższe maksima dotyczą zapisanych pomiarów **generowania odpowiedzi**;
nie obejmują całego czasu ładowania modelu.

| Wariant | Peak próbek VRAM [MiB] | Peak próbek RSS [MiB] | Peak allocated [MiB] | Peak reserved [MiB] |
|---|---|---|---|---|
| base-nf4 | 5633.00 | 1863.55 | 3074.50 | 5090.00 |
| finetuned-nf4 | 5603.00 | 1882.73 | 3078.93 | 5066.00 |

Próbkowanie może pominąć krótkie piki. RSS nie jest całkowitym RAM systemu;
reserved to rezerwacja alokatora, której nie sumuje się z globalnym VRAM.
Nie wykonano nowych pomiarów sprzętowych.

## 5. Kontrola integralności i audyt wykonania

Sesja: `adc19862-27f6-4327-a478-1554818da3f3`; dwa różne run_id z sufiksami
`-base-nf4` i `-finetuned-nf4`. Oba warianty zawierają 66 rekordów i 66
surowych odpowiedzi. Zweryfikowano manifesty, łańcuchy hashy rekordów,
zgodność `predictions.jsonl` z rekordami oraz zgodność wejść ocen z surowymi
przebiegami. Brakujące, powtórzone i obce ID nie występują.

Ponowne wywołanie wyłącznie kontrolnego `verify_pair` offline zakończyło się
poprawnie. `read_evaluation` odtworzył dokładnie `per_example.jsonl`,
`summary.json` i raporty tekstowe obu wariantów, a `read_comparison` sprawdził
porównanie wraz z kopiami obu ocen. Sprawdzono także historyczną validation,
wzory metryk i sumy przekrojów. Oficjalny fingerprint referencji testowych:
`a24a474a7c48d15ef14f1db697ff73318694eaf5f1a57fc6681abf8154e2fc53`.
Jest wspólny dla obu ocen. Fingerprint wejść obrazowych inferencji:
`086698fa04fff5b8466e1cfc2f8e4986dced0dc18692722d23ad86085988a06d`.
Są to dwa różne zakresy identyfikacji.

Kontrola przed/po dokumentacji objęła **4039 plików**,
w tym wszystkie **3212 plików datasetu**: brak zmian, usunięć i dodanych
plików w kontrolowanych źródłach. Sprawdzono aktualne bajty bazy i procesora
według 11 zapisanych pozycji tożsamości, wybrany adapter, efektywną konfigurację,
manifesty, protokół, kod sesji i wybór modelu. `final46b/SOURCES.json` określa
dokładny zakres i SHA-256 każdego chronionego pliku. Wynik nie jest podpisem
autentyczności ani dowodem nieistnienia zewnętrznych uruchomień.

Audyt zachowuje wszystkie 20 dostępnych rekordów zakończenia 4.6.
Poniżej podano identyfikatory plików `results/vlm46-<tryb>-<ID>.exit.json`;
pełne ścieżki, czasy UTC i końcówki konsoli są w `execution_audit.json`.

| Tryb | ID logu | Kod |
|---|---|---|
| dry-run | a7b7adb91edf444a8e42acb599037701 | 0 |
| infer | 08c8c24cb19b4aafb9cc541fbcfc8d70 | 1 |
| dry-run | b0c857d2db1a4fdda6ed1e5ebd93873e | 1 |
| dry-run | a544bff601714d3ba593f8cf2ce1c9da | 0 |
| prepare | eb58b5ea9e854d61a887169f0b6870b3 | 0 |
| infer | 1bc0fff3937f4b2baca99e02d57cf7c1 | 1 |
| verify-variant | df9aa09126c74b599344ccd5a5c31ebc | 1 |
| infer | 3e44cc192ee74464ad09c30142ef86d3 | 1 |
| verify-pair | 4dbc764686a040c1a527fac34d350fad | 1 |
| score-pair | 55a7b7225f3540e290cffb40f56380c3 | 1 |
| infer | 4a63600caf6542f4900ed7789a1c38a7 | 1 |
| verify-variant | 881a5f7456d346c19cb0ce8d673247a9 | 1 |
| infer | 3f8c7eccf39d45c2ad69ae0fd5610c79 | 0 |
| verify-variant | 08f07f7ef1984756b4c34bab9d716b42 | 0 |
| infer | 5d0e01799f084b2a8e5096abfaec355a | 0 |
| verify-pair | 31ef83d560cc4192b1956e4948f8925c | 0 |
| infer | a60cfbdeb20b4caaa57ad599534e2468 | 1 |
| verify-pair | 9488368e1ddb4ab49038a828cc6ee374 | 0 |
| score-pair | def4df1e0db14c1a89622fe4c423ff04 | 0 |

Niezerowe kody obejmują brak jawnej zgody, niedozwolony dataset, zajętość GPU
453>450 MiB, próby kontroli/oceny i uruchomienia wariantu dostrojonego przed
powstaniem manifestu bazy oraz próbę utworzenia istniejącego wariantu bez resume.
Pierwsza baza zakończyła się przed generowaniem; wznowienie z zera ukończyło 66
odpowiedzi. Końcowe `verify-pair` (dwukrotnie) i `score-pair` mają kod 0;
istnieją trzy kompletne oficjalne raporty. Baza zakończyła generowanie
o 21:02:38 UTC, finetuned rozpoczął o 21:06:56 i zakończył o 21:12:55 UTC.
Ocenę zakończono o 21:14:15 UTC, po obu przebiegach.

Odmowa `Variant already complete; rerun/resume is forbidden` z kodem 1
po zakończeniu inferencji była **oczekiwanym działaniem zabezpieczenia**
jednorazowości. Nie stanowi niekompletności wyników ani powodu do powtarzania
inferencji. W obu plikach events zapisano po 14 ostrzeżeń DeprecationWarning
dotyczących `torch.jit.script_method`; zachowano także oryginalne logi konsoli
z komunikatami bibliotek i miejscowymi zniekształceniami kodowania tekstu.

## 6. Oficjalne wyniki

Micro-precision=TP/(TP+FP), micro-recall=TP/(TP+FN),
micro-F1=2TP/(2TP+FP+FN). Liczności sumuje się po stronach i wykresach.
Wsparcia i opory dopasowuje się osobno, jeden do jednego, przy
|pred−ref|≤k·ATR; maksymalizuje się liczbę TP, następnie minimalizuje błąd,
a remisy rozstrzyga leksykograficznie indeksami. Nie zmieniono progów ani
metody. Wartość `null` oznacza niezdefiniowany iloraz, a nie zero.

| Wariant | ATR | TP | FP | FN | Precision | Recall | Micro-F1 | JSON | MAE/ATR |
|---|---|---|---|---|---|---|---|---|---|
| base-nf4 | 0.25 | 0 | 0 | 257 | null | 0.0000000000 | 0.0000000000 | 0/66 | null |
| base-nf4 | 0.5 | 0 | 0 | 257 | null | 0.0000000000 | 0.0000000000 | 0/66 | null |
| base-nf4 | 1.0 | 0 | 0 | 257 | null | 0.0000000000 | 0.0000000000 | 0/66 | null |
| finetuned-nf4 | 0.25 | 60 | 217 | 197 | 0.2166064982 | 0.2334630350 | 0.2247191011 | 66/66 | 0.1257876090 |
| finetuned-nf4 | 0.5 | 109 | 168 | 148 | 0.3935018051 | 0.4241245136 | 0.4082397004 | 66/66 | 0.2402191219 |
| finetuned-nf4 | 1.0 | 159 | 118 | 98 | 0.5740072202 | 0.6186770428 | 0.5955056180 | 66/66 | 0.4199891073 |

Wszystkie 66 odpowiedzi bazowych narusza ścisły kontrakt JSON przez zewnętrzne
ogrodzenie Markdown (`invalid_json: 66`). Protokół przypisuje takim odpowiedziom
TP=FP=0 i FN równe wszystkim 257 referencjom. Oficjalnie liczba odczytanych
poziomów wynosi 0; precision i MAE są niezdefiniowane. Nie oznacza to braku
cen w surowym tekście. F1=0 jest wynikiem całego zadania wraz z formatem.

Model dostrojony zwrócił 66/66 odpowiedzi spełniających pełny schemat, 277
poziomów wobec 257 referencji i zero duplikatów. Przy 0.5 ATR uzyskał 109 TP,
168 FP i 148 FN. MAE/ATR=0.2402191219 dotyczy wyłącznie 109 dopasowanych
par (109 z poprawną normalizacją; brak par wyłączonych przez ATR=0).
Brak pełnych zestawów: 0/66; bez TP pozostaje 9/66 wykresów.
Przy 0.25 ATR pełnych zestawów jest 0/66, bez TP 27/66; przy 1.0 ATR
odpowiednio 5/66 i 4/66. Wzrost F1 z tolerancją nie jest poprawą samych cen.

## 7. Analiza diagnostyczna modelu bazowego

**Poniższa tabela jest analizą diagnostyczną, odrębną od oficjalnego testu.**
Zastosowano istniejącą funkcję `inference.domain.price_diagnostics.unwrap_fence`,
realizującą historyczną regułę usuwania wyłącznie zewnętrznego ogrodzenia
Markdown. Reguła pochodzi z analiz etapów 4.1–4.2 i była udokumentowana
przed testem. Wszystkie 66 odpowiedzi miały zewnętrzne znaczniki otwierające
<code>```json</code> i zamykające <code>```</code>; po ich zdjęciu wszystkie spełniły ścisły schemat.
Nie zmieniano cen, list, kolejności, liczby poziomów ani innych fragmentów tekstu.

Wynik przeliczono offline z zapisanych referencji i odpowiedzi przez te same
`parse_response`, `score_example` i `aggregate` protokołu sr-eval-v1.
Nie dodano reguł naprawy ani filtrów. Pliki `diagnostic_base_*` przechowują
przekształcone teksty, wyniki jednostkowe i agregaty, bez nadpisania oryginałów.

| Analiza diagnostyczna: ATR | TP | FP | FN | Precision | Recall | F1 | MAE/ATR |
|---|---|---|---|---|---|---|---|
| 0.25 | 48 | 348 | 209 | 0.1212121212 | 0.1867704280 | 0.1470137825 | 0.1282157478 |
| 0.5 | 73 | 323 | 184 | 0.1843434343 | 0.2840466926 | 0.2235834609 | 0.2110809815 |
| 1.0 | 108 | 288 | 149 | 0.2727272727 | 0.4202334630 | 0.3307810107 | 0.3860719650 |

Potwierdzono wstępne niezależne przeliczenie: F1 0.1470137825, 0.2235834609
i 0.3307810107. Przy 0.5 ATR baza diagnostycznie ma 396 przewidzianych
poziomów, 257 referencji oraz TP/FP/FN=73/323/184. Liczba 396=66×6 wskazuje
na maksymalną liczbę poziomów w każdym odczytanym zestawie. Te wartości
nie zastępują oficjalnego F1=0 i nie uczestniczą w wyborze modelu.

## 8. Porównanie modelu bazowego i dostrojonego

Oficjalne sparowane porównanie obejmuje identyczny fingerprint referencji,
model bazowy, rewizję, instrukcję i ustawienia inferencji. Poniższe różnice
candidate−baseline odczytano z odtworzonego `comparison.json`.

| ATR | ΔTP | ΔFP | ΔFN | ΔPrecision | ΔRecall | ΔF1 | ΔJSON [p.p.] |
|---|---|---|---|---|---|---|---|
| 0.25 | 60 | 217 | -60 | null | 0.2334630350 | 0.2247191011 | 100 |
| 0.5 | 109 | 168 | -109 | null | 0.4241245136 | 0.4082397004 | 100 |
| 1.0 | 159 | 118 | -159 | null | 0.6186770428 | 0.5955056180 | 100 |

Oficjalny przyrost F1 przy 0.5 ATR wynosi 0.4082397004, a poprawności JSON
100 punktów procentowych. Wzrost oficjalnego FP z 0 do 168 nie oznacza
pogorszenia lokalizacji: baza z błędnym formatem nie dostarczała ewaluatorowi
odczytanych predykcji. Różnica precision jest niezdefiniowana, ponieważ
bazowe precision ma zerowy mianownik. Na poziomie wykresów F1 wzrosło
w 57 przypadkach, pozostało równe w 9, nie spadło w żadnym.

Pomocnicze zestawienie lokalizacji po zdjęciu Markdown z bazy wskazuje
F1 0.2235834609 wobec oficjalnego 0.4082397004 finetuned, różnicę
0.1846562394,
TP 73→109, FP 323→168 i FN 184→148. Stanowi to opisową przesłankę poprawy
zgodności poziomów poza samym formatem. Porównanie korzysta z różnych
warunków przetwarzania odpowiedzi, dlatego zachowuje status diagnostyczny;
bez ablacji nie rozdziela przyczyn poprawy.

## 9. Porównanie validation i test

Wybrany model i próg 0.5 ATR pozostają te same; porównywane zbiory mają
różne liczebności i okresy, dlatego nie jest to porównanie sparowane.

| Split | Okres | Wykresy | TP/FP/FN | Precision | Recall | F1 | JSON | MAE/ATR |
|---|---|---|---|---|---|---|---|---|
| Validation | 2024 | 36 | 70/82/77 | 0.4605263158 | 0.4761904762 | 0.4682274247 | 36/36 | 0.2212751625 |
| Test | 2025–2026-10 | 66 | 109/168/148 | 0.3935018051 | 0.4241245136 | 0.4082397004 | 66/66 | 0.2402191219 |

Spadek F1 wynosi 0.0599877244, czyli około 0.059988
(około 6.00 punktów procentowych skali F1). Pomocniczo F1 przy 0.25 ATR
zmienia się 0.2876254181→0.2247191011, a przy 1.0 ATR
0.6688963211→0.5955056180. Zachowana poprawność JSON przy niższych P/R
wskazuje na ograniczenie zgodności lokalizacji i liczby poziomów w późniejszym
okresie, a nie na ponowne załamanie formatu odpowiedzi.

Możliwe wyjaśnienia obejmują zmianę warunków rynkowych, skali cen,
charakterystyk okien i składu referencji oraz ograniczoną reprezentatywność
train/validation. Wielokrotna analiza 36 validation i decyzja o dodatkowej
epoce po obejrzeniu walidacji mogły sprzyjać dopasowaniu wyboru do tego zbioru.
Sam spadek nie stanowi dowodu przeuczenia. Nie wykonano testu istotności,
bootstrapu ani przedziałów ufności; nie deklaruje się istotności statystycznej.

## 10. Analiza jakości i błędów

Poniższe przekroje przedstawiają model dostrojony przy głównym 0.5 ATR.
W pełnym `final46b/metrics.csv` zapisano oba modele, diagnostykę oraz wszystkie
przekroje dla trzech tolerancji. Oficjalna baza ma F1=0 w każdym z tych
przekrojów wskutek błędnego formatu wszystkich odpowiedzi.

| Przekrój | N | TP | FP | FN | Precision | Recall | F1 | MAE/ATR |
|---|---|---|---|---|---|---|---|---|
| BTCUSDT | 33 | 43 | 94 | 87 | 0.3138686131 | 0.3307692308 | 0.3220973783 | 0.2598578932 |
| ETHUSDT | 33 | 66 | 74 | 61 | 0.4714285714 | 0.5196850394 | 0.4943820225 | 0.2274241648 |
| supports | 66 | 65 | 91 | 74 | 0.4166666667 | 0.4676258993 | 0.4406779661 | 0.2448074331 |
| resistances | 66 | 44 | 77 | 74 | 0.3636363636 | 0.3728813559 | 0.3682008368 | 0.2334409349 |
| BTCUSDT/supports | 33 | 28 | 53 | 42 | 0.3456790123 | 0.4000000000 | 0.3708609272 | 0.2520590681 |
| BTCUSDT/resistances | 33 | 15 | 41 | 45 | 0.2678571429 | 0.2500000000 | 0.2586206897 | 0.2744157000 |
| ETHUSDT/supports | 33 | 37 | 38 | 32 | 0.4933333333 | 0.5362318841 | 0.5138888889 | 0.2393197093 |
| ETHUSDT/resistances | 33 | 29 | 36 | 29 | 0.4461538462 | 0.5000000000 | 0.4715447154 | 0.2122470908 |

BTCUSDT uzyskuje F1=0.3220973783 wobec ETHUSDT=0.4943820225.
Wsparcia (0.4406779661) są odtwarzane skuteczniej niż opory (0.3682008368),
a najniższe F1 w kombinacjach instrument×strona mają opory BTC
(0.2586206897). W BTC bez TP pozostaje 7/33 wykresów, w ETH 2/33.
MAE dopasowanych par w USDT wynosi 293.2881395349 dla BTC (43 pary)
i 12.3077272727 dla ETH (66 par); nie należy uśredniać tych skal dolarowych
jako głównego globalnego błędu. Porównywalniejszy MAE/ATR wynosi odpowiednio
0.2598578932 i 0.2274241648.

Poziomy referencyjne to 139 wsparć i 118 oporów; model zwrócił 156 i 121.
Poprawnie puste wsparcia występują w 12/14 przypadków pustej referencji
(85.71%), a opory w 7/18 (38.89%). Mianowniki obejmują wyłącznie puste
referencje danej strony. Nie ma referencji pustych po obu stronach ani
poprawnych odpowiedzi modelu pustych po obu stronach. Medianowe F1 wykresu
wynosi 0.4, kwartyle 0.25 i 0.5928571429, maksimum 0.8571428571;
średnie F1 wykresów 0.4048428003 jest odrębne od głównego micro-F1.

Trzy poniższe przypadki wskazał autor jako błędy skali; nie stanowią losowej
próby ani rankingu wszystkich błędów. Zachowano oryginalne ceny, bez mnożenia
przez dziesięć i bez dodatkowego przeliczania jakości po korekcie.

| ID (BTCUSDT) | Predykcja [USDT] | Referencja [USDT] | TP/FP/FN (0.5 ATR) |
|---|---|---|---|
| `bef2f03dc933f5e4e8ca151f` | supports: [9650.00, 9350.00, 9250.00]; resistances: [] | supports: [97371.00, 98976.91, 95940.00]; resistances: [] | 0/3/3 |
| `9ae321c8cccbc677d118c424` | supports: [8650.00, 8750.00, 8550.00]; resistances: [8950.00, 9050.00, 9100.00] | supports: [86510.95, 85230.32]; resistances: [89477.61, 90530.32, 88274.17] | 0/6/5 |
| `ca556edc7c6210775a96e28f` | supports: [7590.00, 7640.00, 7680.00]; resistances: [8000.00, 8100.00] | supports: [76155.29, 76442.00]; resistances: [79250.00, 79825.00, 77632.58] | 0/5/5 |

Predykcje są około dziesięciokrotnie niższe od referencji. Wszystkie trzy
odpowiedzi są poprawnym JSON, ale nie mają TP także przy 1.0 ATR.
Łącznie dają 14 FP i 13 FN przy głównym progu. Jest to zgodne z hipotezą
błędu odczytu osi lub pominięcia cyfry w generowaniu, lecz same artefakty
nie pozwalają rozstrzygnąć mechanizmu. Poprawny format nie gwarantuje
poprawności skali ceny.

FP i FN nie są rozłącznymi przyczynami błędu: przesunięta cena może jednocześnie
pozostać niedopasowaną predykcją i pozostawić referencję bez trafienia.
Nie każde FP oznacza ekonomicznie bezsensowny poziom; oznacza brak zgodności
z przyjętą referencją i tolerancją. Nie stosowano filtrów względem Close,
korekt skali ani dodatkowej kary poza zamrożonym protokołem.

## 11. Interpretacja i ograniczenia

Uzyskany wynik potwierdza poprawę realizacji kontraktu wyjściowego i częściowe
odtwarzanie referencji na późniejszym okresie. Nadal 168/277 przewidzianych
poziomów pozostaje niedopasowanych, 148/257 referencji nie zostaje odnalezionych,
a pełny zestaw przy 0.5 ATR nie został odtworzony na żadnym wykresie.
Niski MAE dopasowanych par nie opisuje błędu wszystkich predykcji i nie
kompensuje licznych FP/FN. Różnice MAE między wariantami lub tolerancjami
dotyczą różnych zbiorów par.

Badanie ograniczają 66 wykresów, dwa instrumenty, jeden interwał i styl
renderowania, prefiksowy wybór testu oraz współzależność warunków rynkowych
BTC i ETH. Nie należy traktować 66 okien jako 66 niezależnych sytuacji
rynkowych. Train ma 440/698 syntetyków (63.04%), podczas gdy test jest realny.
Zamrożony enkoder wizualny, LoRA q_proj/v_proj i budżet 8 GB ograniczają
adaptację. SFT optymalizuje stratę tokenową, a nie bezpośrednio zbiór poziomów
lub micro-F1. Nie wykonano ablacji rozdzielającej te czynniki.

Jest to **odtwarzanie poziomów referencyjnych, a nie sprawdzian rentowności
handlu**. Nie przeprowadzono backtestu strategii, oceny zysków, kosztów,
ryzyka, wykonania zleceń ani prognozy przyszłych cen. Wyniki nie uzasadniają
twierdzeń o rentowności lub niezawodności inwestycyjnej.

## 12. Wnioski końcowe

Jednorazowa para ewaluacyjna została ukończona i zabezpieczona: po 66
odpowiedzi, zgodne warunki oraz trzy oficjalne raporty. Wybrany adapter
pozostał niezmieniony, bez aktualizacji wag w etapie testowym.

Model dostrojony osiągnął oficjalne micro-F1=0.4082397004 przy 0.5 ATR
i 66/66 poprawnych odpowiedzi JSON. Oficjalne F1 bazy wynosi 0 ze względu
na format, a osobna diagnostyka wykazuje częściowe rozpoznawanie poziomów
przez bazę (F1=0.2235834609). Dostrajanie wiąże się z poprawą formatu
i opisową poprawą zgodności cen, przy wciąż znacznej liczbie błędów.

Niższe F1 testowe niż validation wskazuje na ograniczenia generalizacji,
bez dowodu przeuczenia lub istotności statystycznej. Wynik testu nie zmienił
wyboru modelu, datasetu, protokołu ani tolerancji. Etap zamknięto dokumentacją;
nie uruchomiono kolejnych eksperymentów ani ponownej inferencji.

## 13. Wykaz źródłowych artefaktów i sum kontrolnych

Źródłami interpretacji są `FINAL_MODEL_SELECTION.json`,
`RAPORT_KONCOWY_DOSTRAJANIA_4_1_4_4.md`, `RAPORT_4_6A_PRZYGOTOWANIE_TESTU.md`,
`SZABLON_RAPORTU_4_6B.md` oraz `docs/evaluation/PROTOKOL_3_6.md`.
Opisy niewykorzystania testu w dokumentach 4.5 i 4.6A są historyczne.
Poniższa tabela podaje SHA-256 bajtów plików; hash reguł protokołu jest
osobnym identyfikatorem kanonicznej treści:
`dafd622fc17e78fe9e095d0849b4a4ae1f8a748d203a3b8fa48a373e4b3ccf58`.

| Plik (ścieżka od katalogu projektu) | SHA-256 |
|---|---|
| `docs/vlm/FINAL_MODEL_SELECTION.json` | `287e45bd688de30293b129a536086133be380116202ca74a0fe69c6ab9bd921e` |
| `docs/vlm/RAPORT_KONCOWY_DOSTRAJANIA_4_1_4_4.md` | `6fe86f04f1166a30579b946fa6a330821dc942f23a4538c763066605d7f02dbf` |
| `docs/vlm/RAPORT_4_6A_PRZYGOTOWANIE_TESTU.md` | `d16652d6f48e1584b34d41f55ec3bdbb0b693b80817cf8e84cec9736f257721e` |
| `docs/vlm/SZABLON_RAPORTU_4_6B.md` | `3d20caf60932f9001c5cd83bba59a70d9b1c8b53ea1ebb67c425dfa371231c3e` |
| `docs/evaluation/PROTOKOL_3_6.md` | `c1395d4ae79475993ac646f2d4709129a341948a8dd7fb38b95bd5b2e7b13173` |
| `data/datasets/ds35-800-20261107-a/manifest.json` | `0f9093fbdcbd39243fcf802bfdd723cb913b15838aa4a3cc469787d5e7e462d0` |
| `results/vlm44-part2-17554-5354/adapter/adapter_model.safetensors` | `20cbbb8e39ca636108d9533e8e8cc4543371b48eb322fff97999a9b8454ebdf6` |
| `results/vlm44-part2-17554-5354/effective-config.json` | `b5c69a9a4820b892af669feca6b6f1090b431c8d8bd2861829148f924896f2ef` |
| `results/vlm46-final-test/session.json` | `479f00763197f56910e65d00a6a5d996fcafd6e0aee829f40696ea1768c47740` |
| `results/vlm46-final-test/base-nf4/manifest.json` | `f8dffd4f4272197a39af4bc56f56aabef18ed0ee7b123d84e3b8bbb9e5eebbf6` |
| `results/vlm46-final-test/base-nf4/predictions.jsonl` | `8cccc8dbc7c1999d9d60a084fe84ef1f4145aed3273982ee8f7a41df54fb6182` |
| `results/evaluation/vlm46-final-test-base-nf4/manifest.json` | `37d72e949b462647aab0fee371044fdebad6bfb684922d631d759bb9977a8b39` |
| `results/evaluation/vlm46-final-test-base-nf4/summary.json` | `61479b6e63bf57adb58aa05866ba56b005ad39fdeb02013c08c65976528116d3` |
| `results/evaluation/vlm46-final-test-base-nf4/per_example.jsonl` | `6993cf555894f0899d641e88a96291bca54057a6535ade375946a4a3915f8fc7` |
| `results/vlm46-final-test/finetuned-nf4/manifest.json` | `7bbd03009191b669f112fe960c4630601f2a24549e1fa1a24659e40f7b15afe7` |
| `results/vlm46-final-test/finetuned-nf4/predictions.jsonl` | `62d9ca8e7749651d7ff9167d42eabf9c688bdfc2989c98de7c42bcb622359b77` |
| `results/evaluation/vlm46-final-test-finetuned-nf4/manifest.json` | `b853176025ead98080ed6035bbbbc7431404b512cbeff9d8339726b7295f1819` |
| `results/evaluation/vlm46-final-test-finetuned-nf4/summary.json` | `98dbac21d83ae47da663f388b6b83be43f5e1071d0333e17f0eb4f58423aab07` |
| `results/evaluation/vlm46-final-test-finetuned-nf4/per_example.jsonl` | `9e99bb79ba3d67c71dd6ac4ff324a60723ba1806eda5ea9cc753780bd970b938` |
| `results/evaluation/vlm46-final-test-comparison/manifest.json` | `050bbe1d09a713f1317bf83934bf74f43e6e87434e4127b55ebed16cbea46e17` |
| `results/evaluation/vlm46-final-test-comparison/comparison.json` | `a63c657f9ee5b46e3b65220c78931d22edb0c37e38b4ec21fc99a7b55505b7d7` |

Pełny wykaz chronionych plików i rozmiarów: [SOURCES.json](final46b/SOURCES.json).
Kontrola integralności: [integrity.json](final46b/integrity.json).
Audyt procesów, kodów i manifestów: [execution_audit.json](final46b/execution_audit.json).
Zweryfikowane oficjalne metryki: [verified_metrics.json](final46b/verified_metrics.json),
[metrics.csv](final46b/metrics.csv), [porównanie](final46b/official_comparison.json).
Diagnostyka: [diagnostic_base_summary.json](final46b/diagnostic_base_summary.json),
odrębne predictions/per_example w tym samym katalogu. Przypadki błędów:
[error_cases.json](final46b/error_cases.json). Historyczna validation:
[validation_metrics.json](final46b/validation_metrics.json).

Procedura odtworzenia audytu: `.venv/Scripts/python.exe scripts/audit_vlm46b.py`
z katalogu projektu, wyłącznie do nowego katalogu wyjściowego (skrypt odmawia
nadpisania `final46b`). Nie wymaga środowiska VLM; nie importuje torch ani
transformers. Dokument renderuje `scripts/build_vlm46b_report.py`.

Mała paczka `handoff/vlm46b-final-report-20261112.zip` zawiera raport,
zestawienia, skrypty dokumentacyjne, audyt, źródła metryk, logi i kody
zakończenia oraz manifest zawartości. Nie zawiera wag, adapterów, checkpointów,
obrazów, OHLC ani całego datasetu. Małe bindingi referencji są częścią
źródłowych raportów ewaluatora. SHA-256 ZIP zapisano obok archiwum;
wewnętrzny `PACKAGE_MANIFEST.json` umożliwia kontrolę każdego pliku.

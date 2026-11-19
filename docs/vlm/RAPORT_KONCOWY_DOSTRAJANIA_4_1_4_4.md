# Raport końcowy dostrajania Qwen3-VL — etapy 4.1–4.4

Etap 4.5, data dokumentacji: 2026-11-11. Status: eksperymenty zamknięte,
wybór lokalnego adaptera utrwalony; końcowej oceny testowej nie wykonano.

## 1. Streszczenie

Dostrojono `Qwen/Qwen3-VL-2B-Instruct` do odtwarzania algorytmicznych poziomów
wsparcia i oporu z wykresów kryptowalutowych. Główny eksperyment QLoRA objął
dwie epoki, 350 aktualizacji i 1396 prezentacji przykładów. Po analizie validation
autor zlecił dodatkowy eksperyment jednej epoki: 175 aktualizacji od wyuczonych
wag, z nowym AdamW, schedulerem i RNG. Były to dwa harmonogramy optymalizacji.

Na tych samych 36 validation oficjalne micro-F1 przy 0,5 ATR wyniosło
0,3972125436 po pierwszej epoce, 0,4651162791 po drugiej i 0,4682274247 po
dodatkowej epoce. Wszystkie adaptery zwróciły 36/36 poprawnych odpowiedzi JSON.
Przyrost ostatniego F1 o 0.0031111457 wynika z FP 84→82 przy TP=70 i FN=77.
Nie wykazano istotności statystycznej ani poprawy wszystkich podgrup.
Wybrano `results/vlm44-part2-17554-5354/adapter`; adapter 350 zachowano.

## 2. Cel i zakres eksperymentów

Celem jest zgodność cen i stron S/R z etykietami przygotowanymi algorytmicznie,
przy ścisłym kontrakcie wyjściowym. Nie badano rentowności ani prognozy przyszłej
ceny. Etap 4.1 obejmował wykonalność i bazowe BF16/NF4, 4.2 implementację pętli
i kontrolę wznowienia, 4.3 główny trening, 4.4 dalsze uczenie wag. Etap 4.5
obejmuje wyłącznie audyt plików, obliczenia offline, ilustracje i dokumentację.
Nie uruchamiano treningu, Qwen, inferencji GPU, nowych danych ani oceny testu.

## 3. Środowisko sprzętowe i programowe

Historyczny sprzęt: RTX 3060 Ti 8192 MiB, CC 8.6, Ryzen 5 3600X (6/12), około
16 GiB RAM, Windows 10/19045, WDDM. Źródło sprzętu: raport 4.1 część 1
i `results/vlm-feasibility-20261109-210209/`; wersje wykonania poniżej pochodzą
z `identity.json` końcowego przebiegu, Python 3.12.12.

| Biblioteka | Wersja historycznego treningu |
|---|---|
| torch | 2.10.0+cu128 |
| torchvision | 0.25.0+cu128 |
| transformers | 5.3.0 |
| peft | 0.18.1 |
| accelerate | 1.12.0 |
| bitsandbytes | 0.49.2 |
| pillow | 12.1.1 |
| psutil | 7.2.2 |
| numpy | 2.5.4 |
| huggingface-hub | 1.33.0 |
| safetensors | 0.8.0 |
| tokenizers | 0.22.2 |

Środowisko treningowe: `D:/ml-envs/market-levels-vlm`; cache wag poza repozytorium.
Audyt 4.5 korzysta z istniejącego środowiska danych, Matplotlib/Agg oraz osobnego
porównania zaufanych stanów na CPU. Nie jest to nowy pomiar szybkości GPU.

## 4. Dane i ich przygotowanie

Dataset: `ds35-800-20261107-a`; katalog `data/datasets/ds35-800-20261107-a`.
SHA-256 manifestu: `0f9093fbdcbd39243fcf802bfdd723cb913b15838aa4a3cc469787d5e7e462d0`.
Manifest i wszystkie jego pliki sprawdzono bez regeneracji zbioru.

| Split | BTC real | ETH real | BTC synthetic | ETH synthetic | Razem |
|---|---:|---:|---:|---:|---:|
| Train |129|129|220|220|698|
| Validation |18|18|0|0|36|
| Test (tylko inwentarz) |33|33|0|0|66|
| Razem |180|180|220|220|800|

Całość: 45% realnych / 55% syntetycznych; train: 258/698 = 36,96% realnych
i 440/698 = 63,04% syntetycznych. Obraz ma 1024×768, 120 świec 4h.
`chronological_v1` rozdziela train 2020–2023, validation 2024, test
2025–2026-10. Dokładne granice zatwierdzonych okresów zapisano w zamrożonym
`config.json`; ostatnie otwarcia okresów: 2023-12-31 20:00, 2024-12-31 20:00,
2026-10-31 20:00 UTC. Faktycznie wybrane realne train kończą się
2023-12-30 12:00, validation 2024-12-25 20:00 UTC; oba zaczynają się 1 stycznia
pierwszego roku o 00:00. Historyczny raport 3.5 podaje pokrycie testu
2025-01-01 00:00–2026-10-22 20:00 UTC; nie odczytywano ponownie jego metadanych.

Train: przesunięcie 60 świec (nakładanie wewnątrz treningu), validation/test:
120. Okna nie przekraczają granic splitów; luka 2020-02-19 12:00 UTC nie jest
interpolowana. Realny train wybrano warstwowo chronologicznie, seed 20261107;
validation/test to prefiksy kandydatów. Profile syntetyczne kalibrowano tylko
na treningu i zatwierdzono w kopiach 3.5; syntetyki występują wyłącznie w train.
Mała próba dwóch instrumentów, jednego interwału i jednego stylu wykresu,
dominacja syntetyków w train oraz prefiksowa selekcja ograniczają reprezentatywność.

## 5. Metoda wyznaczania etykiet S/R

Algorytm `sr-extreme-first-1.0.0`: ścisłe ekstrema 3+3, Wilder ATR(14),
delta=0,5 końcowego ATR; wspólne grupowanie H/L o pełnej rozpiętości ≤delta,
bez łączenia łańcuchowego. Cena grupy to mediana wszystkich jej ekstremów
przed filtrowaniem. Wybór reakcji zaczyna od najbardziej skrajnego ekstremum;
usuwa reakcje odległe o mniej niż 5 świec. Wymagane co najmniej dwie reakcje.
Odrzuca poziomy w odległości ≤delta od ostatniego Close. Pozostałe dzieli
względem Close i szereguje według liczby reakcji, ostatniej reakcji, odległości,
ceny i ID, maksymalnie trzy na stronę. Decimal 50 cyfr; ROUND_HALF_UP do centów
przy serializacji; kolizje rozstrzyga ranking. Nie jest to maksymalizacja liczby
reakcji. Nie używa przyszłości poza oknem ani metadanych generatora.

Instrukcja `pl-sr-v1` żąda maksymalnie trzech wsparć i oporów oraz wyłącznie
JSON z listami cen. Źródło: `src/market_levels/datasets/domain/examples.py`,
schemat i `docs/datasets/FORMAT.md`. Obrazy wejściowe nie mają linii referencyjnych;
model nie otrzymuje OHLC, etykiet ani metadanych jako dodatkowego promptu.

## 6. Architektura Qwen3-VL i zastosowanie QLoRA

Rewizja bazowa: `89644892e4d85e24eaac8bacfd4f463576704203`;
klasa wykonawcza `Qwen3VLForConditionalGeneration`. Procesor przekształca
obraz w tokeny wizualne, a część językowa generuje autoregresyjnie odpowiedź.
Adaptery niskiego rzędu aktualizują wybrane projekcje uwagi językowej,
przy zamrożonych wagach bazowych. Nie dostrajano enkodera wizualnego.

| Parametr | Eksperyment główny | Eksperyment dodatkowy |
|---|---|---|
| Kwantyzacja / compute | NF4 + double quantization / BF16 | bez zmian |
| Wizja | zamrożona, BF16 | bez zmian |
| LoRA | q_proj/v_proj części językowej; r=8, alpha=16, dropout=0 | bez zmian |
| Tensory / parametry LoRA | 112 / 1 605 632 | 112 / 1 605 632 |
| AdamW | betas=(0.9,0.999), eps=1e-8, weight_decay=0.01 | nowy stan; te same parametry |
| Batch / akumulacja | 1 / 4 | 1 / 4 |
| Epoki / aktualizacje | 2 / 350 | 1 / 175 lokalnych |
| LR / warmup | 0.0002 / 18 | 0.00005 / 9 |
| Scheduler | linear, horyzont 350 | nowy linear, horyzont 175 |
| Seed | 20261110.0000000000 | 20261112 |
| Checkpoint | co 25 kroków + początek/koniec odcinka | tak samo |
| Gradient clipping / checkpointing | 1.0 / use_reentrant=False | bez zmian |
| Sekwencja / obraz | limit 2048 / 1024×768, 768 tokenów obrazu | bez zmian |
| Attention / urządzenie | SDPA / cuda:0; brak jawnego offloadu | bez zmian |

QLoRA ogranicza pamięć zamrożonych wag dzięki NF4 i uczy mały adapter zamiast
pełnego modelu. Zamrożenie wizji zmniejsza liczbę parametrów objętych gradientami
i koszty stanów optymalizatora. Akumulacja pozwala uzyskać grupę czterech
przykładów przy mikrobatche 1; ostatnia grupa każdej epoki liczy dwa przykłady
(698 = 174×4+2). Jest to wybór wynikający z budżetu 8 GB, z ograniczoną
zdolnością adaptacji wizualnej. `model.visual` i `lm_head` pomijają kwantyzację;
wizja ma BF16, inne zamrożone niekwantyzowane parametry FP32 po PEFT.
Opis mechanizmu oparto na konfiguracji i kodzie projektu. Bibliografia pracy
powinna uzupełnić źródła pierwotne Qwen3-VL, LoRA i QLoRA; nie dodano fikcyjnych cytowań.

## 7. Model bazowy i wyniki przed dostrajaniem

| Baza | Oficjalne JSON /36 | Oficjalne F1 | Diagnostyczne TP/FP/FN | Diagnostyczne F1 |
|---|---|---|---|---|
| NF4 | 0.0000000000 | 0.0000000000 | 48/168/99 | 0.2644628099 |
| BF16 | 0.0000000000 | 0.0000000000 | 58/158/89 | 0.3195592287 |

Oficjalny `sr-eval-v1` odrzucił wszystkie odpowiedzi bazowe opakowane Markdownem:
TP=0, FP=0, FN=147 dla obu wariantów. To skutek niespełnienia pełnego kontraktu
odpowiedzi, a nie dowód braku rozpoznawania poziomów. Oddzielna diagnostyka 4.2
zdjęła wyłącznie zewnętrzne znaczniki Markdown i uzyskała częściową zgodność cen.
Jej wyniki nie są oficjalnymi wynikami i nie uczestniczą w wyborze checkpointu.
Nie mieszamy ich z oficjalną krzywą F1. Bazowe BF16/NF4 różnią się warunkami
precyzji; głównym punktem odniesienia dla adapterów NF4 jest baza NF4.

## 8. Implementacja pipeline'u treningowego

`training/workflows/pipeline.py` koordynuje istniejące ładowanie, SFT, sampler,
AdamW, scheduler, kontrolę pamięci i zapisy. Superwizja obejmuje tokeny odpowiedzi
i zakończenia; obraz, instrukcja i role prefiksu są maskowane. Loss to średnia
średnich po tokenach nadzorowanych dla przykładów w faktycznej grupie akumulacji.
Nie optymalizuje bezpośrednio micro-F1 ani błędu ATR. Zbyt długie sekwencje są
kontrolowane, a nie cicho obcinane. Gradient clipping = 1, gradient checkpointing
z `use_reentrant=False`, SDPA, TF32 wyłączone, deterministyczność `warn_only`.

Pełne checkpointy zawierają adapter, AdamW, scheduler, sampler i RNG.
Eksport `adapter/` służy inferencji i nie zastępuje pełnego checkpointu.
Tożsamość wiąże konfigurację, dataset, rewizję i środowisko. Wznowienie zapisuje
stan w nowym katalogu; STOP działa na granicy aktualizacji. Walidacja jest osobnym
procesem po treningu. Etap 4.2 obejmował sześć technicznych aktualizacji A=3,
B1=1, B2=2 oraz kontrolę odtworzenia; nie zaliczamy ich do 350+175 aktualizacji
eksperymentów jakości. Historyczna próba 4.1 miała osobny adapter techniczny.

## 9. Przebieg dwuepokowego treningu

| Przebieg | Kroki | Nowe przykłady | Narastająco | Status | Suma czasów kroków [s] |
|---|---|---|---|---|---|
| vlm43-part1-14789-1679 | 1–25 | 100 | 100.0000000000 | stopped | 113.4250000000 |
| vlm43-part2-17032-13034 | 26–175 | 598 | 698.0000000000 | stopped | 643.4270000000 |
| vlm43-part3-2708-16743 | 176–350 | 698 | 1396.0000000000 | stopped | 695.6950000000 |
| vlm44-part1-24755-21138 | 1–25 | 100 | 100.0000000000 | stopped | 115.6200000000 |
| vlm44-part2-17554-5354 | 26–175 | 598 | 698.0000000000 | stopped | 607.3020000000 |

Pierwsze trzy wiersze to jeden eksperyment 1–350 z odtwarzaniem pełnego stanu.
Logi mają komplet kroków, bez duplikatów i luk; każda epoka prezentuje dokładnie
698 train w kolejności `Random(seed+epoch)` nad posortowanymi ID (epoka od zera).
Suma to 1396 przykładów. Resume 25→26 i 175→176 zachowuje sampler i stany;
nie ma ponownej inicjalizacji od rodzica. Ponowne ładowanie modelu w nowym procesie
jest oczekiwane. Jedyną różnicą metadanych początkowego checkpointu wznowienia
jest rosnący `elapsed_seconds` uwzględniający ładowanie; nie resetuje postępu.

Checkpointy: 0,25 w odcinku 1; 25,50,…,175 w odcinku 2; 175,200,…,350
w odcinku 3. Manifesty i wszystkie pliki checkpointów zweryfikowano.
Status końcowy `stopped` jest zgodny z granicami StopAfter/walidacji,
w tym końcem planu. Nie stwierdzono zdarzeń `failed` lub `memory_pressure`.
W dostępnych logach konsoli nie zapisano niezależnych liczbowych kodów wyjścia
procesów treningu; nie deklarujemy historycznego kodu 0 wyłącznie na podstawie statusu.

![Strata i LR](final45/01_loss_lr.png)

Rysunek 1. Surowe wartości loss i LR dla wszystkich 525 kroków; odrębne osie
dla dwóch harmonogramów. Źródło: pięć `events.jsonl`, tabela `training_steps.csv`.
Brak wygładzania i interpolacji. LR w rekordzie jest wartością używaną do danej
aktualizacji: pierwszy krok ma 0, szczyt przypada po warmup, ostatnia aktualizacja
ma jeszcze dodatni LR; scheduler osiąga 0 po niej. To konwencja istniejącej pętli.

## 10. Wyniki pierwszej i drugiej epoki

| Metryka | Krok 175 | Krok 350 | Dodatkowe 175 |
|---|---|---|---|
| micro_f1 | 0.3972125436 | 0.4651162791 | 0.4682274247 |
| micro_precision | 0.4071428571 | 0.4545454545 | 0.4605263158 |
| micro_recall | 0.3877551020 | 0.4761904762 | 0.4761904762 |
| tp | 57.0000000000 | 70.0000000000 | 70.0000000000 |
| fp | 83.0000000000 | 84.0000000000 | 82.0000000000 |
| fn | 90.0000000000 | 77.0000000000 | 77.0000000000 |
| predicted_levels | 140.0000000000 | 154.0000000000 | 152.0000000000 |
| reference_levels | 147.0000000000 | 147.0000000000 | 147.0000000000 |
| valid_json_count | 36.0000000000 | 36.0000000000 | 36.0000000000 |
| complete_set_correct_count | 2.0000000000 | 2.0000000000 | 2.0000000000 |
| zero_tp_examples | 4.0000000000 | 2.0000000000 | 3.0000000000 |
| MAE/ATR (dopasowane) | 0.2448075504 | 0.2297119152 | 0.2212751625 |

Wszystkie wartości z trzech oryginalnych `summary.json` odtworzono dokładnie
przez `read_evaluation`. Druga epoka zwiększyła TP 57→70, zmniejszyła FN 90→77,
przy FP 83→84 i F1 +0.0679037355.
Wzrost zgodności obejmuje więc lokalizację względem referencji, nie tylko format.
Skuteczniejsze generowanie schematu po SFT jest zgodne z bezpośrednią superwizją
poprawnych odpowiedzi JSON; bez ablacji nie rozdzielamy przyczyn tego efektu.

Precision=TP/(TP+FP) opisuje udział trafień w przewidzianych poziomach,
recall=TP/(TP+FN) pokrycie referencji, a micro-F1=2TP/(2TP+FP+FN) kompromis
z sum liczności obu stron i wszystkich wykresów. MAE/ATR to średnia |pred−ref|/ATR
wyłącznie dopasowanych par; nie obejmuje wszystkich przewidzianych cen ani FN.
Lepsze MAE przy innym zbiorze par nie gwarantuje lepszego odtworzenia całego zestawu.

## 11. Motywacja dodatkowego eksperymentu

Autor zdecydował o dodatkowej epoce **po obejrzeniu wyników validation** 175/350.
Sprawdzał, czy dalsze uczenie wag poprawi lokalizację. Reguła przed startem 4.4:
wyższe oficjalne micro-F1 przy 0,5 ATR, potem udział JSON, potem wcześniejszy 350.
Źródło: sekcja E instrukcji 4.4 i raport przygotowania. Decyzja ta rozszerza
badanie po analizie walidacji; nie była z góry niezmiennym planem trzech epok.

## 12. Przebieg dodatkowej epoki

Punkt startowy: `results/vlm43-part3-2708-16743/adapter`.
Nowy AdamW, nowy linear na 175 lokalnych kroków, warmup 9, LR=0,00005;
nowy sampler/RNG z seed=20261112. Te same 698 obrazów i etykiet oraz ta sama LoRA.
Przebiegi 1–25 i 26–175 są segmentami tego jednego dodatkowego eksperymentu.
Wznowienie drugiego segmentu odtwarza już jego pełny stan, bez ponownego resetu.

`initialized_from_adapter` i `initialization.json`: `tensor_values_exact=true`,
`tensor_count=112`, `trainable_parameters=1605632`; rodzic ma krok 350 i SHA-256
`3b7af8dd8835923a561aa356248b075042fa022f45be5426833bf2b2662c4a7c`.
`optimizer_state=new`, `scheduler_state=new`, `rng_state=new seed, not inherited`.
Bajty wszystkich tensorów początkowego adaptera są zgodne z rodzicem; sprawdzono
również powiązanie manifestu rodzica i checkpointu z konfiguracją.
Nowy stan nie oznacza resetu przy wznowieniu 26–175. Liczba 525 jest sumą
350+175 aktualizacji dwóch harmonogramów. W nowym etapie przetworzono 698 przykładów.

## 13. Końcowa walidacja i porównanie checkpointów

| Tolerancja ATR | 175: TP/FP/FN | 175: F1 | 350: TP/FP/FN | 350: F1 | Dodatkowe: TP/FP/FN | Dodatkowe: F1 |
|---|---|---|---|---|---|---|
| 0.25 | 31/109/116 | 0.2160278746 | 40/114/107 | 0.2657807309 | 43/109/104 | 0.2876254181 |
| 0.5 | 57/83/90 | 0.3972125436 | 70/84/77 | 0.4651162791 | 70/82/77 | 0.4682274247 |
| 1.0 | 84/56/63 | 0.5853658537 | 98/56/49 | 0.6511627907 | 100/52/47 | 0.6688963211 |

| Przekrój | 175: TP/FP/FN | F1 | 350: TP/FP/FN | F1 | Dodatkowe: TP/FP/FN | F1 |
|---|---|---|---|---|---|---|
| BTCUSDT | 29/37/49 | 0.4027777778 | 35/36/43 | 0.4697986577 | 36/35/42 | 0.4832214765 |
| ETHUSDT | 28/46/41 | 0.3916083916 | 35/48/34 | 0.4605263158 | 34/47/35 | 0.4533333333 |
| supports | 37/65/36 | 0.4228571429 | 38/55/35 | 0.4578313253 | 39/51/34 | 0.4785276074 |
| resistances | 20/18/54 | 0.3571428571 | 32/29/42 | 0.4740740741 | 31/31/43 | 0.4558823529 |

Końcowe 36 odpowiedzi zawiera 152 poziomy przy 147 referencjach, 2/36 pełnych
zestawów i 3 wykresy bez TP. Nie występują duplikaty cen. Przy 0,5 ATR MAE/ATR
70 dopasowanych par wynosi 0,2212751625 (350: 0.2297119152).
Dokładne wartości i wszystkie przekroje: `final45/verified_metrics.json`.
Większa tolerancja dopuszcza więcej par, stąd wyższe F1 przy 1,0 niż 0,25 ATR;
nie oznacza to nowej predykcji ani bardziej dokładnych cen.

Ostatni przyrost to **dwa mniej FP**, bez wzrostu TP i recall. BTC i supports
poprawiły się, ETH i resistances pogorszyły się. Porównanie jest sparowane na
identycznym fingerprintcie, instrukcji, rewizji i ustawieniach inferencji:
NF4, `do_sample=false`, `num_beams=1`, `max_new_tokens=256`, `use_cache=true`,
budżet 786432 pikseli. Nie zmieniano ustawień generowania ani ewaluatora.

![Oficjalne metryki](final45/03_official_metrics.png)

Rysunek 2. Oficjalne F1/P/R i tolerancje ATR. Zerowa baza jest wynikiem rygoru
formatu; diagnostyki po zdjęciu Markdown nie pokazano jako oficjalnej serii.

![Przekroje](final45/04_groups.png)

Rysunek 3. Dwa ostatnie adaptery według instrumentu i strony, na tych samych validation.

## 14. Analiza błędów

FP=82 oznacza wskazania niedopasowane do algorytmicznej referencji przy 0,5 ATR;
FN=77 to pominięte poziomy referencyjne. Nie każde FP jest ekonomicznie bezsensowne.
Niedokładna cena może dać równocześnie FP i FN; matching nie rozdziela automatycznie
przyczyn wizualnych, semantycznych i błędnej liczby poziomów. Wsparcia i opory
dopasowuje się osobno, maksymalizując TP, następnie minimalizując błąd i remisy indeksów.

| ID | Symbol | 175 dodatkowych: TP/FP/FN | F1 przed → po |
|---|---|---|---|
| 96c921e8c98c52ebb5df7050 | BTCUSDT | 0/3/4 | 0.000000 → 0.000000 |
| f7c6ae850bee490c324d8935 | BTCUSDT | 3/0/0 | 1.000000 → 1.000000 |
| 9e022b1b5cdfce2e75b4697c | BTCUSDT | 0/3/3 | 0.000000 → 0.000000 |
| 6782325988b61211e827c9f7 | BTCUSDT | 4/0/0 | 1.000000 → 1.000000 |
| e298ecdb7053db8953d03aa8 | ETHUSDT | 0/6/3 | 0.222222 → 0.000000 |

Pełne sparowane porównanie 36 przykładów: `final45/paired_validation.csv`.
F1 przykładów wzrosło w 6, spadło w 8, pozostało równe w 22. Równe F1
nie dowodzi identycznych cen. Zmiany są nierówne, mimo dodatniego micro-F1 ogółem.
Największa poprawa: `d6bf408fd0b0d23877ae60a0`; największy spadek (remis po ID):
`7c14d9de5f11728d769fb10d`. Tabele tolerancji pokazują, jak część wskazań
przechodzi z FP/FN do TP po rozszerzeniu progu; nie zmieniamy oficjalnego 0,5 ATR.

Istniejąca diagnostyka względem Close wykazała w końcowym adapterze 10/90
wsparć po niewłaściwej stronie Close i 1/62 oporów; po 6/36 pustych list obu stron.
Adapter 350 miał odpowiednio 14/93 i 1/61 wskazań po niewłaściwej stronie oraz
5/36 pustych list supports i 6/36 resistances. Nie przekłada się to bezpośrednio
na sumę FP, ponieważ dopasowanie cen i ta diagnostyka mają różne kryteria.
To osobne proxy, a nie dodatkowa kara w oficjalnym F1. Weryfikacja tych liczności
odtworzyła istniejącą diagnostykę wyłącznie na 36 CSV validation. Źródło:
`results/vlm44-validation-4184-25636/price-diagnostics/diagnostics.json`.
Hipotezy obejmują zaokrąglanie cen do typowych wartości, trudność odczytu osi,
ograniczoną pojemność adaptera i niedopasowanie syntetyków do realnych wykresów;
nie przeprowadzono ablacji dowodzącej ich udziału.

![Przykład 1](final45/case_01.png)

Rysunek 5. ID `96c921e8c98c52ebb5df7050`; BTCUSDT; F1 przy 0,5 ATR: 0.000000 → 0.000000. Świece przerysowane wyłącznie z istniejącego CSV validation. Oryginalny obraz: `data/datasets/ds35-800-20261107-a/images/96c921e8c98c52ebb5df7050.png`. Dobór: odpowiednio pierwszy brak trafień, pierwszy kompletny zestaw, największa poprawa i największe pogorszenie (remisy po ID).

![Przykład 2](final45/case_02.png)

Rysunek 6. ID `f7c6ae850bee490c324d8935`; BTCUSDT; F1 przy 0,5 ATR: 1.000000 → 1.000000. Świece przerysowane wyłącznie z istniejącego CSV validation. Oryginalny obraz: `data/datasets/ds35-800-20261107-a/images/f7c6ae850bee490c324d8935.png`. Dobór: odpowiednio pierwszy brak trafień, pierwszy kompletny zestaw, największa poprawa i największe pogorszenie (remisy po ID).

![Przykład 3](final45/case_03.png)

Rysunek 7. ID `d6bf408fd0b0d23877ae60a0`; BTCUSDT; F1 przy 0,5 ATR: 0.200000 → 0.727273. Świece przerysowane wyłącznie z istniejącego CSV validation. Oryginalny obraz: `data/datasets/ds35-800-20261107-a/images/d6bf408fd0b0d23877ae60a0.png`. Dobór: odpowiednio pierwszy brak trafień, pierwszy kompletny zestaw, największa poprawa i największe pogorszenie (remisy po ID).

![Przykład 4](final45/case_04.png)

Rysunek 8. ID `7c14d9de5f11728d769fb10d`; ETHUSDT; F1 przy 0,5 ATR: 0.666667 → 0.333333. Świece przerysowane wyłącznie z istniejącego CSV validation. Oryginalny obraz: `data/datasets/ds35-800-20261107-a/images/7c14d9de5f11728d769fb10d.png`. Dobór: odpowiednio pierwszy brak trafień, pierwszy kompletny zestaw, największa poprawa i największe pogorszenie (remisy po ID).

## 15. Analiza wykorzystania zasobów

| Przebieg | Peak próbek VRAM [MiB] | Peak próbek RSS [MiB] | Peak allocated [MiB] | Peak reserved [MiB] |
|---|---|---|---|---|
| vlm43-part1-14789-1679 | 7889.0000000000 | 4516.0000000000 | 5166.2600000000 | 9762.0000000000 |
| vlm43-part2-17032-13034 | 7881.0000000000 | 2925.0900000000 | 5167.6100000000 | 8162.0000000000 |
| vlm43-part3-2708-16743 | 7969.0000000000 | 3890.8600000000 | 5168.1100000000 | 8882.0000000000 |
| vlm44-part1-24755-21138 | 7919.0000000000 | 4484.4800000000 | 5167.9000000000 | 9480.0000000000 |
| vlm44-part2-17554-5354 | 7988.0000000000 | 4551.8200000000 | 5166.7600000000 | 9480.0000000000 |

![Pamięć](final45/02_memory.png)

Rysunek 4. Próbki po krokach i skumulowane szczyty próbek w obrębie procesu,
nie ciągły zapis fizycznej pamięci. Reset licznika przy nowym procesie jest oczekiwany.
WDDM i cache alokatora powodują, że `reserved` może przekraczać fizyczne 8192 MiB;
nie należy go sumować z globalnym VRAM ani nazywać ilością fizycznego VRAM.
Nie zmierzono osobno stronicowania. Peak globalnych próbek osiągnął 7969 MiB
w treningu głównym i 7988 MiB w dodatkowym; próbkowanie może ominąć krótkie piki.
Pomiary RSS nie są całkowitym zajęciem RAM systemu. W logach są również dostępny
RAM i commit; sumy czasów kroków wykluczają przerwy między procesami i część
operacji ładowania/zapisu. Brak porównywalnego profilu wszystkich etapów 4.1/4.2
nie pozwala tworzyć wspólnego benchmarku. Nie przeprowadzono nowych pomiarów GPU.

## 16. Ograniczenia metodologiczne

698 train, 63,04% syntetyków, zamrożona wizja i LoRA wyłącznie q/v ograniczają
zakres uczenia. SFT minimalizuje loss tokenów, nie miarę zbioru poziomów ani błąd
ATR. Budżet 8 GB ogranicza konfigurację, a etykiety algorytmiczne nie zastępują
pełnej oceny eksperckiej. Nadal występuje wiele FP/FN; tylko 2/36 pełnych zestawów.

36 validation, po 18 na instrument, daje ograniczoną pewność wniosków.
Wielokrotna ocena i decyzja o dalszym eksperymencie na tym samym validation
zwiększają ryzyko dopasowania wyboru do walidacji. Nie liczono przedziałów ufności
ani testu istotności; niewielki przyrost F1 nie dowodzi istotnej poprawy.
Okna dwóch instrumentów mogą współdzielić warunki rynkowe, więc nie należy
zakładać niezależności wszystkich obserwacji. Wyniki validation z 2024 r. nie są
jeszcze oceną generalizacji na późniejszych okresach.

## 17. Wybór ostatecznego modelu

Wybrany adapter: `results/vlm44-part2-17554-5354/adapter`, lokalny krok 175 nowego eksperymentu.
SHA-256 pliku wag: `20cbbb8e39ca636108d9533e8e8cc4543371b48eb322fff97999a9b8454ebdf6`.
SHA-256 manifestu adaptera: `cc11b18830876107d075b560d8abe37b718c46f22725e2d0cbf430b73bae1c83`.
Oficjalna walidacja: `vlm44-validation-4184-25636`;
SHA-256 jej `summary.json`: `577fe3c358bb63829a9c751d8e3283e774d245cb87397d45251bb0e2476a107f`.
Pełne powiązanie konfiguracji, checkpointu, danych, rewizji i walidacji:
[FINAL_MODEL_SELECTION.json](FINAL_MODEL_SELECTION.json).

Reguła ustalona przed dodatkowym eksperymentem wybiera większe oficjalne F1
0,4682274247 zamiast 0,4651162791; remis nie wystąpił. Alternatywny adapter
`results/vlm43-part3-2708-16743/adapter` i jego checkpointy pozostają zachowane.
Zamrożenie oznacza zapis lokalnych tożsamości i kontrolę hashy, nie podpis
autentyczności ani blokadę zapisu w systemie plików. Dane wymagane do identyfikacji
są dostępne; kody wyjścia nie są wymaganym identyfikatorem wyboru i ich braku nie ukrywamy.

## 18. Wnioski z eksperymentów

Dostrajanie poprawiło realizację kontraktu JSON i zgodność poziomów z etykietami
algorytmicznymi na validation. Druga epoka zwiększyła liczbę trafień; dodatkowy
eksperyment dał niewielki zysk przez ograniczenie FP. Brak dużego zysku może być
zgodny z ograniczoną adaptacją, małą próbą lub plateau SFT, ale nie dowodzi żadnej
z tych przyczyn. Nie uzasadnia to twierdzeń o niezawodnej analizie technicznej
ani przydatności inwestycyjnej. Autor zamknął eksperymenty bez kolejnych epok,
nowych danych i zmian protokołu.

## 19. Przygotowanie do końcowej oceny na teście

Test 66 realnych wykresów pozostaje odłożony do osobnej decyzji po niezależnym
audycie. Nie generowano odpowiedzi testowych i nie analizowano jego etykiet
w celu wyboru modelu. Hashowanie bajtów całego datasetu służyło ochronie integralności.
Po osobnej autoryzacji należy zachować wybrany adapter, rewizję, prompt,
ustawienia inferencji, dataset i `sr-eval-v1`, opublikować komplet surowych odpowiedzi
i pełne metryki. Nie dostrajać po obejrzeniu testu. Niniejszy dokument nie uruchamia
ani nie zatwierdza ewaluacji testowej. Nie podaje wyników testowych.

## 20. Wykaz źródeł danych, konfiguracji, logów i załączników

- `AGENTS.md`, `.ai/`, `docs/ARCHITECTURE.md`; raporty 3.5 części 1/2,
  4.1 części 1/2, 4.2, przygotowania 4.3 i 4.4, instrukcje PowerShell 4.2–4.4.
- `docs/labeling/RAPORT_3_4.md`, `docs/datasets/FORMAT.md`,
  `docs/evaluation/PROTOKOL_3_6.md`, kod protokołu i instrukcji `pl-sr-v1`.
- `configs/vlm/` i zamrożony dataset (`manifest.json`, `config.json`, `plan.json`).
- Pięć przebiegów w tabeli 9: `result.json`, `identity.json`,
  `effective-config.json`, `events.jsonl`, `model.json`, `preflight.json`,
  manifesty/metadane checkpointów, eksporty adapterów i dostępne logi konsoli.
- Pięć oficjalnych ocen w `results/evaluation/` (dwie bazy i 175/350/dodatkowa),
  `summary.json`, `predictions.jsonl`, `per_example.jsonl`, binding i manifesty.
  Dwa osobne wyniki `vlm42-price-baseline-20261110-a-{nf4,bf16}` są diagnostyczne.
- `final45/SOURCES.json` zawiera ścieżki, rozmiary i SHA-256 źródeł;
  `final45/verified_metrics.json`, CSV, wykresy, audyt CPU i kontrola integralności
  stanowią załączniki. Pełny lokalny inwentarz przed pracą pozostaje poza małym ZIP.

Końcowa kontrola: 14 204 historyczne pliki bez zmiany SHA-256 i bez usunięć,
w tym 3212 plików datasetu; sprawdzono wszystkie manifesty checkpointów pięciu
segmentów. Dokładne stany optymalizacji/RNG porównano na trzech granicach CPU,
bez inicjalizacji CUDA. [Raport integralności](final45/INTEGRITY_REPORT.md),
[wykaz źródeł](final45/SOURCES.json), [kontrole](final45/checks.json)
oraz [dowód CPU](final45/cpu-states.json) utrwalają zakres i wynik audytu.

Nie znaleziono odrębnego dokumentu z formalnym tematem i wymaganiami uczelnianymi
pracy; nie rekonstruowano go. Nie ma osobnego raportu końca wykonania 4.3/4.4
poza oryginalnymi artefaktami i tym raportem; dokumenty przygotowania opisują
historyczny stan. Brak niezależnego zapisu kodów zakończenia wskazano w sekcji 9.
Status niewykorzystania testu opiera się na deklaracji autora, dostępnych artefaktach
i zakresie tej pracy; lokalny audyt nie dowodzi nieistnienia zewnętrznych uruchomień.

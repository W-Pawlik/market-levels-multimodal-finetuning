# Etap 4.2 — pipeline treningowy Qwen3-VL

2026-11-10. Artefakty: `results/vlm42-pipeline-20261110-a/`.
Zaimplementowano pełny pipeline i wykonano ograniczoną próbę techniczną.
**355/355 testów offline OK; sześć kroków Qwen GPU łącznie; wznowienie dokładne.**
Nie uruchomiono pełnego treningu 698 przykładów, nowej pełnej walidacji adaptera,
inferencji na test ani etapu 4.3. Smoke nie jest wynikiem właściwego dostrajania.

## Architektura i mechanizm treningu

Rozbudowano sprawdzoną ścieżkę PyTorch + PEFT. Trainer oferuje gotowe epoki,
scheduler i zapis, lecz nie wykazano jego bezpiecznej integracji na 8 GB z tym
modelem, NF4, zamrożoną wizją i polityką typów PEFT pod Windows. Nie wykonano
benchmarku Trainer i nie przypisujemy mu zmierzonego narzutu. Niewielka pętla
zachowuje przygotowanie obrazu, maskowanie i batch=1 ze sprawdzonego pilota.
Autograd i AdamW pozostają implementacjami PyTorch; adapter — PEFT.

Interfejsy pilota 4.1 zachowano. Nowe elementy:

| Lokalizacja | Odpowiedzialność |
| --- | --- |
| `training/config.py`, `configs/vlm/training.json` | Efektywna konfiguracja i walidacja; runtime przez `$file` z stability.json |
| `training/domain/schedule.py` | Permutacje epok, cursor samplera, grupy i LR |
| `training/io/data.py` | Wszystkie 698 train, PNG na żądanie, istniejące maskowanie |
| `training/io/checkpoints.py` | Pełny stan, RNG, atomowa publikacja i osobny eksport adaptera |
| `training/io/resources.py`, `events.py` | GPU, RAM, commit Windows, CPU, terminal i JSONL |
| `training/workflows/pipeline.py` | Preflight, pętla, scheduler, zapis, STOP i wznowienie |
| `inference/workflows/adapter_validation.py` | Osobny proces: jeden train lub komplet validation |
| `inference/domain/price_diagnostics.py`, `workflows/price_diagnostics.py` | Pomocnicza diagnostyka Markdown i cen |
| `cli/train_vlm.py`, `scripts/run_vlm_training.ps1` | Uruchomienie z terminala bez IDE |
| `scripts/check_vlm42_resume.py`, `verify_vlm42.py` | Porównanie stanów i kontrola integralności |

Biblioteki: Python 3.12.12, torch 2.10.0+cu128, Transformers 5.3.0,
PEFT 0.18.1, bitsandbytes 0.49.2, Accelerate 1.12.0. Użyto istniejącego
`D:/ml-envs/market-levels-vlm/`; niczego nie instalowano. Zwykłe testy działają
w `.venv` bez ciężkich importów. Skrypt PowerShell bez trybu robi dry-run;
CLI bez argumentów pokazuje błąd użycia. `full` wymaga dwóch jawnych blokad.

## Dane, maskowanie i QLoRA

Model: `Qwen/Qwen3-VL-2B-Instruct`, rewizja
`89644892e4d85e24eaac8bacfd4f463576704203`. Lokalny cache i pliki procesora
są sprawdzane wobec SHA-256 z pobierania w 4.1. Preflight wymaga zweryfikowanych
wersji bibliotek, jednego GPU RTX 3060 Ti 8192 MiB i natywnego BF16.

NF4, double quantization, compute BF16, SDPA; wizja zamrożona w BF16.
Pozostałe niekwantyzowane zamrożone parametry mają FP32 po PEFT. LoRA:
56 językowych projekcji q/v, rank 8, alpha 16, dropout 0, bias=none, CAUSAL_LM.
Uczy się 1 605 632 parametrów w 112 tensorach. Gradient checkpointing:
`use_reentrant=False`; trening: `use_cache=False`. AdamW: początkowy LR=0,0002,
betas=(0,9; 0,999), eps=1e-8, weight decay=0,01, clipping normy=1, batch=1,
akumulacja=4. Pełne efektywne opcje są w `effective-config.json`, konkretny
processor/model i biblioteki w metadanych. Brak CPU/disk offloadu.

Manifest i JSONL muszą określać dokładnie 698 unikalnych train: 258 realnych,
440 syntetycznych. Loader nie parsuje JSONL, OHLC ani etykiet testu.
Kontrola manifestu i inwentarz SHA czytają bajty wszystkich plików zbioru.
Do modelu wchodzą tylko oryginalny RGB PNG 1024×768 i instrukcja z JSONL,
zgodna z niezmienioną `pl-sr-v1`. Odpowiedź JSONL jest celem SFT; OHLC, ATR,
symbol i metadane nie wchodzą do rozmowy. Puste listy są dozwolone.

Oficjalny processor/chat template przygotowuje prefiks i pełną rozmowę.
Istniejące `assistant_labels` sprawdza zgodność prefiksu tokenów i maskuje obraz,
instrukcję oraz wcześniejsze role. Superwizja obejmuje odpowiedź i `<|im_end|>`;
jego obecność jest kontrolowana. Przekroczenie limitu, domyślnie 2048 tokenów,
powoduje błąd, bez obcinania. Smoke: 880–903 tokeny wejściowe, 768 obrazu,
35–58 nadzorowanych tokenów.

Kolejność: sortowanie ID, potem `Random(seed+epoch).shuffle`. Pełna permutacja
i pozycja trafiają do checkpointu. Obrazy są ładowane pojedynczo, bez workerów
i bez cache wszystkich pikseli w RAM. Grupowania długości nie włączono: przy
batch=1 nie usuwa paddingu, wymaga pomiaru fragmentacji, a kolejność nie może
zależeć od walidacji.

Strata kroku to średnia strat przykładów; każda jest średnią jego tokenów
superwizji. Backward dzieli przez **rzeczywistą liczbę przykładów w grupie**.
Dłuższy JSON nie ma większej wagi tylko z powodu liczby tokenów. Pełna epoka:
174×4 i 1×2 przykłady, bez pomijania. Końcowy gradient jest średnią dwóch,
zamiast sztucznie osłabionej połowy kroku: współczynnik 1/2 w tej grupie wobec
1/4 w grupie pełnej. Jest to jawnie średnia na krok, nie globalna średnia epoki.
Autograd sprawdzono osobno dla grup 4, 2 i 1 o różnych długościach.

## Checkpointy, wznowienie i walidacja

`checkpoints/step-NNNNNN/` zawiera adapter safetensors i konfigurację PEFT,
`state.pt` (AdamW, scheduler, sampler, liczniki przykładów/tokenów i czasu,
RNG Python/NumPy/torch CPU/CUDA), `metadata.json` oraz manifest SHA-256.
Metadane obejmują schemat 1, rewizję/pliki bazowe, efektywną konfigurację,
manifest/train SHA, ID, processor/tokenizer, LoRA i środowisko bibliotek.

Zapis wyłącznie po kroku i wyczyszczeniu gradientów; zapis początkowy chroni
punkt przed pierwszą aktualizacją. Unikalny `.partial` na tym samym woluminie
jest odczytywany kontrolnie, weryfikowany i publikowany istniejącym atomowym
rename z krótkimi ponowieniami konfliktów Windows. Dopiero potem zmienia się
`latest.txt`. Przerwany zapis zachowuje poprzedni checkpoint; publiczny odczyt
odrzuca `.partial`. Nie ma automatycznej retencji/usuwania.

Zapis zachowuje RNG sprzed serializacji. Odczyt sprawdza hashe, schemat,
tożsamość modelu/config/danych/procesora/środowiska, klucze i kształty adaptera,
stan samplera i granicę kroku, potem przywraca AdamW, scheduler i RNG.
Wznowienie zaczyna od następnego nieprzetworzonego ID. PyTorch odczytuje lokalny
stan z `weights_only=False`; należy używać własnych zaufanych checkpointów.
Osobny zapieczętowany `adapter/` jest eksportem inferencji, nie pełnym stanem.

Walidacja jest odcinkowa: zapis → zakończenie procesu → osobny proces z adapterem
i 36 validation → surowe odpowiedzi → istniejący evaluator/verify → oddzielna
diagnostyka → ręczne wznowienie treningu. `validation_due` kończy proces na
skonfigurowanej granicy. W pamięci pozostaje jeden model. Koszt: ponowne
ładowanie modelu i checkpointu. Pełne 36 z nowym adapterem nie zostało jeszcze
wykonane; wdrożona ścieżka używa sprawdzonej generacji 4.1 i ewaluatora.
Generowanie jest takie samo jak bazowe NF4, bez zmiany instrukcji i naprawy JSON.

## Zasoby, terminal i błędy

Przed modelem: globalny VRAM NVIDIA ≤450 MiB, dostępny RAM ≥4096 MiB,
commit headroom ≥8192 MiB. Windows commit pochodzi z `GetPerformanceInfo`
(CommitTotal, CommitLimit, PageSize), nie z przybliżenia swap; brak odczytu blokuje
start. Pierwszy preflight poprawnie odmówił przy 493 MiB GPU. Autor zamknął
zbędne aplikacje; progu nie podnoszono. Następny preflight i smoke przeszły.

Wątek próbkuje globalny VRAM, RSS, RAM/commit i CPU co około 0,5 s; główny
wątek zapisuje allocated/reserved i szczyty PyTorch. JSONL zawiera minima
RAM/commit, szczyty RSS/globalnego VRAM, ID, tokeny, loss, LR i czasy kroków.
Terminal pokazuje skrót, a stdout/stderr zapisuje PowerShell. Kody: 0 dla
kontrolowanego końca, 1 dla błędu, 3 dla przerwania z powodu pamięci hosta.
Próbkowanie może pominąć krótki globalny pik. Reserved pod WDDM nie jest
pomiarem fizycznego VRAM; zmienne aktywacje mogą powiększać cache i RAM/commit.

Nie zmieniano alokatora. Po granicy kroku, bez grafu i gradientów, nieaktywne
bloki zwalnia się tylko, gdy reserved przekroczy skonfigurowane 8000 MiB;
0 wyłącza tę politykę. W B1 spadło ono 8222→4690 MiB, w B2 8190→4750 MiB.
Nie jest to dowód rozwiązania wszystkich problemów pamięci ani plateau.
Rozdzielczości, LoRA i precyzji nie zmieniano.

NaN/Inf straty lub normy kończy proces. OOM jest zapisywany bez ponowień
i bez checkpointu częściowego kroku; ostatni poprawny pozostaje. Krytyczny
RAM/commit jest kontrolowany na granicach, także według próbek z wnętrza kroku,
i prowadzi do zapisu/zakończenia. STOP i `--stop-after` działają na granicy kroku.
Ctrl+C/zamknięcie okna nie gwarantują zachowania niezapisanych kroków.
Nie zmieniano usług, sterowników ani pliku stronicowania.

## Wykonane próby

Najpierw istniejące **334/334 testy offline**, następnie nowe testy i dopiero GPU.
Sprawdzono CLI, rzeczywisty skrypt PowerShell, preflight, dry-run bez modelu,
odmowę full i propagację niezerowego kodu procesu.

CPU: mała losowa Llama + PEFT, bez pobierania, z dropoutem i konsumpcją RNG
Python/NumPy/torch. Trzy procesy: A=3 kroki, B1=1, B2=wznowienie+2.
Adapter, AdamW, scheduler, sampler i RNG dokładnie równe. To osobny test mechanizmu.

GPU: **6 aktualizacji optymalizatora łącznie**, 9 różnych train, bez OOM/NaN/Inf.
A=3 kroki, B1=1 i koniec procesu, B2=wznowienie+2. Ta sama kolejność ID,
straty 1,959446 → 1,776291 → 1,687358, grupy 4/4/1.

| Proces | Kroki | Czas kroków [s] | Peak global VRAM [MiB] | Peak allocated/reserved [MiB] | Peak RSS [MiB] | Min RAM / commit headroom [MiB] |
| --- | --- | --- | --- | --- | --- | --- |
| A | 3 | 7,85 / 4,06 / 1,01 | 7729 | 5133 / 7162 | 2054 | 8243 / 15759 |
| B1 | 1 | 5,39 | 7878 | 5134 / 8222 | 2786 | 7656 / 15203 |
| B2 | 2 | 5,13 / 1,06 | 7907 | 5127 / 8190 | 2771 | 7689 / 15236 |

Końcowe adaptery: exact=True, maksymalna różnica 0. AdamW, scheduler, sampler
i RNG: exact=True. Ustalona tolerancja FP32 adaptera/momentów: atol=1e-6,
rtol=1e-5; osiągnięto silniejszą dokładną zgodność. Nie rozszerzamy tego dowodu
na inne GPU, sterowniki, biblioteki ani długie przebiegi.

Osobny proces wczytał eksport B2, potwierdził dokładnie 112 tensorów i wykonał
generację jednego train w 5,77 s. Nie oceniano jego jakości. Ostrzeżenie
Transformers o temperature/top_p/top_k dotyczyło bazowych ustawień ignorowanych
przy do_sample=False; parametrów generowania nie zmieniono.

Końcowo **355/355 testów offline OK**, bez pominięć, w 143,822 s; osobno
**3/3 maskowania** i **4/4 autograd** w środowisku VLM. Zwykły zestaw wzrósł
z 334 o 21 testów. Obejmuje konfigurację, izolację splitów, grupy końcowe,
shuffle/cursor, STOP, granicę walidacji, pamięć krytyczną, symulowany OOM,
niekompletne/uszkodzone/niezgodne checkpointy, przerwany zapis, JSONL i Markdown.
Stany AdamW/schedulera/RNG sprawdzono też rzeczywistym porównaniem procesów.

Wcześniejsze 350/350 było OK. Jedna późniejsza próba 354 testów wykryła zmianę
hashy źródeł, ponieważ agent jeszcze edytował nowy kod w trakcie jej pracy;
nie była to regresja generatora. Końcowe wykonanie nastąpiło po zamrożeniu src,
z PYTHONUTF8=1 i PYTHONIOENCODING=utf-8 dla procesów potomnych. Wcześniejsze logi
i nieudany preflight zachowano. Dowód końcowy: `tests-delivery.log` i
`tests-delivery-exit.json`; wcześniejszy poprawny: `tests-final-frozen.log`.

## OFICJALNA OCENA `sr-eval-v1`

Nie wykonano nowej pełnej walidacji adaptera. Historyczne BF16 i NF4 ponownie
zweryfikowano oficjalnym CLI, bez zmiany predykcji i protokołu. Oba: 36 odpowiedzi,
0 poprawnych JSON, TP=0, FP=0, FN=147, micro-F1=0 przy 0,5 ATR. Wszystkie mają
zewnętrzny Markdown. To pozostaje oficjalnym wynikiem.

## DIAGNOSTYKA TRAFNOŚCI CEN

Moduł usuwa tylko pojedyncze ogrodzenie całej odpowiedzi: trzy backticki, opcjonalnie z oznaczeniem json,
otwarcie i zamknięcie na własnych liniach. Obcy tekst, wewnętrzne/powtórzone
ogrodzenia, inne języki, błędne pola, wartości i duplikaty kluczy nie są naprawiane.
Wnętrze przechodzi istniejący ścisły parser. Scoring, tolerancje, matching i ATR
pochodzą z niezmienionego sr-eval-v1. Oba modele: Markdown zdjęto z 36/36,
36/36 poprawnych zawartości JSON. Surowe predykcje pozostały bez zmian.

| Model | ATR | TP | FP | FN | Pomocniczy micro-F1 | MAE/ATR dopasowanych par |
| --- | --- | --- | --- | --- | --- | --- |
| NF4 | 0,25 | 24 | 192 | 123 | 0,132231 | 0,126086 |
| NF4 | 0,5 | 48 | 168 | 99 | 0,264463 | 0,237527 |
| NF4 | 1,0 | 75 | 141 | 72 | 0,413223 | 0,434113 |
| BF16 | 0,25 | 32 | 184 | 115 | 0,176309 | 0,100282 |
| BF16 | 0,5 | 58 | 158 | 89 | 0,319559 | 0,212296 |
| BF16 | 1,0 | 87 | 129 | 60 | 0,479339 | 0,404137 |

Odtworzono oczekiwane regresje; wyniki nie są stałymi w funkcji scoringu.

| Model | Symbol, 0,5 ATR | TP / FP / FN | Pomocniczy F1 | MAE USDT dopasowanych |
| --- | --- | --- | --- | --- |
| NF4 | BTCUSDT | 30 / 78 / 48 | 0,322581 | 319,9937 |
| NF4 | ETHUSDT | 18 / 90 / 51 | 0,203390 | 15,5550 |
| BF16 | BTCUSDT | 31 / 77 / 47 | 0,333333 | 283,6094 |
| BF16 | ETHUSDT | 27 / 81 / 42 | 0,305085 | 13,2070 |

Oba generują 216 poziomów wobec 147 referencyjnych, zawsze 3 supports i 3
resistances, bez pustych list. NF4: 14/108 wsparć i 18/108 oporów po niewłaściwej
stronie ostatniego Close; BF16: 12/108 i 28/108. Równość Close zalicza się do
niewłaściwej strony (wsparcie ma być niżej, opór wyżej). Pomiar nie zmienia predykcji.

Wszystkie P/R, przekroje supports/resistances i symbol×strona, liczebności, puste
referencje i MAE są w `diagnostics-{nf4,bf16}/diagnostics.json`. Nowe zapieczętowane
kopie obok ocen: `results/evaluation/vlm42-price-baseline-20261110-a-{nf4,bf16}/`.
Pomocnicze F1 nie jest oficjalne. MAE dotyczy tylko dopasowanych par; referencje
są poziomami naszego algorytmu, nie dowodem prawdy rynkowej.

## Propozycja etapu 4.3 — do osobnego zatwierdzenia

Jeden ograniczony eksperyment: 2 epoki / 350 kroków, LR=0,0002, linear decay,
18 kroków warmup (~5%), seed=20261110, batch=1, accumulation=4, limit 2048,
log co krok, checkpoint co 25 i na końcu epoki, validation po każdej epoce
(175 kroków). Warmup zaczyna LR=0 zgodnie z LambdaLR; smoke ma jawnie warmup=0.

Przed wykonaniem zatwierdzić ranking: maksymalne **oficjalne micro-F1 przy 0,5 ATR**;
przy remisie wyższy udział poprawnych JSON, potem wcześniejszy globalny krok.
Diagnostyczne F1/MAE są opisowe, bez wpływu na ranking. Bez siatki hiperparametrów,
dwóch dodatkowych epok automatycznie ani dobierania czegokolwiek na 66 testowych.
Dwa punkty validation ograniczają dobór na niewielkim zbiorze 36 obrazów.

Zakończenie wcześniej: błąd/NaN/OOM, krytyczna pamięć lub żądanie autora;
bez zatrzymywania na podstawie pomocniczego F1. Po dwóch epokach zakończyć
i ocenić plan. OOM: zachować logi/checkpoint, ustalić przyczynę, bez automatycznych
ponowień, zmniejszania obrazu/rank. Zmieniona konfiguracja oznacza nowy eksperyment.

Pełne grupy kosztowały około 4–8 s/krok, końcowa około 1 s. 350 kroków daje
23–47 minut pętli, dwie bazowo podobne walidacje około 6–7 minut generacji,
dodatkowo zapis, hash i ładowanie. Roboczo **30–60 minut całości**, z dużą
niepewnością WDDM/fragmentacji i bardzo krótkiej próby. To nie gwarancja czasu
ani stabilności. Najwyższa próbka 7907/8192 MiB: tylko 285 MiB nominalnego zapasu.

## Integralność i przekazanie

Przed pracą zapisano Git status/diff i inwentarz SHA-256 **13 191 historycznych
plików**, w tym **3212 plików produkcyjnego zbioru**. Kontrola końcowa:
**13 191/13 191 bez zmian, 3212/3212 plików zbioru bez zmian**, zero usunięć
i nieoczekiwanych dodatków (`integrity-summary.json`). Dozwolone nowe lokalizacje to katalog iteracji i dwa
osobne katalogi diagnostyczne. Oficjalny evaluator, prompt, OHLC, PNG, etykiety,
generator, ATR i stare adaptery/raporty pozostały bez zmian. Nie wykonano operacji
commit, push, reset, stash ani clean.

Lokalne końcowe checkpointy: `gpu-a/checkpoints/step-000003/` i
`gpu-b2/checkpoints/step-000003/` pod katalogiem iteracji. Punkt przerwania:
`gpu-b1/checkpoints/step-000001/`. Eksporty: `gpu-*/adapter/`. Dowody:
`gpu-resume-comparison.json`, `smoke-summary.json`, logi konsoli i `events.jsonl`.

[Instrukcja autora](INSTRUKCJA_POWERSHELL_4_2.md). Handoff:
`handoff/vlm42-pipeline-20261110-a.zip` i zewnętrzny SHA-256. ZIP zawiera aktywny
kod, konfiguracje, testy, dokumentację i małe wyniki iteracji z własnym manifestem;
wyklucza wagi, adaptery, state.pt, dane, środowiska i cache. Metadane checkpointów
opisują pliki lokalne — sama paczka nie służy do wznowienia. Po przekazaniu
nie rozpoczynać pełnego treningu ani etapu 4.3.

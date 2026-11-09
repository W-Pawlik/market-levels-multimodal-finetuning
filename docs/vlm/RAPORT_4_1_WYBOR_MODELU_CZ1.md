# Etap 4.1, część 1 — audyt i wykonalność lokalnego VLM

Data: **2026-11-09**. Przebieg: `vlm-feasibility-20261109-210209`.
Wyniki: `results/vlm-feasibility-20261109-210209/`.

**Oba wskazane modele działają lokalnie na RTX 3060 Ti 8 GB w BF16, przy
oryginalnym obrazie 1024 × 768. Dla Qwen3-VL wykonano poprawnie dokładnie jeden
krok QLoRA.** Oba modele bazowe naruszają jednak wymagany format odpowiedzi:
wszystkie 32 odpowiedzi S/R zawierają Markdown wokół JSON. Żadnej nie naprawiono.
Rekomendujemy Qwen3-VL jako głównego kandydata do dalszych prób technicznych;
nie jest to ostateczny wybór modelu ani potwierdzenie jakości lub stabilności
pełnego treningu. Próba adaptera wykorzystała niemal całą dostępną pamięć GPU.

## A. Rzeczywisty sprzęt i środowisko

| Element | Wynik lokalnego pomiaru |
| --- | --- |
| GPU | NVIDIA GeForce RTX 3060 Ti, 8192 MiB, Compute Capability 8.6 |
| Początkowe VRAM według NVIDIA | użyte 894 MiB, wolne 7131 MiB; wartości zmieniają się wraz z pulpitem |
| Sterownik | 621.14, WDDM |
| CUDA wskazywana przez sterownik | UMD 13.5; to nie wersja zainstalowanego toolkitu |
| CUDA używana przez PyTorch | 12.8, wheel `2.10.0+cu128`, cuDNN 91002 |
| CPU | AMD Ryzen 5 3600X, 6 rdzeni / 12 wątków |
| RAM | 16 722 384 KiB widoczne dla systemu, około 15,95 GiB; początkowo wolne około 5,43 GiB |
| Dysk C przed pracą | 153 311 256 576 B wolne |
| Dysk D przed pracą | 513 446 580 224 B wolne |
| Windows | Windows 10 Pro, 10.0.19045; WSL raportuje pełną wersję 19045.7807 |
| WSL | 3.0.3.0, domyślna wersja 2, jądro pakietu 6.18.54.1-1 |
| Zainstalowane dystrybucje | tylko `docker-desktop`, początkowo zatrzymana; brak Ubuntu |
| Jądro uruchomionej dystrybucji | `6.18.54.1-microsoft-standard-WSL2` |
| GPU w WSL | istnieje `/dev/dxg`; `nvidia-smi` w dystrybucji Dockera nie daje się uruchomić |
| Python początkowo | tylko CPython 3.13.15 w launcherze |

W `.venv` nie było torch, torchvision, Transformers, PEFT, Accelerate ani
bitsandbytes. Były Pillow 13.0.0 i Matplotlib 3.11.2. Tego środowiska nie zmieniano.
Brak `nvcc` w PATH nie blokuje wykorzystanych binarnych bibliotek CUDA.

### Rzeczywisty test CUDA i precyzji

`cuda-probe.json` zawiera pomiar PyTorch: `cuda.is_available() == True`,
CC `(8,6)`, `is_bf16_supported(including_emulation=False) == True`.
Macierze 256 × 256 przeszły forward i backward w FP16, BF16 i FP32, z wynikami
i gradientami bez NaN/Inf. BF16 nie zostało przyjęte wyłącznie na podstawie nazwy GPU.
Test powtórzono działającym skryptem PowerShell w `reproducible-audit/`.

WSL2 jest obecne, lecz nie ma gotowej dystrybucji badawczej. Sam `/dev/dxg`
nie dowodzi działania PyTorch wewnątrz WSL. Nie instalowano Ubuntu, komponentów
Windows, sterowników ani systemowego CUDA. Odczyt jądra i urządzenia uruchomił
techniczną dystrybucję Dockera; nie instalowano w niej pakietów.

**Środowisko sprawdzone praktycznie w tej iteracji: izolowany Windows.**
Docelowo warto przygotować osobne Ubuntu WSL2, jeśli potrzebne będą narzędzia
wymagające Linuksa; ich zgodność trzeba sprawdzić ponownie. Nie ma potrzeby
zmiany systemu tylko po to, aby odtworzyć już udany pilot. NVIDIA opisuje
udostępnianie GPU przez sterownik Windows i zakaz instalowania linuksowego
sterownika w WSL: [CUDA on WSL](https://docs.nvidia.com/cuda/wsl-user-guide/index.html).

### Izolacja i zależności

- Interpreter zarządzany przez istniejące `uv`: Python **3.12.12**, pod
  `D:/ml-envs/python/`; instalacja bez rejestracji i bez dodawania binarek do PATH.
- Środowisko: `D:/ml-envs/market-levels-vlm/`.
- Wagi: `D:/ml-cache/market-levels/hub/`; cache instalatora w sąsiednim `uv/`.
- Główne wersje: torch 2.10.0+cu128, torchvision 0.25.0+cu128,
  Transformers 5.3.0, PEFT 0.18.1, bitsandbytes 0.49.2, Accelerate 1.12.0,
  Pillow 12.1.1 i psutil 7.2.2.
- Pełne wersje są w `configs/vlm/environment-lock.txt` i `requirements-freeze.txt`.
  `uv pip check`: wszystkie 46 zainstalowanych pakietów zgodne.

Wybrano przypięty stos obejmujący obie architektury, z gotowymi wheelami Windows.
Transformers 5.3.0 dokumentuje Qwen3.5, a wydanie bitsandbytes 0.49.2 wspiera
Windows x86-64/CUDA 12.8/SM86: [Transformers](https://huggingface.co/docs/transformers/v5.3.0/model_doc/qwen3_5),
[bitsandbytes](https://huggingface.co/docs/bitsandbytes/v0.49.2/en/installation).
Nie instalowano FlashAttention, Unsloth, DeepSpeed, Tritona ani rozszerzeń ze źródeł.

## B. Checkpointy, przetwarzanie i porównanie

| Cecha | Qwen3-VL-2B-Instruct | Qwen3.5-2B |
| --- | --- | --- |
| Oficjalny identyfikator | `Qwen/Qwen3-VL-2B-Instruct` | `Qwen/Qwen3.5-2B` |
| Rewizja | `89644892e4d85e24eaac8bacfd4f463576704203` | `15852e8c16360a2fea060d615a32b45270f8a8fc` |
| Licencja i dostęp | Apache 2.0, publiczny, bez logowania | Apache 2.0, publiczny, bez logowania |
| Oficjalne wagi safetensors | 4 255 140 312 B | 4 548 221 488 B |
| Klasa Transformers | `Qwen3VLForConditionalGeneration` | `Qwen3_5ForConditionalGeneration` |
| Procesor | `Qwen3VLProcessor` | `Qwen3VLProcessor` |
| Procesor obrazu | `Qwen2VLImageProcessorFast`, wersja stosu 5.3.0 | ten sam typ i wersja stosu |
| Wariant | wskazany Instruct | wskazany checkpoint post-trained, `enable_thinking=False` |
| Inferencja | BF16, cały model na `cuda:0`, bez kwantyzacji | BF16, cały model na `cuda:0`, bez kwantyzacji |
| Ukończone zadania S/R | 8 native + 8 reduced | 8 native + 8 reduced |
| Poprawny ścisły JSON | 0/8 + 0/8 | 0/8 + 0/8 |
| Kontrolny krok adaptera | udany jeden krok NF4 + LoRA | nie wykonano; wykonalność treningu pozostaje do sprawdzenia |

Karty i konfiguracje zweryfikowano przed pobieraniem. Oba repozytoria to
checkpointy obrazu i tekstu; Qwen3.5-2B nie jest zamieniony na `-Base`, Thinking,
GGUF ani adaptację innego autora. [Karta Qwen3-VL](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct),
[karta Qwen3.5](https://huggingface.co/Qwen/Qwen3.5-2B).
Apache 2.0 dotyczy modeli; licencje kodu projektu i danych pozostają odrębne.

Łączny transfer wybranych plików modeli wyniósł **8 837 919 895 B**, poniżej
limitu 18 GB. Cache ma sprawdzone rozmiary i SHA-256; sumy dużych plików zgadzają
się z LFS oficjalnego Huba. Zachowano `download-plan.json`, `downloaded-models.json`
i `cache-summary.json`. Dane projektu nie były wysyłane do API inferencyjnego.
Ładowanie jest lokalne, z `trust_remote_code=False` i wyłączonym Hubem podczas prób.

### Te same osiem obrazów

Selekcja została ustalona przed odpowiedziami. Sortowanie po dacie początku
i ID, osobno dla instrumentu; wybrano rangi **0, 6, 11, 17 z 18**. Tylko validation.

| Instrument | Początek okna 2024 | ID |
| --- | --- | --- |
| BTCUSDT | 01-01 | `96c921e8c98c52ebb5df7050` |
| BTCUSDT | 04-30 | `87633620fa04d22cade746df` |
| BTCUSDT | 08-08 | `6ffb5806f04230de7e7f58d1` |
| BTCUSDT | 12-06 | `d6bf408fd0b0d23877ae60a0` |
| ETHUSDT | 01-01 | `d65603fe75d3817e370988af` |
| ETHUSDT | 04-30 | `a95a0451f22c064bb23fbea3` |
| ETHUSDT | 08-08 | `83135772b232d194e2f7d8d1` |
| ETHUSDT | 12-06 | `5c2240d9d0a047b98f72a960` |

Wejście modelu to obiekt obrazu RGB wczytany z oryginalnego PNG i **niezmieniona
instrukcja `pl-sr-v1` z JSONL**. ID, ścieżka, symbol, źródło, answer, ATR i OHLC
nie są dodawane do wiadomości. Odczyt metadanych służy selekcji i kontroli braku
overlays, a nie budowaniu promptu. Etykiety są dostępne wyłącznie oddzielnemu
kodowi uczenia lub późniejszej oceny. Wagi obu modeli pozostają bazowe w inferencji.

Użyto oficjalnego `apply_chat_template`, bez few-shot i dodatkowego system promptu.
Seed 20261109, `do_sample=False`, `num_beams=1`, `max_new_tokens=256`, cache KV.
Włączono deterministyczne algorytmy z ostrzeżeniem i wyłączono TF32. Nie jest to
gwarancja identycznych wyników między wersjami bibliotek, sterowników i GPU.
Żadna odpowiedź S/R nie osiągnęła limitu tokenów.

### Rozdzielczość i udział obrazu

| Ustawienie | Limit pikseli | Faktyczny obraz obu modeli | Siatka t,h,w | Tokeny obrazu | Tokeny wejścia Q3-VL / Q3.5 |
| --- | ---: | --- | --- | ---: | ---: |
| native | 786432 | 1024 × 768 | 1,48,64 | 768 | 845 / 836 |
| reduced | 393216 | 704 × 512 | 1,32,44 | 352 | 429 / 420 |

Minimalny budżet to 65536 pikseli. Patch 16, merge 2; tokeny policzono zarówno
z siatki, jak i rzeczywistych `image_pad` we wejściu. Oba wyniki są zgodne.
Zmienia się wyłącznie przetwarzanie w RAM. Nie zmieniano zapisanych PNG.
Oficjalny opis API wyjaśnia budżety pikseli pomimo nazw `shortest_edge` i
`longest_edge`: [Qwen3-VL](https://github.com/QwenLM/Qwen3-VL#quickstart).

Każde wywołanie S/R zarejestrowało jeden forward encodera wizualnego. Kontrola
na rzeczywistym wykresie identyfikuje świeczki, kolory i nazwy osi. Ten sam prompt
na białym obrazie daje inne, zmyślone opisy. To wraz z pikselami, siatką i hookiem
potwierdza udział obrazu, ale ujawnia skłonność do halucynacji przy braku informacji.
Qwen3.5 trafniej opisuje znaczenie kolorów; Qwen3-VL myli wzrost/spadek z wysokością.

Kontrolny prompt prosił o dwie etykiety osi cenowej; oba modele podały głównie
nazwy osi zamiast dwóch liczbowych ticków. Nie potwierdzono więc precyzyjnego OCR
podziałki. Niższa rozdzielczość zmienia wybrane ceny S/R i zmniejsza napisy oraz
knoty świec. Nie ma podstaw, by uznać ją za jakościowo równoważną oryginałowi,
ani by przypisać jej konkretną zmierzoną stratę OCR. Rekomendowany punkt odniesienia
to native; ewentualne obniżenie wymaga osobnej kontroli czytelności osi.

### Pamięć i czas

MiB = 2^20 B, GiB = 2^30 B. Poniżej peak allocated PyTorch jest pamięcią
tensorów, a globalne VRAM z `nvidia-smi` obejmuje również pulpit i inne procesy.
Globalne VRAM/RSS próbkowano co około 0,4 s; bardzo krótkie piki mogą być pominięte.
PyTorch niezależnie zapisuje peak allocated/reserved. Pełne szeregi czasowe
i pomiary przed/po każdym etapem są w JSON-ach.

| Pomiar | Qwen3-VL native | Qwen3-VL reduced | Qwen3.5 native | Qwen3.5 reduced |
| --- | ---: | ---: | ---: | ---: |
| Allocated przed modelem | 0 | ten sam załadowany model | 0 | ten sam załadowany model |
| Allocated po załadowaniu modelu, GiB | 3,96 | 3,96 | 4,12 | 4,12 |
| Peak allocated inferencji S/R, GiB | 4,27 | 4,11 | 4,31 | 4,24 |
| Peak globalne VRAM, MiB, wraz z kontrolami | 5552 | 5583 | 5542 | 5572 |
| Peak RSS procesu po załadowaniu, GiB | 1,79 | 1,79 | 1,83 | 1,83 |
| Średni czas odczytu PNG, s | 0,0254 | 0,0044 | 0,0200 | 0,0040 |
| Średnie przetwarzanie CPU, s | 0,0219 | 0,0167 | 0,0241 | 0,0193 |
| Średnie generowanie po kontrolach, s | 4,166 | 3,665 | 5,214 | 4,546 |
| Średnie tokeny odpowiedzi | 68,375 | 68,375 | 80,500 | 80,375 |
| Średnie tokeny/s, z prefillem | 16,51 | 18,77 | 15,48 | 17,71 |

Przeniesienie gotowego wejścia na GPU trwało średnio 0,002–0,004 s i jest mierzone
oddzielnie. Czas generowania obejmuje prefill i decoding, bez odczytu obrazu,
przetwarzania procesora i ładowania modelu. Tokens/s nie jest samą szybkością
dekodera. Kontrole obrazu/pustego obrazu stanowią rozgrzewkę dla każdej rozdzielczości.
Natywny wariant wykonano pierwszy; cache alokatora pozostawał aktywny podczas
reduced, stąd globalne VRAM nie musi się zmniejszyć mimo mniejszego peak allocated.

Ładowanie modelu/procesora: Qwen3-VL **4,39 / 1,37 s**, Qwen3.5 **55,66 / 2,74 s**.
Peak RSS podczas ładowania: odpowiednio **4,30 / 4,81 GiB**. Qwen3-VL był już
w cache plików po pierwszej nieudanej próbie diagnostyki; jej pasek ładowania
pokazuje około 48 s. Te czasy ładowania nie stanowią uczciwego benchmarku
zimnego cache obu architektur. Zapisano je jako obserwacje konkretnego przebiegu.

Wszystkie parametry obu modeli były na `cuda:0`; nie skonfigurowano CPU/disk
offload. Qwen3.5 ostrzega o braku szybkiej ścieżki DeltaNet/causal-conv1d
i korzysta z implementacji PyTorch na GPU. Nie przedstawiamy tego jako
wydajności zoptymalizowanego silnika Linux. Ostrzeżenie jest zachowane w logu.

### Wstępna analiza ośmiu odpowiedzi przy native

W obu modelach każda odpowiedź zawiera po trzy liczby w obu listach, ale
otoczone blokiem Markdown. Poniższe uwagi są ręcznym przeglądem surowego tekstu;
nie wyodrębnia się z niego naprawionych predykcji. Skala i ostatnie Close zostały
sprawdzone **po inferencji**, tylko dla tych ośmiu okien, w oddzielnym pliku
`post-inference-scale-review.json`. Nie trafiały do modeli.

| Okno | Qwen3-VL | Qwen3.5 |
| --- | --- | --- |
| BTC 01-01 | właściwa skala dziesiątek tysięcy; supports 42000–44000 powyżej Close 41696,04 | supports 42000–42400 również powyżej Close |
| BTC 04-30 | resistances 60000–62000 poniżej Close 66274,01 | resistances 61000–65000 poniżej Close |
| BTC 08-08 | ceny w zakresie wykresu; strony zgodne z położeniem względem Close | podobnie, drobniejsze regularne odstępy; bez dowodu zgodności z referencją |
| BTC 12-06 | obie strony względem Close 99429,60 rozmieszczone poprawnie | support 100000 powyżej Close; pozostałe wymagają oceny względem referencji |
| ETH 01-01 | opór 2400 poniżej Close 2472,01 | wszystkie opory 2280–2320 poniżej Close |
| ETH 04-30 | opór 3100–3300; 3300 wychodzi nieco ponad górę osi około 3272,65 | opory 3000–3020 poniżej Close 3071,19 |
| ETH 08-08 | wsparcie 2500 powyżej Close 2457,33 | wszystkie wsparcia 2550–2600 powyżej Close |
| ETH 12-06 | liczby w skali wykresu, obie strony względem Close poprawne | obie strony względem Close poprawne; opory skupione blisko 3500–3600 |

Oba modele rozpoznają ogólny typ zadania i rozróżniają skalę BTC od ETH.
Zwracają jednak regularne, często okrągłe siatki cen, mylą klasyfikację stron
i nie dowodzą odtworzenia operacyjnej definicji poziomów S/R. Sam odpowiedni
rząd wielkości ceny nie jest poprawnym wskazaniem poziomu.

Pomocniczą ocenę policzono istniejącymi `score_example` i `aggregate`, bez zmiany
ewaluatora. Dla każdego modelu i rozdzielczości: **0/8 poprawnych odpowiedzi,
TP=0, FP=0, FN=34, micro-F1=0** przy 0,25 / 0,5 / 1,0 ATR. FP=0 wynika
z zamrożonej reguły błędnego formatu; nie oznacza braku błędnych cen.
To ocena ośmiu wybranych obrazów, **nie pełna walidacja 36 przykładów**.
Nie usuwano backticków i nie obchodzono kontroli kompletności normalnego CLI.
Zero obu modeli nie daje podstaw do ich rankingu jakościowego.

## C. Próba techniczna dostrajania Qwen3-VL

Oficjalny projekt opisuje LoRA i niezależne zamrażanie części wizualnej:
[Qwen3-VL fine-tuning](https://github.com/QwenLM/Qwen3-VL/blob/main/qwen-vl-finetune/README.md).
NF4, double quantization i przygotowanie modelu do k-bit training wynikają
z interfejsu PEFT/bitsandbytes: [PEFT quantization](https://huggingface.co/docs/peft/v0.18.0/en/developer_guides/quantization).
Próba korzysta z lokalnej implementacji maskowania i multimodalnego forward;
nie uruchamia bez zmian tekstowego skryptu treningowego.

| Parametr / kontrola | Wynik |
| --- | --- |
| Metoda | NF4 4-bit + double quantization, obliczenia BF16, LoRA |
| Część wizualna | zamrożona, BF16, wyłączona z kwantyzacji |
| Adapter | językowe `q_proj` i `v_proj`, 56 modułów, rank 8, alpha 16, dropout 0 |
| Parametry trenowane | 1 605 632; 112 tensorów adaptera |
| Optymalizator | AdamW, LR 0,0002, domyślny weight decay 0,01, clipping normy do 1 |
| Batch i kroki | cztery microbatche po 1; akumulacja; **dokładnie 1 optimizer.step** |
| Pamięć | gradient checkpointing z `use_reentrant=False`, KV cache wyłączony |
| Obraz | 1024 × 768, 768 tokenów obrazu w każdym przykładzie |
| Długości całych sekwencji | 885, 915, 903, 884; bez obcinania |
| Nadzorowane tokeny odpowiedzi | 40, 70, 58, 39; po 845 tokenów prefiksu zamaskowanych -100 |
| Loss czterech przykładów | 2,183405; 1,459504; 1,549071; 2,084109 — wszystkie skończone |
| Gradienty | obecne w 112 tensorach; 56 z niezerowym gradientem; wszystkie skończone |
| Norma gradientu przed clippingiem | 2,334507 |
| Zmiana parametrów adaptera | 112 tensorów; największe zmiany `lora_B` około 0,0002 |
| Udział obrazu | 4 forwardy zamrożonego encodera; nie trenowano parametrów wizualnych |
| Czas czterech forward/backward i jednego kroku | 10,237 s, z przygotowaniem microbatchy, bez ładowania modelu |
| Peak allocated PyTorch | 5 404 739 584 B = około 5,03 GiB |
| Peak reserved PyTorch | 8 518 631 424 B = 8124 MiB |
| Peak globalnego VRAM z próbek NVIDIA | **7923 MiB z 8192 MiB** |
| Peak RSS podczas kroku | około 2,77 GiB |
| Ładowanie NF4 | 60,65 s; osobny pomiar przed krokiem |
| OOM / NaN / Inf | nie wystąpiły w wykonanej próbie |

W początkowym LoRA macierze B są zerowe, więc gradient A może być zerowy
w pierwszym kroku. Drobne zmiany A wynikają także z weight decay; nie opisujemy
112 zmienionych tensorów jako 112 niezerowych gradientów. Aktualizacja B
i obecność skończonych gradientów potwierdzają działanie kroku.

Wybrano tylko cztery train: po pierwszym syntetycznym ID po sortowaniu
i ostatnim chronologicznym realnym oknie każdego instrumentu:
`002976a589880e9fc02ce585`, `7283c009c4d6d16fdbe64575`,
`01cee4ac966cf4532b5816bf`, `eb041624f86fdc2fa17274c8`.
Odpowiedzi JSON są celami assistant. Prefix obrazu/instrukcji jest sprawdzany
bajtowo na poziomie tokenów przed maskowaniem, a nie szacowany po długości tekstu.
Trzy osobne testy na rzeczywistych tensorach PyTorch potwierdziły maskowanie
obrazu/instrukcji, zachowanie odpowiedzi/EOS oraz odrzucenie złego prefiksu/braku celu.

Adapter zapisano lokalnie w `qwen3-vl-train-step-a/adapter/`: safetensors ma
6 438 952 B. Odczyt CPU potwierdził 112 tensorów bez NaN/Inf i 56 niezerowych
macierzy B. To weryfikacja deserializacji; nie wykonano ponownego ładowania
pełnego modelu z adapterem ani inferencji dostrojonej wersji. Adapter nie trafia do ZIP.

**Ograniczenie pamięci jest istotne.** Sukces pojedynczego kroku nie gwarantuje
stabilności dłuższych lub trudniejszych batchy. Peak globalny pozostawia około
269 MiB do nominalnej pojemności; wartości reserved i globalnego VRAM mierzą
różne rzeczy. WDDM zarządza pamięcią wirtualną GPU, więc nie należy z ich różnicy
wyciągać wniosku o dużym fizycznym zapasie. Wszystkie parametry miały urządzenie
CUDA i nie skonfigurowano CPU offload; nie mierzono jednak osobno potencjalnego
stronicowania przez WDDM. Nie wykonano dodatkowych kroków po sukcesie.

### Qwen3.5 — wykonalność uczenia bez praktycznego kroku

Nie uruchomiono treningu Qwen3.5. Inference BF16 mieści się w pamięci, ale
architektura ma naprzemienne warstwy DeltaNet i pełnej uwagi, a lokalny Windows
nie ma szybkich kerneli. Nie przenosimy na nią automatycznie listy modułów ani
konfiguracji QLoRA Qwen3-VL.

Dokumentacja Unsloth opisuje multimodalny LoRA Qwen3.5, lecz odradza QLoRA tej
rodziny ze względu na różnice kwantyzacji. Jej podawany VRAM nie jest pomiarem
naszego obrazu i stosu: [przewodnik producenta narzędzia](https://unsloth.ai/docs/models/qwen3.5/fine-tune).
Potwierdza to istnienie ścieżki dostrajania, nie jej zgodność z obecnym środowiskiem.
Po uzyskaniu jednego poprawnego kroku głównego kandydata, przy tak małym zapasie
VRAM, nie dokładano drugiego niezweryfikowanego stosu. B nie jest uznany za
niemożliwy do dostrojenia; jego praktyczna wykonalność pozostaje niepotwierdzona.

## D. Rekomendacja i następne decyzje

1. **Główny kandydat do dalszej kontroli: Qwen3-VL-2B-Instruct.** Przesądza
   udany multimodalny krok adaptera na rzeczywistym sprzęcie, działający
   stos i prostsza obsługa. Nie ma dowodu przewagi jakościowej nad Qwen3.5.
2. **Metoda: QLoRA NF4, rank 8, początkowo tylko językowe q/v, zamrożona część
   wizualna, batch 1 i gradient checkpointing.** To sprawdzony punkt startowy
   diagnostyki, nie zatwierdzony zestaw hiperparametrów pełnego eksperymentu.
3. **System: do odtworzenia pilota użyć sprawdzonego izolowanego Windows.**
   Ubuntu WSL2 rekomendujemy do przygotowania docelowego środowiska Linux,
   jeśli autor wybierze tę drogę; wymaga oddzielnego testu CUDA i tego samego kroku.
4. **Obraz: utrzymać native jako odniesienie.** Rozmiar 704 × 512 daje mniejsze
   aktywacje i szybszą inferencję, lecz nie potwierdzono zachowania czytelności
   osi ani jakości poziomów. Nie zmieniać PNG produkcyjnych.
5. **Przed pełnym treningiem sprawdzić stabilność pamięci** na zróżnicowanych
   długościach train, kontrolę alokatora i zapas względem innych aplikacji GPU.
   Rozważyć jawny limit pamięci lub mniejszy budżet obrazu dopiero z pomiarem
   i oceną czytelności. Nie uznawać obecnych 269 MiB za bezpieczny margines.
6. W kolejnej, oddzielnie zleconej iteracji zweryfikować zapis/wczytanie całego
   zestawu model+adapter, stabilność loss i formatu, a potem dopiero właściwy
   plan dostrajania i kompletną ocenę validation. Naprawa formatu powinna być
   oceniana jako zachowanie modelu; nie wolno poprawiać predykcji w ewaluatorze.

**Nie rozpoczęto pełnego dostrajania, inferencji na 66 testowych obrazach,
automatycznego wyboru modelu ani publikacji adapterów.** Osiem skorelowanych
czasowo obrazów nie stanowi oszacowania końcowej jakości.

## E. Kod, testy i integralność

Nowy kod jest w `modeling/`, `inference/`, `training/` oraz osobnym CLI
`vlm_feasibility`. Nie dodano ciężkich zależności do podstawowego pakietu.
Ustawienia pilotażu są w `configs/vlm/`, bez zmian parametrów generatora,
etykietowania, rendererów lub ewaluatora. Zachowano architekturę domain/io/workflows.

Wykonane kontrole:

- **317/317 testów projektu OK**, 171,501 s, zero pominięć: 300 istniejących
  i 17 nowych. Testy VLM obejmują konfigurację, format produkcyjnego JSONL,
  selekcję i ID, brak etykiet w wiadomości, brak testu, overlays, integralność
  obrazów, zapis surowego tekstu/metadanych, budżety obrazu, klasyfikację i przerwanie
  OOM oraz limity pobierania/dysku. OOM w teście jest symulowany; rzeczywistego OOM nie było.
- **3/3 testy maskowania na tensorach PyTorch OK**, oddzielnie w środowisku VLM.
- Rzeczywisty test CUDA, oba modele i procesory, 40 wywołań inferencji:
  32 S/R i 8 kontrolnych; dokładnie jeden krok optymalizatora na czterech train.
- Praktyczne uruchomienie skryptu PowerShell audytu i `uv pip check`.
- SHA-256 i liczba historycznych plików przed/po są zgodne: **12 771/12 771
  bez zmian**, w tym **3212/3212 plików produkcyjnego zbioru**; brak dodanych,
  usuniętych i zmienionych plików poza katalogiem tej iteracji.
  Hashowanie plików testowych służy integralności bajtów; nie jest ich analizą.

Początkowy working tree był czysty, mimo historycznej informacji o ponad 300
zmianach sprzed wcześniejszego commitu. Nie wykonano reset, stash, checkout,
clean, commit ani push. Historycznych wyników nie przepisywano.

Zachowano także nieudane próby techniczne: pierwsza inferencja A załadowała
wagi, ale kod pomiaru oczekiwał nieobecnego `hf_device_map` w jednoukładowym
Transformers 5; poprawiono diagnostykę na sprawdzanie urządzeń parametrów.
Pierwszy `select` ujawnił `start_utc=null` syntetyków, obsłużone obecnie bez
przypisywania im dat rynkowych. Pierwsze uruchomienie skryptu PowerShell
ujawniło problem znaków UTF-8 bez BOM w Windows PowerShell; komunikaty skryptu
zmieniono na ASCII i wykonano go ponownie. Są to błędy narzędzi pilotażu,
nie awarie modeli ani danych. Nie zmieniano rewizji modeli ani bibliotek po ich pobraniu.

Zestaw źródeł i dat dostępu jest w `sources.json`; kopie dokumentacji służą
odtwarzalności lokalnej analizy. Oficjalny adres repozytorium Qwen3.5 przekierowywał
w czasie przeglądu do Qwen3.8, dlatego wnioski o B oparto na wskazanym,
przypiętym checkpointcie i dokumentacji jego klasy, bez zmiany kandydata.

## F. Artefakty i przekazanie

- [Instrukcja PowerShell](INSTRUKCJA_POWERSHELL_4_1.md).
- `comparison.json`: zestawienie obu modeli i rozdzielczości.
- Katalogi `qwen3-vl-base-b/`, `qwen3.5-base-a/`: surowe odpowiedzi, tokeny,
  procesory, pomiary, pomocnicza ocena ośmiu obrazów.
- `qwen3-vl-train-step-a/`: metadane kroku i lokalny adapter; `adapter-readback.json`.
- `integrity-before.json`, `integrity-after.json`, `integrity-summary.json`.
- `cache-summary.json`: lokalizacja i rzeczywisty rozmiar cache modeli oraz
  wolne miejsce po pobraniu: **499 388 088 320 B**, ponad wymagane 20 GB.
- Handoff `handoff/vlm41-cz1-20261109-210209.zip`, jego manifest plików
  i suma SHA-256 obok archiwum. Zawiera kod, konfiguracje, testy, dokumenty,
  surowe odpowiedzi i pomiary; pomija modele, adapter, `.venv`, cache,
  pełny zbiór produkcyjny i zbędne historyczne dane. Ścieżki użytkownika
  w kopii wyników są anonimizowane; lokalne oryginały pozostają bez zmian.

Po tej części obliczenia modelowe zatrzymano. Dalszy eksperyment wymaga decyzji autora.

# Etap 4.1, część 2 — stabilność QLoRA i walidacja modelu bazowego

Data wykonania: 2026-11-10. Model zatwierdzony przez autora:
**Qwen/Qwen3-VL-2B-Instruct**, rewizja
`89644892e4d85e24eaac8bacfd4f463576704203`.
Artefakty: `results/vlm41-cz2-20261110-1840/`.
Nie ponawiano selekcji modeli, nie uruchamiano Qwen3.5, pełnego treningu
698 przykładów ani inferencji na 66 przykładach testowych.

## A. Stabilność QLoRA

Wykonano **8/8 kolejnych kroków jednego optymalizatora w jednym procesie**.
Wszystkie miały skończone straty i gradienty oraz rzeczywistą aktualizację
adaptera. Nie wystąpił OOM. To udana krótka próba, bez gwarancji stabilności
wielogodzinnego treningu.

Konfiguracja odpowiada udanemu krokowi części 1: NF4 i double quantization,
obliczenia BF16, SDPA, zamrożona wizja w BF16, językowe q/v, rank 8,
alpha 16, dropout 0, batch 1, akumulacja 4, checkpointing z `use_reentrant=False`,
AdamW z lr 0,0002 i clippingiem normy do 1. AdamW zachował domyślne betas
(0,9; 0,999), eps 1e-8 i weight decay 0,01. Zamrożone parametry nieobjęte
kwantyzacją poza wizją mają FP32 po przygotowaniu PEFT; wizję przywrócono do BF16.
Nie skonfigurowano CPU/disk offload. Szczegóły i źródło odtworzenia domyślnych
argumentów optymalizatora: `train/effective-training-settings.json`.

Uczono 1 605 632 parametrów LoRA w 112 tensorach. Wybrano dokładnie 32 różne
train: po 8 dla BTC/ETH × real/synthetic. W każdej grupie sortowanie po
`(answer_tokens, level_count, id)` i osiem równomiernych rang łącznie z krańcami;
grupy przeplatano, więc każdy krok zawiera wszystkie cztery grupy.
Selekcja wykorzystuje długość odpowiedzi, a nie ocenę łatwości uczenia.
Lista ID i reguła są w `train/selected-train.json`.

Wybrane przykłady mają 1–6 poziomów łącznie i 18–68 tokenów samego JSON.
Pełne sekwencje mają 865–915 tokenów, w tym **768 tokenów obrazu**;
superwizja obejmuje 20–70 tokenów odpowiedzi i zakończenia. Obrazy pozostają
1024 × 768, okna mają 120 świec. Tokeny obrazu, instrukcji i ról przed
odpowiedzią są maskowane przez porównanie rzeczywistego prefiksu tokenów.
Nie przycinano sekwencji ani odpowiedzi. Validation/test nie aktualizowały wag.

| Krok | Przykłady narastająco | Loss | Norma przed clip | Czas [s] | Peak allocated [MiB] | Peak reserved [MiB] | Globalny VRAM [MiB] | Peak RSS [MiB] | Zmienione tensory |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 4 | 2.359377 | 4.1782 | 19.45 | 5074 | 6534 | 7012 | 1166 | 112 |
| 2 | 8 | 2.127096 | 2.9589 | 5.05 | 5117 | 8082 | 7936 | 1777 | 112 |
| 3 | 12 | 1.852505 | 2.4609 | 7.28 | 5117 | 9630 | 7948 | 3076 | 112 |
| 4 | 16 | 1.640418 | 2.1833 | 9.01 | 5125 | 11190 | 7936 | 4488 | 112 |
| 5 | 20 | 1.380098 | 1.5758 | 5.95 | 5133 | 11190 | 7936 | 4492 | 112 |
| 6 | 24 | 1.285998 | 1.2302 | 6.09 | 5147 | 12768 | 7935 | 6070 | 112 |
| 7 | 28 | 1.166519 | 0.8611 | 6.89 | 5153 | 12768 | 7935 | 6198 | 112 |
| 8 | 32 | 1.164053 | 0.6058 | 8.55 | 5173 | 14364 | 7935 | 7564 | 112 |

**Pamięć wymaga optymalizacji przed pełnym treningiem.** `allocated` po kroku
pozostaje około 2749 MiB, a peak allocated wzrasta tylko o około 99 MiB przy
rosnącej długości sekwencji. Nie widać narastającego zatrzymywania aktywnych
grafów/tensorów. Jednocześnie `reserved` rośnie od 6534 do 14 364 MiB: alokator
utrzymuje coraz większy cache przy zmieniających się rozmiarach aktywacji.
Osiem kroków nie potwierdza, że ten wzrost osiągnął plateau.
Równolegle peak RSS procesu wzrósł z około 1166 do 7564 MiB. Stałe allocated
nie dowodzi zatem stałego zużycia pamięci całego procesu. Bez osobnego pomiaru
stronicowania nie rozdzielamy ilościowo wpływu cache/WDDM na RAM hosta.

Pod WDDM rezerwacja alokatora może przekraczać fizyczne 8 GiB. Nie oznacza to
takiej ilości fizycznego VRAM ani skonfigurowanego offloadu. Nie zmierzono
oddzielnie stronicowania WDDM. Globalny peak próbek `nvidia-smi` wyniósł
**7948/8192 MiB**, pozostawiając nominalnie tylko 244 MiB; próbkowanie co około
0,4 s może przeoczyć krótszy szczyt. Brak OOM nie jest dowodem bezpiecznego zapasu.

![Strata i pamięć ośmiu kroków](../../results/vlm41-cz2-20261110-1840/stability-memory.png)

Przed długim treningiem trzeba sprawdzić politykę alokatora i grupowanie
długości, powtarzając pomiary przy kontrolowanym obciążeniu GPU i pamięci hosta.
Ewentualny mniejszy budżet obrazu wymaga jawnie odrębnych warunków eksperymentu;
w tej iteracji go nie zastosowano. Nie dodano harmonogramu checkpointów ani epok.

## B. Zapis i ponowne użycie adaptera

Adapter zapisano jako safetensors, z konfiguracją i lokalnym snapshotem
tensorów. W pierwszej próbie snapshot i generacje wykonano po serializacji,
przed zakończeniem procesu, mimo nazwy `adapter-before-save.safetensors`.
Dlatego wykonano dodatkową kontrolę `resave`: ten sam adapter bez aktualizacji
wag, migawka i generacja przed zapisem, następnie odczyt w kolejnym procesie.
Dowody ścisłej kolejności są w `roundtrip-source/` i `roundtrip-reload/`.
Aktualny kod treningu również wykonuje te kontrole przed serializacją.
Proces treningu zakończono. W nowym procesie załadowano
tę samą rewizję Qwen3-VL w NF4, przywrócono te same typy zamrożonych parametrów
i podłączono adapter przez `PeftModel.from_pretrained`.

**112/112 tensorów zgadza się dokładnie** między pamięcią przed zapisem,
plikiem i modelem po odczycie; wszystkie są skończone. Zweryfikowano konfigurację
próby, rewizję w ścieżce modelu bazowego, rank/alpha, strukturę i klucze stanu.

Na dwóch wybranych przed generowaniem obrazach validation, po jednym na instrument:

- `165cdad7b0527dc8aff7bb4a`;
- `165d73579cf12a5b9c7be3e7`.

Generowanie działa przed zapisem i po odczycie. Dla obu obrazów **surowy tekst
i wszystkie ID wygenerowanych tokenów są identyczne**. Pełny wektor logitów
następnego tokenu po prefiksie także jest identyczny: maksymalna różnica 0.
Z góry przyjęte kryterium logitów: `allclose(atol=0.05, rtol=0.01)`; zgodność
tekstu/tokenów raportowana oddzielnie. Nie porównywano wszystkich logitów
każdego kroku generacji. Zgodność tych dwóch prób nie gwarantuje pełnej
deterministyczności GPU w innych konfiguracjach.

Dowody: `reload/adapter-check.json`, `roundtrip-reload/adapter-check.json`,
katalogi `probe-before/` i `probe/`,
surowe odpowiedzi i pliki `logits-*.safetensors`. Nie wykonano oficjalnej oceny
jakości adaptera po ośmiu krokach. To adapter techniczny, nie model końcowy.

Pierwszą kontrolę odczytu zatrzymała zbyt restrykcyjna walidacja konfiguracji:
PEFT serializuje cele jako skróty `q_proj`, `v_proj`, choć przy tworzeniu podano
pełne nazwy. Kontrola dopuszcza teraz oba zapisy, nadal wymagając dokładnych
kluczy i wartości wszystkich tensorów, co wyklucza dodatkowe adaptery wizji.
Nieudany przebieg zachowano w `reload-attempt-a/` i `reload.log`.

## C. Pełna walidacja bazowego modelu

Przed uruchomieniem ustalono role wariantów w `preflight/roles.json`:
**BF16 — pomocniczy wynik checkpointu w wyższej precyzji**;
**NF4 bez adaptera — główny punkt odniesienia dla przyszłego NF4 + adapter**.
Nie wybierano korzystniejszego wyniku po obejrzeniu odpowiedzi.

Oba warianty korzystają z tego samego splitu validation zbioru
`data/datasets/ds35-800-20261107-a`: 36 realnych obrazów, po 18 BTCUSDT/ETHUSDT.
Obraz 1024 × 768, instrukcja `pl-sr-v1` bez zmian, oficjalny chat template,
`do_sample=False`, `num_beams=1`, `max_new_tokens=256`, cache generacji włączony.
Bez few-shot, dodatkowego system promptu, OHLC, ATR, etykiet i metadanych w rozmowie.
Tokenizer, procesor, generowanie, rewizja i środowisko są zapisane osobno
w każdym katalogu `base-*`.

NF4 zachowuje również typy niekwantyzowanych parametrów zgodne z przygotowaniem
QLoRA, aby przyszłe porównanie NF4 → NF4 + adapter miało te same warunki.
Różnice BF16–NF4 obejmują zatem kwantyzację oraz tę politykę typów; nie należy
przypisywać ich wyłącznie błędowi zaokrągleń NF4.

**Oba warianty: 36/36 odpowiedzi, 0 poprawnych JSON, micro-F1 = 0.** Nie naprawiano predykcji.

| Wariant | Tolerancja ATR | TP | FP | FN | Precision | Recall | Micro-F1 | MAE/ATR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BF16 | 0.25 | 0 | 0 | 147 | n/d | 0 | 0 | n/d |
| BF16 | 0.5 | 0 | 0 | 147 | n/d | 0 | 0 | n/d |
| BF16 | 1.0 | 0 | 0 | 147 | n/d | 0 | 0 | n/d |
| NF4 | 0.25 | 0 | 0 | 147 | n/d | 0 | 0 | n/d |
| NF4 | 0.5 | 0 | 0 | 147 | n/d | 0 | 0 | n/d |
| NF4 | 1.0 | 0 | 0 | 147 | n/d | 0 | 0 | n/d |

Precision jest nieokreślone (`null`), ponieważ TP+FP=0. MAE/ATR i MAE USDT są nieokreślone: brak dopasowanych par. FP=0 nie oznacza poprawnych poziomów; przy niepoprawnym formacie protokół nie odczytuje cen i nalicza wszystkie referencje jako FN.

| Wariant | Przekrój przy 0,5 ATR | TP | FP | FN | Micro-F1 |
| --- | --- | --- | --- | --- | --- |
| BF16 | BTCUSDT | 0 | 0 | 78 | 0 |
| BF16 | ETHUSDT | 0 | 0 | 69 | 0 |
| BF16 | supports | 0 | 0 | 73 | 0 |
| BF16 | resistances | 0 | 0 | 74 | 0 |
| BF16 | BTCUSDT / supports | 0 | 0 | 41 | 0 |
| BF16 | BTCUSDT / resistances | 0 | 0 | 37 | 0 |
| BF16 | ETHUSDT / supports | 0 | 0 | 32 | 0 |
| BF16 | ETHUSDT / resistances | 0 | 0 | 37 | 0 |
| NF4 | BTCUSDT | 0 | 0 | 78 | 0 |
| NF4 | ETHUSDT | 0 | 0 | 69 | 0 |
| NF4 | supports | 0 | 0 | 73 | 0 |
| NF4 | resistances | 0 | 0 | 74 | 0 |
| NF4 | BTCUSDT / supports | 0 | 0 | 41 | 0 |
| NF4 | BTCUSDT / resistances | 0 | 0 | 37 | 0 |
| NF4 | ETHUSDT / supports | 0 | 0 | 32 | 0 |
| NF4 | ETHUSDT / resistances | 0 | 0 | 37 | 0 |

W każdym przekroju recall=0, precision i MAE są nieokreślone. Te same zerowe F1 występują przy 0,25 i 1,0 ATR; komplet pozostałych metryk zawierają oficjalne `summary.json`.

| Wariant | Czas generacji: średni / mediana [s] | Min / P95 / max [s] | Globalny VRAM [MiB] | Peak allocated / reserved [MiB] | Preprocessing średnio [s] |
| --- | --- | --- | --- | --- | --- |
| BF16 | 3.720 / 3.466 | 3.000 / 4.489 / 10.072 | 4853 | 4376.0 / 4396.0 | 0.041 |
| NF4 | 5.336 / 5.301 | 4.648 / 6.126 / 6.234 | 5575 | 3070.3 / 5066.0 | 0.019 |

Oba warianty: **0 błędów wykonania i 0 ucięć**, po 36/36 odpowiedzi z blokiem Markdown (`invalid_json`). To najczęstszy i rozstrzygający oficjalnie błąd. Nie wyznaczano dodatkowego F1 po usunięciu Markdown.

Średnie obejmują pierwszą generację; P95 obliczono przez interpolację liniową. Pełne rozkłady i pomiary poszczególnych obrazów są w `base-*/summary.json` i rekordach ID. Generacja nie obejmuje otwierania PNG ani transferu wejścia na GPU; preprocessing mierzy wykonanie procesora/chat template. W tej konfiguracji NF4 nie obniżył globalnego szczytu VRAM inferencji; nie jest to izolowany pomiar samego wpływu zaokrągleń kwantyzacji.

Oceny wykonuje istniejący CLI `evaluate evaluate`, po odczytaniu rzeczywistego
`--help`, następnie `evaluate verify`. Manifesty wymagają kompletnego splitu;
predykcje mają dokładnie tekstowe `id` i `response`. Surowych odpowiedzi nie
przycinano, nie usuwano Markdown ani nie wyodrębniano JSON. Raporty zachowują
`protocol.json`, `dataset_binding.json`, predykcje i manifesty SHA-256.
Oficjalne katalogi to `results/evaluation/vlm41-cz2-20261110-1840-bf16/`
i odpowiednik `-nf4/`; ich identyczne zapieczętowane kopie są również
w `results/vlm41-cz2-20261110-1840/evaluation-*/`. Pierwszą próbę publikacji
bezpośrednio pod katalogiem iteracji odrzuciła istniejąca kontrola lokalizacji
ewaluatora. Zachowano log, a oceny uruchomiono w dozwolonej lokalizacji;
reguł i walidatora nie zmieniano.

## D. Wniosek i zakres etapu 4.2

Można rozpocząć **projektowanie i implementację ograniczonego pełnego treningu**,
ale nie można jeszcze uznać obecnych warunków za bezpieczne dla wielogodzinnego
przebiegu na 8 GB. Krótka próba potwierdza kolejne aktualizacje, zamrożenie wizji,
maskowanie i odtwarzalne użycie adaptera. Wzrost cache alokatora i mały fizyczny
zapas wymagają osobnej kontroli przed długim uruchomieniem.

Punkt odniesienia przyszłego eksperymentu: **bazowy NF4, z tą samą rewizją,
przygotowaniem typów, procesorem, obrazami, promptem i generowaniem co NF4 + adapter**.
BF16 pozostaje wynikiem pomocniczym. W 4.2 pozostają plan pełnego treningu,
kontrola pamięci hosta/GPU, uzgodnione checkpointy i wznowienie, trening na 698
train oraz późniejsza pełna ocena validation. Nie zmieniać `sr-eval-v1` ani
promptu w odpowiedzi na błędy formatu. Test pozostaje niewykorzystany.

## E. Środowisko, błędy techniczne i weryfikacja

Windows 10/19045, RTX 3060 Ti 8192 MiB, sterownik 621.14, Python 3.12.12,
torch 2.10.0+cu128, Transformers 5.3.0, PEFT 0.18.1, bitsandbytes 0.49.2.
Wykorzystano istniejące środowisko `D:/ml-envs/market-levels-vlm/` i kompletny
lokalny cache. Rewizję i SHA plików checkpointu porównano z zapisanym inwentarzem
części 1; bez pobierania wag, aktualizacji bibliotek, instalacji WSL/sterowników.
Pełne wersje i stan CUDA: `preflight/cuda.json`, `preflight/checkpoint.json`.
Startowy globalny VRAM wynosił 324 MiB, bez obcego procesu obliczeniowego.

Pierwsze ładowanie BF16 zakończyło się błędem Windows **1455** przed pierwszą
predykcją. Diagnostyka wskazała usługę powiadomień `WpnUserService_9648847`,
która zajmowała około 54 GiB pamięci prywatnej/zadeklarowanej. Po osobnej zgodzie
autora uruchomiono restart tej konkretnej usługi. Nie zmieniano checkpointu,
promptu, precyzji ani konfiguracji generowania. Zachowano katalog
`base-bf16-attempt-a/`, log i diagnostykę pamięci/usługi. Ta awaria hosta nie
jest CUDA OOM i nie stanowi odpowiedzi modelu; próba nie wytworzyła predykcji.
Usługa wróciła do stanu Running z nowym PID; stan zapisano w
`service-restart-result.json`. Trening i kontrola adaptera odbyły się przed
restartem, a końcowe walidacje bazowe po nim. Nacisk na pamięć hosta mógł
wpływać na czasy i zachowanie WDDM; krótkiej próby treningu nie należy traktować
jako kontrolowanego benchmarku przepustowości. Nie powtarzano udanego treningu.

**334/334 testy repozytorium OK**, 152,752 s, bez pominięć; obejmuje 317
wcześniejszych i 17 nowych. **3/3 testy maskowania na rzeczywistych tensorach
PyTorch OK** w środowisku VLM, oddzielnie. Nowe testy obejmują selekcję train,
izolację splitów, 120 świec, niezmienioną instrukcję i obraz bez overlay,
kompletność 36 ID, kontrakt ewaluatora, jeden optymalizator i osiem aktualizacji,
zapis adaptera, przerwanie po pierwszym symulowanym OOM oraz odrzucanie
niezgodnych tensorów, konfiguracji i rewizji przy odczycie.
Rzeczywista inferencja modelu/adaptera stanowi dodatkową kontrolę integracyjną.
Wcześniejsze nieudane logi testów również zachowano; końcowy wynik pochodzi
z `regression-tests-final-v2.log`, po uzupełnieniu atrap tensorów/optimizera
i dodaniu ścisłej próby serializacji. Poprzedni pełny przebieg także miał
334/334 OK (169,788 s); nie zastępuje on końcowego uruchomienia po zmianach.

Inwentarz początkowy objął **12 920 historycznych plików data/results**, w tym
**3212 plików produkcyjnego zbioru**. Kontrola końcowa potwierdziła identyczne
SHA-256 wszystkich tych plików, bez usunięć i nieoczekiwanych dodatków.
Dodatkowe 22 pliki to dwa nowe oficjalne raporty w dozwolonym
`results/evaluation/`; ich kopie są w katalogu iteracji, wyłączonym z porównania
historii. Pozostałe stare katalogi wyników pozostały niezmienione.
`completion-checks.json` potwierdza osiem kroków, obie walidacje 36/36,
odczyt adaptera i integralność; skrypt sprawdził też dodatkową ścisłą próbę zapisu.
Hashowanie bajtów plików testowych służyło wyłącznie ochronie integralności.

Wszystkie zmiany repozytorium są nowymi plikami; `git diff` dla istniejących
śledzonych plików pozostaje pusty. Uzupełnienie instrukcji jest osobno w
`.ai/ETAP_4_1_CZ2.md`, aby zachować wymóg tej iteracji tworzenia wyłącznie
nowych plików. Nie wykonano reset, clean, stash, commit ani push.

## F. Artefakty i przekazanie

Nowy kod: `modeling/stability_config.py`, `modeling/io/adapter_check.py`,
`inference/io/stability.py`, `inference/workflows/validation.py`,
`training/workflows/stability.py`, CLI `vlm_stability` i skrypt
`scripts/verify_vlm41_cz2.py`. Konfiguracja: `configs/vlm/stability.json`.
Kod wcześniejszego pilota, dane, renderer, etykietowanie i ewaluator niezmienione.

[Instrukcja PowerShell](INSTRUKCJA_POWERSHELL_4_1_CZ2.md) zawiera wyłącznie
zaimplementowane polecenia. Lokalny adapter pozostaje pod
`results/vlm41-cz2-20261110-1840/train/adapter/`.

ZIP: `handoff/vlm41-cz2-20261110-1840.zip`, obok manifest zawartości
`vlm41-cz2-20261110-1840.manifest.json` i suma
`vlm41-cz2-20261110-1840.zip.sha256`.
Zawiera kod, testy, konfiguracje, dokumentację, surowe predykcje, oba kompletne
raporty ewaluatora, pomiary, logity i manifesty integralności. Wspólny pełny
tokenizer zachowano raz w `base-nf4/tokenizer/`, wraz z konfiguracjami każdego
wariantu; identyczne duże kopie tokenizerów pominięto.

Nie zawiera wag Qwen, wag adapterów ani kopii tensorów adaptera, pełnego
zbioru, cache, środowisk, build czy egg-info. Adapter główny pozostaje lokalnie
w `results/vlm41-cz2-20261110-1840/train/adapter/`, a niezmieniona kopia użyta
w dodatkowej kontroli pod `roundtrip-source/adapter/`.
Lokalny pełny manifest katalogu wynikowego obejmuje także adaptery; ZIP ma
własny manifest wybranego podzbioru. Kompletne manifesty oficjalnych ocen
pozostają w ZIP i pozwalają je samodzielnie zweryfikować.

Po zakończeniu tej części obliczenia zatrzymano. Etapu 4.2 nie rozpoczęto.

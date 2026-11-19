# Etap 4.4, część 1 — przygotowanie dodatkowej epoki

Data: 2026-11-11. **Właściwego treningu Qwen, pierwszych 25 kroków, preflight GPU
ani walidacji GPU nie uruchomiono.** Gotowe są kod, konfiguracja, kontrole CPU
i instrukcja do ręcznego wykonania przez autora po zamknięciu IDE/Codexa.

## Stan wejściowy i weryfikacja oryginalnych wyników

Autor ukończył jeden eksperyment QLoRA: 2 epoki, 350 aktualizacji, 698 train
na epokę, 1396 przykładów narastająco. Źródłowy model:
`Qwen/Qwen3-VL-2B-Instruct`, rewizja
`89644892e4d85e24eaac8bacfd4f463576704203`.
Wybrany adapter to `results/vlm43-part3-2708-16743/adapter`, a pełny checkpoint
to `results/vlm43-part3-2708-16743/checkpoints/step-000350`.
Eksport PEFT i pełny checkpoint nie są zamienne.

Przed zmianami zweryfikowano zapieczętowane raporty, surowe predykcje i metadane:

- `results/evaluation/vlm43-validation-step175-26351-3437/`;
- `results/evaluation/vlm43-validation-step350-9320-26567/`.

`read_evaluation` ponownie kontrolował integralność i zgodność ocen. Nie
generowano nowych odpowiedzi ani nie naprawiano JSON. Zapis dowodów i hashy:
`results/vlm44-preparation-20261111-a/baseline-validation.json`.

| Oficjalne sr-eval-v1, 0,5 ATR | Krok 175 | Krok 350 |
| --- | ---: | ---: |
| Micro-F1 | 0,3972125436 | 0,4651162791 |
| Precision | 0,4071428571 | 0,4545454545 |
| Recall | 0,3877551020 | 0,4761904762 |
| TP / FP / FN | 57 / 83 / 90 | 70 / 84 / 77 |
| Poprawny JSON | 36/36 | 36/36 |
| Przewidziane / referencyjne poziomy | 140 / 147 | 154 / 147 |
| Cały poprawny zestaw | 2/36 | 2/36 |

Oryginalny zbiór `data/datasets/ds35-800-20261107-a` nadal ma 698/36/66.
Manifest sprawdzono przed i po pracach. Testu nie analizowano; odczyt jego bajtów
w hashowaniu służył wyłącznie ochronie integralności.

Początkowy working tree zawierał wcześniejsze zmiany etapu 4.3: trzy zmienione
dokumenty, zatwierdzoną konfigurację, dwa dokumenty 4.3 i dwa testy. Zachowano je.
Status i diff zapisano przed pracą w katalogu przygotowania. Nie wykonano commit,
push, reset, stash ani clean.

## Decyzja badawcza i konfiguracja

Autor podjął decyzję o **jednym dodatkowym eksperymencie po obejrzeniu validation**.
To świadome rozszerzenie badań, które należy ujawnić w pracy. Nie jest to
matematycznie równoważne trzem epokom od początku ze wspólnym AdamW/schedulerem.
Nie zmieniamy starego `epochs=2`, tożsamości checkpointu ani `state.pt`.

Nowa konfiguracja: `configs/vlm/extra-epoch-approved-local.json`. Utworzona
przez `read_configuration` z rozwiniętej kopii wcześniejszego wejścia, bez
zmiany lokalizacji danych. Oba stare pliki `training.json` i
`training-approved-local.json` pozostały bez zmian. Dodatkowe pole `extra_epoch`
jest obsługiwane wyłącznie jako jawny nowy eksperyment.

| Parametr nowego eksperymentu | Wartość |
| --- | --- |
| Dodatkowe epoki / train / aktualizacje | 1 / 698 / 175 |
| Batch / gradient accumulation | 1 / 4 |
| LR / scheduler / warmup | 0,00005 / linear / 9 |
| Seed nowego eksperymentu | 20261112 |
| max_steps | null; plan wynika z jednej epoki |
| Zapis / log / granica walidacji | co 25 / co krok / 175 |
| QLoRA | NF4, double quantization, BF16 compute |
| LoRA | rank 8, alpha 16, dropout 0, językowe q_proj/v_proj |
| Encoder wizualny | zamrożony, BF16 |
| Sekwencja / PNG | maks. 2048 bez obcinania / 1024 × 768 |
| AdamW | nowy stan; betas 0,9/0,999, eps 1e-8, weight decay 0,01 |
| Clipping / checkpointing | 1,0 / use_reentrant=False |
| Zgoda | extra_epoch.approved=true i --approve-extra-epoch |
| Oryginalne full_approved w nowym wejściu | false; nie służy do uruchomienia 4.4 |

Reszta konfiguracji i zasady maskowania, straty, QLoRA, danych i sprzętu
pozostały z 4.2. Konfiguracja nowego eksperymentu jest ściśle walidowana,
łącznie z niezmienionymi progami pamięci. Nie dobierano kolejności na validation.
Test potwierdził, że `epoch_order(ids,20261112,0)` jest dokładnie równe
`epoch_order(ids,20261110,2)`.

## Weryfikacja wag początkowych

Nowy `training/io/initialization.py` sprawdza na CPU:

1. Przypięte SHA-256 pliku wag adaptera oraz manifestów eksportu/checkpointu.
2. Pełne inwentarze i hashe obu źródeł, w tym bajty starego `state.pt`.
3. Zgodność tożsamości eksportu i checkpointu, rewizji, danych i warunków
   modelu; zakończone dwie epoki, 350 kroków i 1396 przykładów.
4. Zgodność PEFT: rank/alpha/dropout, komplet q/v, bias i opcji wpływających
   na architekturę/skaling. Akceptowane są dwa równoważne zapisy targetów:
   pełne 56 nazw albo sufiksy q_proj/v_proj.
5. Dokładnie 112 oczekiwanych kluczy językowych, prawidłowe kształty FP32,
   skończone wartości i 1 605 632 elementy. Tensorów wizji nie akceptuje.
6. `torch.equal` dla wszystkich tensorów eksportu i adaptera checkpointu 350.

Wynik rzeczywistej kontroli źródeł: **112/112 tensorów dokładnie równych**,
**1 605 632 parametrów**, zgodne manifesty i tożsamość. SHA-256 źródłowego
`adapter_model.safetensors`:

```text
3b7af8dd8835923a561aa356248b075042fa022f45be5426833bf2b2662c4a7c
```

Pełny zapis: `parent-verification.json`. Stary `state.pt` jest wyłącznie
hashowany, nigdy deserializowany jako źródło nowego eksperymentu. Osobny test
CPU blokował każde `torch.load` podczas weryfikacji rodzica i przeszedł.

Przy przyszłym starcie GPU pipeline ładuje zweryfikowaną bazę NF4, przygotowuje
dotychczasową jedną architekturę LoRA i wymaga zamrożonej wizji, wyłącznie LoRA
trenowalnej oraz dokładnej liczby parametrów. `load_initial_adapter` wczytuje
wyłącznie safetensors przez `set_peft_model_state_dict` do istniejącego adaptera.
Przed i po operacji porównuje wszystkie klucze, kształty, dtype i wartości.
Nie używa merge ani drugiej nakładki. Kontrola CPU lekkiego PEFT potwierdziła
również brak zmiany bazowych parametrów.

Dopiero potem powstają nowy AdamW i LambdaLR na 175 kroków. Przed krokiem 0
pipeline wymaga pustego stanu optymalizatora i `scheduler.last_epoch=0`.
Zapisuje `initialization.json`, pochodzenie w `identity.json`, zdarzenie
`initialized_from_adapter` i pełny checkpoint `step-000000`.
Rzeczywistego załadowania Qwen/112 tensorów do nowego modelu GPU jeszcze nie
wykonano; powyższe porównanie w pamięci będzie obowiązkową kontrolą runtime.

## Inicjalizacja, wznowienie i numeracja

Nowy interfejs CLI:

```text
extra-epoch --config <nowy JSON> --approve-extra-epoch
  (--initialize-adapter <eksport 350> | --resume <checkpoint etapu 4.4>)
  --stop-after <liczba aktualizacji w tym procesie> --output <nowy vlm44-...>
```

PowerShell udostępnia odpowiednio `-Mode extra-epoch`, `-ApproveExtraEpoch`,
`-InitializeAdapter` i `-ResumeCheckpoint`. Dwie ostatnie opcje wzajemnie się
wykluczają także na poziomie skryptu. Nowy output nie może istnieć i wymaga
identyfikatora `vlm44-...`. Dry-run/preflight nowej konfiguracji również wymagają
specjalnej zgody; odmowa następuje przed ładowaniem modelu i CUDA.
Domyślny dry-run i obie stare blokady `full` pozostają.

Źródła, ich hashe i nowa konfiguracja tworzą tożsamość pochodzenia. Wznowienie
sprawdza ją przed CUDA, a później dotychczasowa pełna kontrola obejmuje również
config, dane, środowisko, bazę, procesor i tokenizer. **Stary checkpoint 350
z nową konfiguracją jest odrzucany**, nie ma obejścia ani edycji starego stanu.
Przy wznowieniu nowego checkpointu `load_initial_adapter` nie jest wywoływane.
Przywracane są wyłącznie własne AdamW, scheduler, sampler i RNG etapu 4.4.
Źródłowe artefakty rodzica muszą pozostać dostępne do kontroli pochodzenia.

`domain/provenance.py` zapisuje w identity/metadanych pochodzenie, nowe stany
AdamW/schedulera i dodatkową epokę. Metadane checkpointów, zdarzenia kroków
i wynik zawierają też `additional_optimizer_steps`,
`total_training_examples_seen_in_new_stage` i umowną sumę 350+lokalny krok.
Identity jest stałe, a liczniki postępu zmieniają się w metadanych, bez
unieważniania wznowienia. `optimizer_state=new` opisuje początek eksperymentu,
nie reset przy każdym wznowieniu.

Plan wykonania przez autora:

- Lokalny 0: dokładne źródłowe wagi, nowy stan, checkpoint początkowy.
- Lokalne 1–25: 100 train, `step-000025`, status `stopped`, kod 0.
- Wznowienie 26–175: kolejnych 150 aktualizacji; łącznie 698 train,
  `step-000175`, status `stopped` przy podanym limicie 150, kod 0.
- Bez automatycznej walidacji. Bez limitu procesu pętla kończy plan statusem
  `complete`. Ostatnia grupa ma 2 przykłady i dzieli stratę przez 2.

StopAfter liczy aktualizacje w bieżącym procesie i nie zmienia schedulera.
Nie ustawiono `max_steps=25`. Nowy lokalny 175 nie jest starym krokiem 175;
umowne 525 nie oznacza ciągłego planu jednego schedulera.

## Checkpointy, sprzęt i błędy

Dotychczasowy zapis atomowy pozostał: puste gradienty na granicy kroku,
adapter + AdamW/scheduler/sampler/RNG, staging `.partial`, fsync, manifest,
odczyt CPU `state.pt`, atomowa publikacja i dopiero potem `latest.txt`.
Nowe pola pochodzenia dopisywane są tylko dla nowego eksperymentu.
Nie usuwa się wcześniejszych checkpointów. OOM/NaN/wyjątek nie zapisują stanu
częściowej aktualizacji. STOP działa na granicy kroku. Nagłe zabicie procesu
może pozostawić jedynie wcześniejszy pełny checkpoint i niepełne logi.

Nie zmieniono idle VRAM ≤450 MiB, RAM ≥4096 MiB, commit ≥8192 MiB,
monitorowania globalnego VRAM/allocated/reserved/RSS, kontroli NaN/Inf,
zwalniania nieaktywnych bloków cache ani progów presji pamięci. Brak
automatycznych retry, zmiany rozdzielczości, rank, offloadu i ustawień Windows.
Zachowano przypięte wersje. Nie instalowano bibliotek ani sterowników.
Rzeczywisty preflight wykona autor po zamknięciu IDE.

W logach starego przebiegu 4.3 odnotowano nawet **7969/8192 MiB** globalnego
VRAM. To około 223 MiB nominalnego zapasu; próbki mogą pominąć krótsze piki.
Powodzenie dwóch epok nie gwarantuje dodatkowej. Reserved pod WDDM nie jest
fizycznie zajętą pamięcią GPU. Zatrzymanie po kroku nie zapobiega każdej awarii
wewnątrz kroku lub podczas zapisu.

## Wykonane testy i dry-run

| Kontrola | Wynik |
| --- | --- |
| Pełny końcowy `unittest discover -s tests -v` w `.venv` | **377/377 OK**, 144,823 s, bez pominięć |
| Nowe testy offline | 17, włączone w powyższe 377 |
| Nowe testy PEFT/PyTorch CPU 4.4 w środowisku VLM | **4/4 OK** |
| Dotychczasowy CPU checkpoint/resume 4.3 | 1/1 OK |
| Dotychczasowy CPU autograd/akumulacja/NaN 4.2 | 4/4 OK |
| Dotychczasowe CPU maskowanie | 3/3 OK |
| Dry-run nowej konfiguracji | 698 train, 175 kroków, bez modelu/CUDA |
| Natywny PowerShell: dry-run / brak zgody / obie opcje / stary resume | kody 0 / 1 / 1 / 1 |
| Natywne CMD: dokładne polecenie dry-run z instrukcji | kod 0 |
| Kontrole po 25/175 i porównanie źródła z checkpointem 0 na sztucznych plikach | OK |

Poprzedni pełny przebieg też miał 377/377 OK (160,891 s). Końcowy wykonano
po doprecyzowaniu kompletności target modules. Testy działały offline,
z `PYTHONUTF8=1` i `PYTHONIOENCODING=utf-8`; CPU VLM dodatkowo z ukrytym GPU
i wyłączonym Hubem. Nie deklarujemy pełnego zestawu jako uruchomionego również
w drugim środowisku. Wersje są w `environment.json`.

Nowe testy obejmują: zgody, niezmienione stare ustawienia, rewizję, hashe,
rank/alpha/q-v, 112 tensorów/kształty/NaN, wzajemne wykluczenie opcji,
odrzucenie starego resume i zmienionego pochodzenia przed CUDA, świeży stan,
permutację dawnej trzeciej epoki, scheduler 175/warmup 9, granice 25/175
i grupę 2, kody wyjścia oraz zgodność eksportu z wejściową kontrolą walidacji.
Pełny zestaw zachowuje dotychczasowe kontrole STOP, OOM, uszkodzonego/przerwanego
checkpointu, splitu test i oficjalnego JSON bez napraw.

Rzeczywisty lekki PEFT CPU: źródłowy adapter był wcześniej aktualizowany,
potem jego dokładne wagi załadowano do jednego nowego adaptera. Baza nie uległa
zmianie, AdamW był pusty, scheduler nowy. Porównano pełne 175 aktualizacji
na 698 sztucznych ID z 25 + odtworzeniem + 150: adapter, AdamW, scheduler,
kolejne RNG Python/NumPy/torch i kolejność wszystkich przykładów były dokładnie
równe. Źródłowe wagi zachowały hash. GPU RNG nie jest dowiedzione testem CPU.
Osobny test wykrył zmianę tensora w tymczasowej kopii checkpointu, mimo
ponownego zapieczętowania jej manifestu.

Dowody w `results/vlm44-preparation-20261111-a/`: `tests-final.log`,
`tests-final-exit.json`, `cpu44-final.log`, `cpu44-final-exit.json`,
`cpu-regression-exit.json`, logi wcześniejszych testów CPU, `powershell-checks.json`,
`documentation-checks.json`, `dry-run/report.json`, `cmd-dry-run/report.json`.
Sztuczne fixture instrukcji nie są wynikami uczenia Qwen i nie trafiają do ZIP.

## Integralność i lista zmian

Inwentarz początkowy obejmuje **13 780 historycznych plików** data/results/handoff,
konfiguracji VLM, raportów VLM, ewaluatora i etykietowania; osobna kontrola
krytycznych wejść przed zmianami objęła 3266 plików. Końcowe SHA-256 i rozmiary
pozostały zgodne dla wszystkich 13 780, w tym **3212/3212 plików produkcyjnego
zbioru**. Bez usunięć i nieoczekiwanych dodatków do starych korzeni.
Źródłowy adapter, checkpoint/state.pt 350, historyczne predykcje, oceny,
PNG/JSONL, etykiety, prompt, ATR i evaluator pozostały bez zmian.
Dowody: `inventory-before.json`, `critical-integrity-before.json`,
`integrity-summary.json`. Oba stare wejścia konfiguracji zachowały bajty.

Zmiany tego zadania:

- Nowe `training/io/initialization.py` i `domain/provenance.py`.
- Niewielkie rozszerzenia `training/config.py`, `workflows/pipeline.py`,
  `io/checkpoints.py`, CLI `train_vlm.py` i `scripts/run_vlm_training.ps1`.
- Nowe `configs/vlm/extra-epoch-approved-local.json`.
- Nowe `tests/unit/modeling/test_extra_epoch.py` i
  `tests/checks/check_vlm44_initialization.py`.
- Ten raport, instrukcja `INSTRUKCJA_POWERSHELL_4_4.md` oraz aktualizacja
  `.ai/CURRENT_STATE.md`, `.ai/WORKFLOW.md`, `docs/ARCHITECTURE.md`.
- Nowy lokalny katalog dowodów i mały handoff. Wcześniejsze zmiany working tree
  pozostały; nie zastąpiono ich ani nie cofnięto.

## Ręczne wykonanie i późniejszy wybór modelu

[Instrukcja CMD](INSTRUKCJA_POWERSHELL_4_4.md) zawiera dokładne polecenia dry-run,
preflight, pierwszych 25, ich kontroli, wznowienia 150 oraz późniejszej walidacji
i porównania. Zapisuje log konsoli i rzeczywisty kod zakończenia. Polecenie
pierwszego odcinka, po poprawnych kontrolach i zamknięciu IDE:

```cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\run_vlm_training.ps1 -Mode extra-epoch -Config configs/vlm/extra-epoch-approved-local.json -ApproveExtraEpoch -InitializeAdapter results\vlm43-part3-2708-16743\adapter -StopAfter 25 -OutputDirectory results\vlm44-part1-NOWY
```

`NOWY` zastąp unikalnym identyfikatorem; instrukcja ustawia go przez `%RANDOM%`.
Polecenia tego nie wykonano. Nie należy od razu uruchamiać drugiego odcinka.
Po nim walidacja jest osobnym procesem na tych samych 36 wykresach. Dotychczasowy
walidator akceptuje nową konfigurację eksportu; nie zmieniano jego zasad ani
oficjalnego ewaluatora. Ocenimy wszystkie przekroje i błędy wskazane w zleceniu,
również dobre/złe odpowiedzi, dopiero po powstaniu predykcji modelu B.

Reguła ustalona przed treningiem: wyższe oficjalne micro-F1 przy 0,5 ATR,
następnie więcej poprawnych JSON, następnie wcześniejszy adapter A po 350.
Nie będziemy wybierać według korzystniejszej pomocniczej diagnostyki. Jeśli B
nie wygra według tej reguły, pozostaje A. Bez czwartej epoki, siatki LR lub testu.
Nie tworzono raportu jakości dodatkowej epoki, ponieważ wynik jeszcze nie istnieje.

Handoff: `handoff/vlm44-preparation-20261111-a.zip`, obok manifest i
`.zip.sha256`. Zawiera wybrane nowe/zmienione pliki i małe dowody, z własną
kontrolą SHA-256; nie jest całym repozytorium ani samodzielnym środowiskiem.
Wyklucza wagi, adaptery, checkpointy, state.pt, dane produkcyjne, cache,
środowiska oraz sztuczne wagi fixture. Weryfikacja zawartości i hashy ZIP przeszła.

Ograniczenia: nowy start i kontynuacja Qwen GPU nie zostały wykonane; testy CPU
nie gwarantują deterministyczności CUDA ani pamięci 8 GB; runtime porówna
załadowane tensory przed pierwszym krokiem; wyniki validation są małe i już
wpłynęły na decyzję o rozszerzeniu badań. Autor sam uruchomi trening po
zamknięciu VS Code/Codexa. **Przygotowania zakończone bez uczenia Qwen.**

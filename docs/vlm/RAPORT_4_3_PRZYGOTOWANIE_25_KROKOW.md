# Etap 4.3, część 1 — przygotowanie pierwszych 25 kroków

Data: 2026-11-10. **Nie uruchomiono właściwego treningu Qwen, kroków 1–25,
preflight GPU, dodatkowego QLoRA ani walidacji/inferencji.** Pierwszy odcinek
uruchomi dopiero autor po zamknięciu IDE i Codexa. Ten raport dotyczy przygotowań.

## Stan wejściowy i zakres

Etap 4.2 był zaakceptowany: działał pipeline NF4/PEFT, pełny checkpoint,
deterministyczny sampler, scheduler, STOP i PowerShell. Historyczny raport
opisywał sześć kroków GPU i porównanie wznowienia; nie ponawiano tych prób.
Początkowy `git status --short` i `git diff` były puste. Zapisano je w
`results/vlm43-preparation-20261110-a/git-status-before.txt` i `git-diff-before.patch`.
Przeczytano wskazane instrukcje, raporty 4.1/4.2, instrukcję PowerShell,
architekturę oraz aktualny kod i testy. Pipeline nie wymagał poprawki.

Historyczne wyniki pozostają w `results/vlm-feasibility-20261109-210209/`,
`results/vlm41-cz2-20261110-1840/`, `results/vlm42-pipeline-20261110-a/`
oraz `results/evaluation/`. Checkpointy techniczne 4.2 są pod
`results/vlm42-pipeline-20261110-a/gpu-{a,b1,b2}/checkpoints/`;
ostatnie kroki to odpowiednio 3, 1 i 3. Nie usuwano ani nie przepisywano artefaktów.

## Zatwierdzony eksperyment

Nowy plik: `configs/vlm/training-approved-local.json`. Utworzony przez
`shared.configuration.read_configuration`, z rozwinięciem `$file`.
Porównanie całych struktur przed i po `load_config` potwierdziło jedyną zmianę
wartości: `pipeline.full_approved=false → true`. Oryginalne `training.json`
i `stability.json` pozostały bajtowo bez zmian. Nie dodano tokenów ani danych
dostępowych. Wejście zawiera pełne runtime/pipeline; `load_config` nadal dopisuje
sekcję `fixed` i stosuje pipeline seed do runtime dokładnie jak w 4.2.
Efektywny seed wynosi 20261110, mimo zachowanego historycznego runtime seed
20261109 w rozwiniętym wejściu. Nie jest to nowa zmiana zachowania.

| Kontrola programowa | Wynik |
| --- | --- |
| Model | Qwen/Qwen3-VL-2B-Instruct |
| Rewizja | 89644892e4d85e24eaac8bacfd4f463576704203 |
| Train / validation / test | 698 / 36 / 66 |
| Epoki, batch, akumulacja | 2 / 1 / 4 |
| Kroki na epokę / łącznie | ceil(698/4) = 175 / 350 |
| max_steps | null, bez skrócenia planu |
| Scheduler / warmup / LR | linear / 18 / 0,0002 |
| Zapis / logowanie | co 25 / co krok |
| Granice walidacji | 175 i 350 |
| Obraz / sekwencja | 1024 × 768 / maksymalnie 2048 tokenów, bez obcinania |
| QLoRA | NF4, double quantization, BF16 |
| LoRA | rank 8, alpha 16, dropout 0, wyłącznie językowe q_proj/v_proj |
| Wizja / checkpointing | zamrożona / włączony, use_reentrant=False |
| Optymalizator | istniejący AdamW, bez zmian ustawień |

Kontrole: `configuration-checks.json`, `effective-config-reviewed.json`,
`dry-run/report.json` w katalogu przygotowania. Dry-run pełnego planu odczytał
698 train, zweryfikował zapieczętowany zbiór i instrukcje `pl-sr-v1`, podał 350
kroków, `loads_model=false`, `full_training_started=false`. Liczby wszystkich
splitów sprawdzono w manifeście. Testowych przykładów nie analizowano;
hashowanie plików służyło wyłącznie integralności. Nie zmieniono etykietowania,
promptu, rozdzielczości, podziału ani `sr-eval-v1`.

## StopAfter i plan 25 → 175 → 350

Analiza `run_vlm_training.ps1`, CLI, `pipeline.py` i `domain/schedule.py`:

- PowerShell przekazuje `-StopAfter 25` jako `--stop-after 25`.
- `train_loop` zwiększa licznik sesji po `backend.step(group)` i zatwierdzeniu
  samplera. Backend wykonuje jedną aktualizację AdamW i jeden scheduler step
  na grupę czterech przykładów, po czym czyści gradienty.
- Po 25 grupach wynik normalny to `stopped`, global_step=25,
  processed_examples=100. Zapis `step-000025` następuje przed powrotem z pętli.
  Potem następują eksport adaptera, `result.json`, zdarzenie `finished`, kod 0.
- Nie rozpoczyna się krok 26 ani walidacja. Walidacja jest osobnym procesem;
  granica 175 tylko kończy proces treningu ze statusem `validation_due`.
- Scheduler powstaje od razu na 350 kroków; StopAfter nie trafia do jego
  obliczeń. Wartość mnożnika po 25 wynosi 325/332, nie zero.
- Wznowienie z 25 odtwarza kursor 100 i zaczyna globalny krok 26. Do 175
  pozostaje 150 kroków. Po 175 przetworzono 698 przykładów; po 350 — 1396.
  Końcowa grupa każdej epoki ma dwa przykłady, bez odrzucania ogona.
- Po 350 status to `complete`; końcową walidację trzeba uruchomić później
  ręcznie. Nie przygotowano automatycznego wznowienia ani walidacji.

Test na atrapach wykonał segmenty 25, 1, do 175 i do 350 oraz porównał wszystkie
grupy z przebiegiem bez przerw procesowych; kolejność była zgodna, ustawienia
pozostały identyczne. Wcześniejszy STOP, presja RAM/commit lub błąd mogą zakończyć
proces przed 25 — taki wynik nie zalicza pierwszego odcinka.

## Checkpoint, wznowienie i STOP

Zapis wymaga pustych gradientów, zapisuje adapter, AdamW, scheduler, sampler
i RNG Python/NumPy/torch CPU/CUDA. Staging `.partial` otrzymuje manifest SHA-256,
kontrolę wymaganych plików i odczyt `state.pt` na CPU, a następnie atomową
publikację. Dopiero poprawny checkpoint aktualizuje `latest.txt`.
Nie ma automatycznego usuwania checkpointów. Awaria zapisu zachowuje poprzedni
opublikowany checkpoint; nie zapisuje się stanu częściowej aktualizacji.

Nowy test `tests/checks/check_vlm43_resume.py` użył małego modelu Linear+LoRA
na CPU, rzeczywistych AdamW, LambdaLR, PEFT i safetensors oraz produkcyjnych
funkcji `save_checkpoint`/`load_checkpoint`. Po 25 aktualizacjach zapisał
`step-000025`/100 przykładów, wczytał stan do nowego modelu i optymalizatora,
sprawdził stan schedulera 25 i wykonał krok 26. Adapter, momenty AdamW,
scheduler i kolejne losowania wszystkich trzech generatorów CPU były dokładnie
zgodne z kontynuacją. Nie ładowano Qwen ani danych produkcyjnych. GPU było
ukryte przez `CUDA_VISIBLE_DEVICES=''`; test nie odtwarza RNG CUDA.
Znany test GPU wznowienia pochodzi z historycznego etapu 4.2.

STOP jest sprawdzany na granicy aktualizacji. Jeżeli pojawi się w trakcie
microbatchy, kończona jest cała grupa. Wyjście przed kolejną grupą nie wykonuje
nowej aktualizacji; końcowy kod workflow zapewnia zapis aktualnego stanu.
Wyjątek/KeyboardInterrupt nie serializuje częściowego kroku. Zamknięcie procesu
przez system może uniemożliwić zapis `result.json`; zachowane checkpointy
pozostają jedyną podstawą późniejszego wznowienia.

`verify-checkpoint` sprawdza hashe/manifest i metadane, bez deserializacji pełnego
stanu do GPU. Zapis sprawdza także odczyt CPU. Pełne odtworzenie treningu to
osobna kontrola obejmująca adapter, optymalizator, scheduler, sampler i RNG.
Nie utożsamiamy tych poziomów weryfikacji.

## Pamięć, terminal i błędy

W pełnej konfiguracji nadal aktywne: idle VRAM ≤450 MiB przed CUDA,
RAM ≥4096 MiB, wolny commit ≥8192 MiB, wymagany RTX 3060 Ti/8192 MiB,
BF16 i przypięte wersje bibliotek. Nie zmieniono progów. Pętla kontroluje
RAM/commit przed i po kroku, uwzględnia próbki wewnątrz kroku; zatrzymuje się
na bezpiecznej granicy z kodem 3. Nie gwarantuje to ochrony przed nagłym
wyczerpaniem pamięci wewnątrz aktualizacji lub przy zapisie.
Cache nieaktywnych bloków jest zwalniany na granicy przy reserved >8000 MiB.
Nie ma automatycznego retry OOM, zmiany rank/obrazu/schedulera ani systemu.

Terminal i JSONL zawierają wszystkie wymagane pomiary: epoka, globalny krok
i plan, przykłady, loss, LR użyty w kroku, czas kroku/łączny, VRAM,
allocated/reserved, RSS, RAM/commit, checkpointy, ostrzeżenia i status.
Próbki globalnego VRAM/RSS co około 0,5 s mogą pominąć krótkie piki; PyTorch
peak jest oddzielny. Elapsed obejmuje przygotowanie i wcześniejsze odcinki,
nie czas oczekiwania między procesami ani końcowy eksport.
WDDM reserved nie jest fizycznie zajętym VRAM. Historyczny globalny peak
7907/8192 MiB pozostawia niewielki zapas i nie gwarantuje stabilności 25 kroków.

Rzeczywisty preflight wykona autor po zamknięciu IDE/Codexa. Nie mierzono
aktualnego obciążenia GPU jako warunków docelowych. Środowiska nie instalowano
ani nie modyfikowano. `environment.json` zapisuje wersje przez metadane pakietów.

Natywny PowerShell sprawdzono przez dwa osobne procesy: dry-run (kod 0)
i `full` zatwierdzonej konfiguracji **bez flagi wykonania** (kod 1, brak katalogu
treningu). Testy CLI na mockach potwierdziły przekazanie kodów 0/1/3.
Pozytywnych poleceń GPU nie wykonano. Stdout/stderr zapisują się obok wyniku
w `<run>.console.log`; skrypt pokazuje checkpoint i kod procesu. Interaktywne
okno PowerShell pozostaje otwarte. Nie potrzeba serwera ani Codexa w tle.

## Wykonana weryfikacja

| Kontrola | Rzeczywisty wynik |
| --- | --- |
| Pełny zestaw `unittest discover -s tests -v` | 360/360 OK, 147,705 s, bez pominięć |
| Osobny VLM CPU: maskowanie | 3/3 OK |
| Osobny VLM CPU: produkcyjna akumulacja/autograd i NaN | 4/4 OK |
| Osobny VLM CPU: pełny checkpoint 25 → 26 | 1/1 OK |
| Pełny dry-run 698/350 | OK, bez ładowania modelu |
| Natywny PowerShell dry-run i blokada full | kody 0 i 1, OK |
| Parser PowerShell 5.1 dla ośmiu bloków instrukcji | OK |
| Kontrole wyniku i mały ZIP na sztucznym wyniku | OK, brak wag/state.pt w ZIP |

Pełny zestaw uruchomiono projektowym `.venv` jak w dotychczasowych regresjach,
z `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`. Dodatkowe osiem testów PyTorch/PEFT
uruchomiono Pythonem 3.12.12 ze środowiska VLM, bez GPU i dostępu do Huba.
Nie deklarujemy pełnego zestawu jako wykonanego także w środowisku VLM.
Logi: `tests-offline.log`, `tests-offline-exit.json`, `cpu-{masking,autograd,resume}.log`,
`cpu-checks-exit.json`, `powershell-checks.json`, `documentation-checks.json`.
Nowe pięć testów offline podniosło liczbę z 355 do 360.

Próba instrukcji ujawniła ograniczenie PowerShell 5.1: `ConvertFrom-Json`
odrzuca pusty klucz `fixed.device_map` w pełnej konfiguracji/metadanych.
Poprawiono wyłącznie instrukcję: Python wybiera sekcję pipeline/sampler przed
przekazaniem JSON do PowerShella. Ponowna próba kontroli i archiwizacji przeszła.
Nie zmieniono formatu checkpointów ani kodu pipeline'u. Wyniki fixture w katalogu
przygotowania są wyraźnie sztuczne i nie stanowią wyniku treningu Qwen.

## Integralność i zmiany

Początkowy inwentarz SHA-256 obejmuje **13 438 istniejących plików**, w tym
**3212 plików zbioru produkcyjnego**: data, stare results/handoff, raporty VLM,
konfiguracje VLM, evaluator i etykietowanie. Manifest zbioru zweryfikowano przed
i po przygotowaniu. Końcowa kontrola: wszystkie 13 438 zachowały rozmiar i SHA-256,
żaden nie zniknął; 3212/3212 plików zbioru bez zmian. Historyczne korzenie
data/results/handoff nie otrzymały nieoczekiwanych plików. Dowód:
`inventory-before.json` i `integrity-summary.json` w katalogu przygotowania.
Nie zmieniono produkcyjnych PNG/JSONL, ewaluatora, etykiet, danych finansowych,
starych raportów ani checkpointów. Nie wykonano pobierania, reset, clean, stash,
commitu ani push. Początkowy working tree był czysty.

Zmiany w repozytorium:

- `configs/vlm/training-approved-local.json` — rozwinięta, zatwierdzona kopia.
- `tests/unit/modeling/test_training_segments.py` — pięć testów segmentów,
  konfiguracji, blokady, kodów wyjścia i pomiarów w logach.
- `tests/checks/check_vlm43_resume.py` — osobny pełny test CPU zapisu/wznowienia.
- Ten raport i `docs/vlm/INSTRUKCJA_POWERSHELL_4_3_CZ1.md`.
- `.ai/CURRENT_STATE.md`, `.ai/WORKFLOW.md`, `docs/ARCHITECTURE.md` — aktualny
  stan zatwierdzenia i odnośnik do instrukcji; historyczne raporty zachowano.
- Lokalne dowody pod `results/vlm43-preparation-20261110-a/` i mały handoff.

Kod pipeline'u, skrypt uruchamiający i hiperparametry nie uległy zmianie.

## Przekazanie i ograniczenia przed startem

Instrukcja autora: `docs/vlm/INSTRUKCJA_POWERSHELL_4_3_CZ1.md`. Zawiera
preflight, jedno polecenie pierwszych 25 kroków, monitorowanie, STOP, ścisłe
kontrole zaliczenia i jawnie ograniczony ZIP wyników bez wag. Opisuje CUDA OOM,
VRAM, RAM/commit, ładowanie, NaN/Inf, zapis/uszkodzenie checkpointu, zamknięcie
procesu, błędną konfigurację i brak wersji bibliotek. Należy zachować logi
i ostatni poprawny checkpoint, a dopiero potem analizować przyczynę.

Handoff: `handoff/vlm43-preparation-20261110-a.zip`, obok manifest zawartości
i `.zip.sha256`. ZIP zawiera tylko nowe konfiguracje/testy, aktualizacje
instrukcji, raport, małe wyniki dry-run i dowody kontroli środowiska/testów;
ma własny manifest SHA-256. Nie zawiera całego repozytorium, wag, adapterów,
checkpointów, sztucznych wag fixture, danych finansowych, cache ani środowisk.
Inwentarz historycznych plików pozostaje lokalny; w paczce jest jego podsumowanie.

Najważniejsze ograniczenia: rzeczywisty 25-krokowy przebieg i preflight GPU
nie zostały wykonane; mały zapas VRAM pozostaje; test CPU nie dowodzi
deterministyczności CUDA; weryfikacja manifestu nie zastępuje odtworzenia GPU;
nie ma nowego wyniku jakości modelu. Wybór końcowego checkpointu i walidacje
po 175/350 należą do następnych części, bez automatycznego wykonania teraz.

**Przygotowania zakończone. Pierwsze 25 kroków czeka na ręczne uruchomienie autora.**

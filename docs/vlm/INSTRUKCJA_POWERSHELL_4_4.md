# Etap 4.4 — dodatkowa epoka od adaptera po kroku 350

Instrukcja dla **Windows CMD**. Kod i dry-run są przygotowane; treningu etapu
4.4 ani walidacji GPU nie uruchomiono. Polecenia treningowe wykonuje autor po
zamknięciu VS Code i Codexa. Nie potrzeba IDE, serwera, notebooka ani API.

To **nowy eksperyment**: źródłowe wagi LoRA z kroku 350, ale nowy AdamW,
scheduler, RNG i sampler. Nie jest równoważny treningowi trzech epok od początku
z jednym schedulerem. Źródłowy eksport i checkpoint 350 pozostają bez zmian.

## A. Przygotowanie i kontrole

Zapisz pracę, zamknij VS Code/Codexa i zbędne aplikacje GPU/RAM. Otwórz CMD
z menu Start. Sprawdź ustawienia uśpienia i wolne miejsce bez automatycznych
zmian systemowych. Nie zmieniaj środowiska, sterownika, usług ani pagefile.

```cmd
cd /d "D:\Studies\Inżynierka\market-levels-multimodal-finetuning"
set "PY_VLM=D:\ml-envs\market-levels-vlm\Scripts\python.exe"
set "CFG=configs/vlm/extra-epoch-approved-local.json"
set "PARENT=results\vlm43-part3-2708-16743\adapter"
"%PY_VLM%" -X utf8 -c "import sys,importlib.metadata as m; print(sys.version); print({k:m.version(k) for k in ('torch','transformers','peft','bitsandbytes','accelerate')})"
nvidia-smi
powershell.exe -NoProfile -Command "Get-PSDrive -PSProvider FileSystem | Select-Object Name,Used,Free"
"%PY_VLM%" -X utf8 -c "import json; from market_levels.training.io.resources import snapshot; print(json.dumps(snapshot(),indent=2))"
```

Wymagane środowisko: Python 3.12.12, torch 2.10.0+cu128, Transformers 5.3.0,
PEFT 0.18.1, bitsandbytes 0.49.2, Accelerate 1.12.0. Guard wymaga idle VRAM
≤450 MiB, dostępnego RAM ≥4096 MiB i zapasu commit ≥8192 MiB. Nie zwiększaj
progów w odpowiedzi na odmowę. Pozostaw kilka GiB na checkpointy i staging;
nie jest to gwarantowany górny limit. Nie usuwaj wcześniejszych wyników.

Dry-run sprawdza manifesty, przypięte hashe rodzica i wszystkie jego 112 tensorów
na CPU, bez ładowania Qwen i bez kontekstu CUDA:

```cmd
set "PLAN_DIR=results\vlm44-plan-%RANDOM%-%RANDOM%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\run_vlm_training.ps1 -Mode dry-run -Config "%CFG%" -ApproveExtraEpoch -InitializeAdapter "%PARENT%" -OutputDirectory "%PLAN_DIR%"
echo Kod dry-run: %ERRORLEVEL%
type "%PLAN_DIR%\report.json"
```

Oczekujemy kodu 0, `examples=698`, `total_steps=175`, `loads_model=false`,
`parent_tensor_values_exact=true`. Dry-run nie wykonuje aktualizacji wag.
Jeżeli kontrola nie przejdzie, zatrzymaj się i zachowaj komunikat.

Następnie wykonaj rzeczywisty preflight sprzętu:

```cmd
set "PREFLIGHT_DIR=results\vlm44-preflight-%RANDOM%-%RANDOM%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\run_vlm_training.ps1 -Mode preflight -Config "%CFG%" -ApproveExtraEpoch -InitializeAdapter "%PARENT%" -OutputDirectory "%PREFLIGHT_DIR%"
echo Kod preflight: %ERRORLEVEL%
```

Preflight tworzy kontekst CUDA dla kontroli GPU/BF16 i sprawdza wersje, zasoby
oraz SHA-256 modelu bazowego; nie ładuje modelu i nie uczy. Autor wykonuje go
po zamknięciu IDE. Po kodzie innym niż 0 nie uruchamiaj treningu.

## B. Odcinek 1 — lokalne kroki 1–25

Po poprawnym dry-run i preflight, w tej samej sesji CMD:

```cmd
set "RUN_DIR=results\vlm44-part1-%RANDOM%-%RANDOM%"
echo %RUN_DIR%>results\vlm44-part1-last-path.txt
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\run_vlm_training.ps1 -Mode extra-epoch -Config "%CFG%" -ApproveExtraEpoch -InitializeAdapter "%PARENT%" -StopAfter 25 -OutputDirectory "%RUN_DIR%"
set "TRAIN_EXIT=%ERRORLEVEL%"
echo Kod treningu: %TRAIN_EXIT%
```

`extra_epoch.approved=true` w specjalnej konfiguracji i flaga
`-ApproveExtraEpoch` są dwiema osobnymi blokadami. Przy pierwszym uruchomieniu
obowiązuje `-InitializeAdapter`, a nie `-ResumeCheckpoint` starego checkpointu.
Wagi trafiają do jednego istniejącego zestawu LoRA; brak merge i drugiej nakładki.
Nowy sampler ma seed 20261112, czyli permutację dawnej trzeciej epoki
`Random(20261110+2)`. Lokalny licznik zaczyna od 0.

Pierwszy checkpoint `step-000000` zawiera dokładne wagi źródłowe, nowy AdamW
bez momentów i nowy scheduler 175 kroków. Potem wykonywanych jest maksymalnie
25 aktualizacji po cztery train: 100 przykładów. `StopAfter` nie skraca planu
schedulera. LR bazowy 0,00005, warmup 9, linear decay do zera przy 175.
Pierwsza aktualizacja ma LR=0 zgodnie z dotychczasowym LambdaLR.

Pozostaw terminal otwarty do komunikatu `finished`. Skrypt pokazuje epokę,
lokalny krok/175, przykłady, loss, LR, czasy, VRAM, allocated/reserved, RSS,
dostępny RAM/commit i checkpointy. Zapisuje stdout/stderr **obok** katalogu
w `%RUN_DIR%.console.log`, zdarzenia w `%RUN_DIR%\events.jsonl`.
Po 25 nie rozpocznie kroku 26 ani walidacji.

W drugim CMD można podejrzeć GPU przez `nvidia-smi -l 2`, a plik logu przez
PowerShell `Get-Content -Tail 10 -Wait`. W nowym oknie ustaw prawdziwą ścieżkę
przebiegu; zmienne CMD nie przenoszą się do innych okien.

Aby poprosić o wcześniejszy STOP, w drugim CMD ustaw ścieżkę przebiegu i użyj:

```cmd
type nul > "%RUN_DIR%\STOP"
```

STOP kończy na granicy aktualizacji z zapisem checkpointu. Wcześniejszy STOP
nie zalicza pełnych 25 kroków. Zamknięcie okna lub Ctrl+C w oknie treningu
nie gwarantuje nowego zapisu. Ctrl+C w osobnym podglądzie logu kończy tylko podgląd.

## C. Kontrola po kroku 25

Oczekujemy kodu 0, `status=stopped`, lokalnego kroku 25, 100 przykładów,
planu nadal 175 i checkpointu `step-000025`. Poniższy test odczytuje wyłącznie
metadane, hashe i raport inicjalizacji; nie tworzy kontekstu CUDA:

```cmd
"%PY_VLM%" -X utf8 -c "import json,sys; from pathlib import Path; from market_levels.training.io.checkpoints import checkpoint_metadata; p=Path(sys.argv[1]); r=json.loads((p/'result.json').read_text(encoding='utf-8')); i=json.loads((p/'initialization.json').read_text(encoding='utf-8')); m=checkpoint_metadata(p/'checkpoints/step-000025'); z=checkpoint_metadata(p/'checkpoints/step-000000'); e=[json.loads(x) for x in (p/'events.jsonl').read_text(encoding='utf-8').splitlines()]; s=[x for x in e if x['event']=='step']; assert r['status']=='stopped' and r['sampler']['global_step']==25 and r['sampler']['processed_examples']==100; assert m['sampler']==r['sampler']; assert z['sampler']['global_step']==0 and z['sampler']['processed_examples']==0; assert i['tensor_values_exact'] and i['tensor_count']==112 and i['trainable_parameters']==1605632; assert i['parent_adapter_sha256']==m['parent_adapter_sha256']; assert [x['step'] for x in s]==list(range(1,26)) and all(x['total_steps']==175 for x in s); assert not any(x['event'] in ('failed','memory_pressure') for x in e); print('OK: lokalne 25 krokow, 100 train; plan 175; inicjalizacja i manifesty zgodne')" "%RUN_DIR%"
```

Dodatkowo można porównać faktyczne tensory źródła i checkpointu początkowego
na CPU (nie ładuje modelu ani starego `state.pt`):

```cmd
"%PY_VLM%" -X utf8 -c "import sys,torch; from pathlib import Path; from safetensors.torch import load_file; a=load_file(str(Path(sys.argv[1])/'adapter_model.safetensors'),device='cpu'); b=load_file(str(Path(sys.argv[2])/'checkpoints/step-000000/adapter/adapter_model.safetensors'),device='cpu'); assert len(a)==112 and a.keys()==b.keys() and all(torch.equal(a[k],b[k]) for k in a); print('112/112 tensorow poczatkowych dokladnie zgodnych')" "%PARENT%" "%RUN_DIR%"
```

Zachowaj ścieżkę `%RUN_DIR%` i prześlij logi do analizy. **Nie przechodź samoczynnie
do kolejnego odcinka przed kontrolą pierwszych 25 kroków.** Każda niezgodność
lub niezerowy kod oznacza brak zaliczenia odcinka. Kod 3 oznacza kontrolowane
zatrzymanie z powodu pamięci hosta, nie sukces 25 kroków.

`verify-checkpoint` / `checkpoint_metadata` sprawdzają manifest i bajty,
bez odtworzenia stanu na GPU. Zapis checkpointu sprawdza również deserializację
`state.pt` na CPU. Faktyczne odtworzenie modelu, AdamW, schedulera i RNG nastąpi
dopiero przy ręcznym wznowieniu nowego eksperymentu.

## D. Odcinek 2 — wznowienie lokalnych kroków 26–175

Po analizie odcinka 1, znów po zamknięciu IDE/Codexa, ustaw zmienne z sekcji A
oraz rzeczywistą ścieżkę pierwszego przebiegu. Jeżeli nadal jesteś w tej samej
sesji, `%RUN_DIR%` już ją zawiera:

```cmd
set "EXTRA_CHECKPOINT=%RUN_DIR%\checkpoints\step-000025"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\run_vlm_training.ps1 -Mode preflight -Config "%CFG%" -ApproveExtraEpoch -ResumeCheckpoint "%EXTRA_CHECKPOINT%"
echo Kod preflight wznowienia: %ERRORLEVEL%
```

Wyłącznie po kodzie 0:

```cmd
set "PART2_DIR=results\vlm44-part2-%RANDOM%-%RANDOM%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\run_vlm_training.ps1 -Mode extra-epoch -Config "%CFG%" -ApproveExtraEpoch -ResumeCheckpoint "%EXTRA_CHECKPOINT%" -StopAfter 150 -OutputDirectory "%PART2_DIR%"
set "PART2_EXIT=%ERRORLEVEL%"
echo Kod kontynuacji: %PART2_EXIT%
```

Nie podawaj `-InitializeAdapter` przy wznowieniu. Obie opcje wzajemnie się
wykluczają. Wznawiany jest pełny **nowy** checkpoint etapu 4.4: jego AdamW,
scheduler, RNG i kursor po pierwszych 100 train. Źródłowy adapter 350 jest
kontrolowany jako pochodzenie, ale nie jest ponownie ładowany do wag modelu.
Stary checkpoint 350 z nową konfiguracją zostanie odrzucony przed CUDA.

Kontrola końca nowej epoki:

```cmd
"%PY_VLM%" -X utf8 -c "import json,sys; from pathlib import Path; from market_levels.training.io.checkpoints import checkpoint_metadata; p=Path(sys.argv[1]); r=json.loads((p/'result.json').read_text(encoding='utf-8')); m=checkpoint_metadata(p/'checkpoints/step-000175'); e=[json.loads(x) for x in (p/'events.jsonl').read_text(encoding='utf-8').splitlines()]; s=[x for x in e if x['event']=='step']; assert r['status']=='stopped' and r['sampler']['global_step']==175 and r['sampler']['processed_examples']==698; assert m['sampler']==r['sampler']; assert [x['step'] for x in s]==list(range(26,176)) and all(x['total_steps']==175 for x in s); assert not any(x['event'] in ('failed','memory_pressure','initialized_from_adapter') for x in e); assert m['parent_checkpoint_step']==350 and m['additional_optimizer_steps']==175 and m['total_training_examples_seen_in_new_stage']==698; print('OK: nowy eksperyment zakonczony po 175 krokach i 698 train')" "%PART2_DIR%"
```

Lokalny krok 175 to koniec **dodatkowego eksperymentu**, nie krok 175 starego.
Umowne 350+175=525 jest liczbą aktualizacji obu eksperymentów, bez wspólnego
schedulera. `optimizer_state=new` i `scheduler_state=new` w pochodzeniu oznaczają
utworzenie ich na początku etapu 4.4, a nie reset przy każdym wznowieniu.

## E. Walidacja — po zakończeniu obu odcinków

Nie uruchamiaj jej równolegle z treningiem. Zakończony proces zwolni kontekst
CUDA. Oceniamy tylko te same 36 validation, oryginalny prompt i generowanie,
bez aktualizacji wag i bez użycia 66 testowych. Po kodzie 0 obu odcinków
i poprawnych kontrolach:

```cmd
set "VAL_NAME=vlm44-validation-%RANDOM%-%RANDOM%"
"%PY_VLM%" -u -X utf8 -m market_levels.cli.train_vlm validate-adapter --config "%CFG%" --adapter "%PART2_DIR%\adapter" --output results\%VAL_NAME%
echo Kod walidacji: %ERRORLEVEL%
```

Jeżeli kod wynosi 0:

```cmd
"%PY_VLM%" -X utf8 -m market_levels.cli.evaluate verify --output results\evaluation\%VAL_NAME%
type "results\evaluation\%VAL_NAME%\summary.json"
```

Oficjalny `sr-eval-v1` ocenia surowy JSON bez naprawy. Osobna diagnostyka cen
powstaje w `results\%VAL_NAME%\price-diagnostics\diagnostics.json` i nie zastępuje
oceny oficjalnej. Summary zawiera główne F1/P/R/TP/FP/FN, 0,25/1,0 ATR, JSON,
symbole i strony, przypadki bez trafienia, całe poprawne zestawy i MAE/ATR.
Diagnostyka obejmuje niewłaściwą stronę ostatniego Close. `per_example.jsonl`
w katalogu oficjalnej oceny oraz surowe `predictions.jsonl` pozwolą później
opisać najlepsze/najgorsze odpowiedzi według oficjalnego F1 przy 0,5 ATR,
z deterministycznym rozstrzyganiem remisów po ID. Nie twórz takich przykładów
przed powstaniem wyników.

Można później zapisać oficjalne porównanie:

```cmd
set "COMPARE_DIR=results\evaluation\vlm44-comparison-%RANDOM%-%RANDOM%"
"%PY_VLM%" -X utf8 -m market_levels.cli.evaluate compare --baseline results\evaluation\vlm43-validation-step350-9320-26567 --candidate results\evaluation\%VAL_NAME% --output "%COMPARE_DIR%"
"%PY_VLM%" -X utf8 -m market_levels.cli.evaluate verify --output "%COMPARE_DIR%"
```

Reguła ustalona przed startem: wyższe **oficjalne micro-F1 przy 0,5 ATR**,
następnie większy udział poprawnych JSON, następnie wcześniejszy adapter 350.
Pierwotny model A ma F1=0,4651162791. Diagnostyka cen nie wpływa na wybór.
Nie wykonujemy czwartej epoki ani siatki LR. Decyzję o dodatkowym eksperymencie
autor podjął po obejrzeniu validation; należy ujawnić to w pracy. Wybór nadal
opiera się na małej walidacji, nie na niezależnym teście.

## F. Błędy i przekazanie plików

Kod 0 oznacza poprawny koniec procesu, 1 — błąd, 2 może oznaczać błąd argumentów,
3 — zatrzymanie ze względu na RAM/commit. Kod i zawartość wyniku sprawdzaj razem.
Przy OOM, NaN/Inf, odmowie guard, złej rewizji, hashach/tensorach, nieudanym
zapisie, braku wersji bibliotek lub nieoczekiwanym zamknięciu zachowaj logi
i ostatni poprawny checkpoint. Nie uruchamiaj automatycznie ponownie i nie
zmieniaj rank, obrazu, LR, planu, offloadu ani systemu. Nie wybieraj `.partial`.

Do analizy przekaż z obu odcinków: `result.json`, `events.jsonl`,
`effective-config.json`, `identity.json`, `preflight.json`, `initialization.json`
(tylko z inicjalizacji), metadane i `manifest.json`/`manifest.sha256` checkpointów,
logi `<katalog>.console.log` i zapisane kody. Po walidacji dodaj kompletny mały
raport oficjalny z surowymi predykcjami i diagnostykę cen. Nie przesyłaj wag
Qwen, adapterów, `state.pt`, zbioru, środowiska ani cache.

W logach mogą pojawić się ostrzeżenia biblioteki; nie zmieniaj samodzielnie
parametrów generowania, żeby je usunąć. Czas i pamięć są rzeczywistymi pomiarami,
a próbki VRAM mogą pominąć krótki pik. Poprzedni trening osiągał nawet 7969 MiB
globalnego VRAM, więc powodzenie etapu 4.3 nie gwarantuje nowego przebiegu.

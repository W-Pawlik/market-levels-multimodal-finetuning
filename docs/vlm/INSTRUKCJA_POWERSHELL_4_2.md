# Etap 4.2 — uruchamianie z PowerShell

Pipeline korzysta z lokalnego Pythona VLM, bez IDE, notebooka, serwera ani Codexa.
Pełny trening pozostaje zablokowany w dostarczonej konfiguracji. Parametry etapu
4.3 są propozycją do zatwierdzenia, nie wynikiem zakończonego eksperymentu.

## Przygotowanie terminala

Otwórz menu Start, wpisz PowerShell i uruchom Windows PowerShell. Wpisz:

```powershell
Set-Location -LiteralPath 'D:\Studies\Inżynierka\market-levels-multimodal-finetuning'
$pythonVlm = 'D:/ml-envs/market-levels-vlm/Scripts/python.exe'
& $pythonVlm -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0)); print(torch.cuda.is_bf16_supported(including_emulation=False))"
nvidia-smi
```

Oczekiwane: torch 2.10.0+cu128, CUDA True, NVIDIA GeForce RTX 3060 Ti, BF16 True.
Nie instaluj ponownie środowiska. Preflight wymaga bezczynnego GPU ≤450 MiB
przed utworzeniem kontekstu CUDA, co najmniej 4096 MiB dostępnego RAM i 8192 MiB
zapasu systemowego commit. Zamknij zbędne aplikacje GPU. Nie zabijaj usług systemu.
Nie podnoś progów tylko po to, aby ominąć błąd kontroli.

## Kontrola bez treningu

Skrypt bez podania trybu wykonuje dry-run. Każdy przebieg dostaje unikalny katalog;
opcjonalne `-OutputDirectory` musi wskazywać nieistniejący katalog.

```powershell
.\scripts\run_vlm_training.ps1 -Mode dry-run
.\scripts\run_vlm_training.ps1 -Mode preflight
.\scripts\run_vlm_training.ps1 -Mode preflight -SmokePlan
```

Dry-run sprawdza cały manifest i train, planuje 698 przykładów i 350 kroków
dla dwóch proponowanych epok, ale nie ładuje modelu. Preflight dodatkowo sprawdza
GPU, BF16, wersje bibliotek, pamięć hosta i SHA-256 lokalnego checkpointu bazowego.
Odczyt pozostałych splitów podczas weryfikacji manifestu służy wyłącznie hashowaniu
bajtów. Nie wykonuje ich analizy ani inferencji.

## Ograniczony smoke-test i wznowienie

Poniższa próba wykonuje łącznie trzy kroki na dziewięciu train, w grupach 4/4/1.
Pierwszy proces kończy się po pierwszym kroku. Wznowienie używa nowego katalogu
wyjścia i nie zmienia całkowitego planu schedulera. Smoke ma warmup=0; pełny plan
zachowuje warmup z konfiguracji.

```powershell
$smokeRoot = 'results/smoke42-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
.\scripts\run_vlm_training.ps1 -Mode smoke-test -OutputDirectory ($smokeRoot + '-part1') -StopAfter 1
$checkpoint = $smokeRoot + '-part1/checkpoints/step-000001'
& $pythonVlm -m market_levels.cli.train_vlm verify-checkpoint --checkpoint $checkpoint
.\scripts\run_vlm_training.ps1 -Mode smoke-test -OutputDirectory ($smokeRoot + '-part2') -ResumeCheckpoint $checkpoint
& $pythonVlm -m market_levels.cli.train_vlm probe-adapter --adapter ($smokeRoot + '-part2/adapter') --output ($smokeRoot + '-probe')
```

`probe-adapter` odczytuje adapter w nowym procesie, wymaga dokładnej zgodności
tensorów i generuje odpowiedź na jednym train. To test techniczny, nie ocena jakości.
Nie ponawiaj automatycznie udanej próby tej iteracji. Budżet wykonanych tutaj
kroków GPU podaje raport. Dodatkowe ręczne próby wymagają osobnego planu.

## Logi, zasoby i zatrzymywanie

Terminal pokazuje epokę, globalny krok/plan, liczbę przykładów, loss, LR, czas kroku
i upływ treningu, globalny VRAM, allocated/reserved, RSS i dostępny RAM/commit.
Pełny zapis maszynowy to `events.jsonl`; stdout/stderr zapisują się obok katalogu
wyniku w `<katalog>.console.log`. Skrypt zwraca rzeczywisty kod procesu: 0 dla
kontrolowanego zakończenia, 1 dla błędu, 3 dla przerwania z powodu pamięci hosta.

```powershell
Get-Content -LiteralPath 'results/NAZWA_PRZEBIEGU/events.jsonl' -Tail 10 -Wait
nvidia-smi -l 2
```

Monitoruj je w dodatkowym oknie PowerShell. Reserved pod Windows WDDM może
przekraczać 8192 MiB; nie jest to liczba fizycznie zajętych MiB VRAM.

Aby zażądać zatrzymania, w drugim terminalu utwórz plik:

```powershell
New-Item -ItemType File -Path 'results/NAZWA_PRZEBIEGU/STOP'
```

Pętla dokończy bieżącą grupę microbatchy, wykona krok i zapisze pełny checkpoint.
Żądanie istniejące przed grupą nie rozpocznie następnego kroku. Po komunikacie
`finished` odczytaj `result.json` i `checkpoints/latest.txt`. Nie zamykaj okna
treningu przed potwierdzeniem zapisu. Ctrl+C lub zamknięcie terminala może utracić
niezapisane kroki; nie jest gwarantowanym sposobem bezpiecznego zatrzymania.

Checkpoint `checkpoints/step-NNNNNN/` zawiera adapter oraz `state.pt`, stany RNG,
optymalizatora, schedulera, samplera, metadane i manifest. Osobny `adapter/`
służy wyłącznie inferencji. Wznawiaj tylko własne zaufane checkpointy lokalne:
stan PyTorch jest odczytywany z `weights_only=False` po kontroli hashy.

## OOM i pozostałe błędy

Nie ma automatycznych powtórzeń OOM ani zmiany rozdzielczości, rank, offloadu
czy pliku stronicowania. Proces zapisuje błąd i ścieżkę ostatniego poprawnego
checkpointu, bez zapisu częściowo wykonanego kroku. Po diagnozie wolno wznowić
z ostatniego kompletnego checkpointu do nowego katalogu. Kroki od jego zapisu
trzeba wykonać ponownie. Nie wybieraj `.partial`; ostatni poprawny katalog pozostaje
nienaruszony. Checkpointy nie są automatycznie usuwane.

Wznowienie wymaga tej samej efektywnej konfiguracji, danych, rewizji, procesora
i środowiska bibliotek. `--stop-after` ogranicza tylko bieżący proces, więc nie
zmienia planu eksperymentu. Zmiana `max_steps`, LR lub epok unieważnia zgodność.

## Przyszły pełny trening — NIE DO WYKONANIA W ETAPIE 4.2

Najpierw autor zatwierdza plan i regułę rankingu opisaną w raporcie. Następnie
tworzy kopię pełnej konfiguracji przez `read_configuration`, ustawia w niej
`pipeline.full_approved=true` i świadomie przekazuje osobną flagę wykonania.
Rozwinięcie konfiguracji jest potrzebne, aby `$file` nadal działało po zmianie
lokalizacji pliku. Przykład utworzenia kopii po zatwierdzeniu:

```powershell
& $pythonVlm -c "import json; from pathlib import Path; from market_levels.shared.configuration import read_configuration; c=read_configuration(Path('configs/vlm/training.json')); c['pipeline']['full_approved']=True; Path('configs/vlm/training-approved-local.json').open('x', encoding='utf-8').write(json.dumps(c, ensure_ascii=False, indent=2))"
```

Zapisz pracę, zamknij VS Code i Codexa, pozostaw zwykły PowerShell w katalogu
projektu. Zamknij zbędne aplikacje GPU i wykonaj ponownie preflight. Dopiero
w osobno zatwierdzonym etapie:

```powershell
.\scripts\run_vlm_training.ps1 -Mode full -Config configs/vlm/training-approved-local.json -ApproveFullTraining
```

Proces zakończy się również na skonfigurowanej granicy walidacji, domyślnie po
175 krokach. Po pełnym zakończeniu procesu treningowego uruchom w osobnym procesie:

```powershell
& $pythonVlm -m market_levels.cli.train_vlm validate-adapter --config configs/vlm/training-approved-local.json --adapter results/NAZWA_PRZEBIEGU/adapter --output results/vlm42-validation-NOWY
& $pythonVlm -m market_levels.cli.evaluate verify --output results/evaluation/vlm42-validation-NOWY
```

To pełna walidacja 36 obrazów z identycznym generowaniem jak bazowe NF4.
Powstają surowe predykcje, oficjalny raport `sr-eval-v1` oraz oddzielna diagnostyka
cen. Żaden JSON nie jest naprawiany przed oficjalną oceną. Następnie ręcznie
wznów `full` do nowego katalogu z `-ResumeCheckpoint` i tą samą zatwierdzoną
konfiguracją. Koszt granic procesu obejmuje ponowne ładowanie modelu i checkpointu.
Nie uruchamiaj walidacji równolegle z treningiem. Nie używaj splitu test.

## Diagnostyka zapisanych odpowiedzi

Nie wymaga GPU ani nowej inferencji:

```powershell
& $pythonVlm -m market_levels.cli.train_vlm diagnostics --predictions results/evaluation/vlm41-cz2-20261110-1840-nf4/predictions.jsonl --output results/diagnostics/nf4-price-NOWY
```

Oficjalne F1 pozostaje osobną miarą. Pomocnicze F1 po zdjęciu samego zewnętrznego
Markdown nie jest oficjalnym wynikiem. Raport nie dowodzi poprawności rynkowej
referencji algorytmu; MAE opisuje jedynie faktycznie dopasowane pary.

# Etap 4.1, część 2 — polecenia PowerShell

Uruchamiać z katalogu głównego projektu. Środowisko VLM pozostaje oddzielone
od `.venv` procesu danych. Nie instalować ponownie bibliotek ani wag.
Każde wyjście musi być nowym katalogiem. Polecenia poniżej działają w kodzie
`market_levels.cli.vlm_stability`; nie uruchamiają etapu 4.2 ani splitu test.

```powershell
$pythonVlm = 'D:/ml-envs/market-levels-vlm/Scripts/python.exe'
$run = 'results/vlm41-cz2-20261110-1840' # istniejący wynik: tylko do odczytu
& $pythonVlm -m market_levels.cli.vlm_stability --help
& $pythonVlm -m market_levels.cli.evaluate evaluate --help
nvidia-smi
Get-Content "$run/preflight/cuda.json"
Get-Content "$run/preflight/checkpoint.json"
```

Odtworzenie obliczeń wymaga nowej nazwy przebiegu. Przed nim zapisać inwentarz
historycznych `data/` i `results/` (skrypt kontroli poniżej, tryb `before`).
Nie wykonywać kolejnego treningu tylko w celu odczytania istniejących wyników.

```powershell
$newRun = 'results/vlm41-cz2-NOWY-ID'
& $pythonVlm scripts/verify_vlm41_cz2.py before --run $newRun
& $pythonVlm -m market_levels.cli.vlm_stability preflight --output "$newRun/preflight"
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed' }
& $pythonVlm -m market_levels.cli.vlm_stability train --output "$newRun/train"
if ($LASTEXITCODE -ne 0) { throw 'Training failed; inspect the result, do not retry automatically' }
```

Trening wykonuje dokładnie osiem kolejnych aktualizacji AdamW na 32 train,
po cztery microbatche, z jedną instancją modelu i optymalizatora. Lista i reguła
selekcji są w `train/selected-train.json`. OOM kończy próbę bez ponowień.
Próg startowy 450 MiB dotyczy globalnego użycia przed ładowaniem modelu.
Nie oznacza gwarancji dostatecznego zapasu podczas pracy WDDM.

```powershell
Get-Content "$run/train/training-result.json"
Get-Content "$run/train/step-01.json"
Get-Content "$run/train/step-08.json"
Get-ChildItem "$run/train/adapter"
```

Odczyt adaptera koniecznie w nowym procesie. Korzysta z identycznej konfiguracji
próby, rewizji i NF4, przywraca również typy zamrożonych parametrów po przygotowaniu
PEFT. Wykonuje dwie inferencje techniczne; nie ocenia jakości tego adaptera.

```powershell
& $pythonVlm -m market_levels.cli.vlm_stability reload --precision nf4 --adapter "$newRun/train/adapter" --output "$newRun/reload"
if ($LASTEXITCODE -ne 0) { throw 'Adapter reload failed' }
Get-Content "$run/reload/adapter-check.json"
Get-Content "$run/reload/probe/predictions.jsonl"
& $pythonVlm -m market_levels.cli.vlm_stability resave --precision nf4 --adapter "$newRun/train/adapter" --output "$newRun/roundtrip-source"
if ($LASTEXITCODE -ne 0) { throw 'Adapter resave failed' }
& $pythonVlm -m market_levels.cli.vlm_stability reload --precision nf4 --adapter "$newRun/roundtrip-source/adapter" --output "$newRun/roundtrip-reload"
if ($LASTEXITCODE -ne 0) { throw 'Strict roundtrip failed' }
Get-Content "$run/roundtrip-reload/adapter-check.json"
```

Dodatkowe `resave` nie trenuje modelu. Wykonuje migawkę tensorów i dwie
inferencje przed serializacją niezmienionego adaptera; kolejny `reload`
w nowym procesie pozwala porównać dosłownie stan przed zapisem i po odczycie.
W pierwszej wykonanej próbie migawka `train/adapter-before-save.safetensors`
powstała po serializacji, przed zamknięciem procesu; dodatkowa próba domyka
to rozróżnienie bez powtarzania treningu. Aktualny kod treningu zapisuje już
migawkę i próby generacji przed `save_pretrained`.

Pełna walidacja bazowego modelu: osobne procesy BF16 i NF4, te same 36 obrazów.
NF4 jest głównym odniesieniem przyszłego NF4 + adapter; BF16 wynikiem pomocniczym.
NF4 zachowuje również typy parametrów niemających kwantyzacji, zgodne z próbą
QLoRA: przygotowanie PEFT, wizja przywrócona do BF16. Wszystkie parametry pozostają
na CUDA. Bez adaptera i bez aktualizacji parametrów podczas walidacji.

```powershell
foreach ($precision in @('bf16', 'nf4')) {
    & $pythonVlm -m market_levels.cli.vlm_stability validate --precision $precision --output "$newRun/base-$precision"
    if ($LASTEXITCODE -ne 0) { throw "Validation failed: $precision" }
    $evaluationDirectory = "results/evaluation/$(Split-Path $newRun -Leaf)-$precision"
    & $pythonVlm -m market_levels.cli.evaluate evaluate --dataset data/datasets/ds35-800-20261107-a --split validation --predictions "$newRun/base-$precision/predictions.jsonl" --run-manifest "$newRun/base-$precision/run.json" --output $evaluationDirectory
    if ($LASTEXITCODE -ne 0) { throw "Evaluation failed: $precision" }
    & $pythonVlm -m market_levels.cli.evaluate verify --output $evaluationDirectory
    if ($LASTEXITCODE -ne 0) { throw "Verification failed: $precision" }
    if (Test-Path -LiteralPath "$newRun/evaluation-$precision") { throw 'Evaluation copy already exists' }
    Copy-Item -LiteralPath $evaluationDirectory -Destination "$newRun/evaluation-$precision" -Recurse
}
```

Nie używać `evaluate compare` do porównania tych dwóch bazowych wariantów:
obecny kontrakt tego polecenia wymaga pary base → finetuned i identycznych
ustawień inferencji. Oba raporty pozostają osobnymi oficjalnymi ocenami.
Surowy Markdown w odpowiedzi pozostaje błędem formatu, bez naprawiania JSON.
Ewaluator dopuszcza publikację tylko w `results/evaluation/` lub
`results/diagnostics/`; dlatego oficjalne wyniki powstają w pierwszej lokalizacji,
a ich zapieczętowane kopie są dołączane do katalogu iteracji. Kontrola integralności
dopuszcza te dwa nowe katalogi, wciąż wymagając niezmienionych SHA wszystkich
historycznych plików i odrzucając pozostałe nieoczekiwane nowe pliki.

Monitoring w osobnym terminalu (zakończenie Ctrl+C):

```powershell
nvidia-smi --query-gpu=timestamp,memory.used,memory.free,utilization.gpu --format=csv -l 1
```

Po OOM zachować `training-result.json`, log, konfigurację i pomiary. Poczekać
na zakończenie procesu, ponownie wykonać `nvidia-smi`, sprawdzić aktywne aplikacje.
Nie uruchamiać pętli prób ani automatycznego CPU offload. Zmniejszenie budżetu obrazu
byłoby osobnym wariantem warunków; obecny CLI celowo odrzuca taką zmianę zamrożonej
konfiguracji. Rezerwacja PyTorch i fizyczny VRAM WDDM mają różne znaczenie.

Podczas wykonania wykryto również **Windows 1455**, błąd pamięci zadeklarowanej
hosta przy otwieraniu safetensors, przed predykcjami BF16. Diagnostyka:

```powershell
Get-Process | Sort-Object PrivateMemorySize64 -Descending | Select-Object -First 10 ProcessName,Id,WorkingSet64,PrivateMemorySize64
Get-CimInstance Win32_OperatingSystem | Select-Object FreePhysicalMemory,FreeVirtualMemory,TotalVirtualMemorySize
Get-CimInstance Win32_PageFileUsage | Select-Object Name,AllocatedBaseSize,CurrentUsage,PeakUsage
# Dla konkretnego PID wykrytego powyżej:
Get-CimInstance Win32_Service | Where-Object ProcessId -eq 9980 | Select-Object Name,State,ProcessId
```

W tej konkretnej próbie winna była usługa powiadomień `WpnUserService_9648847`,
zajmująca około 54 GiB pamięci prywatnej. Autor osobno zezwolił na jej restart;
usługa wróciła do stanu Running i zwolniła pamięć. PID i sufiks usługi są
lokalne dla tamtej sesji; nie używać ich bez ponownej identyfikacji procesu.
Nie zmieniano rozmiaru pliku stronicowania ani ustawień modelu. Po usunięciu
przyczyny uruchomiono cały wariant BF16 od początku w nowym katalogu, ponieważ
nieudana próba nie wygenerowała żadnych predykcji. Nie ponawiano wybiórczo ID.

Testy i kontrola danych:

```powershell
& .venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -v
& $pythonVlm -X utf8 tests/checks/check_vlm_masking.py
& $pythonVlm scripts/verify_vlm41_cz2.py after --run $newRun
```

Skrypt `after` porównuje SHA historycznych danych i wyników oraz wymaga kompletnego
treningu, zgodności adaptera i obu zestawów 36 predykcji. Nie zmienia danych.
Adapter lokalnej wykonanej próby: `results/vlm41-cz2-20261110-1840/train/adapter/`.

# Etap 4.3, część 1 — ręczne uruchomienie kroków 1–25

Przygotowano jeden eksperyment: 698 train, dwie epoki, 350 aktualizacji.
Ta instrukcja uruchamia tylko pierwszy odcinek. Treningu jeszcze nie wykonano.
Do uruchomienia wystarcza zwykły Windows PowerShell; IDE, Codex, notebook,
serwer HTTP i zewnętrzne API nie są potrzebne.

## A. Przygotowanie

Zapisz pracę i zamknij VS Code oraz Codexa. Zamknij zbędne aplikacje korzystające
z GPU/RAM. Z menu Start otwórz Windows PowerShell. W ustawieniach zasilania
sprawdź, czy komputer nie uśnie podczas eksperymentu; skrypty nie zmieniają
ustawień systemowych. Nie zatrzymuj losowo usług Windows.

```powershell
Set-Location -LiteralPath 'D:\Studies\Inżynierka\market-levels-multimodal-finetuning'
$pythonVlm = 'D:/ml-envs/market-levels-vlm/Scripts/python.exe'
$config = 'configs/vlm/training-approved-local.json'
if (-not (Test-Path -LiteralPath $pythonVlm)) { throw 'Brak Pythona VLM' }
& $pythonVlm -X utf8 -c "import sys,importlib.metadata as m; print(sys.version); print({k:m.version(k) for k in ('torch','transformers','peft','bitsandbytes','accelerate','psutil')})"
if ($LASTEXITCODE -ne 0) { throw 'Błąd środowiska; zachowaj komunikat, nie instaluj automatycznie bibliotek' }
& $pythonVlm -X utf8 -c "from market_levels.training.io.resources import snapshot; import json; print(json.dumps(snapshot(),indent=2))"
nvidia-smi
Get-PSDrive -PSProvider FileSystem | Select-Object Name,Used,Free
```

Python: 3.12.12; torch 2.10.0+cu128, Transformers 5.3.0, PEFT 0.18.1,
bitsandbytes 0.49.2, Accelerate 1.12.0. Nie aktualizuj środowiska ani sterownika.
Wymagane przed kontekstem CUDA: globalny VRAM ≤450 MiB, dostępny RAM ≥4096 MiB,
wolny commit Windows ≥8192 MiB. `snapshot()` pokazuje MiB, także RSS procesu
pomiarowego; właściwy trening ma osobny RSS. Sprawdź wolne miejsce na C i D.
Zostaw kilka GiB na checkpointy, logi i staging; nie jest to gwarantowany
górny limit. Checkpointy nie są automatycznie usuwane.

## B. Kontrola przed uruchomieniem

```powershell
$preflightDir = 'results/vlm43-preflight-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6)
.\scripts\run_vlm_training.ps1 -Mode preflight -Config $config -OutputDirectory $preflightDir
$preflightExit = $LASTEXITCODE
if ($preflightExit -ne 0) { throw "Preflight nie przeszedł: $preflightExit. Nie uruchamiaj treningu." }
Get-Content -LiteralPath (Join-Path $preflightDir 'report.json') -Raw
```

Preflight nie uruchamia uczenia ani nie ładuje modelu. Tworzy kontekst CUDA
do kontroli BF16/GPU, sprawdza wersje, pamięć i lokalne SHA-256 bazowych wag.
Nie potrzebuje flagi zatwierdzenia treningu. Nie omijaj odmowy przez podnoszenie
progów. Po poprawnej kontroli jej proces kończy się i zwalnia własny kontekst.
Właściwy proces powtarza preflight tuż przed ładowaniem modelu. Codex nie wykonał
tego rzeczywistego preflight podczas przygotowania.

## C. Pierwsze 25 kroków — wykonuje wyłącznie autor

W tym samym interaktywnym terminalu, dopiero po poprawnym preflight:

```powershell
$runDir = 'results/vlm43-part1-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6)
$runDir | Set-Content -Encoding UTF8 -LiteralPath 'results/vlm43-part1-last-path.txt'
.\scripts\run_vlm_training.ps1 -Mode full -Config configs/vlm/training-approved-local.json -ApproveFullTraining -StopAfter 25 -OutputDirectory $runDir
$trainingExit = $LASTEXITCODE
@{ exit_code = $trainingExit; output = $runDir } | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath ($runDir + '.exit.json')
```

Polecenia nie wykonano podczas przygotowania. `StopAfter` liczy aktualizacje
optymalizatora w tym procesie: 25 × 4 microbatche po jednym przykładzie = 100.
Nie zmienia `max_steps`, dwóch epok ani schedulera 350 kroków. Warmup: 18 kroków,
LR bazowy 0,0002, linear decay. Pierwsza aktualizacja używa LR=0 zgodnie
z dotychczasowym LambdaLR. Limit obejmuje wywołania `optimizer.step()`.

Katalog wyjścia musi być nowy. Log stdout/stderr powstaje **obok** niego:
`$runDir.console.log`. Nie ma osobnego `console.log` wewnątrz katalogu.
Skrypt zwraca kod Pythona; wywołany z interaktywnego PowerShella pozostawia
terminal otwarty. Nie uruchamiaj go przez dwuklik ani zamykające się `powershell -File`.

## D. Monitorowanie i żądanie STOP

W drugim PowerShellu przejdź do tego samego katalogu projektu i odczytaj ścieżkę:

```powershell
Set-Location -LiteralPath 'D:\Studies\Inżynierka\market-levels-multimodal-finetuning'
$runDir = (Get-Content -Encoding UTF8 -LiteralPath 'results/vlm43-part1-last-path.txt' -Raw).Trim()
Get-Content -Encoding UTF8 -LiteralPath (Join-Path $runDir 'events.jsonl') -Tail 5 -Wait
```

Każdy poniższy podgląd ciągły uruchamiaj oddzielnie; Ctrl+C kończy podgląd,
nie proces treningowy w innym oknie:

```powershell
Get-Content -LiteralPath ($runDir + '.console.log') -Tail 20 -Wait
nvidia-smi -l 2
Get-ChildItem -LiteralPath (Join-Path $runDir 'checkpoints') -Directory
Get-Content -LiteralPath (Join-Path $runDir 'checkpoints/latest.txt')
```

Terminal pokazuje epokę, krok/350, przykłady, loss, LR użyty w danym kroku,
czas kroku i łączny czas przebiegu, globalny VRAM, allocated/reserved,
RSS, dostępny RAM i wolny commit. Zapisuje checkpointy, ostrzeżenia i zakończenie.
`events.jsonl` zawiera dodatkowo próbki pamięci co około 0,5 s w trakcie kroku,
minimum RAM/commit i peak VRAM/RSS. Próbkowanie może pominąć krótki pik.
PyTorch peak allocated/reserved zapisuje osobno. Reserved pod WDDM może
przekraczać fizyczne 8 GiB i nie oznacza fizycznie zajętego VRAM.
`elapsed_seconds` obejmuje przygotowanie procesu i wcześniejsze odcinki,
ale nie czas, przez który komputer czekał między procesami, ani końcowy eksport.

W razie potrzeby zakończenia przed krokiem 25:

```powershell
New-Item -ItemType File -Path (Join-Path $runDir 'STOP')
```

Program dokończy bieżącą aktualizację, wyczyści gradienty i zapisze checkpoint.
Jeśli STOP jest widoczny przed grupą, nie rozpocznie jej. Czekaj na `finished`.
Ctrl+C w oknie treningu lub zamknięcie okna nie gwarantuje nowego checkpointu.
Wcześniejsze zatrzymanie jest bezpiecznym przerwaniem, ale nie zalicza odcinka 25.

## E. Sprawdzenie po zakończeniu

W pierwszym terminalu, bez uruchamiania kolejnego treningu lub walidacji:

```powershell
if ($trainingExit -ne 0) { throw "Błąd procesu: $trainingExit" }
$r = Get-Content -Encoding UTF8 -LiteralPath (Join-Path $runDir 'result.json') -Raw | ConvertFrom-Json
$e = @(Get-Content -Encoding UTF8 -LiteralPath (Join-Path $runDir 'events.jsonl') | ForEach-Object { $_ | ConvertFrom-Json })
$pythonVlm = 'D:/ml-envs/market-levels-vlm/Scripts/python.exe'
$c = & $pythonVlm -X utf8 -c "import json,sys; print(json.dumps({'pipeline':json.load(open(sys.argv[1],encoding='utf-8'))['pipeline']}))" (Join-Path $runDir 'effective-config.json') | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Błąd odczytu konfiguracji' }
$ckpt = Join-Path $runDir 'checkpoints/step-000025'
$meta = & $pythonVlm -X utf8 -c "import json,sys; print(json.dumps({'sampler':json.load(open(sys.argv[1],encoding='utf-8'))['sampler']}))" (Join-Path $ckpt 'metadata.json') | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Błąd odczytu metadanych' }
$steps = @($e | Where-Object { $_.event -eq 'step' })
$bad = @($e | Where-Object { $_.event -in @('failed','memory_pressure') })
$finished = @($e | Where-Object { $_.event -eq 'finished' })
if ($r.status -ne 'stopped' -or $r.sampler.global_step -ne 25 -or $r.sampler.processed_examples -ne 100) { throw 'Nieprawidłowy wynik odcinka' }
if ($steps.Count -ne 25 -or ($steps.step -join ',') -ne ((1..25) -join ',') -or $bad.Count -gt 0 -or $finished.Count -ne 1) { throw 'Nieprawidłowe zdarzenia' }
if ($meta.sampler.global_step -ne 25 -or $meta.sampler.processed_examples -ne 100) { throw 'Nieprawidłowe metadane' }
if ((Get-Content -LiteralPath (Join-Path $runDir 'checkpoints/latest.txt') -Raw).Trim() -ne 'step-000025') { throw 'Inny ostatni checkpoint' }
if ((Resolve-Path -LiteralPath $r.latest_checkpoint).Path -ne (Resolve-Path -LiteralPath $ckpt).Path) { throw 'Niezgodna ścieżka checkpointu' }
if ($c.pipeline.epochs -ne 2 -or $null -ne $c.pipeline.max_steps -or $c.pipeline.gradient_accumulation -ne 4 -or $c.pipeline.warmup_steps -ne 18 -or $c.pipeline.validate_every_steps -ne 175) { throw 'Zmieniony plan' }
if (@($steps | Where-Object { $_.total_steps -ne 350 }).Count -gt 0) { throw 'Inny plan schedulera' }
$pythonVlm = 'D:/ml-envs/market-levels-vlm/Scripts/python.exe'
& $pythonVlm -X utf8 -m market_levels.cli.train_vlm verify-checkpoint --config configs/vlm/training-approved-local.json --checkpoint $ckpt
if ($LASTEXITCODE -ne 0) { throw 'Checkpoint nie przeszedł weryfikacji' }
$r | Select-Object status,latest_checkpoint
$r.sampler | Select-Object global_step,processed_examples,epoch,position
'Kolejna granica walidacji: 175; koniec eksperymentu: 350. Teraz zatrzymaj pracę.'
```

`verify-checkpoint` sprawdza manifest, SHA-256, wymagane komponenty i metadane;
nie ładuje Qwen ani stanu treningu na GPU. Sam zapis checkpointu sprawdza też
deserializację `state.pt` na CPU. Pełne odtworzenie adaptera, AdamW, schedulera
i RNG nastąpi dopiero przy przyszłym ręcznym wznowieniu. Nie traktuj samej
weryfikacji manifestu jako testu odtworzenia GPU.

Konfigurację i metadane odczytujemy przez Pythona, wybierając potrzebną sekcję.
Windows PowerShell 5.1 nie umie przetworzyć przez `ConvertFrom-Json` pustego
klucza w `fixed.device_map` pełnej konfiguracji. Plików nie trzeba zmieniać.

Po kroku 25 oczekujemy `status=stopped`, kodu 0, 100 przykładów,
`step-000025`, braku kroku 26 i braku walidacji. Obejrzyj także końcówkę
logu konsoli: ostrzeżenie biblioteki nie musi oznaczać awarii, ale błędu zapisu
lub tracebacku nie wolno zignorować. Każda rozbieżność oznacza brak zaliczenia
odcinka. Zatrzymaj się i przekaż materiały do analizy.

Przyszłe odcinki tego samego eksperymentu zachowają konfigurację i pełny stan:
po wznowieniu z 25 kolejny krok to 26; granica 175 przetworzy 698 przykładów,
a 350 — 1396. Ostatnia grupa każdej epoki ma dwa przykłady. Granica 175 kończy
proces ze statusem `validation_due`; 350 ze statusem `complete`, a końcową
walidację uruchamia się później osobno. Ta część nie zawiera poleceń wznowienia
ani walidacji. Nie są wykonywane automatycznie.

## F. Błędy i przekazanie do analizy

Kod 0 oznacza kontrolowane zakończenie, 1 — błąd, 3 — zatrzymanie z powodu
pamięci hosta. Błąd argumentów parsera może zwrócić 2. Nie utożsamiaj samego
kodu 0 z zaliczeniem; wymagane są wszystkie kontrole sekcji E.

| Sytuacja | Działanie |
| --- | --- |
| Zajęty GPU, mało RAM lub wolnego commit przed startem | Zachowaj komunikat; zamknij zbędne aplikacje, ponownie oceń pamięć. Nie podnoś progów. |
| CUDA OOM | Zachowaj logi, `result.json` i ostatni poprawny checkpoint. Bez automatycznego ponawiania. |
| Błąd ładowania modelu, np. Windows 1455 | Zachowaj błąd i pomiary RAM/commit. To nie musi być CUDA OOM. |
| NaN/Inf loss lub gradientów | Proces przerywa bez zapisywania częściowej aktualizacji; zachowaj ostatni pełny checkpoint. |
| Nieudany zapis, brak miejsca lub uszkodzony checkpoint | Nie używaj `.partial`; zachowaj cały katalog i wcześniejszy poprawny checkpoint. Nie nadpisuj manifestów. |
| Nieoczekiwane zamknięcie procesu | Wynik/zdarzenie `finished` może nie istnieć; zachowaj dostępne logi i nie uznawaj odcinka za zakończony. |
| Błąd konfiguracji lub brak wymaganej wersji pakietu | Zachowaj komunikat i wersje; bez automatycznej instalacji lub zmiany parametrów. |

Program nie zmienia rozdzielczości, rank, LR, schedulera, liczby kroków ani
pliku stronicowania i nie ponawia automatycznie treningu. Wznawianie wymaga
oddzielnej analizy oraz świadomego uruchomienia autora.

Przekaż do ChatGPT: `result.json`, `events.jsonl`, `preflight.json`,
`effective-config.json`, `identity.json`, `model.json` (jeżeli powstał),
`checkpoints/step-000025/metadata.json`, `manifest.json`, `manifest.sha256`,
log konsoli obok przebiegu, zapis kodu zakończenia oraz osobny raport preflight.
Zdarzenia i wynik zawierają pomiary RAM/VRAM; dołącz również obserwacje
`nvidia-smi`, jeśli widziałeś inne procesy lub nietypowe zachowanie.
Nie przesyłaj wag Qwen, adapterów, `state.pt`, całego zbioru, środowiska ani cache.

Poniższy opcjonalny blok tworzy mały ZIP z jawnej listy plików tekstowych.
Można go użyć także po awarii; lista brakujących plików trafi do archiwum.
Nie pakuje katalogów rekurencyjnie. Przed wysłaniem obejrzyj jego zawartość;
nie dopisuj tokenów ani danych dostępowych do logów.

```powershell
$reviewDir = 'results/vlm43-review-' + [guid]::NewGuid().ToString('N').Substring(0,8)
New-Item -ItemType Directory -Path $reviewDir | Out-Null
$files = @('result.json','events.jsonl','preflight.json','effective-config.json','identity.json','model.json',
    'checkpoints/step-000025/metadata.json','checkpoints/step-000025/manifest.json','checkpoints/step-000025/manifest.sha256')
$missing = @()
foreach ($relative in $files) {
    $source = Join-Path $runDir $relative
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        $target = Join-Path $reviewDir $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $source -Destination $target
    } else { $missing += $relative }
}
if (Test-Path -LiteralPath ($runDir + '.console.log')) { Copy-Item -LiteralPath ($runDir + '.console.log') -Destination (Join-Path $reviewDir 'console.log') }
if (Test-Path -LiteralPath ($runDir + '.exit.json')) { Copy-Item -LiteralPath ($runDir + '.exit.json') -Destination (Join-Path $reviewDir 'exit.json') }
if ($preflightDir -and (Test-Path -LiteralPath (Join-Path $preflightDir 'report.json'))) { Copy-Item -LiteralPath (Join-Path $preflightDir 'report.json') -Destination (Join-Path $reviewDir 'preflight-separate.json') }
$missing | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $reviewDir 'missing-files.json')
$textFiles = @(Get-ChildItem -LiteralPath $reviewDir -File -Recurse)
# W razie trafienia obejrzyj plik lokalnie i usuń sekret wyłącznie z kopii do wysłania.
foreach ($file in $textFiles) {
    $text = Get-Content -LiteralPath $file.FullName -Raw
    if ($text -match '(?i)hf_[a-z0-9]{20,}|sk-[a-z0-9_-]{20,}|bearer\s+[a-z0-9._-]+|"(?:access_token|api_key|password|secret)"\s*:\s*"[^"\s]+"') { throw ('Możliwy sekret w kopii: ' + $file.FullName) }
}
$textFiles | ForEach-Object { [pscustomobject]@{ file=$_.FullName.Substring((Resolve-Path -LiteralPath $reviewDir).Path.Length+1); sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash } } | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $reviewDir 'review-manifest.json')
Compress-Archive -Path (Join-Path $reviewDir '*') -DestinationPath ($reviewDir + '.zip')
Get-FileHash -Algorithm SHA256 -LiteralPath ($reviewDir + '.zip') | Format-List
```

Kontrola wzorców wykrywa typowe tokeny; nie jest ogólnym wykrywaczem wszystkich
sekretów. Źródłowe pliki eksperymentu pozostają nienaruszone. Manifest checkpointu
odnosi się także do lokalnych wag i `state.pt`, których ZIP celowo nie zawiera;
archiwum służy analizie, a nie wznowieniu treningu.

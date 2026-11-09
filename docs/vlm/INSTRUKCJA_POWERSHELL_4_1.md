# Etap 4.1, część 1 — lokalna diagnostyka VLM

Polecenia wykonuj z głównego katalogu projektu. Ten interfejs obsługuje
osiem obrazów validation i jeden krok optymalizatora na czterech przykładach
train. Nie udostępnia pełnego treningu ani wyboru splitu test.

## 1. Sprzęt i WSL2

```powershell
nvidia-smi
nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,driver_version,compute_cap --format=csv
py -0p
wsl --status
wsl --version
wsl --list --verbose
Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors
Get-CimInstance Win32_OperatingSystem | Select-Object Caption,BuildNumber,TotalVisibleMemorySize,FreePhysicalMemory
Get-PSDrive -PSProvider FileSystem
```

Na komputerze audytu jest WSL2 i tylko techniczna dystrybucja `docker-desktop`.
Nie używaj jej jako środowiska treningowego. Próby wykonano w izolowanym Windows.
Opcjonalne przygotowanie Ubuntu to osobna, ręczna czynność autora:

```powershell
# Tylko jeśli autor chce przygotować nowe środowisko Linux:
wsl --install -d Ubuntu-24.04
wsl --set-version Ubuntu-24.04 2
wsl -d Ubuntu-24.04 -- uname -r
wsl -d Ubuntu-24.04 -- /usr/lib/wsl/lib/nvidia-smi
```

Instalator może wymagać praw administratora lub restartu. W tej części go
nie uruchamiano. Nie instaluj sterownika NVIDIA wewnątrz WSL; GPU udostępnia
sterownik Windows. Obecność `nvidia-smi` nie zastępuje testu PyTorch.

## 2. Istniejące środowisko VLM

```powershell
$vlmPython = 'D:/ml-envs/market-levels-vlm/Scripts/python.exe'
& $vlmPython -X utf8 -c "import torch; print(torch.__version__, torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name()); print(torch.cuda.is_bf16_supported(including_emulation=False))"
.\scripts\audit_vlm_environment.ps1 -Python $vlmPython -OutputDirectory ('results/vlm-audit-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
```

Skrypt audytu sprawdza również rzeczywisty forward i backward dla FP16, BF16
i FP32. Biblioteki i runtime CUDA znajdują się w osobnym środowisku; systemowego
CUDA ani sterowników nie zmieniano. `.venv` nadal obsługuje proces danych.

## 3. Odtworzenie środowiska, jeśli jest potrzebne

Wykonuj tylko przy braku środowiska. `uv` był już zainstalowany u autora.
Wersje głównych zależności zapisano w `configs/vlm/requirements-windows-cu128.txt`,
a wszystkich rozwiązanych bibliotek w `configs/vlm/environment-lock.txt`.

```powershell
uv python install 3.12.12 --install-dir D:/ml-envs/python --no-bin --no-registry
uv venv D:/ml-envs/market-levels-vlm --python D:/ml-envs/python/cpython-3.12.12-windows-x86_64-none/python.exe
$vlmPython = 'D:/ml-envs/market-levels-vlm/Scripts/python.exe'
uv pip install --python $vlmPython --cache-dir D:/ml-cache/market-levels/uv --index-url https://download.pytorch.org/whl/cu128 'torch==2.10.0+cu128' 'torchvision==0.25.0+cu128'
uv pip install --python $vlmPython --cache-dir D:/ml-cache/market-levels/uv -r configs/vlm/requirements-windows-cu128.txt -c configs/vlm/environment-lock.txt
uv pip install --python $vlmPython --cache-dir D:/ml-cache/market-levels/uv --no-deps -e .
uv pip check --python $vlmPython
```

Nie uruchamiaj tych instalacji w projektowym `.venv`. Polecenia nie wymagają
zmiany globalnego Pythona, systemowego CUDA ani rejestru Pythona.

## 4. Cache i wybór przykładów

Konfiguracja pilotażu: `configs/vlm/feasibility.json`. Każdy model ma pełny
40-znakowy identyfikator rewizji i własną klasę Transformers.
Cache: `D:/ml-cache/market-levels/hub/<organizacja--model>/<rewizja>/`.

```powershell
$run = 'results/vlm-feasibility-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
& $vlmPython -X utf8 -m market_levels.cli.vlm_feasibility select --output "$run/selection"
# Istniejący kompletny cache jest weryfikowany i używany ponownie:
& $vlmPython -X utf8 -m market_levels.cli.vlm_feasibility download --output "$run/download"
```

Download najpierw sprawdza oficjalną tożsamość, rewizję, publiczny dostęp,
licencję, rozmiary wszystkich wybranych plików i wolne miejsce. Odmawia, jeśli
modele przekraczają 18 GB lub pozostawiają mniej niż 20 GB. Nie używa tokenu
ani zdalnego kodu Python. Pozostawiony `.partial` wymaga diagnozy; program
nie usuwa go automatycznie i nie rozpoczyna niekontrolowanych ponowień.

Selekcja validation: daty i ID w obrębie instrumentu, rangi 0, 6, 11 i 17
spośród 18 okien. Daje 1 stycznia, 30 kwietnia, 8 sierpnia i 6 grudnia 2024
dla BTC i ETH. Nie zależy od etykiet ani odpowiedzi modelu.

## 5. Inferencja modeli bazowych

Uruchamiaj modele kolejno. Każdy proces ładuje cały model na GPU w BF16
(po potwierdzeniu natywnego wsparcia), bez CPU offload i kwantyzacji.

```powershell
& $vlmPython -X utf8 -u -m market_levels.cli.vlm_feasibility infer --model qwen3-vl --output "$run/qwen3-vl"
if ($LASTEXITCODE -ne 0) { throw 'Sprawdź failure.json pierwszego modelu' }
& $vlmPython -X utf8 -u -m market_levels.cli.vlm_feasibility infer --model qwen3.5 --output "$run/qwen3.5"
```

Każdy model wykonuje kontrolę obrazu/pustego obrazu i osiem odpowiedzi S/R
przy dwóch budżetach: 786432 oraz 393216 pikseli. Procesor dopasowuje wielkość
do własnej siatki. Faktyczne wymiary i tokeny są zapisywane dla każdej odpowiedzi.
Oryginalne PNG pozostają bez zmian. Generowanie: greedy, jeden beam, do 256
nowych tokenów, bez few-shot i bez zmiany instrukcji produkcyjnej.

Pliki wyników:

- `selected-validation.json`: wspólne osiem ID, daty i SHA obrazów.
- `model.json`: rewizja, klasa/procesor, konfiguracje, czas ładowania i pamięć.
- `native/`, `reduced/`: `predictions.jsonl` z surowym tekstem i osobne pomiary
  każdego wywołania, w tym tokeny, czas, ostrzeżenia i wywołania encodera obrazu.
- `summary.json`: zestawienie szybkości i pamięci po kontrolnej rozgrzewce.
- `failure.json`: błąd uniemożliwiający wykonanie danego przebiegu.

Nie usuwaj Markdown ani innych fragmentów odpowiedzi. To rzeczywiste błędy
formatu w wymaganym zadaniu. Standardowe dekodowanie pomija specjalne tokeny
tokenizera; zapis zachowuje też ich pełną wersję i identyfikatory tokenów.

Ocena pomocnicza ośmiu przykładów, oddzielnie dla każdego gotowego katalogu:

```powershell
& $vlmPython -X utf8 -c "import sys; from pathlib import Path; from market_levels.inference.workflows.scoring import score_pilot; score_pilot(Path(sys.argv[1]), Path(sys.argv[2]))" 'data/datasets/ds35-800-20261107-a' "$run/qwen3-vl"
```

Dla drugiego modelu zmień ostatni argument. Funkcja używa istniejącego
`score_example` i `aggregate`, a wynik nazywa pomocniczym. Zwykły ewaluator
nadal wymaga kompletnych 36 ID validation. Ośmiu odpowiedzi nie należy podawać
jako pełnego splitu. Ocena nie naprawia odpowiedzi.

## 6. Kontrolny krok adaptera

To oddzielny proces po zamknięciu inferencji. Polecenie wykonuje dokładnie
jeden krok optymalizatora, z akumulacją czterech microbatchy train po jednym
przykładzie. Nie wykonuje pełnego treningu ani inferencji dostrojonego modelu.

```powershell
& $vlmPython -X utf8 -u -m market_levels.cli.vlm_feasibility train-step --model qwen3-vl --resolution native --output "$run/train-step"
```

Konfiguracja: NF4/double quantization językowej części modelu, BF16 obliczeń,
zamrożona część wizualna, LoRA na językowych `q_proj` i `v_proj`, rank 8,
alpha 16, gradient checkpointing, AdamW. Instrukcja i obraz są maskowane
wartością -100; nadzorowana jest pełna odpowiedź assistant z tokenem końca.
Nie obcina się instrukcji ani odpowiedzi. `training-result.json` zachowuje
loss, gradienty, zmiany tensorów adaptera, czas, pamięć i ewentualny OOM.

Mały adapter pozostaje lokalny w podkatalogu `adapter/` wyniku. Nie jest
publikowany i nie jest dołączany do handoffu. CLI celowo odrzuca `train-step`
dla Qwen3.5: jego metoda wymaga odrębnej weryfikacji architektury i kerneli.

## 7. Diagnozowanie i testy

W drugim oknie PowerShell obserwuj:

```powershell
nvidia-smi --query-gpu=timestamp,memory.used,memory.free,utilization.gpu --format=csv -l 1
# Ctrl+C kończy obserwację.
```

Przy `CUDA out of memory` zachowaj wynik, zamknij ukończony proces i sprawdź
inne aplikacje GPU. Program zapisuje OOM i przerywa daną rozdzielczość po jednej
próbie. Ewentualną świadomą próbę niższej rozdzielczości wykonaj w nowym katalogu
z zapisaną konfiguracją; nie zmieniaj PNG. Po jednym udanym kroku zakończ próby.

`CUDA unavailable` zwykle oznacza niewłaściwy interpreter lub wheel CPU.
Sprawdź `sys.executable`, `torch.__version__` i `torch.version.cuda` przed
jakąkolwiek instalacją. Ostrzeżenie Qwen3.5 o wolnej implementacji DeltaNet
dotyczy wydajności; nie instaluj losowych kerneli ani nie aktualizuj sterownika
w odpowiedzi na to ostrzeżenie. Przy problemie środowiska zachowaj log i manifest.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
& $vlmPython -X utf8 tests/checks/check_vlm_masking.py -v
```

Testy projektu działają offline i nie wymagają instalacji modeli ani PyTorch
w `.venv`. Historycznych danych nie należy regenerować w ramach diagnostyki.

Wyniki tej iteracji i rekomendację wskazuje
[raport](RAPORT_4_1_WYBOR_MODELU_CZ1.md). Po pilotażu zatrzymaj się przed pełnym
dostrajaniem i przed użyciem testu.

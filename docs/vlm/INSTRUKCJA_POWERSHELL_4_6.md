# Etap 4.6 — ręczne wykonanie końcowego testu

Przygotowano 2026-11-12. **W etapie 4.6A nie uruchomiono właściwej inferencji
ani oceny testowej.** Polecenia B–D są przeznaczone dla autora po niezależnej
kontroli przygotowania. Nie są instrukcją automatycznego uruchomienia przez agenta.
Nie zmieniaj modelu, konfiguracji, danych ani promptu na podstawie testu.

## A. Przygotowanie

Zamknij VS Code/Codexa oraz inne aplikacje zajmujące VRAM. Otwórz osobny
Windows PowerShell 5.1 lub nowszy. Polecenia wykonuj z katalogu projektu.

```powershell
Set-Location -LiteralPath 'D:\Studies\Inżynierka\market-levels-multimodal-finetuning'
$pyVlm = 'D:/ml-envs/market-levels-vlm/Scripts/python.exe'
$finalCfg = 'configs/vlm/final-test.json'
$datasetDir = 'data/datasets/ds35-800-20261107-a'
$selectionFile = 'docs/vlm/FINAL_MODEL_SELECTION.json'
$finalSession = 'results/vlm46-final-test'
$chosenAdapter = 'results/vlm44-part2-17554-5354/adapter'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
if (-not (Test-Path -LiteralPath $pyVlm -PathType Leaf)) { throw 'Brak środowiska VLM' }
& $pyVlm --version
nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free --format=csv
& $pyVlm -X utf8 -c "import json; from pathlib import Path; from market_levels.inference.final_config import load_plan; from market_levels.training.io.resources import guard; c,s=load_plan(Path('configs/vlm/final-test.json')); print(json.dumps(guard(c['resources'])))"
if ($LASTEXITCODE -ne 0) { throw 'Kontrola zasobów nie przeszła' }
```

Wymagania: RTX 3060 Ti 8192 MiB, początkowe zajęcie VRAM ≤450 MiB, dostępny
RAM ≥4096 MiB, commit headroom ≥8192 MiB. Kontrola jest ponawiana przed każdym
załadowaniem modelu; runtime wymaga jednej GPU, CUDA i natywnego BF16.
Obowiązuje historyczne środowisko VLM (Python i wersje bibliotek zgodne
z `training-identity.json` adaptera). Nie instaluj aktualizacji w trakcie testu.

Kontrola zamrożonych plików, obrazu i planu bez CUDA/Qwen i bez odczytu wartości
referencji testowych:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_vlm_final_test.ps1 -Mode dry-run -Python $pyVlm
if ($LASTEXITCODE -ne 0) { throw 'Dry-run nie przeszedł' }
Get-FileHash -Algorithm SHA256 -LiteralPath $selectionFile
Get-FileHash -Algorithm SHA256 -LiteralPath "$chosenAdapter/adapter_model.safetensors"
Get-FileHash -Algorithm SHA256 -LiteralPath "$chosenAdapter/manifest.json"
```

Dry-run potwierdza 66 obrazów i fingerprint wejść obrazowych:
`086698fa04fff5b8466e1cfc2f8e4986dced0dc18692722d23ad86085988a06d`.
To fingerprint inferencji, **nie** fingerprint referencji ewaluatora.
Hash wag adaptera: `20cbbb8e39ca636108d9533e8e8cc4543371b48eb322fff97999a9b8454ebdf6`.
Hash manifestu adaptera: `cc11b18830876107d075b560d8abe37b718c46f22725e2d0cbf430b73bae1c83`.
Pełne identyfikatory pochodzą z niezmienionego `FINAL_MODEL_SELECTION.json`.

Przed zgodą autora na wykonanie porównaj kod i konfigurację z audytowaną paczką
4.6A i jej manifestem SHA-256. Nie zmieniaj `final-test.json`. Zawiera odrębne
`purpose=one_final_test_pair_v1` i `execution_approved=true`; samo to pole
nie uruchamia testu. Wymagana jest osobna flaga `-ApproveFinalTest`.
Zgody treningowe nie są akceptowane jako zgoda na test.

Po zgodzie autora zarezerwuj **jeden nowy katalog** pary, bez ładowania GPU:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_vlm_final_test.ps1 -Mode prepare -Python $pyVlm -ApproveFinalTest
if ($LASTEXITCODE -ne 0) { throw 'Rezerwacja sesji nie przeszła; zachowaj log' }
```

Katalog jest celowo ustalony w planie. Nowy UUID w `session.json` daje różne
`run_id` obu wariantów. Istniejący katalog jest odrzucany; nie zastępuj go nowym
katalogiem w celu powtórzenia zakończonego testu. Po przerwaniu używa się
tej samej sesji i `-Resume`. Zmiana kodu/planu po rezerwacji blokuje wykonanie.
Awaria samego `prepare` wymaga sprawdzenia plików sesji; nie usuwaj ich automatycznie.

## B. Inferencja bazowego NF4

Uruchom jeden proces, bez adaptera, bez równoległego treningu/inferencji:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_vlm_final_test.ps1 -Mode infer -Python $pyVlm -Variant base-nf4 -ApproveFinalTest
if ($LASTEXITCODE -ne 0) { throw 'Baza przerwana; zachowaj log i zatwierdzone odpowiedzi' }
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_vlm_final_test.ps1 -Mode verify-variant -Python $pyVlm -Variant base-nf4
if ($LASTEXITCODE -ne 0) { throw 'Niekompletna lub niespójna baza' }
```

Oczekiwany wynik techniczny: `count=66`, manifest kompletny, **bez metryk jakości**.
`base-nf4/predictions.jsonl` przechowuje dokładny tekst odpowiedzi, również błędny
JSON lub Markdown. W tej fazie nie uruchamiaj ewaluatora ani diagnostyki cen.

## C. Inferencja wybranego adaptera

Dopiero po zakończeniu procesu B i poprawnej kontroli kompletności:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_vlm_final_test.ps1 -Mode infer -Python $pyVlm -Variant finetuned-nf4 -Adapter $chosenAdapter -ApproveFinalTest
if ($LASTEXITCODE -ne 0) { throw 'Adapter przerwany; zachowaj log i odpowiedzi' }
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_vlm_final_test.ps1 -Mode verify-pair -Python $pyVlm
if ($LASTEXITCODE -ne 0) { throw 'Para nie jest kompletna; nie licz metryk' }
```

Świeży model NF4, ta sama rewizja/procesor/kolejność 66 ID i historyczne parametry
generowania. PEFT ma `is_trainable=False`, bez merge; 112 tensorów jest
porównywanych dokładnie z wagami na dysku przed pierwszą odpowiedzią.
Obie wersje: `eval()`, wszystkie gradienty wyłączone, `torch.inference_mode()`.

### Przerwanie, OOM i wznowienie

Nie ma automatycznego retry ani zmniejszenia obrazu, offloadu i zmiany generowania.
OOM/błąd kończy proces; kod 1, Ctrl+C — kod 130. Zatrzymanie kontrolowane:
utwórz `STOP` w katalogu aktywnego wariantu (w drugim oknie PowerShell).

```powershell
New-Item -ItemType File -Path 'results/vlm46-final-test/base-nf4/STOP'
```

STOP działa na granicy odpowiedzi. Po zakończeniu procesu, przed wznowieniem,
usuń tylko ten znacznik, jeśli istnieje; dla modelu dostrojonego użyj jego katalogu.
Nie usuwaj rekordów, logów ani manifestów.

```powershell
Remove-Item -LiteralPath 'results/vlm46-final-test/base-nf4/STOP'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_vlm_final_test.ps1 -Mode infer -Python $pyVlm -Variant base-nf4 -Resume -ApproveFinalTest
```

Wznowienie modelu dostrojonego:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_vlm_final_test.ps1 -Mode infer -Python $pyVlm -Variant finetuned-nf4 -Adapter $chosenAdapter -Resume -ApproveFinalTest
```

Powyższe polecenia wznowienia są potrzebne tylko po przerwaniu. Działają na
oryginalnym planie/UUID i sprawdzają hashe zapisanych odpowiedzi. Nie generują
ponownie zatwierdzonych ID. Plik `records/NNN-ID.json` opublikowany atomowo
jest punktem zatwierdzenia. `predictions.jsonl` jest odtwarzanym prefiksem tych
rekordów. Plik `.pending` może pozostać po awarii niezakończonego zapisu;
nie jest zatwierdzoną odpowiedzią. Zakończony wariant odrzuca też `-Resume`.
Blokada systemowa sesji uniemożliwia równoległe procesy i zwalnia się po ich śmierci.

## D. Oficjalna ocena po ukończeniu obu wariantów

Zalecane polecenie sprawdza **oba** manifesty przed odczytem referencji, następnie
wywołuje istniejące `evaluate --split test`, `verify`, `compare` i `verify`
bez zmiany `sr-eval-v1`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_vlm_final_test.ps1 -Mode score-pair -Python $pyVlm -ApproveFinalTest
if ($LASTEXITCODE -ne 0) { throw 'Ocena/porównanie nieukończone; zachowaj raporty i logi' }
```

Wyniki:

- `results/evaluation/vlm46-final-test-base-nf4/`;
- `results/evaluation/vlm46-final-test-finetuned-nf4/`;
- `results/evaluation/vlm46-final-test-comparison/`.

Wznowienie samej oceny nie generuje odpowiedzi: sprawdza istniejący kompletny
raport i zgodność jego wejść, następnie wykonuje brakujące oceny. Nie nadpisuje
oryginalnych raportów. Nie wybiera korzystniejszego wyniku z powtórzeń.

Dla audytu składni, równoważne bezpośrednie operacje istniejącego CLI przedstawiono
poniżej. **Nie powtarzaj ich po poprawnym `score-pair`.** Sam historyczny ewaluator
nie ma blokady „oba modele ukończone”; dlatego poniższy blok zaczyna się jej kontrolą.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_vlm_final_test.ps1 -Mode verify-pair -Python $pyVlm
if ($LASTEXITCODE -ne 0) { throw 'Odmowa: brak kompletnej pary' }
& $pyVlm -X utf8 -m market_levels.cli.evaluate evaluate --dataset $datasetDir --split test --predictions "$finalSession/base-nf4/predictions.jsonl" --run-manifest "$finalSession/base-nf4/run.json" --output results/evaluation/vlm46-final-test-base-nf4
if ($LASTEXITCODE -ne 0) { throw 'Błąd oceny bazy' }
& $pyVlm -X utf8 -m market_levels.cli.evaluate evaluate --dataset $datasetDir --split test --predictions "$finalSession/finetuned-nf4/predictions.jsonl" --run-manifest "$finalSession/finetuned-nf4/run.json" --output results/evaluation/vlm46-final-test-finetuned-nf4
if ($LASTEXITCODE -ne 0) { throw 'Błąd oceny adaptera' }
& $pyVlm -X utf8 -m market_levels.cli.evaluate verify --output results/evaluation/vlm46-final-test-base-nf4
if ($LASTEXITCODE -ne 0) { throw 'Błąd verify bazy' }
& $pyVlm -X utf8 -m market_levels.cli.evaluate verify --output results/evaluation/vlm46-final-test-finetuned-nf4
if ($LASTEXITCODE -ne 0) { throw 'Błąd verify adaptera' }
& $pyVlm -X utf8 -m market_levels.cli.evaluate compare --baseline results/evaluation/vlm46-final-test-base-nf4 --candidate results/evaluation/vlm46-final-test-finetuned-nf4 --output results/evaluation/vlm46-final-test-comparison
if ($LASTEXITCODE -ne 0) { throw 'Błąd compare' }
& $pyVlm -X utf8 -m market_levels.cli.evaluate verify --output results/evaluation/vlm46-final-test-comparison
if ($LASTEXITCODE -ne 0) { throw 'Błąd verify porównania' }
```

Zachowaj progi 0,5 ATR (główny), 0,25 i 1,0 ATR (pomocnicze). Wynik testu
nie zmienia `FINAL_MODEL_SELECTION.json` ani nie uruchamia nowego treningu.

## E. Diagnostyka i raport 4.6B

Wypełnij [szablon raportu](SZABLON_RAPORTU_4_6B.md) dopiero po D. Wykorzystaj
`summary.json`, `per_example.jsonl`, `comparison.json`, surowe odpowiedzi i logi.
Rozdziel poprawność formatu od zgodności cen z etykietą algorytmiczną. Nie zakładaj
z góry zera F1 dla bazy. Podaj precision/recall/F1, TP/FP/FN, JSON, duplikaty,
pełne zestawy, brak trafień, rozkład F1, MAE/ATR dopasowanych par i wszystkie
przekroje instrument×strona. Nie traktuj okien jako niezależnych prób rynku.

W planie 4.6A **nie dodano automatycznej diagnostyki zdejmowania Markdown**.
Oficjalne odpowiedzi zawsze pozostają nienaprawione. Istniejąca reguła historyczna
może być osobno wykorzystana w późniejszym raporcie jako wyraźnie pomocnicza analiza,
bez zmiany wyboru modelu. Nie opracowuj nowych reguł naprawy po obejrzeniu testu.

Pomiary czasu/VRAM/RSS są w szczegółach rekordów i zdarzeniu `model_loaded`.
Piki pochodzą z próbkowania, a `reserved` pod WDDM nie oznacza fizycznego VRAM.
Nie wnioskuj o zysku inwestycyjnym z wyniku odtwarzania referencji.

## F. Mała paczka wyników po wykonaniu autora

Skrypt PowerShell zapisuje logi i kody do `results/vlm46-*.console.log`
oraz `results/vlm46-*.exit.json`. Nie znajdują się wewnątrz zapieczętowanych
katalogów wariantów. Przekaż je razem z całą małą sesją surowych wyników
i trzema oficjalnymi raportami. Nie dołączaj źródłowego datasetu ani wag.

Po D można użyć przygotowanego skryptu pakującego:

```powershell
& $pyVlm -X utf8 scripts/package_vlm46_results.py --session $finalSession --output handoff/vlm46-test-results.zip
if ($LASTEXITCODE -ne 0) { throw 'Pakowanie wyników nie przeszło' }
Get-Content -LiteralPath 'handoff/vlm46-test-results.zip.sha256'
```

Pakowanie weryfikuje kompletność obu wariantów i trzech raportów, zachowuje
predykcje, rekordy z pomiarami, manifesty, logi i kody zakończenia. Nie kopiuje
obrazów, etykiet, CSV, adapterów, `state.pt`, checkpointów, cache ani środowiska.
Odmowa nadpisania istniejącego ZIP. Przygotowanie tego mechanizmu nie oznacza
wykonania B–D w etapie 4.6A.

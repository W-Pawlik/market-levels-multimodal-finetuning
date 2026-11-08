# Ewaluator S/R — PowerShell

Uruchamiaj z głównego katalogu istniejącym interpreterem `.venv`.
Ewaluacja nie wymaga bibliotek ML ani Matplotlib i nie uruchamia modelu.
Modułowe CLI działa bez ponownej instalacji; opcjonalne `pip install -e .`
odświeża entry point `market-levels-evaluate`.

Powtarzalna próba **wyłącznie na ręcznych fixture**, w nowych katalogach:

```powershell
$run = [guid]::NewGuid().ToString('N').Substring(0,8)
$root = "results/diagnostics/ev36-$run"
$fixture = 'tests/fixtures/evaluation_v1'

.\.venv\Scripts\python.exe -m market_levels.cli.evaluate evaluate `
  --dataset "$fixture/dataset" --predictions "$fixture/predictions-a.jsonl" `
  --run-manifest "$fixture/run-a.json" --output "$root/manual-a"
if ($LASTEXITCODE -ne 0) { throw 'Nieudana ewaluacja fixture A' }

.\.venv\Scripts\python.exe -m market_levels.cli.evaluate evaluate `
  --dataset "$fixture/dataset" --predictions "$fixture/predictions-b.jsonl" `
  --run-manifest "$fixture/run-b.json" --output "$root/manual-b"
if ($LASTEXITCODE -ne 0) { throw 'Nieudana ewaluacja fixture B' }

.\.venv\Scripts\python.exe -m market_levels.cli.evaluate compare `
  --baseline "$root/manual-a" --candidate "$root/manual-b" --output "$root/comparison"
if ($LASTEXITCODE -ne 0) { throw 'Nieudane porównanie fixture' }

.\.venv\Scripts\python.exe -m market_levels.cli.evaluate verify --output "$root/manual-a"
.\.venv\Scripts\python.exe -m market_levels.cli.evaluate verify --output "$root/comparison"
```

Domyślny split to validation. Fixture ma 12 ręcznych przypadków validation
i niezależne rekordy train/test służące testowaniu pomylenia ID.
Nie są to prawdziwe okna testowe ani odpowiedzi modelu. Dane i oba zestawy
predykcji są w paczce, a `expected-main.json` opisuje wyniki policzone ręcznie.
Wykonana próba: `results/diagnostics/ev36-20261107-a/`.

Przyszła ocena prawdziwych odpowiedzi, **po osobnym zatwierdzeniu eksperymentu**:

```powershell
# Ścieżki model-base.* są przyszłymi plikami; nie zostały teraz utworzone.
.\.venv\Scripts\python.exe -m market_levels.cli.evaluate evaluate `
  --dataset data/datasets/ds35-800-20261107-a `
  --predictions results/predictions/model-base.jsonl `
  --run-manifest results/predictions/model-base.run.json `
  --output results/evaluation/base-NOWY
```

To domyślnie ocena 36 przykładów validation. `--split test` oznacza jawny
dostęp do 66 testowych referencji i wymaga odpowiadającego manifestu oraz
kompletu ID. Nie uruchomiono takiej oceny w tej iteracji. Train jest odrzucany.
Nie ma parametru CLI zmieniającego tolerancje ani reguły protokołu.

Manifest przyszłych predykcji (poniższe wartości są opisowymi placeholderami):

```json
{
  "run_id": "unikalny-id-przebiegu",
  "model_id": "identyfikator-wspolnego-modelu-bazowego",
  "checkpoint_id": "identyfikator-konkretnych-wag",
  "variant": "base",
  "protocol_version": "sr-eval-v1",
  "instruction_version": "pl-sr-v1",
  "inference": {},
  "prediction_kind": "model",
  "dataset_manifest_sha256": "SHA-256-pliku-manifest.json-zbioru",
  "split": "validation"
}
```

W `inference` należy zapisać faktycznie użyte ustawienia, np. sposób dekodowania,
seed, limit odpowiedzi i wersje narzędzi. Dla dostrojonego checkpointu zmieniają
się run_id/checkpoint_id/variant, a model_id, wejścia i ustawienia inferencji
pozostają identyczne. W tej iteracji nie ustalono tych parametrów dla VLM.

Kody wyjścia: 0 — kompletny wynik/kontrola; 2 — brakujące/nieznane/powtórzone
ID, zmieszane splity lub zewnętrzne błędne rekordy; 1 — inne błędy, niezgodność
manifestów, źródeł lub kolizja katalogu. Dla kodu 2 szczegóły JSON są na stderr,
a wynik kompletny nie powstaje. Niepoprawny `response` modelu nie przerywa
kompletnego przebiegu — jest oceniany według protokołu i uwzględniony w raporcie.

Pliki wyniku: `per_example.jsonl`, `summary.json`, `RAPORT.md`, `protocol.json`,
`dataset_binding.json`, oryginalne `predictions.jsonl` i `run-input.json`,
zwalidowany `run.json`, `SOURCE_INTEGRITY.json`, manifest i jego hash.
Liczby cenowe i metryki pozostają liczbami JSON zapisanymi bez float;
wartości niezdefiniowane to null. Markdown zaokrągla wyłącznie prezentację.

Testy:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_evaluation*.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

[Protokół](PROTOKOL_3_6.md), [raport etapu](RAPORT_3_6_CZ1.md).

# PowerShell: profile v2 i porównanie V1/V2

Po WinError 32 przy końcowym sprzątaniu sprawdź opublikowaną partię i użyj nowego
outputu do ponowienia próby. [Potwierdzona przyczyna, poprawka i dokładne komendy](WINDOWS_STAGING_CLEANUP_FIX.md).

Uruchamiaj z katalogu głównego projektu. Nie uruchomiono automatycznie kalibracji
v2 rynku ani pełnej serii eksperymentów. Poniższe kroki wykonuje autor po przeglądzie.
Wszystkie profile pozostają `unapproved`, a generowanie ma tryb diagnostyczny.

## Instalacja i granice

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

$experiment = Get-Content -LiteralPath configs/experiment.json -Raw -Encoding UTF8 | ConvertFrom-Json
$trainStart = $experiment.chronological_split.periods.train.start
$trainEnd = $experiment.chronological_split.periods.train.end
$symbols = @('BTCUSDT', 'ETHUSDT')
$v1Profiles = @{
    BTCUSDT = 'data/synthetic/calibration/BTCUSDT_train_2020_2023_unapproved.json'
    ETHUSDT = 'data/synthetic/calibration/ETHUSDT_train_2020_2023_unapproved.json'
}
$v2Profiles = @{
    BTCUSDT = 'data/synthetic/calibration/v2/BTCUSDT_train_2020_2023_v2_unapproved.json'
    ETHUSDT = 'data/synthetic/calibration/v2/ETHUSDT_train_2020_2023_v2_unapproved.json'
}
```

V1 używa istniejących profili autora. Jeśli są w innych plikach, popraw mapę.
Nie twórz ich na nowo tylko po to, żeby nadpisać poprzednią kalibrację.

## Kalibracja obu profili v2

Najpierw dry-run: wykonuje pełną ograniczoną kalibrację, ale nic nie zapisuje.
Ponowny zapis powtórzy obliczenia deterministycznie; może to potrwać.

```powershell
foreach ($symbol in $symbols) {
    .\.venv\Scripts\market-levels-calibrate.exe --generator-version v2 `
        --symbol $symbol --input "data/processed/${symbol}_4h_2020-01_2026-10.csv" `
        --start $trainStart --end $trainEnd --output $v2Profiles[$symbol] --dry-run
    if ($LASTEXITCODE -ne 0) { throw "Błąd dry-run kalibracji $symbol" }
}
```

Zapis osobnych profili v2 (bez zmiany plików v1):

```powershell
foreach ($symbol in $symbols) {
    .\.venv\Scripts\market-levels-calibrate.exe --generator-version v2 `
        --symbol $symbol --input "data/processed/${symbol}_4h_2020-01_2026-10.csv" `
        --start $trainStart --end $trainEnd --output $v2Profiles[$symbol]
    if ($LASTEXITCODE -ne 0) { throw "Błąd kalibracji $symbol" }
}
```

Domyślne seedy symulacyjnej kalibracji to 73001/73002/73003. Nie używaj ich
jako seedów głównych właściwej diagnostyki. Siatki i liczbę rund zapisuje sekcja
`synthetic_v2_calibration`. Nie dobieraj ich według walidacji 2024 ani testu.

## Funkcja małej próby i właściwej oceny

Funkcja korzysta z istniejących CLI, najpierw dry-run. Przechwytuje ścieżkę
manifestu z komunikatu generowania i ścieżkę JSON z wyniku porównania.
Każdy wariant/seed ma osobny output; dzięki temu neutralne ablacjie mogą dać
identyczne OHLC bez naruszania kontroli duplikatów w obrębie jednego output.

```powershell
function Invoke-OhlcDiagnostic {
    param(
        [ValidateSet('v1','v2')][string]$Version,
        [ValidateSet('base','bridge','tails','volatility','full')][string]$Variant = 'full',
        [int]$Seed = 20261105,
        [int]$Count = 2,
        [string]$OutputRoot = 'data/synthetic/v2-evaluation'
    )
    $profiles = if ($Version -eq 'v1') { $v1Profiles } else { $v2Profiles }
    $runOutput = Join-Path $OutputRoot "$Version-$Variant-$Seed-$Count"
    $generationArgs = @(
        '--diagnostic', '--generator-version', $Version,
        '--count', "$Count", '--symbols', 'BTCUSDT', 'ETHUSDT', '--seed', "$Seed",
        '--profile', "BTCUSDT=$($profiles['BTCUSDT'])",
        '--profile', "ETHUSDT=$($profiles['ETHUSDT'])", '--output', $runOutput
    )
    if ($Version -eq 'v2') {
        $generationArgs += @('--v2-variant', $Variant, '--experiment-id', 'ohlc-v2-training-diagnostics')
    }
    & .\.venv\Scripts\market-levels-generate-synthetic.exe @generationArgs --dry-run | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Błąd dry-run generatora' }
    $generationOutput = @(& .\.venv\Scripts\market-levels-generate-synthetic.exe @generationArgs)
    if ($LASTEXITCODE -ne 0) { throw 'Błąd generatora; nie wybieraj innej partii po cichu' }
    $generationOutput | Out-Host
    $batchPath = ($generationOutput[-1] -split ': ', 2)[1]
    $manifestPath = Join-Path $batchPath 'manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'Brak manifestu nowej partii' }

    foreach ($symbol in $symbols) {
        $comparisonArgs = @(
            '--symbol', $symbol, '--real-csv', "data/processed/${symbol}_4h_2020-01_2026-10.csv",
            '--synthetic-manifest', $manifestPath, '--start', $trainStart, '--end', $trainEnd,
            '--window-count', "$Count", '--selection-seed', '20261106',
            '--output', (Join-Path $OutputRoot 'comparisons')
        )
        & .\.venv\Scripts\market-levels-compare-synthetic.exe @comparisonArgs --dry-run | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Błąd dry-run porównania $symbol" }
        $comparisonOutput = @(& .\.venv\Scripts\market-levels-compare-synthetic.exe @comparisonArgs)
        if ($LASTEXITCODE -ne 0) { throw "Błąd porównania $symbol" }
        $comparisonOutput | Out-Host
        $jsonLine = @($comparisonOutput | Where-Object { $_ -like 'Raport JSON:*' })[-1]
        [pscustomobject]@{
            Symbol = $symbol; Version = $Version; Variant = $Variant; Seed = $Seed; Count = $Count
            Manifest = $manifestPath; Report = ($jsonLine -split ': ', 2)[1]
        }
    }
}
```

Najpierw mała próba po 2 BTC/ETH dla każdego wariantu (24 serie łącznie z V1):

```powershell
$smallRuns = @(Invoke-OhlcDiagnostic -Version v1 -Count 2 -Seed 20261107 -OutputRoot data/synthetic/v2-small)
foreach ($variant in @('base','bridge','tails','volatility','full')) {
    $smallRuns += @(Invoke-OhlcDiagnostic -Version v2 -Variant $variant -Count 2 -Seed 20261107 -OutputRoot data/synthetic/v2-small)
}
$smallRuns | Format-Table Symbol, Version, Variant, Seed, Report -AutoSize
```

To techniczna próba działania z profilami treningowymi, nie wystarczająca ocena
realizmu. Jeśli profile nie istnieją, prosty test samego generatora bez kalibracji:

```powershell
.\.venv\Scripts\market-levels-generate-synthetic.exe --generator-version v2 --v2-variant full --diagnostic --count 2 --symbols BTCUSDT ETHUSDT --seed 20261107 --output data/synthetic/v2-manual-smoke --dry-run
.\.venv\Scripts\market-levels-generate-synthetic.exe --generator-version v2 --v2-variant full --diagnostic --count 2 --symbols BTCUSDT ETHUSDT --seed 20261107 --output data/synthetic/v2-manual-smoke
```

Taki ręczny profil ma `estimation_kind=diagnostic`; porównanie empiryczne odmawia
użycia go jako kalibracji rynkowej. Nie dopisuj flagi `--profile` ze starym v1 do v2.

## Właściwe próbki 60 i kilka seedów

Po przeglądzie małej próby wybierz warianty. Poniższy przykład ocenia wszystkie
pięć wariantów v2 i V1 na trzech seedach: **2160 serii, 4320 plików CSV/JSON**,
plus raporty i wielokrotnie zapisane profile w metadanych. Nie jest uruchamiany
przez testy ani instalację. Można zawęzić `$variants`, np. do `@('full')`.

```powershell
$variants = @('base','bridge','tails','volatility','full')
$diagnosticSeeds = @(20261105,20261115,20261125)
$evaluationRuns = @()
foreach ($seed in $diagnosticSeeds) {
    $evaluationRuns += @(Invoke-OhlcDiagnostic -Version v1 -Count 60 -Seed $seed)
    foreach ($variant in $variants) {
        $evaluationRuns += @(Invoke-OhlcDiagnostic -Version v2 -Variant $variant -Count 60 -Seed $seed)
    }
}
$evaluationRuns | Export-Csv -LiteralPath data/synthetic/v2-evaluation/run-index.csv -NoTypeInformation -Encoding UTF8 -NoClobber
```

Każde wywołanie Count=60 tworzy **60 BTC + 60 ETH**. Porównania mają zawsze ten
sam okres treningowy, count=60 i seed selekcji 20261106. Ponowne identyczne
uruchomienie odmawia zapisu. Nie wybieramy „najnowszego katalogu” zamiast błędnej
partii. Istniejące manifesty można porównywać bez ponownego generowania.

## Zbiorcze tabele V1/V2

Najpierw dry-run, potem zapis osobno dla BTC i ETH:

```powershell
foreach ($symbol in $symbols) {
    $reportPaths = @($evaluationRuns | Where-Object { $_.Symbol -eq $symbol } | ForEach-Object { $_.Report })
    .\.venv\Scripts\market-levels-compare-synthetic.exe --symbol $symbol --reports $reportPaths --output data/synthetic/comparisons/v2/aggregate --dry-run
    if ($LASTEXITCODE -ne 0) { throw "Błąd podsumowania $symbol" }
    .\.venv\Scripts\market-levels-compare-synthetic.exe --symbol $symbol --reports $reportPaths --output data/synthetic/comparisons/v2/aggregate
    if ($LASTEXITCODE -ne 0) { throw "Błąd zapisu podsumowania $symbol" }
}
```

Do małej próby zamiast `$evaluationRuns` użyj `$smallRuns` i innego output.
Można też podać istniejący historyczny raport V1 i nowe pliki bez odtwarzania
baseline, pod warunkiem identycznej referencji. Jedno powtórzenie V1 daje jednak
słabszą podstawę do oceny losowej zmienności błędów niż kilka seedów.

Wynik zawiera tabelę Realne/V1/V2-*, błędy względem treningu i kierunek zmiany
każdego błędu. Rozrzut między seedami jest w JSON. Do dalszej analizy przekaż
dwa zbiorcze `*_comparison.json`, dwa `*_summary.md` oraz profile v2 z audytem.
Indeks run-index.csv ułatwia odnalezienie źródeł. Nie przesyłaj automatycznie
pełnych danych i wag; obowiązują ograniczenia materiałów pochodnych Binance.

Żaden krok nie zatwierdza generatora. Pełna ocena, kontrola wizualna i decyzja
autora pozostają osobne. Podstawowa interpretacja i równania:
[SYNTHETIC_GENERATOR_V2.md](SYNTHETIC_GENERATOR_V2.md).

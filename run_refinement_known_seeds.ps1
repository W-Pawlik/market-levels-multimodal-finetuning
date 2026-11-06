# Market Levels: diagnostyka porownawcza trzech znanych seedow.
# Tylko train 2020-2023; bez zatwierdzania profili i bez nadpisywania.
# Wykonaj z katalogu glownego projektu po zainstalowaniu najnowszego handoffu.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$project = (Get-Location).Path
$configPath = Join-Path $project 'configs/experiment.json'
$generatorExe = Join-Path $project '.venv/Scripts/market-levels-generate-synthetic.exe'
$compareExe = Join-Path $project '.venv/Scripts/market-levels-compare-synthetic.exe'
$profileDir = Join-Path $project 'data/synthetic/refinement-81150be97c7448dc94ce6004d3514832/profiles'
$oldSummaryRoot = Join-Path $project 'data/synthetic/comparisons/v2/aggregate-multiseed'
$oldSummaryIds = @{
    'BTCUSDT' = 'fd1d5ad4a1b13ef3c746ae99'
    'ETHUSDT' = '7e41a760ce448aa4eb060e38'
}
$symbols = @('BTCUSDT', 'ETHUSDT')
$seeds = @(20261105, 20261115, 20261125)

foreach ($path in @($configPath, $generatorExe, $compareExe)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Nie znaleziono pliku: $path" }
}
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$trainStart = $config.chronological_split.periods.train.start
$trainEnd = $config.chronological_split.periods.train.end
$oldPaths = @{}
$refinedProfiles = @{}
$realCsvs = @{}

# Preflight: zanim rozpoczniemy generowanie, zweryfikuj obecność WSZYSTKICH
# dwunastu starych raportow indywidualnych i czterech nowych profili.
foreach ($symbol in $symbols) {
    $realCsvs[$symbol] = Join-Path $project "data/processed/${symbol}_4h_2020-01_2026-10.csv"
    if (-not (Test-Path -LiteralPath $realCsvs[$symbol] -PathType Leaf)) {
        throw "Brak oryginalnego pliku CSV: $($realCsvs[$symbol])"
    }
    foreach ($variant in @('full', 'bridge_volatility')) {
        $key = "$symbol|$variant"
        $profilePath = Join-Path $profileDir "${symbol}_${variant}_refined_unapproved.json"
        if (-not (Test-Path -LiteralPath $profilePath -PathType Leaf)) {
            throw "Brak nowego profilu: $profilePath"
        }
        $profile = Get-Content -LiteralPath $profilePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($profile.status -ne 'unapproved' -or $profile.calibration.variant -ne $variant -or
            $profile.calibration.method -ne 'volatility_refinement_v1' -or $profile.symbol -ne $symbol) {
            throw "Nieoczekiwane metadane profilu: $profilePath"
        }
        $refinedProfiles[$key] = $profilePath
    }

    $summaryPath = Join-Path (Join-Path $oldSummaryRoot $oldSummaryIds[$symbol]) "${symbol}_comparison.json"
    if (-not (Test-Path -LiteralPath $summaryPath -PathType Leaf)) {
        throw "Brak dawnego raportu zbiorczego: $summaryPath"
    }
    $summary = Get-Content -LiteralPath $summaryPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($summary.report_kind -ne 'variant_summary' -or $summary.symbol -ne $symbol) {
        throw "Nieoczekiwany format starego raportu: $summaryPath"
    }
    $entries = @($summary.reports | Where-Object { $_.variant -in @('V1', 'V2-full') })
    if ($entries.Count -ne 6) { throw "Oczekiwano szesciu starych raportow dla $symbol" }
    foreach ($entry in $entries) {
        $seed = [int]$entry.master_seed
        if ($seed -notin $seeds) { throw "Niespodziewany stary seed: $seed" }
        $key = "$symbol|$($entry.variant)|$seed"
        if ($oldPaths.ContainsKey($key)) { throw "Zdublowany stary raport: $key" }
        if (-not (Test-Path -LiteralPath $entry.path -PathType Leaf)) {
            throw "Brak oryginalnego raportu: $($entry.path)"
        }
        $oldPaths[$key] = [string]$entry.path
    }
}
if ($oldPaths.Count -ne 12) { throw "Oczekiwano 12 starych raportow, otrzymano: $($oldPaths.Count)" }
Write-Host 'OK: sprawdzono 12 starych raportow i 4 profile refinement.'

# Unikalny katalog: niczego nie usuwamy i niczego nie nadpisujemy.
$runRoot = Join-Path $project ('data/synthetic/refinement-known-seeds-' + [guid]::NewGuid().ToString('N'))
$comparisonRoot = Join-Path $runRoot 'comparisons'
$summaryRoot = Join-Path $runRoot 'summary'
$newPaths = @{}
$runIndex = @()
foreach ($seed in $seeds) {
    foreach ($family in @('full', 'bridge_volatility')) {
        $runOutput = Join-Path $runRoot "$family-$seed-60"
        $btcProfile = $refinedProfiles["BTCUSDT|$family"]
        $ethProfile = $refinedProfiles["ETHUSDT|$family"]
        $generateArgs = @(
            '--config', $configPath, '--diagnostic', '--generator-version', 'v2',
            '--v2-variant', $family, '--count', '60', '--symbols', 'BTCUSDT', 'ETHUSDT',
            '--seed', "$seed", '--profile', "BTCUSDT=$btcProfile", '--profile', "ETHUSDT=$ethProfile",
            '--experiment-id', 'volatility-refinement-v1-diagnostics', '--output', $runOutput
        )
        Write-Host "Generowanie: $family / $seed"
        $generationOutput = @(& $generatorExe @generateArgs)
        if ($LASTEXITCODE -ne 0) { throw "Blad generowania: $family / $seed" }
        $generationOutput | Out-Host
        $manifests = @(Get-ChildItem -LiteralPath $runOutput -Recurse -File -Filter 'manifest.json')
        if ($manifests.Count -ne 1) { throw "Nieprawidlowa liczba manifestow: $family / $seed" }
        $manifestPath = $manifests[0].FullName

        foreach ($symbol in $symbols) {
            $compareArgs = @(
                '--config', $configPath, '--symbol', $symbol,
                '--real-csv', $realCsvs[$symbol], '--synthetic-manifest', $manifestPath,
                '--start', "$trainStart", '--end', "$trainEnd",
                '--window-count', '60', '--selection-seed', '20261106', '--output', $comparisonRoot
            )
            $comparisonOutput = @(& $compareExe @compareArgs)
            if ($LASTEXITCODE -ne 0) { throw "Blad porownania: $symbol / $family / $seed" }
            $jsonLines = @($comparisonOutput | Where-Object { $_ -like 'Raport JSON:*' })
            if ($jsonLines.Count -ne 1) { throw "Nie znaleziono sciezki raportu: $symbol / $family / $seed" }
            $reportPath = ($jsonLines[0] -split ': ', 2)[1].Trim()
            if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) {
                throw "Raport nie istnieje: $reportPath"
            }
            $key = "$symbol|$family|$seed"
            $newPaths[$key] = $reportPath
            $runIndex += [pscustomobject]@{
                Symbol = $symbol; Variant = $family; Seed = $seed
                Manifest = $manifestPath; Report = $reportPath
            }
            Write-Host "OK: $symbol / $family / $seed"
        }
    }
}

# Agregacja tylko 4 uzgodnionych grup, na tych samych seedach i tych samych
# oknach. Agregator sam kontroluje zgodnosc danych, profili i referencji.
foreach ($symbol in $symbols) {
    $reportPaths = @()
    foreach ($seed in $seeds) {
        $reportPaths += $oldPaths["$symbol|V1|$seed"]
        $reportPaths += $oldPaths["$symbol|V2-full|$seed"]
        $reportPaths += $newPaths["$symbol|full|$seed"]
        $reportPaths += $newPaths["$symbol|bridge_volatility|$seed"]
    }
    if ($reportPaths.Count -ne 12) { throw "Blad indeksu porownan: $symbol" }
    $aggregateArgs = @('--symbol', $symbol, '--reports')
    $aggregateArgs += $reportPaths
    $aggregateArgs += @('--output', $summaryRoot)
    Write-Host "Raport zbiorczy: $symbol"
    $aggregateOutput = @(& $compareExe @aggregateArgs)
    if ($LASTEXITCODE -ne 0) { throw "Blad agregacji: $symbol" }
    $aggregateOutput | Out-Host
}
$runIndex | Export-Csv -LiteralPath (Join-Path $runRoot 'new-run-index.csv') -NoTypeInformation -Encoding UTF8 -NoClobber
Write-Host ''
Write-Host 'Gotowe. Katalog wynikow:'
Write-Host $runRoot
Write-Host 'Wyslij po 1 *_comparison.json i *_summary.md dla BTC oraz ETH z podkatalogu summary.'

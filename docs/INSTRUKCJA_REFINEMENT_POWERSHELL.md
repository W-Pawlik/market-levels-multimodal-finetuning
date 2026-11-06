# Refinement v2 — Windows PowerShell

Po wykonanej kalibracji używaj [oficjalnej procedury porównania](INSTRUKCJA_POWERSHELL.md)
z CheckOnly/SmokeTest/RunFull i wznowieniem. Poniższy dokument zachowuje opis
pierwotnego dostrajania; nie ponawiaj jego kroku kalibracji gotowych profili.

Uruchamiaj z katalogu projektu. Polecenia po instalacji są przeznaczone do
świadomego wykonania przez autora: nie wykonano tu kalibracji rynku ani dużej
diagnostyki. Zachowaj lokalne CSV, pierwotne profile i raporty poza ZIP-em.
Bloki wykonuj kolejno w jednej sesji PowerShell. Każde nowe wykonanie otrzymuje
osobny katalog z GUID; programy nadal odmawiają nadpisania.

## 1. Instalacja, testy i konfiguracja

```powershell
if (-not (Test-Path -LiteralPath .venv/Scripts/python.exe)) { py -3 -m venv .venv }
& ./.venv/Scripts/python.exe -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw 'Instalacja nieudana' }
& ./.venv/Scripts/python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Testy nieudane' }

$configPath = 'configs/experiment.json'
$experiment = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$trainStart = $experiment.chronological_split.periods.train.start
$trainEnd = $experiment.chronological_split.periods.train.end
$symbols = @('BTCUSDT', 'ETHUSDT')
$runRoot = 'data/synthetic/refinement-' + [guid]::NewGuid().ToString('N')
$profileRoot = Join-Path $runRoot 'profiles'
$realCsv = @{}
$v1Profiles = @{}
$v2Profiles = @{}
$refinedProfiles = @{ full = @{}; bridge_volatility = @{} }
foreach ($symbol in $symbols) {
    $realCsv[$symbol] = "data/processed/${symbol}_4h_2020-01_2026-10.csv"
    $v1Profiles[$symbol] = "data/synthetic/calibration/${symbol}_train_2020_2023_unapproved.json"
    $v2Profiles[$symbol] = "data/synthetic/calibration/v2/${symbol}_train_2020_2023_v2_unapproved.json"
    foreach ($variant in @('full', 'bridge_volatility')) {
        $refinedProfiles[$variant][$symbol] = Join-Path $profileRoot "${symbol}_${variant}_refined_unapproved.json"
    }
    foreach ($path in @($realCsv[$symbol], $v1Profiles[$symbol], $v2Profiles[$symbol])) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Brak wejścia: $path" }
    }
}
$runRoot
```

Granice obejmują otwarcia świec UTC włącznie. Nie wpisuj dat validation/test.
W przypadku innych ścieżek wejściowych zmień wyłącznie powyższe mapy.
Domyślną siatkę i budżet definiuje `volatility_refinement_v1` w konfiguracji.

## 2. Cztery nowe profile, bez zmiany starych

```powershell
foreach ($symbol in $symbols) {
    $sourceDigest = (Get-FileHash -LiteralPath $v2Profiles[$symbol] -Algorithm SHA256).Hash.ToLowerInvariant()
    foreach ($variant in @('full', 'bridge_volatility')) {
        $refineArgs = @(
            '--config', $configPath, '--symbol', $symbol, '--input', $realCsv[$symbol],
            '--source-profile', $v2Profiles[$symbol], '--source-sha256', $sourceDigest,
            '--variant', $variant, '--start', $trainStart, '--end', $trainEnd,
            '--output', $refinedProfiles[$variant][$symbol]
        )
        & ./.venv/Scripts/market-levels-refine-v2-volatility.exe @refineArgs
        if ($LASTEXITCODE -ne 0) { throw "Błąd refinement $symbol/$variant" }
    }
}
```

Opcjonalne `--dry-run` policzy całą siatkę bez zapisu; późniejszy zapis powtórzy
te obliczenia. Profile pozostaną unapproved. Nie zmieniaj wag ani zakresów na
podstawie wyników validation/test. Przed dalszą oceną zamroź te cztery pliki.

## 3. Funkcje i mała próba techniczna

Funkcja obsługuje nową partię albo istniejący manifest. Przy podanym manifeście
nie wywołuje generatora. Wynikami funkcji są obiekty indeksu, komunikaty trafiają
na ekran. Dla neutralnych ablacji każdy profil/seed ma odrębny output.

```powershell
function Invoke-RefinementDiagnostic {
    param(
        [ValidateSet('V1','original','full-refined','bridge-refined')][string]$Family,
        [int]$Seed,
        [int]$Count = 2,
        [string]$ExistingManifest = ''
    )
    $version = 'v2'; $variant = 'full'
    $profiles = $v2Profiles
    switch ($Family) {
        'V1' { $version = 'v1'; $profiles = $v1Profiles }
        'full-refined' { $profiles = $refinedProfiles['full'] }
        'bridge-refined' { $variant = 'bridge_volatility'; $profiles = $refinedProfiles['bridge_volatility'] }
    }
    $manifestPath = $ExistingManifest
    if (-not $manifestPath) {
        $generationArgs = @(
            '--config', $configPath, '--diagnostic', '--generator-version', $version,
            '--count', "$Count", '--symbols', 'BTCUSDT', 'ETHUSDT', '--seed', "$Seed",
            '--profile', "BTCUSDT=$($profiles['BTCUSDT'])",
            '--profile', "ETHUSDT=$($profiles['ETHUSDT'])",
            '--output', (Join-Path $runRoot "$Family-$Seed-$Count")
        )
        if ($version -eq 'v2') {
            $generationArgs += @('--v2-variant', $variant, '--experiment-id', 'volatility-refinement-v1-diagnostics')
        }
        $generationOutput = @(& ./.venv/Scripts/market-levels-generate-synthetic.exe @generationArgs)
        if ($LASTEXITCODE -ne 0) { throw "Błąd generowania $Family/$Seed" }
        $generationOutput | Out-Host
        $batchPath = ($generationOutput[-1] -split ': ', 2)[1]
        $manifestPath = Join-Path $batchPath 'manifest.json'
    }
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Brak manifestu $manifestPath" }
    foreach ($symbol in $symbols) {
        $compareArgs = @(
            '--config', $configPath, '--symbol', $symbol, '--real-csv', $realCsv[$symbol],
            '--synthetic-manifest', $manifestPath, '--start', $trainStart, '--end', $trainEnd,
            '--window-count', "$Count", '--selection-seed', '20261106',
            '--output', (Join-Path $runRoot 'comparisons')
        )
        $comparisonOutput = @(& ./.venv/Scripts/market-levels-compare-synthetic.exe @compareArgs)
        if ($LASTEXITCODE -ne 0) { throw "Błąd porównania $symbol/$Family/$Seed" }
        $comparisonOutput | Out-Host
        $jsonLine = @($comparisonOutput | Where-Object { $_ -like 'Raport JSON:*' })[-1]
        [pscustomobject]@{
            Symbol = $symbol; Family = $Family; Seed = $Seed; Count = $Count
            Manifest = $manifestPath; Report = ($jsonLine -split ': ', 2)[1]
        }
    }
}

function Save-RefinementSummary {
    param([object[]]$Runs, [string]$Name)
    foreach ($symbol in $symbols) {
        $reportPaths = @($Runs | Where-Object { $_.Symbol -eq $symbol } | ForEach-Object { $_.Report })
        & ./.venv/Scripts/market-levels-compare-synthetic.exe --symbol $symbol --reports $reportPaths --output (Join-Path $runRoot $Name) | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Błąd zbiorczej tabeli $symbol/$Name" }
    }
}

$smallRuns = @()
foreach ($family in @('V1','original','full-refined','bridge-refined')) {
    $smallRuns += @(Invoke-RefinementDiagnostic -Family $family -Seed 20261107 -Count 2)
}
Save-RefinementSummary -Runs $smallRuns -Name 'small-summary'
```

To 16 serii po 120 świec: cztery grupy × dwa symbole × dwa przykłady.
Wyniki oceniają działanie ścieżki, nie realizm rynku. Tej próby nie łącz z count=60.

## 4. Właściwa ocena na trzech znanych seedach — uruchomi autor osobno

Najpierw odzyskaj stare raporty V1/full z lokalnego katalogu. Kod nie modyfikuje
ich i nie przelicza statystyk. Gdy raportu brak, używa dokładnie jednego starego
manifestu właściwej partii. Brak albo wieloznaczność wejść kończą pracę błędem,
zamiast generować stare dane od nowa. Dostosuj korzeń tylko jeśli przeniesiono pliki.

```powershell
$oldRoot = 'data/synthetic/v2-evaluation'
$knownSeeds = @(20261105, 20261115, 20261125)
$oldReports = @(Get-ChildItem -LiteralPath (Join-Path $oldRoot 'comparisons') -Filter '*_comparison.json' -Recurse -File | ForEach-Object {
    $doc = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($doc.report_kind -ne 'variant_summary') {
        [pscustomobject]@{ Path = $_.FullName; Doc = $doc }
    }
})
$knownRuns = @()
foreach ($seed in $knownSeeds) {
    foreach ($family in @('V1','original')) {
        $version = if ($family -eq 'V1') { '1.0.0' } else { '2.0.0' }
        $reused = @()
        foreach ($symbol in $symbols) {
            $matches = @($oldReports | Where-Object {
                $_.Doc.symbol -eq $symbol -and $_.Doc.synthetic_source.generator_version -eq $version -and
                $_.Doc.synthetic_source.master_seed -eq $seed -and $_.Doc.selection.window_count -eq 60 -and
                $_.Doc.selection.selection_seed -eq 20261106 -and
                ($family -eq 'V1' -or $_.Doc.synthetic_source.variant -eq 'full')
            })
            if ($matches.Count -gt 1) { throw "Niejednoznaczny stary raport $symbol/$family/$seed" }
            if ($matches.Count -eq 1) {
                $reused += [pscustomobject]@{
                    Symbol = $symbol; Family = $family; Seed = $seed; Count = 60
                    Manifest = ''; Report = $matches[0].Path
                }
            }
        }
        if ($reused.Count -eq $symbols.Count) {
            $knownRuns += $reused
        } else {
            $prefix = if ($family -eq 'V1') { 'v1' } else { 'v2' }
            $batchRoot = Join-Path $oldRoot "$prefix-full-$seed-60"
            $manifests = @(Get-ChildItem -LiteralPath $batchRoot -Filter manifest.json -Recurse -File -ErrorAction Stop)
            if ($manifests.Count -ne 1) { throw "Wymagany dokładnie jeden stary manifest: $batchRoot" }
            $knownRuns += @(Invoke-RefinementDiagnostic -Family $family -Seed $seed -Count 60 -ExistingManifest $manifests[0].FullName)
        }
    }
    foreach ($family in @('full-refined','bridge-refined')) {
        $knownRuns += @(Invoke-RefinementDiagnostic -Family $family -Seed $seed -Count 60)
    }
}
Save-RefinementSummary -Runs $knownRuns -Name 'known-seeds-summary'
$knownRuns | Export-Csv -LiteralPath (Join-Path $runRoot 'known-index.csv') -NoTypeInformation -Encoding UTF8 -NoClobber
```

Wspólna referencja: train 2020–2023, 60 rozłącznych okien po 120 świec,
selection_seed=20261106. Zapis nowych syntetyków: 720 serii (dwa warianty ×
trzy seedy × dwa symbole × 60). Baseline używa poprzednich partii/raportów.
Agregator dodatkowo sprawdzi hash, dokładną selekcję, statystyki referencyjne,
profile, seedy i liczności. Nie łączy różnych profili ani innego CSV po cichu.

## 5. Dwa nowe seedy po zamrożeniu parametrów i raporty

Seedy 20261205/20261215 nie występowały w 28 lokalnych manifestach w chwili
wdrożenia. Sprawdź ponownie, jeśli od tego czasu wykonywano eksperymenty.
Ocena jest nadal kontrolą stabilności na treningu.

```powershell
$newSeeds = @(20261205, 20261215)
$stabilityRuns = @()
foreach ($seed in $newSeeds) {
    foreach ($family in @('V1','original','full-refined','bridge-refined')) {
        $stabilityRuns += @(Invoke-RefinementDiagnostic -Family $family -Seed $seed -Count 60)
    }
}
Save-RefinementSummary -Runs $stabilityRuns -Name 'new-seeds-summary'
Save-RefinementSummary -Runs @($knownRuns + $stabilityRuns) -Name 'all-seeds-summary'
$stabilityRuns | Export-Csv -LiteralPath (Join-Path $runRoot 'stability-index.csv') -NoTypeInformation -Encoding UTF8 -NoClobber
```

Nowe seedy tworzą 960 serii. Przeglądaj osobno trzy znane seedy i dwie nowe
próby, a potem tabelę łączną pięciu seedów. Przekaż cztery profile oraz JSON/MD
obu instrumentów z katalogów `known-seeds-summary`, `new-seeds-summary`,
`all-seeds-summary` i indeksy CSV. Nie akceptuj profilu samą liczbą poprawionych
metryk; oceń priorytety, kontrolne pogorszenia i niepewność między seedami.

Powtórzenie po błędzie: zachowaj dotychczasowy katalog i wybierz nowy `$runRoot`.
Nie usuwaj wcześniejszych partii. Jeżeli nowe profile są już gotowe, przypnij
ich istniejące ścieżki w `$refinedProfiles` i pomiń krok 2. Poprawka WinError 32
pozostaje aktywna: przejściowa blokada końcowego pustego katalogu jest ponawiana,
a trwała blokada po zweryfikowanej publikacji kończy się ostrzeżeniem.

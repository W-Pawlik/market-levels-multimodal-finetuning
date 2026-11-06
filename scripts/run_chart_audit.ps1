param(
    [string]$OutputDirectory = '',
    [int]$SelectionSeed = 20261106,
    [ValidateSet(6,7,8)][int]$PerGroup = 8
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Brak interpretera .venv projektu.' }
Push-Location $projectRoot
try {
    if (-not $OutputDirectory) {
        $OutputDirectory = Join-Path 'results\diagnostics' ('dc-' + [guid]::NewGuid().ToString('N').Substring(0,12))
    }
    & $pythonPath -m market_levels.cli.audit_charts `
        --btc-csv 'data/processed/BTCUSDT_4h_2020-01_2026-10.csv' `
        --eth-csv 'data/processed/ETHUSDT_4h_2020-01_2026-10.csv' `
        --selection-seed $SelectionSeed --per-group $PerGroup --output $OutputDirectory
    if ($LASTEXITCODE -ne 0) { throw "Audyt nie powiodl sie (kod $LASTEXITCODE)." }
} finally {
    Pop-Location
}

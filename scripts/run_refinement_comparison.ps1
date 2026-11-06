[CmdletBinding(DefaultParameterSetName = 'Check')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Check')][switch]$CheckOnly,
    [Parameter(Mandatory = $true, ParameterSetName = 'Smoke')][switch]$SmokeTest,
    [Parameter(Mandatory = $true, ParameterSetName = 'Full')][switch]$RunFull,
    [string]$ResumeDirectory,
    [string]$InputsFile,
    # Domyslnie data/synthetic/rc-<12 hex>; pelny UUID jest w run.json.
    # Takze CheckOnly sprawdza dlugosc sciezek wskazanego katalogu.
    [string]$OutputDirectory,
    [string]$PythonPath,
    [switch]$FreshSeeds
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$project = Split-Path -Parent $PSScriptRoot
if (-not $PythonPath) { $PythonPath = Join-Path $project '.venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Brak interpretera: $PythonPath. Utworz .venv i wykonaj python -m pip install -e ."
}
$mode = switch ($PSCmdlet.ParameterSetName) { 'Check' { 'check' }; 'Smoke' { 'smoke' }; 'Full' { 'full' } }
$arguments = @('-I', '-X', 'utf8', '-m', 'market_levels.cli.refinement_comparison', '--mode', $mode, '--project', $project)
if ($FreshSeeds) { $arguments += '--fresh-seeds' }
foreach ($pair in @(@('--resume', $ResumeDirectory), @('--inputs', $InputsFile), @('--output', $OutputDirectory))) {
    if ($pair[1]) { $arguments += $pair }
}
# -I korzysta z instalacji editable wybranego interpretera, bez PYTHONPATH/CWD.
# Przechwytujemy stderr w pliku, aby PowerShell 5.1 nie ukryl tracebacku natywnego procesu.
$errorLog = Join-Path ([IO.Path]::GetTempPath()) ('market-levels-comparison-' + [guid]::NewGuid().ToString('N') + '.log')
Push-Location -LiteralPath $project
try {
    # PowerShell 5.1 traktuje stderr procesu jako NativeCommandError nawet przy
    # redirekcji. Continue pozwala odebrac caly traceback i sprawdzic exit code.
    $ErrorActionPreference = 'Continue'
    & $PythonPath @arguments 2> $errorLog
    $result = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($result -ne 0) {
        Get-Content -LiteralPath $errorLog -Tail 8 | Write-Host
        throw "Przerwano procedure (kod $result). Pelny blad: $errorLog. Sprawdz etap wskazany powyzej."
    }
} finally { $ErrorActionPreference = 'Stop'; Pop-Location }

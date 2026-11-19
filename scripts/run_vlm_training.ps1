param(
    [string]$Config = 'configs/vlm/training.json',
    [ValidateSet('preflight', 'dry-run', 'smoke-test', 'full', 'extra-epoch')]
    [string]$Mode = 'dry-run',
    [string]$OutputDirectory,
    [string]$ResumeCheckpoint,
    [string]$InitializeAdapter,
    [int]$StopAfter = 0,
    [switch]$SmokePlan,
    [switch]$ApproveFullTraining,
    [switch]$ApproveExtraEpoch
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonVlm = 'D:/ml-envs/market-levels-vlm/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonVlm)) { throw "Brak interpretera: $pythonVlm" }
if ($ResumeCheckpoint -and $InitializeAdapter) { throw 'InitializeAdapter i ResumeCheckpoint wzajemnie się wykluczają' }
if ($StopAfter -lt 0) { throw 'StopAfter musi być nieujemne' }
if (-not $OutputDirectory) {
    $prefix = if ($Mode -eq 'extra-epoch' -or $ApproveExtraEpoch) { 'results/vlm44-' } else { 'results/vlm42-pipeline-' }
    $OutputDirectory = $prefix + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
}
if (Test-Path -LiteralPath $OutputDirectory) { throw "Katalog już istnieje: $OutputDirectory" }
$logPath = $OutputDirectory + '.console.log'
if (Test-Path -LiteralPath $logPath) { throw "Log już istnieje: $logPath" }
$logParent = Split-Path -Parent $logPath
if ($logParent) { New-Item -ItemType Directory -Force -Path $logParent | Out-Null }
$arguments = @('-u', '-X', 'utf8', '-m', 'market_levels.cli.train_vlm', $Mode, '--config', $Config, '--output', $OutputDirectory)
if ($ResumeCheckpoint) { $arguments += @('--resume', $ResumeCheckpoint) }
if ($InitializeAdapter) { $arguments += @('--initialize-adapter', $InitializeAdapter) }
if ($StopAfter -gt 0) { $arguments += @('--stop-after', "$StopAfter") }
if ($SmokePlan) { $arguments += '--smoke-plan' }
if ($ApproveFullTraining) { $arguments += '--approve-full-training' }
if ($ApproveExtraEpoch) { $arguments += '--approve-extra-epoch' }
# Training executes its own preflight immediately before model loading.
# Continue lets native stderr pass through Tee-Object in Windows PowerShell 5.1.
$ErrorActionPreference = 'Continue'
& $pythonVlm @arguments 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $logPath
$processExitCode = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
$latestFile = Join-Path $OutputDirectory 'checkpoints/latest.txt'
if (Test-Path -LiteralPath $latestFile) {
    Write-Host ('Ostatni checkpoint: ' + (Join-Path (Join-Path $OutputDirectory 'checkpoints') (Get-Content -LiteralPath $latestFile -Raw).Trim()))
}
Write-Host "Wyniki: $OutputDirectory; log: $logPath; kod procesu: $processExitCode"
exit $processExitCode

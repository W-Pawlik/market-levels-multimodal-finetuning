param(
    [string]$Config = 'configs/vlm/training.json',
    [ValidateSet('preflight', 'dry-run', 'smoke-test', 'full')]
    [string]$Mode = 'dry-run',
    [string]$OutputDirectory,
    [string]$ResumeCheckpoint,
    [int]$StopAfter = 0,
    [switch]$SmokePlan,
    [switch]$ApproveFullTraining
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonVlm = 'D:/ml-envs/market-levels-vlm/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonVlm)) { throw "Brak interpretera: $pythonVlm" }
if (-not $OutputDirectory) {
    $OutputDirectory = 'results/vlm42-pipeline-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
}
if (Test-Path -LiteralPath $OutputDirectory) { throw "Katalog już istnieje: $OutputDirectory" }
$logPath = $OutputDirectory + '.console.log'
if (Test-Path -LiteralPath $logPath) { throw "Log już istnieje: $logPath" }
$logParent = Split-Path -Parent $logPath
if ($logParent) { New-Item -ItemType Directory -Force -Path $logParent | Out-Null }
$arguments = @('-u', '-X', 'utf8', '-m', 'market_levels.cli.train_vlm', $Mode, '--config', $Config, '--output', $OutputDirectory)
if ($ResumeCheckpoint) { $arguments += @('--resume', $ResumeCheckpoint) }
if ($StopAfter -gt 0) { $arguments += @('--stop-after', "$StopAfter") }
if ($SmokePlan) { $arguments += '--smoke-plan' }
if ($ApproveFullTraining) { $arguments += '--approve-full-training' }
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

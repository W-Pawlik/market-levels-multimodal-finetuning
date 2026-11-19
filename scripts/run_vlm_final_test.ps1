param(
    [ValidateSet('dry-run','prepare','infer','verify-pair','verify-variant','score-pair')]
    [string]$Mode = 'dry-run',
    [string]$Python = 'D:/ml-envs/market-levels-vlm/Scripts/python.exe',
    [string]$Config = 'configs/vlm/final-test.json',
    [string]$Dataset = 'data/datasets/ds35-800-20261107-a',
    [string]$Selection = 'docs/vlm/FINAL_MODEL_SELECTION.json',
    [string]$SessionDirectory = 'results/vlm46-final-test',
    [ValidateSet('base-nf4','finetuned-nf4')][string]$Variant,
    [string]$Adapter,
    [switch]$Resume,
    [switch]$ApproveFinalTest
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Missing Python: $Python" }
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$arguments = @('-u','-X','utf8','-m','market_levels.cli.final_test',$Mode,
    '--config',$Config,'--dataset',$Dataset,'--selection',$Selection,'--split','test')
if ($Mode -eq 'prepare') { $arguments += @('--output',$SessionDirectory) }
elseif ($Mode -ne 'dry-run') { $arguments += @('--session',$SessionDirectory) }
if ($Variant) { $arguments += @('--variant',$Variant) }
if ($Adapter) { $arguments += @('--adapter',$Adapter) }
if ($Resume) { $arguments += '--resume' }
if ($ApproveFinalTest) { $arguments += '--approve-final-test' }
$logId = [Guid]::NewGuid().ToString('N')
$logPath = "results/vlm46-$Mode-$logId.console.log"
$exitPath = "results/vlm46-$Mode-$logId.exit.json"
# Avoid PowerShell 5.1 turning benign native stderr warnings into terminating errors.
$ErrorActionPreference = 'Continue'
& $Python @arguments 2>&1 | Tee-Object -FilePath $logPath
$processExit = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
if ($null -eq $processExit) { $processExit = 1 }
@{mode=$Mode; exit_code=$processExit; log=$logPath; utc=[DateTime]::UtcNow.ToString('o')} |
    ConvertTo-Json | Set-Content -LiteralPath $exitPath -Encoding UTF8
Write-Host "Exit=$processExit; log=$logPath; exit record=$exitPath"
exit $processExit

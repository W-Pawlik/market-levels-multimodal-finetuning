param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$Python = 'D:/ml-envs/market-levels-vlm/Scripts/python.exe'
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Output directory already exists' }
$null = New-Item -ItemType Directory -Path $OutputDirectory
Get-CimInstance Win32_OperatingSystem |
    Select-Object Caption,Version,BuildNumber,TotalVisibleMemorySize,FreePhysicalMemory |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'windows.json') -Encoding utf8
Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'cpu.json') -Encoding utf8
Get-PSDrive -PSProvider FileSystem | Select-Object Name,Used,Free,Root |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'disks.json') -Encoding utf8
nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,driver_version,compute_cap --format=csv |
    Set-Content -LiteralPath (Join-Path $OutputDirectory 'gpu.txt') -Encoding utf8
nvidia-smi | Set-Content -LiteralPath (Join-Path $OutputDirectory 'nvidia-smi.txt') -Encoding utf8
# wsl.exe returns UTF-16; decoding through Python avoids the Windows PowerShell NUL issue.
$auditCode = @'
import json, pathlib, subprocess, sys
out = pathlib.Path(sys.argv[1])
for flag in ('--status', '--version', '--list'):
    args = ['wsl', flag] + (['--verbose'] if flag == '--list' else [])
    result = subprocess.run(args, capture_output=True, timeout=30)
    text = (result.stdout + result.stderr).decode('utf-16-le', errors='replace')
    (out / ('wsl-' + flag[2:] + '.txt')).write_text(text, encoding='utf-8')
from market_levels.modeling.io.runtime import setup, environment, gpu_snapshot
torch = setup(20261109)
report = {'environment': environment(), 'cuda_build': torch.version.cuda,
          'gpu': torch.cuda.get_device_name(), 'capability': torch.cuda.get_device_capability(),
          'bf16_native': torch.cuda.is_bf16_supported(including_emulation=False),
          'memory': gpu_snapshot(torch), 'precision': {}}
for name in ('float16', 'bfloat16', 'float32'):
    try:
        a = torch.randn(256, 256, device='cuda', dtype=getattr(torch, name), requires_grad=True)
        y = a @ torch.randn_like(a)
        loss = y.float().square().mean()
        loss.backward()
        torch.cuda.synchronize()
        report['precision'][name] = {'forward_finite': bool(torch.isfinite(y).all()),
                                    'backward_finite': bool(torch.isfinite(a.grad).all())}
        del a, y, loss
    except Exception as error:
        report['precision'][name] = {'error': str(error)}
(out / 'cuda-probe.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
'@
& $Python -X utf8 -c $auditCode $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw 'CUDA probe failed; inspect the log' }

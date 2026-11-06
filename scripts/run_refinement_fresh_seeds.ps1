# Oddzielna kontrola stabilnosci: 20261201 i 20261211, cztery grupy.
# Wspolny runner zachowuje importy, SHA, MAX_PATH, logi i wznowienie.
[CmdletBinding(DefaultParameterSetName = 'Check')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Check')][switch]$CheckOnly,
    [Parameter(Mandatory = $true, ParameterSetName = 'Smoke')][switch]$SmokeTest,
    [Parameter(Mandatory = $true, ParameterSetName = 'Full')][switch]$RunFull,
    [string]$ResumeDirectory,
    [string]$InputsFile,
    [string]$OutputDirectory,
    [string]$PythonPath
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'run_refinement_comparison.ps1') @PSBoundParameters -FreshSeeds

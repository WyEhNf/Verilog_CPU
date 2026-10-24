$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Enter-CpuEnvironment.ps1')
$cpuProjectRoot = Split-Path -Parent $PSScriptRoot
$cpuPython = Join-Path $cpuProjectRoot '.deps/msys64/mingw64/bin/python.exe'
$cpuValidation = Join-Path $cpuProjectRoot '.deps/validate_environment.py'
if (-not (Test-Path -LiteralPath $cpuValidation)) {
    throw "Environment validation script is missing: $cpuValidation"
}
& $cpuPython $cpuValidation
if ($LASTEXITCODE -ne 0) {
    throw "CPU environment validation failed with exit code $LASTEXITCODE"
}

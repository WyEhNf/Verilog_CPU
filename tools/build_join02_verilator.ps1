param(
    [Parameter(Mandatory = $true)][string]$Verilator,
    [Parameter(Mandatory = $true)][string]$VerilatorRoot,
    [Parameter(Mandatory = $true)][string]$CompilerBin
)

$ErrorActionPreference = "Stop"

function Resolve-ExistingPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Description
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Description not found: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

$verilatorPath = Resolve-ExistingPath -Path $Verilator -Description "Verilator executable"
$verilatorRootPath = Resolve-ExistingPath -Path $VerilatorRoot -Description "Verilator root"
$compilerBinPath = Resolve-ExistingPath -Path $CompilerBin -Description "MinGW compiler directory"

foreach ($tool in @("make.exe", "g++.exe", "ar.exe")) {
    if (-not (Test-Path -LiteralPath (Join-Path $compilerBinPath $tool) -PathType Leaf)) {
        throw "Required MinGW tool not found: $(Join-Path $compilerBinPath $tool)"
    }
}

# Verilator's generated makefile uses POSIX recipes even when its compiler is
# MinGW. Git for Windows supplies the shell and small utilities needed by those
# recipes; discover it instead of relying on a machine-specific installation
# directory.
$gitCommand = Get-Command git.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $gitCommand) {
    throw "Git for Windows is required to build the Verilator model (git.exe was not found on PATH)"
}

$gitRoot = Split-Path -Parent (Split-Path -Parent $gitCommand.Source)
$gitBin = Join-Path $gitRoot "bin"
$gitUsrBin = Join-Path $gitRoot "usr\bin"
$shellPath = Join-Path $gitBin "sh.exe"

foreach ($toolPath in @(
    $shellPath,
    (Join-Path $gitUsrBin "uname.exe"),
    (Join-Path $gitUsrBin "test.exe"),
    (Join-Path $gitUsrBin "cat.exe"),
    (Join-Path $gitUsrBin "xargs.exe"),
    (Join-Path $gitUsrBin "rm.exe")
)) {
    if (-not (Test-Path -LiteralPath $toolPath -PathType Leaf)) {
        throw "Required Git for Windows POSIX tool not found: $toolPath"
    }
}

$fileListPath = Resolve-ExistingPath -Path "rtl/filelist.f" -Description "RTL file list"
$rtlFiles = @(
    Get-Content -LiteralPath $fileListPath |
        ForEach-Object { ($_ -split '#', 2)[0].Trim() } |
        Where-Object { $_ -ne "" }
)

if ($rtlFiles.Count -eq 0) {
    throw "RTL file list is empty: $fileListPath"
}

$sources = @($rtlFiles) + @(
    "tb/models/rv32im_memory_model.v",
    "tb/integration/cpu_core_image_tb.v"
)
foreach ($source in $sources) {
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Verilator source not found: $source"
    }
}

$oldPath = $env:PATH
$oldShell = $env:SHELL
$oldVerilatorRoot = $env:VERILATOR_ROOT
try {
    $env:PATH = "$compilerBinPath;$gitUsrBin;$gitBin;$oldPath"
    $env:SHELL = $shellPath
    $env:VERILATOR_ROOT = $verilatorRootPath

    $arguments = @(
        "--binary",
        "--timing",
        "-Wno-fatal",
        "--debug",
        "--language", "1364-2005",
        "-Irtl",
        "--top-module", "cpu_core_image_tb",
        "--Mdir", "build/vlt/obj_dir",
        "-o", "cpu_core_image_vlt"
    ) + $sources

    & $verilatorPath @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Verilator build failed with exit code $LASTEXITCODE"
    }
}
finally {
    $env:PATH = $oldPath
    $env:SHELL = $oldShell
    $env:VERILATOR_ROOT = $oldVerilatorRoot
}

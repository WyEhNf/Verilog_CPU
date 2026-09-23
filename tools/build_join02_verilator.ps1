param(
    [Parameter(Mandatory = $true)][string]$Verilator,
    [Parameter(Mandatory = $true)][string]$VerilatorRoot,
    [Parameter(Mandatory = $true)][string]$CompilerBin,
    [string]$Mdir = "build/vlt/obj_dir",
    [string]$Output = "cpu_core_image_vlt",
    [int]$FeWidth = 1,
    [int]$BeWidth = 1,
    [int]$PhysRegs = 48,
    [int]$RobEntries = 16,
    [int]$RsEntries = 4,
    [int]$LsqEntries = 4,
    [int]$IntIssueWidth = 1,
    [int]$CdbWidth = 1,
    [int]$EnableCacheStats = 0,
    [int]$IcacheMshrs = 8,
    [int]$DcacheMshrs = 4,
    [int]$DcacheLines = 256,
    [int]$DcacheWays = 1,
    [int]$DcacheIndexHash = 0,
    [int]$DcacheRequestPipeline = 0,
    [int]$RamSizeBytes = 1048576,
    [int]$LegacySentinelHalt = 1,
    [int]$MemoryLatency = 50,
    [int]$BuildJobs = 2,
    [int]$IMemoryOutstanding = 8,
    [int]$DMemoryOutstanding = 4,
    [int]$FetchQueueDepth = 16,
    [int]$CompletionDepth = 4,
    [int]$MulImpl = 0,
    [int]$ShiftImpl = 0,
    [int]$PhysTagImpl = 0,
    [int]$GenerationWidth = 8,
    [int]$CheckpointImpl = 0,
    [int]$StoreBufferedRetire = 1,
    [int]$CompletionBypass = 0,
    [int]$SerialBackend = 0
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
        "-j", "$BuildJobs",
        "--timing",
        "-Wno-fatal",
        "--language", "1364-2005",
        "-Irtl",
        "--top-module", "cpu_core_image_tb",
        "--Mdir", $Mdir,
        "-o", $Output,
        "-GFE_WIDTH=$FeWidth",
        "-GBE_WIDTH=$BeWidth",
        "-GPHYS_REGS=$PhysRegs",
        "-GROB_ENTRIES=$RobEntries",
        "-GRS_ENTRIES=$RsEntries",
        "-GLSQ_ENTRIES=$LsqEntries",
        "-GINT_ISSUE_WIDTH=$IntIssueWidth",
        "-GCDB_WIDTH=$CdbWidth",
        "-GENABLE_CACHE_STATS=$EnableCacheStats",
        "-GICACHE_MSHRS=$IcacheMshrs",
        "-GDCACHE_MSHRS=$DcacheMshrs",
        "-GDCACHE_LINES=$DcacheLines",
        "-GDCACHE_WAYS=$DcacheWays",
        "-GDCACHE_INDEX_HASH=$DcacheIndexHash",
        "-GDCACHE_REQUEST_PIPELINE=$DcacheRequestPipeline",
        "-GRAM_SIZE_BYTES=$RamSizeBytes",
        "-GLEGACY_SENTINEL_HALT=$LegacySentinelHalt",
        "-GMEMORY_LATENCY=$MemoryLatency",
        "-GI_MEMORY_OUTSTANDING=$IMemoryOutstanding",
        "-GD_MEMORY_OUTSTANDING=$DMemoryOutstanding",
        "-GFETCH_QUEUE_DEPTH=$FetchQueueDepth",
        "-GCOMPLETION_DEPTH=$CompletionDepth",
        "-GMUL_IMPL=$MulImpl",
        "-GSHIFT_IMPL=$ShiftImpl",
        "-GPHYS_TAG_IMPL=$PhysTagImpl",
        "-GGENERATION_WIDTH=$GenerationWidth",
        "-GCHECKPOINT_IMPL=$CheckpointImpl",
        "-GSTORE_BUFFERED_RETIRE=$StoreBufferedRetire",
        "-GCOMPLETION_BYPASS=$CompletionBypass",
        "-GSERIAL_BACKEND=$SerialBackend"
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

param(
    [ValidateSet(8,12,16)][int]$RsEntries = 8,
    [ValidateSet(8,16)][int]$LsqEntries = 16,
    [ValidateSet(0,2)][int]$CompletionMode = 0,
    [ValidateSet(0,1)][int]$RsWake = 1,
    [ValidateSet(0,1)][int]$RenameRead = 1,
    [ValidateSet(0,1)][int]$CacheAction = 1,
    [ValidateSet(0,1)][int]$RobRead = 1,
    [ValidateSet(0,1)][int]$RobWrite = 1,
    [ValidateSet(0,1)][int]$CacheIndex = 1,
    [ValidateSet(0,1)][int]$CacheMetadata = 1,
    [ValidateSet(0,1,2)][int]$CacheUpdates = 2,
    [int]$BuildJobs = 1,
    [string]$ArtifactRoot = 'F:/CPU2026Integration',
    [string]$RunSuffix = '20261002',
    [switch]$FullArea
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if ($RunSuffix -notmatch '^[A-Za-z0-9_-]+$') { throw 'Invalid run suffix' }
$label = "r64p64rs${RsEntries}lsq${LsqEntries}_cdbmode${CompletionMode}_robr${RobRead}w${RobWrite}_dc${CacheUpdates}i${CacheIndex}m${CacheMetadata}_rswake${RsWake}_ratread${RenameRead}_action${CacheAction}_$RunSuffix"
$out = Join-Path $ArtifactRoot $label
if (Test-Path -LiteralPath $out) { throw 'Use a fresh run directory; existing evidence is preserved' }
New-Item -ItemType Directory -Path $out | Out-Null
$tempDir = Join-Path $ArtifactRoot 'temp'
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
$savedTemp = $env:TEMP
$savedTmp = $env:TMP
$env:TEMP = $tempDir
$env:TMP = $tempDir
Push-Location $repoRoot
try {
    $build = Join-Path $out 'build'
    $area = Join-Path $out 'area'
    $parameters = @{
        ASAP7_FANOUT_BUFFERS = 0; ROB_CONTROL_REGISTER_BANKS = 0;
        ROB_COMMIT_BANKED_READ = $RobRead; ROB_ALLOC_BANKED_WRITE = $RobWrite;
        DCACHE_TAG_SRAM = 1; DCACHE_STATIC_UPDATES = $CacheUpdates;
        DCACHE_REGISTERED_INDEX = $CacheIndex; DCACHE_LOCAL_METADATA_QUERY = $CacheMetadata;
        ICACHE_LINES = 128; PHYS_REGS = 64; ROB_ENTRIES = 64;
        RS_ENTRIES = $RsEntries; LSQ_ENTRIES = $LsqEntries; RS_ISSUE_METADATA = 1;
        COMPLETION_BYPASS = $CompletionMode;
        RS_WAKE_MUX_IMPL = $RsWake; RAT_READ_BYPASS = $RenameRead;
        DCACHE_LOCAL_ACTION_DECODE = $CacheAction;
        EARLY_STORE_ADDRESS = 2; RAT_RECOVERY_IMPL = 1;
        PREDICTOR_DIRECT_BRANCH_TARGET = 1; AXI_RESPONSE_FIFO_DEPTH = 2;
        READ_LINES = 8; WRITE_LINES = 4; WORD_QUEUE = 16
    }
    Write-Output "START native integrated build: $label"
    & ./tools/build_course_verilator_split.ps1 -Mdir $build -BuildJobs $BuildJobs -DisableDfg -Parameters $parameters > (Join-Path $out 'build.log') 2>&1
    if (!$?) { throw 'Integrated native build failed' }
    Write-Output "DONE native integrated build: $label"
    foreach ($suite in @('benchmark','basic','simulator','boundary')) {
        & python tools/run_course_axi_tests.py --build $build --suite $suite --report (Join-Path $out "$suite.json")
        if ($LASTEXITCODE -ne 0) { throw "Integrated suite failed: $suite" }
    }
    if ($FullArea) {
        & python tools/run_course_axi_area.py --build-manifest (Join-Path $build 'build_manifest.json') --outdir $area --clock-period 2
        if ($LASTEXITCODE -ne 0) { throw 'Integrated area failed' }
        & python tools/verify_course_axi_area.py $area --require-current
        if ($LASTEXITCODE -ne 0) { throw 'Independent area verification failed' }
        & python tools/run_course_full_timing.py $area --clock-port clock
        if ($LASTEXITCODE -ne 0) { throw 'Integrated full SRAM timing failed' }
    }
    Write-Output "COMPLETE integrated candidate: $label"
} finally {
    Pop-Location
    $env:TEMP = $savedTemp
    $env:TMP = $savedTmp
}

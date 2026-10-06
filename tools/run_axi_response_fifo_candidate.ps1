param(
    [ValidateSet(0,2,4)][int]$ResponseDepth = 2,
    [ValidateSet(8,16)][int]$LsqEntries = 8,
    [ValidateSet(48,64,96)][int]$PhysRegs = 48,
    [ValidateSet(32,64)][int]$RobEntries = 32,
    [ValidateSet(8,16,32)][int]$RsEntries = 8,
    [ValidateSet(0,1)][int]$RatRecovery = 0,
    [ValidateSet(0,1,2)][int]$EarlyStoreAddress = 0,
    [ValidateSet(0,1,2)][int]$DcacheUpdates = 0,
    [ValidateSet(0,1)][int]$RsIssueMetadata = 0,
    [int]$BuildJobs = 1,
    [string]$BuildRoot = 'D:/CPU2026Builds',
    [string]$AuditRoot = 'D:/CPU2026AreaAudits',
    [string]$RunSuffix = '20261001r2',
    [switch]$FullArea,
    [switch]$SplitCompilation,
    [ValidateSet('-Os','-O0')][string]$ModelOptimization = '-Os',
    [switch]$DisableDfg
)
$ErrorActionPreference = 'Stop'
$responseRoot = Split-Path -Parent $PSScriptRoot
if ($RunSuffix -notmatch '^[A-Za-z0-9_-]+$') { throw 'Invalid artifact suffix' }
if (($ModelOptimization -ne '-Os' -or $DisableDfg) -and !$SplitCompilation) {
    throw 'Explicit host optimization requires the split builder'
}
Push-Location $responseRoot
try {
    $label = "axi_response_fifo${ResponseDepth}_branch1_bus8w4q16_i128_r${RobEntries}p${PhysRegs}rs${RsEntries}"
    if ($LsqEntries -ne 8) { $label += "_lsq${LsqEntries}" }
    if ($RatRecovery -ne 0) { $label += "_rat${RatRecovery}" }
    if ($EarlyStoreAddress -ne 0) { $label += "_earlystore${EarlyStoreAddress}" }
    if ($DcacheUpdates -ne 0) { $label += "_dcupdate${DcacheUpdates}" }
    if ($RsIssueMetadata -ne 0) { $label += "_rsmeta${RsIssueMetadata}" }
    $buildDirectory = Join-Path $BuildRoot "${label}_$RunSuffix"
    $areaDirectory = Join-Path $AuditRoot "${label}_standard_$RunSuffix"
    $buildLog = Join-Path $responseRoot "build/${label}_build_$RunSuffix.log"
    $buildScript = $(if ($SplitCompilation) {
        './tools/build_course_verilator_split.ps1'
    } else { './tools/build_course_verilator.ps1' })
    $hostBuildOptions = @{}
    if ($SplitCompilation) {
        $hostBuildOptions.ModelOptimization = $ModelOptimization
        $hostBuildOptions.DisableDfg = $DisableDfg
    }
    Write-Output "START frozen native build: $label"
    & $buildScript -Mdir $buildDirectory -BuildJobs $BuildJobs -Parameters @{
        ASAP7_FANOUT_BUFFERS = 0; ROB_CONTROL_REGISTER_BANKS = 0;
        DCACHE_STATIC_UPDATES = $DcacheUpdates; DCACHE_TAG_SRAM = 1;
        AXI_RESPONSE_FIFO_DEPTH = $ResponseDepth;
        LSQ_ENTRIES = $LsqEntries;
        ROB_ENTRIES = $RobEntries;
        RAT_RECOVERY_IMPL = $RatRecovery; EARLY_STORE_ADDRESS = $EarlyStoreAddress;
        RS_ISSUE_METADATA = $RsIssueMetadata;
        ICACHE_LINES = 128; PHYS_REGS = $PhysRegs; PREDICTOR_DIRECT_BRANCH_TARGET = 1; RS_ENTRIES = $RsEntries;
        READ_LINES = 8; WRITE_LINES = 4; WORD_QUEUE = 16
    } @hostBuildOptions > $buildLog 2>&1
    if (!$?) { throw "Native build failed; inspect $buildLog" }
    Write-Output "DONE frozen native build: $label"
    foreach ($suite in @('benchmark','basic','simulator','boundary')) {
        Write-Output "START native $suite`: $label"
        & python tools/run_course_axi_tests.py --build $buildDirectory --suite $suite --report "build/cpu2026/${label}_${suite}_$RunSuffix.json"
        if ($LASTEXITCODE -ne 0) { throw "Strict native suite failed: $label $suite" }
    }
    if ($FullArea) {
        Write-Output "START original full-area flow: $label"
        & python tools/run_course_axi_area.py --build-manifest (Join-Path $buildDirectory 'build_manifest.json') --outdir $areaDirectory --clock-period 2
        if ($LASTEXITCODE -ne 0) { throw "Original full-area flow failed: $label" }
        & python tools/verify_course_axi_area.py $areaDirectory --require-current
        if ($LASTEXITCODE -ne 0) { throw "Independent current-input area verification failed: $label" }
        & python tools/run_course_full_timing.py $areaDirectory --clock-port clock
        if ($LASTEXITCODE -ne 0) { throw "Full-SRAM original-constraint STA failed: $label" }
    }
    Write-Output "COMPLETE candidate: $label"
} finally {
    Pop-Location
}

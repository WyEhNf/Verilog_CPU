param(
    [ValidateSet(0,1)][int]$UpdateMode = 1,
    [int]$BuildJobs = 1,
    [string]$BuildRoot = 'D:/CPU2026Builds',
    [string]$AuditRoot = 'D:/CPU2026AreaAudits',
    [string]$RunSuffix = '20261001',
    [switch]$FullArea
)
$ErrorActionPreference = 'Stop'
$candidateRoot = Split-Path -Parent $PSScriptRoot
if ($RunSuffix -notmatch '^[A-Za-z0-9_-]+$') { throw 'Invalid artifact suffix' }
Push-Location $candidateRoot
try {
    $label = "dcache_static_updates${UpdateMode}_branch1_bus8w4q16_i128_r32p48rs8"
    $buildDirectory = Join-Path $BuildRoot "${label}_$RunSuffix"
    $areaDirectory = Join-Path $AuditRoot "${label}_standard_$RunSuffix"
    $buildLog = Join-Path $candidateRoot "build/${label}_build_$RunSuffix.log"
    Write-Output "START frozen native build: $label"
    & ./tools/build_course_verilator.ps1 -Mdir $buildDirectory -BuildJobs $BuildJobs -Parameters @{
        ASAP7_FANOUT_BUFFERS = 0; ROB_CONTROL_REGISTER_BANKS = 0;
        DCACHE_STATIC_UPDATES = $UpdateMode; DCACHE_TAG_SRAM = 1;
        ICACHE_LINES = 128; PHYS_REGS = 48; PREDICTOR_DIRECT_BRANCH_TARGET = 1; RS_ENTRIES = 8;
        READ_LINES = 8; WRITE_LINES = 4; WORD_QUEUE = 16
    } > $buildLog 2>&1
    if (!$?) { throw "Native build failed; inspect $buildLog" }
    Write-Output "DONE frozen native build: $label"
    foreach ($suite in @('benchmark','basic','simulator','boundary')) {
        Write-Output "START native $suite`: $label"
        & python tools/run_course_axi_tests.py --build $buildDirectory --suite $suite --report "build/cpu2026/${label}_${suite}_$RunSuffix.json"
        if ($LASTEXITCODE -ne 0) { throw "Strict native suite failed: $label $suite" }
    }
    if ($FullArea) {
        Write-Output "START official full-area flow: $label"
        & python tools/run_course_axi_area.py --build-manifest (Join-Path $buildDirectory 'build_manifest.json') --outdir $areaDirectory --clock-period 2
        if ($LASTEXITCODE -ne 0) { throw "Official full-area flow failed: $label" }
        & python tools/verify_course_axi_area.py $areaDirectory --require-current
        if ($LASTEXITCODE -ne 0) { throw "Independent current-input area verification failed: $label" }
        & python tools/run_course_full_timing.py $areaDirectory --clock-port clock
        if ($LASTEXITCODE -ne 0) { throw "Full-SRAM original-constraint STA failed: $label" }
    }
    Write-Output "COMPLETE candidate: $label"
} finally {
    Pop-Location
}

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$savedToolPath = $env:PATH
Push-Location $repoRoot
try {
    $env:PATH = "$repoRoot/.deps/oss-cad-suite-install/oss-cad-suite/bin;$repoRoot/.deps/oss-cad-suite-install/oss-cad-suite/lib;$env:PATH"
    foreach ($mergeDelay in @(0, 16, 32)) {
    foreach ($cacheWays in @(1, 2)) {
    foreach ($tagSram in @(0, 1)) {
    $testOutput = "build/dcache_sram_protocol_t${tagSram}_m${mergeDelay}_w$cacheWays.vvp"
    & iverilog.exe -g2012 -I rtl -s rv32_dcache_sram_tb -P "rv32_dcache_sram_tb.MERGE_DELAY=$mergeDelay" -P "rv32_dcache_sram_tb.CACHE_WAYS=$cacheWays" -P "rv32_dcache_sram_tb.TAG_SRAM=$tagSram" -o $testOutput `
        rtl/cache/rv32_dcache_nonblocking.v .deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv `
        tb/unit/rv32_dcache_sram_tb.v
    if ($LASTEXITCODE -ne 0) { throw 'SRAM protocol test compile failed' }
    $result = & vvp.exe -N $testOutput
    "TAG_SRAM=$tagSram STORE_MERGE_DELAY=$mergeDelay CACHE_WAYS=$cacheWays"
    $result
    if ($LASTEXITCODE -ne 0 -or $result -match 'ERROR|FAIL|FATAL' -or -not ($result -match 'PASS')) {
        throw 'SRAM protocol test failed'
    }
    }
    }
    }
} finally {
    $env:PATH = $savedToolPath
    Pop-Location
}

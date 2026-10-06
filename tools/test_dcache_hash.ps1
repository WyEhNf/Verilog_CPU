param([int[]]$TagSramModes = @(0, 1))
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$savedToolPath = $env:PATH
Push-Location $repoRoot
try {
    $env:PATH = "$repoRoot/.deps/oss-cad-suite-install/oss-cad-suite/bin;$repoRoot/.deps/oss-cad-suite-install/oss-cad-suite/lib;$env:PATH"
    foreach ($tagSram in $TagSramModes) {
    foreach ($hashMode in @(0, 1)) {
        foreach ($cacheLines in @(16, 64)) {
          foreach ($cacheWays in @(1, 2)) {
            foreach ($prefetchMode in @(0, 1)) {
                $testFile = "build/dcache_hash_t${tagSram}_h${hashMode}_l${cacheLines}_w${cacheWays}_p${prefetchMode}.vvp"
                & iverilog.exe -g2012 -I rtl -s rv32_dcache_hash_tb `
                    -P "rv32_dcache_hash_tb.INDEX_HASH=$hashMode" `
                    -P "rv32_dcache_hash_tb.CACHE_LINES=$cacheLines" `
                    -P "rv32_dcache_hash_tb.CACHE_WAYS=$cacheWays" `
                    -P "rv32_dcache_hash_tb.PREFETCH=$prefetchMode" `
                    -P "rv32_dcache_hash_tb.TAG_SRAM=$tagSram" `
                    -o $testFile rtl/cache/rv32_dcache_nonblocking.v `
                    .deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv `
                    tb/models/rv32im_memory_model.v tb/unit/rv32_dcache_hash_tb.v
                if ($LASTEXITCODE -ne 0) { throw 'Compile failed' }
                $result = & vvp.exe -N $testFile
                $result
                if ($LASTEXITCODE -ne 0 -or $result -match 'ERROR|FAIL|FATAL' -or -not ($result -match 'PASS')) {
                    throw 'D-cache test failed'
                }
            }
          }
        }
    }
    }
} finally {
    $env:PATH = $savedToolPath
    Pop-Location
}

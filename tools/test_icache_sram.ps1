$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$savedToolPath = $env:PATH
Push-Location $repoRoot
try {
    $env:PATH = "$repoRoot/.deps/oss-cad-suite-install/oss-cad-suite/bin;$repoRoot/.deps/oss-cad-suite-install/oss-cad-suite/lib;$env:PATH"
    foreach ($lines in @(16, 64)) {
        foreach ($ways in @(1, 2)) {
            $output = "build/icache_sram_${lines}_${ways}.vvp"
            & iverilog.exe -g2012 -I rtl -s rv32_icache_sram_tb -o $output `
                "-Prv32_icache_sram_tb.LINES=$lines" "-Prv32_icache_sram_tb.WAYS=$ways" `
                rtl/cache/rv32_icache_nonblocking.v .deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv `
                tb/unit/rv32_icache_sram_tb.v
            if ($LASTEXITCODE -ne 0) { throw 'I-cache SRAM test compile failed' }
            $result = & vvp.exe -N $output
            $result
            if ($LASTEXITCODE -ne 0 -or $result -match '^(FAIL|ERROR|FATAL):' -or -not ($result -match '^PASS:')) {
                throw 'I-cache SRAM protocol test failed'
            }
        }
    }
} finally {
    $env:PATH = $savedToolPath
    Pop-Location
}

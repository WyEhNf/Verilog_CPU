param(
    [string]$CadBin = 'E:/Verilog_cpu/.deps/oss-cad-suite-install/oss-cad-suite/bin',
    [string]$CadLib = 'E:/Verilog_cpu/.deps/oss-cad-suite-install/oss-cad-suite/lib'
)
$ErrorActionPreference = 'Stop'
$savedCacheTestPath = $env:PATH
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $env:PATH = "$CadBin;$CadLib;$savedCacheTestPath"
    $testDir = 'build/cache_memory_share'
    New-Item -ItemType Directory -Force $testDir | Out-Null
    foreach ($hash in @(0, 1)) {
        foreach ($ways in @(1, 2)) {
            $stem = "$testDir/h${hash}_w${ways}"
            # Share only the data/tag ports. Keep a before/after port manifest.
            & yosys.exe -Q -T -q -l "$stem.log" -p "read_verilog -I rtl rtl/cache/rv32_dcache_nonblocking.v; chparam -set CACHE_LINES 16 -set CACHE_WAYS $ways -set INDEX_HASH $hash -set TAG_WIDTH 16 rv32_dcache_nonblocking; hierarchy -top rv32_dcache_nonblocking; proc; opt; memory_dff; memory_collect; write_json ${stem}_before.json; memory_share rv32_dcache_nonblocking/data_mem rv32_dcache_nonblocking/tag_mem; opt_clean; write_json ${stem}_after.json; write_verilog -noattr $stem.v"
            if ($LASTEXITCODE -ne 0) { throw 'Cache memory sharing transform failed' }
            $before = Get-Content "${stem}_before.json" -Raw | ConvertFrom-Json
            $after = Get-Content "${stem}_after.json" -Raw | ConvertFrom-Json
            foreach ($memory in @('data_mem', 'tag_mem')) {
                $original = $before.modules.rv32_dcache_nonblocking.cells.$memory.parameters
                $shared = $after.modules.rv32_dcache_nonblocking.cells.$memory.parameters
                foreach ($field in @('SIZE', 'WIDTH', 'RD_PORTS')) {
                    if ($original.$field -ne $shared.$field) { throw "$memory changed $field" }
                }
                $expectedWrites = if ($memory -eq 'data_mem') { 2 } else { 1 }
                if ([Convert]::ToInt32($shared.WR_PORTS, 2) -ne $expectedWrites) {
                    throw "$memory unexpected write-port count"
                }
                if ($memory -eq 'data_mem' -and
                    [Convert]::ToInt32($shared.RD_PORTS, 2) -ne 1) {
                    throw 'D-cache hit/victim reads must share one data read port'
                }
            }
            & iverilog.exe -g2012 -DSYNTH_CACHE_FIXED -I rtl -s rv32_dcache_hash_tb `
                -P rv32_dcache_hash_tb.CACHE_LINES=16 `
                -P "rv32_dcache_hash_tb.CACHE_WAYS=$ways" `
                -P "rv32_dcache_hash_tb.INDEX_HASH=$hash" `
                -P rv32_dcache_hash_tb.PREFETCH=1 -o "$stem.vvp" `
                "$stem.v" tb/models/rv32im_memory_model.v tb/unit/rv32_dcache_hash_tb.v
            if ($LASTEXITCODE -ne 0) { throw 'Shared cache netlist compile failed' }
            $output = @(& vvp.exe -N "$stem.vvp" 2>&1)
            $output
            if ($LASTEXITCODE -ne 0 -or ($output -match 'ERROR|FAIL|FATAL') -or
                -not ($output -match 'PASS: D-cache')) { throw 'Shared cache netlist test failed' }
        }
    }
    Write-Host 'PASS: cache memory sharing, 4 fixed-netlist configurations'
} finally {
    $env:PATH = $savedCacheTestPath
    Pop-Location
}

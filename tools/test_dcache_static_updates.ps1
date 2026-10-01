param(
    [string]$Outdir = 'build/dcache_static_updates_protocol_20261002',
    [ValidateSet(0,1,2)][int[]]$UpdateModes = @(0,1,2)
)
$ErrorActionPreference = 'Stop'
$testRoot = Split-Path -Parent $PSScriptRoot
$savedTestPath = $env:PATH
Push-Location $testRoot
try {
    $env:PATH = "$testRoot/.deps/oss-cad-suite-install/oss-cad-suite/bin;$testRoot/.deps/oss-cad-suite-install/oss-cad-suite/lib;$env:PATH"
    $destination = [IO.Path]::GetFullPath($(if ([IO.Path]::IsPathRooted($Outdir)) {
        $Outdir
    } else { Join-Path $testRoot $Outdir }))
    $snapshot = Join-Path $destination 'source_snapshot'
    if (Test-Path -LiteralPath (Join-Path $destination 'report.json')) { throw 'Choose a fresh matrix output directory' }
    $inputs = @('rtl/cache/rv32_dcache_nonblocking.v', 'rtl/cache/rv32_dcache_control_banks.v', 'rtl/rv32im_defs.vh',
        '.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv', 'tb/models/rv32im_memory_model.v',
        'tb/unit/rv32_dcache_sram_tb.v', 'tb/unit/rv32_dcache_hash_tb.v',
        'tools/test_dcache_static_updates.ps1')
    $hashes = [ordered]@{}
    foreach ($source in $inputs) {
        $target = Join-Path $snapshot $source
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        $hashes[$source] = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
        if ((Test-Path -LiteralPath $target) -and (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hashes[$source]) {
            throw "Different existing snapshot: $target"
        }
        Copy-Item -LiteralPath $source -Destination $target
    }
    $results = [Collections.Generic.List[object]]::new()
    $cache = Join-Path $snapshot 'rtl/cache/rv32_dcache_nonblocking.v'
    $banks = Join-Path $snapshot 'rtl/cache/rv32_dcache_control_banks.v'
    $ram = Join-Path $snapshot '.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv'
    $memory = Join-Path $snapshot 'tb/models/rv32im_memory_model.v'
    $include = Join-Path $snapshot 'rtl'
    function Run-CacheCase([string]$Name, [string]$Top, [hashtable]$Parameters, [string[]]$Sources) {
        $executable = Join-Path $destination "$Name.vvp"
        $arguments = @('-g2012', '-I', $include, '-s', $Top, '-o', $executable)
        foreach ($key in ($Parameters.Keys | Sort-Object)) { $arguments += @('-P', "$Top.$key=$($Parameters[$key])") }
        $arguments += $Sources
        & iverilog.exe @arguments > (Join-Path $destination "$Name.compile.log") 2>&1
        if ($LASTEXITCODE -ne 0) { throw "Compile failed: $Name" }
        $output = & vvp.exe -N $executable 2>&1
        $exitCode = $LASTEXITCODE
        $output | Set-Content -LiteralPath (Join-Path $destination "$Name.run.log")
        if ($exitCode -ne 0 -or $output -match 'ERROR|FAIL|FATAL' -or -not ($output -match 'PASS')) { throw "Protocol failed: $Name" }
        $results.Add([ordered]@{ name = $Name; status = 'PASS'; top = $Top; parameters = $Parameters })
        Write-Output "PASS $Name"
    }
    $selectedModes = @($UpdateModes | Sort-Object -Unique)
    if ($selectedModes.Count -eq 0) { throw 'At least one update mode is required' }
    foreach ($mode in $selectedModes) {
        foreach ($tag in @(0,1)) { foreach ($ways in @(1,2)) { foreach ($delay in @(0,16,32)) {
            Run-CacheCase "sram_u${mode}_t${tag}_w${ways}_m${delay}" 'rv32_dcache_sram_tb' @{
                STATIC_UPDATES=$mode; TAG_SRAM=$tag; CACHE_WAYS=$ways; MERGE_DELAY=$delay
            } @($cache, $banks, $ram, (Join-Path $snapshot 'tb/unit/rv32_dcache_sram_tb.v'))
        } } }
        foreach ($tag in @(0,1)) { foreach ($ways in @(1,2)) { foreach ($lines in @(16,64,1024)) {
            foreach ($hash in @(0,1)) { foreach ($prefetch in @(0,1)) {
                Run-CacheCase "hash_u${mode}_t${tag}_w${ways}_l${lines}_h${hash}_p${prefetch}" 'rv32_dcache_hash_tb' @{
                    STATIC_UPDATES=$mode; TAG_SRAM=$tag; CACHE_WAYS=$ways; CACHE_LINES=$lines; INDEX_HASH=$hash; PREFETCH=$prefetch
                } @($cache, $banks, $ram, $memory, (Join-Path $snapshot 'tb/unit/rv32_dcache_hash_tb.v'))
            } }
        } } }
    }
    foreach ($source in $inputs) {
        if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hashes[$source] -or
            (Get-FileHash -LiteralPath (Join-Path $snapshot $source) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hashes[$source]) {
            throw "Input changed during matrix: $source"
        }
    }
    if ($results.Count -ne 60 * $selectedModes.Count) { throw 'Incomplete protocol matrix' }
    [ordered]@{ status='COMPLETE'; passed=$results.Count; failed=0; update_modes=$selectedModes;
        source_sha256=$hashes; results=$results.ToArray() } |
        ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $destination 'report.json')
    Write-Output "COMPLETE: $($results.Count) static-update SRAM/hash/cache protocol cases (modes $($selectedModes -join ','))"
} finally {
    $env:PATH = $savedTestPath
    Pop-Location
}

param([string]$Outdir = 'build/rob_control_banks_protocol_20261001')
$ErrorActionPreference = 'Stop'
$controlRoot = Split-Path -Parent $PSScriptRoot
$controlSuite = Join-Path $controlRoot '.deps/oss-cad-suite-install/oss-cad-suite'
$savedPath = $env:PATH
Push-Location $controlRoot
try {
    $env:PATH = "$controlSuite/bin;$controlSuite/lib;$savedPath"
    $directory = [IO.Path]::GetFullPath($(if ([IO.Path]::IsPathRooted($Outdir)) {
        $Outdir
    } else { Join-Path $controlRoot $Outdir }))
    if (Test-Path -LiteralPath (Join-Path $directory 'report.json')) {
        throw 'Completed protocol report exists; choose a fresh output directory'
    }
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $protocolInputs = @(Get-Content -LiteralPath rtl/filelist.f | ForEach-Object {
        $entry = ($_ -split '#', 2)[0].Trim()
        if ($entry) { (Resolve-Path -LiteralPath $entry).Path }
    }) + @((Resolve-Path -LiteralPath rtl/filelist.f).Path,
        (Resolve-Path -LiteralPath rtl/rv32im_defs.vh).Path,
        (Resolve-Path -LiteralPath tb/unit/rv32_rob_tb.v).Path,
        (Resolve-Path -LiteralPath tb/unit/rv32_backend_joint_tb.v).Path,
        (Resolve-Path -LiteralPath .deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv).Path,
        $PSCommandPath)
    $hashes = [ordered]@{}
    foreach ($inputPath in ($protocolInputs | Sort-Object -Unique)) {
        $hashes[$inputPath] = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $results = [Collections.Generic.List[object]]::new()
    function Assert-Inputs {
        foreach ($entry in $hashes.GetEnumerator()) {
            if ((Get-FileHash -LiteralPath $entry.Key -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
                throw "Protocol source changed: $($entry.Key)"
            }
        }
    }
    function Run-ControlCase([string]$Top, [string]$Name, [string[]]$Overrides) {
        Assert-Inputs
        $image = Join-Path $directory "$Name.vvp"
        $compileLog = Join-Path $directory "$Name.compile.log"
        $simulationLog = Join-Path $directory "$Name.simulation.log"
        & "$controlSuite/bin/iverilog.exe" -g2012 -I rtl -s $Top @Overrides -o $image -c rtl/filelist.f .deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv "tb/unit/$Top.v" > $compileLog 2>&1
        if ($LASTEXITCODE -ne 0) { throw "Compile failed: $compileLog" }
        & "$controlSuite/bin/vvp.exe" -N $image > $simulationLog 2>&1
        if ($LASTEXITCODE -ne 0 -or !(Select-String -LiteralPath $simulationLog -Pattern '^PASS:' -Quiet)) {
            throw "Protocol test failed: $simulationLog"
        }
        Assert-Inputs
        $results.Add([ordered]@{ name = $Name; status = 'PASS'; overrides = $Overrides;
            compile_log_sha256 = (Get-FileHash -LiteralPath $compileLog -Algorithm SHA256).Hash.ToLowerInvariant();
            simulation_log_sha256 = (Get-FileHash -LiteralPath $simulationLog -Algorithm SHA256).Hash.ToLowerInvariant() })
        Write-Output "PASS $Name"
    }
    foreach ($width in @(1,2,4)) {
        foreach ($depth in @(8,32)) {
            foreach ($banks in @(0,1)) {
                Run-ControlCase rv32_rob_tb "rob_be${width}_r${depth}_banks${banks}" @(
                    '-P', "rv32_rob_tb.BE_WIDTH=$width", '-P', "rv32_rob_tb.ROB_ENTRIES=$depth",
                    '-P', "rv32_rob_tb.ROB_CONTROL_REGISTER_BANKS=$banks")
            }
        }
        foreach ($completion in @(0,2)) {
            foreach ($posted in @(0,1)) {
                foreach ($metadata in @(0,1)) {
                    Run-ControlCase rv32_backend_joint_tb "backend_be${width}_c${completion}_s${posted}_m${metadata}_banks1" @(
                        '-P', "rv32_backend_joint_tb.BE_WIDTH=$width",
                        '-P', "rv32_backend_joint_tb.COMPLETION_BYPASS=$completion",
                        '-P', "rv32_backend_joint_tb.STORE_BUFFERED_RETIRE=$posted",
                        '-P', "rv32_backend_joint_tb.PREDICTOR_META=$metadata",
                        '-P', 'rv32_backend_joint_tb.ROB_CONTROL_REGISTER_BANKS=1')
                }
            }
        }
    }
    Assert-Inputs
    if ($results.Count -ne 36) { throw 'Incomplete ROB/backend parameter matrix' }
    $report = [ordered]@{ status = 'COMPLETE'; method = 'Pure RTL ROB control-register protocol matrix';
        source_sha256 = $hashes; results = @($results.ToArray()); total_cases = $results.Count }
    [IO.File]::WriteAllText((Join-Path $directory 'report.json'),
        (($report | ConvertTo-Json -Depth 8) + "`n"), [Text.UTF8Encoding]::new($false))
    Write-Output 'PASS: all 36 pure RTL control-bank ROB/backend protocol configurations'
} finally {
    $env:PATH = $savedPath
    Pop-Location
}

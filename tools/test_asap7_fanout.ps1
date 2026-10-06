param([string]$Outdir = 'D:/CPU2026Tests/asap7_fanout_protocol_20261001')
$ErrorActionPreference = 'Stop'
$fanoutRoot = Split-Path -Parent $PSScriptRoot
$fanoutSuite = Join-Path $fanoutRoot '.deps/oss-cad-suite-install/oss-cad-suite'
$savedPath = $env:PATH
Push-Location $fanoutRoot
try {
    $env:PATH = "$fanoutSuite/bin;$fanoutSuite/lib;$savedPath"
    New-Item -ItemType Directory -Force -Path $Outdir | Out-Null
    function Run-Case([string]$Top, [string]$Name, [string[]]$Overrides) {
        $image = Join-Path $Outdir "$Name.vvp"
        $source = "tb/unit/$Top.v"
        & "$fanoutSuite/bin/iverilog.exe" -g2012 -I rtl -s $Top @Overrides -o $image -c rtl/filelist.f .deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv $source
        if ($LASTEXITCODE -ne 0) { throw "Compile failed: $Name" }
        & "$fanoutSuite/bin/vvp.exe" -N $image
        if ($LASTEXITCODE -ne 0) { throw "Protocol test failed: $Name" }
    }
    foreach ($width in @(1,2,4)) {
        foreach ($depth in @(8,32)) {
            foreach ($buffers in @(0,1)) {
                Run-Case rv32_rob_tb "rob_be${width}_r${depth}_buf${buffers}" @(
                    '-P', "rv32_rob_tb.BE_WIDTH=$width", '-P', "rv32_rob_tb.ROB_ENTRIES=$depth",
                    '-P', "rv32_rob_tb.ASAP7_FANOUT_BUFFERS=$buffers")
            }
        }
        foreach ($completion in @(0,2)) {
            foreach ($posted in @(0,1)) {
                foreach ($metadata in @(0,1)) {
                    Run-Case rv32_backend_joint_tb "backend_be${width}_c${completion}_s${posted}_m${metadata}_buf1" @(
                        '-P', "rv32_backend_joint_tb.BE_WIDTH=$width",
                        '-P', "rv32_backend_joint_tb.COMPLETION_BYPASS=$completion",
                        '-P', "rv32_backend_joint_tb.STORE_BUFFERED_RETIRE=$posted",
                        '-P', "rv32_backend_joint_tb.PREDICTOR_META=$metadata",
                        '-P', 'rv32_backend_joint_tb.ASAP7_FANOUT_BUFFERS=1')
                }
            }
        }
    }
    Write-Output 'PASS: 36 buffered/unbuffered ROB and backend protocol configurations'
} finally {
    $env:PATH = $savedPath
    Pop-Location
}

param([string]$Outdir = 'D:/CPU2026Tests/store_admission_20261001')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$savedPath = $env:PATH
Push-Location $repoRoot
try {
    $suite = Join-Path $repoRoot '.deps/oss-cad-suite-install/oss-cad-suite'
    $env:PATH = "$suite/bin;$suite/lib;$savedPath"
    New-Item -ItemType Directory -Force -Path $Outdir | Out-Null
    foreach ($bypass in @(0, 1)) {
        foreach ($be in @(1, 2, 4)) {
            $case = "lsq_be${be}_admit${bypass}"
            $image = Join-Path $Outdir "$case.vvp"
            & iverilog.exe -g2012 -I rtl -s rv32_lsq_tb `
                -P "rv32_lsq_tb.BE_WIDTH=$be" `
                -P "rv32_lsq_tb.STORE_ADMISSION_BYPASS=$bypass" -o $image `
                rtl/backend/rv32_lsq.v tb/unit/rv32_lsq_tb.v
            if ($LASTEXITCODE -ne 0) { throw "Compile failed: $case" }
            $result = & vvp.exe -N $image
            $result | Tee-Object -FilePath (Join-Path $Outdir "$case.log")
            if ($LASTEXITCODE -ne 0 -or $result -match 'FAIL|ERROR|FATAL' -or
                -not ($result -match '^PASS: B-08')) { throw "Regression failed: $case" }
            foreach ($completion in @(0, 2)) {
                foreach ($postedStore in @(0, 1)) {
                    $case = "backend_be${be}_admit${bypass}_cpl${completion}_store${postedStore}"
                    $image = Join-Path $Outdir "$case.vvp"
                    & iverilog.exe -g2012 -I rtl -s rv32_backend_joint_tb `
                        -P "rv32_backend_joint_tb.BE_WIDTH=$be" `
                        -P "rv32_backend_joint_tb.LSQ_STORE_ADMISSION_BYPASS=$bypass" `
                        -P "rv32_backend_joint_tb.COMPLETION_BYPASS=$completion" `
                        -P "rv32_backend_joint_tb.STORE_BUFFERED_RETIRE=$postedStore" -o $image `
                        -c rtl/filelist.f .deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv `
                        tb/unit/rv32_backend_joint_tb.v 2> (Join-Path $Outdir "$case.compile.log")
                    if ($LASTEXITCODE -ne 0) { throw "Compile failed: $case" }
                    $result = & vvp.exe -N $image
                    $result | Tee-Object -FilePath (Join-Path $Outdir "$case.log")
                    if ($LASTEXITCODE -ne 0 -or $result -match 'FAIL|ERROR|FATAL' -or
                        -not ($result -match '^PASS: B-09')) { throw "Regression failed: $case" }
                }
            }
        }
    }
} finally {
    $env:PATH = $savedPath
    Pop-Location
}

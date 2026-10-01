param([string]$Outdir = 'D:/CPU2026Tests/completion_direct_20261001')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$savedPath = $env:PATH
Push-Location $repoRoot
try {
    $suite = Join-Path $repoRoot '.deps/oss-cad-suite-install/oss-cad-suite'
    $env:PATH = "$suite/bin;$suite/lib;$savedPath"
    New-Item -ItemType Directory -Force -Path $Outdir | Out-Null
    foreach ($be in @(1, 2, 4)) {
        foreach ($cdb in @(1, 2, 4)) {
            if ($cdb -gt $be) { continue }
            foreach ($sources in @(1, 2, 6, 9)) {
                $case = "be${be}_cdb${cdb}_sources${sources}"
                $image = Join-Path $Outdir "$case.vvp"
                & iverilog.exe -g2012 -Wall -I rtl -s rv32_completion_direct_tb `
                    -P "rv32_completion_direct_tb.BE_WIDTH=$be" `
                    -P "rv32_completion_direct_tb.CDB_WIDTH=$cdb" `
                    -P "rv32_completion_direct_tb.SOURCES=$sources" -o $image `
                    rtl/backend/rv32_completion_network.v tb/unit/rv32_completion_direct_tb.v
                if ($LASTEXITCODE -ne 0) { throw "Compile failed: $case" }
                $result = & vvp.exe -N $image
                $result | Tee-Object -FilePath (Join-Path $Outdir "$case.log")
                if ($LASTEXITCODE -ne 0 -or $result -match '^(FAIL|ERROR|FATAL):' -or
                    -not ($result -match '^PASS: direct CDB')) { throw "Regression failed: $case" }
            }
        }
    }
    # The integration test observes all retired lanes, precise load errors,
    # MMIO acknowledgement errors, branch recovery and MDU/LSQ contention.
    foreach ($mode in @(0, 2)) {
        foreach ($be in @(1, 2, 4)) {
            foreach ($postedStore in @(0, 1)) {
                $case = "backend_precise_be${be}_store${postedStore}_mode${mode}"
                $image = Join-Path $Outdir "$case.vvp"
                & iverilog.exe -g2012 -I rtl -s rv32_backend_joint_tb `
                    -P "rv32_backend_joint_tb.BE_WIDTH=$be" `
                    -P "rv32_backend_joint_tb.STORE_BUFFERED_RETIRE=$postedStore" `
                    -P "rv32_backend_joint_tb.COMPLETION_BYPASS=$mode" -o $image `
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
} finally {
    $env:PATH = $savedPath
    Pop-Location
}

param([string]$Outdir = 'D:/CPU2026Tests/indexed_history_20261001')
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
$savedPath=$env:PATH
Push-Location $repoRoot
try {
    $suite=Join-Path $repoRoot '.deps/oss-cad-suite-install/oss-cad-suite'
    $env:PATH="$suite/bin;$suite/lib;$savedPath"
    New-Item -ItemType Directory -Force -Path $Outdir | Out-Null
    foreach($width in 1,2,4) {
        foreach($bits in 1,4,6) {
            $case="predictor_w${width}_h${bits}"
            & iverilog.exe -g2012 -I rtl -s rv32_indexed_history_predictor_tb `
                -P "rv32_indexed_history_predictor_tb.WIDTH=$width" `
                -P "rv32_indexed_history_predictor_tb.HISTORY_BITS=$bits" `
                -o "$Outdir/$case.vvp" rtl/predictor/rv32_branch_predictor.v `
                rtl/predictor/rv32_banked_predictor.v tb/unit/rv32_indexed_history_predictor_tb.v
            if($LASTEXITCODE -ne 0){throw "Compile failed: $case"}
            $result=& vvp.exe -N "$Outdir/$case.vvp"
            $result | Tee-Object -FilePath "$Outdir/$case.log"
            if($LASTEXITCODE -ne 0 -or $result -match 'FAIL|FATAL|ERROR' -or
                -not($result -match '^PASS: indexed history')){throw "Failed: $case"}
        }
        foreach($meta in 0,1) {
            $case="frontend_w${width}_meta${meta}"
            & iverilog.exe -g2012 -I rtl -s rv32_fetch_frontend_tb `
                -P "rv32_fetch_frontend_tb.FE_WIDTH=$width" -P "rv32_fetch_frontend_tb.PREDICTOR_META=$meta" `
                -o "$Outdir/$case.vvp" rtl/frontend/rv32_fetch_frontend.v tb/unit/rv32_fetch_frontend_tb.v
            if($LASTEXITCODE -ne 0){throw "Compile failed: $case"}
            $result=& vvp.exe -N "$Outdir/$case.vvp"
            $result | Tee-Object -FilePath "$Outdir/$case.log"
            if($LASTEXITCODE -ne 0 -or $result -match 'FAIL|FATAL|ERROR' -or
                -not($result -match '^PASS: A-04')){throw "Failed: $case"}
        }
        foreach($completion in 0,2) {
            foreach($store in 0,1) {
                $case="backend_w${width}_cpl${completion}_store${store}"
                & iverilog.exe -g2012 -I rtl -s rv32_backend_joint_tb `
                    -P "rv32_backend_joint_tb.BE_WIDTH=$width" -P rv32_backend_joint_tb.PREDICTOR_META=1 `
                    -P "rv32_backend_joint_tb.COMPLETION_BYPASS=$completion" `
                    -P "rv32_backend_joint_tb.STORE_BUFFERED_RETIRE=$store" `
                    -o "$Outdir/$case.vvp" -c rtl/filelist.f `
                    .deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv tb/unit/rv32_backend_joint_tb.v `
                    2> "$Outdir/$case.compile.log"
                if($LASTEXITCODE -ne 0){throw "Compile failed: $case"}
                $result=& vvp.exe -N "$Outdir/$case.vvp"
                $result | Tee-Object -FilePath "$Outdir/$case.log"
                if($LASTEXITCODE -ne 0 -or $result -match 'FAIL|FATAL|ERROR' -or
                    -not($result -match '^PASS: B-09')){throw "Failed: $case"}
            }
        }
    }
} finally {
    $env:PATH=$savedPath
    Pop-Location
}

param([string]$Outdir = 'D:/CPU2026Tests/direct_branch_20261001')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$savedPath = $env:PATH
Push-Location $repoRoot
try {
    $suite = Join-Path $repoRoot '.deps/oss-cad-suite-install/oss-cad-suite'
    $env:PATH = "$suite/bin;$suite/lib;$savedPath"
    New-Item -ItemType Directory -Force -Path $Outdir | Out-Null
    foreach ($bank in @(0, 1, 2)) {
        $case = "bank${bank}"
        $image = Join-Path $Outdir "$case.vvp"
        & iverilog.exe -g2012 -I rtl -s rv32_direct_branch_predictor_tb `
            -P "rv32_direct_branch_predictor_tb.BANK_BITS=$bank" -o $image `
            rtl/predictor/rv32_branch_predictor.v tb/unit/rv32_direct_branch_predictor_tb.v
        if ($LASTEXITCODE -ne 0) { throw "Compile failed: $case" }
        $result = & vvp.exe -N $image
        $result | Tee-Object -FilePath (Join-Path $Outdir "$case.log")
        if ($LASTEXITCODE -ne 0 -or $result -match 'FAIL|ERROR|FATAL' -or
            -not ($result -match '^PASS: direct conditional target')) { throw "Regression failed: $case" }
    }
    foreach ($direct in @(0, 1)) {
        foreach ($width in @(1, 2, 4)) {
            $case = "banked_w${width}_d${direct}"
            $image = Join-Path $Outdir "$case.vvp"
            & iverilog.exe -g2012 -I rtl -s rv32_banked_predictor_tb `
                -P "rv32_banked_predictor_tb.WIDTH=$width" `
                -P "rv32_banked_predictor_tb.DIRECT_BRANCH_TARGET=$direct" -o $image `
                rtl/predictor/rv32_branch_predictor.v rtl/predictor/rv32_banked_predictor.v `
                tb/unit/rv32_banked_predictor_tb.v
            if ($LASTEXITCODE -ne 0) { throw "Compile failed: $case" }
            $result = & vvp.exe -N $image
            $result | Tee-Object -FilePath (Join-Path $Outdir "$case.log")
            if ($LASTEXITCODE -ne 0 -or $result -match 'FAIL|ERROR|FATAL' -or
                -not ($result -match '^PASS: banked predictor')) { throw "Regression failed: $case" }
        }
    }
} finally {
    $env:PATH = $savedPath
    Pop-Location
}

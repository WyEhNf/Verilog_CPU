$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$savedToolPath = $env:PATH
Push-Location $repoRoot
try {
    $env:PATH = "$repoRoot/.deps/oss-cad-suite-install/oss-cad-suite/bin;$repoRoot/.deps/oss-cad-suite-install/oss-cad-suite/lib;$env:PATH"
    foreach ($phys in @(32, 48, 96)) {
        foreach ($width in @(1, 2, 4)) {
            foreach ($entries in @(8, 16, 64)) {
                $output = "build/rob_reclaim_diff_w${width}_e${entries}_p${phys}.vvp"
                & iverilog.exe -g2012 -I rtl -s rv32_rob_reclaim_tb `
                    -P "rv32_rob_reclaim_tb.BE_WIDTH=$width" `
                    -P "rv32_rob_reclaim_tb.ENTRIES=$entries" `
                    -P "rv32_rob_reclaim_tb.PHYS_REGS=$phys" `
                    -o $output rtl/backend/rv32_rob.v tb/unit/rv32_rob_reclaim_tb.v
                if ($LASTEXITCODE -ne 0) { throw 'Compile failed' }
                $result = & vvp.exe -N $output
                $result
                if ($LASTEXITCODE -ne 0 -or $result -match 'FAIL|FATAL' -or -not ($result -match 'PASS')) {
                    throw 'Reclaim differential test failed'
                }
            }
        }
    }
    foreach ($width in @(1, 2, 4)) {
        foreach ($entries in @(8, 16, 32)) {
            $output = "build/rob_reclaim_w${width}_e${entries}.vvp"
            & iverilog.exe -g2005 -I rtl -s rv32_rob_tb `
                -P "rv32_rob_tb.BE_WIDTH=$width" -P "rv32_rob_tb.ROB_ENTRIES=$entries" `
                -o $output rtl/backend/rv32_rob.v tb/unit/rv32_rob_tb.v
            if ($LASTEXITCODE -ne 0) { throw 'Compile failed' }
            $result = & vvp.exe -N $output
            $result
            if ($LASTEXITCODE -ne 0 -or $result -match 'FAIL|FATAL' -or -not ($result -match 'PASS')) {
                throw 'ROB directed test failed'
            }
        }
    }
} finally {
    $env:PATH = $savedToolPath
    Pop-Location
}

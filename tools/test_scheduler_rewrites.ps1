$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
$savedToolPath = $env:PATH
try {
    $env:PATH = "$repoRoot/.deps/oss-cad-suite-install/oss-cad-suite/bin;$repoRoot/.deps/oss-cad-suite-install/oss-cad-suite/lib;$env:PATH"
    function Run-Check($top, $rtl, $parameters, $name) {
        $output = "build/$name.vvp"
        & iverilog.exe -g2012 -I rtl -s $top @parameters -o $output $rtl "tb/unit/$top.v"
        if ($LASTEXITCODE -ne 0) { throw "Compile failed: $name" }
        $result = & vvp.exe -N $output
        $result
        if ($LASTEXITCODE -ne 0 -or $result -match 'FAIL|FATAL' -or -not ($result -match 'PASS')) {
            throw "Test failed: $name"
        }
    }
    foreach ($width in @(1, 2, 4)) {
        foreach ($entries in @(1, 3, 4, 8, 16)) {
            Run-Check 'rv32_rs_rank_tb' 'rtl/backend/rv32_reservation_station.v' @(
                '-P', "rv32_rs_rank_tb.BE_WIDTH=$width", '-P', "rv32_rs_rank_tb.ENTRIES=$entries"
            ) "rs_diff_w${width}_e${entries}"
        }
        foreach ($entries in @(4, 8, 16)) {
            Run-Check 'rv32_reservation_station_tb' 'rtl/backend/rv32_reservation_station.v' @(
                '-P', "rv32_reservation_station_tb.BE_WIDTH=$width", '-P', "rv32_reservation_station_tb.ENTRIES=$entries"
            ) "rs_rank_w${width}_e${entries}"
        }
        Run-Check 'rv32_lsq_tb' 'rtl/backend/rv32_lsq.v' @(
            '-P', "rv32_lsq_tb.BE_WIDTH=$width"
        ) "lsq_static_w$width"
    }
    foreach ($entries in @(1, 2, 4, 8, 16)) {
        Run-Check 'rv32_lsq_hazard_tb' 'rtl/backend/rv32_lsq.v' @(
            '-P', "rv32_lsq_hazard_tb.ENTRIES=$entries"
        ) "lsq_hazard_e$entries"
    }
} finally {
    $env:PATH = $savedToolPath
    Pop-Location
}

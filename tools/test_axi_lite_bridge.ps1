$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$previousPath = $env:PATH
Push-Location $repoRoot
try {
    $env:PATH = "$repoRoot/.deps/oss-cad-suite-install/oss-cad-suite/bin;$repoRoot/.deps/oss-cad-suite-install/oss-cad-suite/lib;$previousPath"
    & iverilog.exe -g2012 -s rv32_axi_lite_bridge_tb -o build/axi_lite_bridge.vvp `
        rtl/course/rv32_axi_lite_bridge.v tb/unit/rv32_axi_lite_bridge_tb.v
    if ($LASTEXITCODE -ne 0) { throw 'AXI bridge compile failed' }
    $result = & vvp.exe -N build/axi_lite_bridge.vvp
    $result
    if ($LASTEXITCODE -ne 0 -or $result -match '^(FAIL|ERROR|FATAL):' -or -not ($result -match 'PASS')) {
        throw 'AXI bridge protocol regression failed'
    }
} finally {
    $env:PATH = $previousPath
    Pop-Location
}

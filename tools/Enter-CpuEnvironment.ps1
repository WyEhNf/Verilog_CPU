# Dot-source this file to activate the project-local native Windows toolchain.
$cpuProjectRoot = Split-Path -Parent $PSScriptRoot
$cpuDependencies = Join-Path $cpuProjectRoot '.deps'
$cpuToolRoot = Join-Path $cpuDependencies 'course-tools'
$cpuRuntime = Join-Path $cpuDependencies 'msys64/mingw64/bin'
$cpuBuildTools = Join-Path $cpuDependencies 'msys64/usr/bin'
$cpuRequired = @(
    "$cpuRuntime/python.exe", "$cpuRuntime/g++.exe", "$cpuBuildTools/make.exe",
    "$cpuToolRoot/verilator/bin/verilator_bin.exe", "$cpuToolRoot/yosys/bin/yosys.exe",
    "$cpuToolRoot/yosys/bin/yosys-abc.exe", "$cpuToolRoot/opensta/bin/sta.exe"
)
foreach ($cpuExecutable in $cpuRequired) {
    if (-not (Test-Path -LiteralPath $cpuExecutable)) {
        throw "CPU environment is incomplete: $cpuExecutable"
    }
}
$cpuPaths = @(
    "$cpuDependencies/bin", "$cpuToolRoot/yosys/bin", "$cpuToolRoot/opensta/bin",
    "$cpuToolRoot/verilator/bin", $cpuRuntime, $cpuBuildTools, "$cpuDependencies/msys64/ucrt64/bin"
)
$env:PATH = ($cpuPaths -join ';') + ';' + $env:PATH
$env:VERILATOR_ROOT = "$cpuToolRoot/verilator/share/verilator".Replace('\', '/')
$env:CPU2026_REAL_VERILATOR = "$cpuToolRoot/verilator/bin/verilator_bin.exe".Replace('\', '/')
$env:CPU2026_BUILD_APPIMAGE = ''
$env:CPU2026_ASAP7_LIB = "$cpuToolRoot/asap7/lib".Replace('\', '/')
$env:CPU2026_HOST_CONFIG = "$cpuDependencies/course_windows.local.json".Replace('\', '/')
$env:MAKE = "$cpuBuildTools/make.exe".Replace('\', '/')
$env:SHELL = "$cpuBuildTools/sh.exe".Replace('\', '/')
$env:CPU2026_PGO = '0'
$env:CPU2026_STABLE_MDU = '0'
$env:CPU2026_ICO_PAIR = '0'
$env:CPU2026_WORD_SIM = '1'
$env:CPU2026_UNROLL_STMTS = '1000000'
$env:CPU2026_TRACE_DEPTH = '1'
Write-Host "CPU Windows environment ready: $cpuToolRoot"

param(
    [string]$Mdir = 'build/vlt/course_axi_p4_r32p64_ctx',
    [int]$BuildJobs = 2,
    [string]$CompilerBin = 'E:/mingw64/bin',
    [hashtable]$Parameters = @{}
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$savedPath = $env:PATH
$savedShell = $env:SHELL
$savedVerilatorRoot = $env:VERILATOR_ROOT
Push-Location $repoRoot
try {
    $suite = Join-Path $repoRoot '.deps/oss-cad-suite-install/oss-cad-suite'
    $framework = Join-Path $repoRoot '.deps/RISC-V-CPU-2026'
    $gitExecutable = (Get-Command git.exe).Source
    $gitRoot = Split-Path -Parent (Split-Path -Parent $gitExecutable)
    $gitBin = Join-Path $gitRoot 'bin'
    $gitUsrBin = Join-Path $gitRoot 'usr/bin'
    $env:PATH = "$CompilerBin;$gitUsrBin;$gitBin;$suite/bin;$suite/lib;$savedPath"
    $env:SHELL = Join-Path $gitBin 'sh.exe'
    $env:VERILATOR_ROOT = Join-Path $suite 'share/verilator'
    $filelist = (Resolve-Path verilog/filelist.f).Path
    $sources = @(Get-Content -LiteralPath $filelist | ForEach-Object {
        $entry = ($_ -split '#', 2)[0].Trim()
        if ($entry) { (Resolve-Path -LiteralPath (Join-Path (Split-Path $filelist) $entry)).Path }
    })
    $sources += Join-Path $framework 'scripts/ram/sram_fakeram.sv'
    # Allow an absolute artifact directory on a drive with sufficient space.
    # Sources and frozen hashes still belong to the same project checkout.
    $directory = [IO.Path]::GetFullPath($(if ([IO.Path]::IsPathRooted($Mdir)) {
        $Mdir
    } else { Join-Path $repoRoot $Mdir }))
    if (Test-Path -LiteralPath (Join-Path $directory 'build_manifest.json')) {
        throw 'This output contains a frozen build; choose a new Mdir'
    }
    $parameterNames = @([regex]::Matches(
        [IO.File]::ReadAllText((Join-Path $repoRoot 'rtl/course/student_top.v')),
        '\b([A-Z][A-Z0-9_]*)\s*=\s*[0-9]+') | ForEach-Object { $_.Groups[1].Value })
    $parameterArguments = @()
    $parameterOverrides = [ordered]@{}
    foreach ($name in ($Parameters.Keys | Sort-Object)) {
        if ($name -cnotin $parameterNames -or "$($Parameters[$name])" -notmatch '^[0-9]+$') {
            throw "Unsupported RTL parameter or non-integer value: $name"
        }
        $value = [int]$Parameters[$name]
        $parameterArguments += "-G$name=$value"
        $parameterOverrides[$name] = $value
    }
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $originalDriver = Join-Path $framework 'scripts/sim.cpp'
    $driverText = [IO.File]::ReadAllText($originalDriver)
    $anchor = '        top.final();'
    if ([regex]::Matches($driverText, [regex]::Escape($anchor)).Count -ne 1) {
        throw 'Official driver changed: expected exactly one observation insertion point'
    }
    # Generated copy differs by ONE read-only counter print. The official
    # memory queues, 32-bit bus, edge sampling and exit-B handshake stay exact.
    $observer = '        std::cerr << "CPU2026 instret=" << top.debug_instret << std::endl;'
    $observedText = $driverText.Replace($anchor, "$anchor`n$observer")
    $observedDriver = Join-Path $directory 'sim_observed.cpp'
    [IO.File]::WriteAllText($observedDriver, $observedText, [Text.UTF8Encoding]::new($false))
    $frozenInputs = $sources + @($filelist, $originalDriver, $PSCommandPath) + @(
        Get-ChildItem rtl -Recurse -Filter '*.vh' -File | ForEach-Object { $_.FullName }
    )
    $hashes = [ordered]@{}
    foreach ($inputFile in ($frozenInputs | Sort-Object -Unique)) {
        $relative = (Resolve-Path -LiteralPath $inputFile -Relative) -replace '^\.\\', ''
        $hashes[$relative.Replace('\', '/')] = (Get-FileHash -LiteralPath $inputFile -Algorithm SHA256).Hash
    }
    $arguments = @('--cc', '--exe', '--build', '--trace', '--assert', '-Wno-fatal',
        '-Irtl', '--top-module', 'student_top', '--Mdir', $directory,
        '-o', 'sim_course', '-j', "$BuildJobs", '-CFLAGS', '-std=c++17 -DVL_TIME_CONTEXT') + $parameterArguments + $sources + @($observedDriver)
    & (Join-Path $suite 'bin/verilator_bin.exe') @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Course AXI Verilator build failed' }
    foreach ($entry in $hashes.Keys) {
        if ((Get-FileHash -LiteralPath (Join-Path $repoRoot $entry) -Algorithm SHA256).Hash -ne $hashes[$entry]) {
            throw "Source changed during course build: $entry"
        }
    }
    $executable = Join-Path $directory 'sim_course.exe'
    if (-not (Test-Path -LiteralPath $executable)) { throw 'Course simulator executable missing' }
    [ordered]@{
        format = 'course-axi-frozen-build-v1'
        configuration = $(if ($Parameters.Count) { 'student_top source defaults plus explicit -G overrides' }
                          else { 'student_top source defaults; no -G overrides' })
        parameter_overrides = $parameterOverrides
        compiler_flags = '-std=c++17 -DVL_TIME_CONTEXT (use the explicit VerilatedContext time already driven by official sim.cpp)'
        source_sha256 = $hashes
        executable = $executable
        executable_sha256 = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash
        generated_driver = $observedDriver
        generated_driver_sha256 = (Get-FileHash -LiteralPath $observedDriver -Algorithm SHA256).Hash
        driver_change = 'exactly one read-only debug_instret print after top.final(); no memory or cycle changes'
        external_memory = 'official sim.cpp: shared AXI4-Lite 32-bit AR/R and AW/W/B, FIFO depth16, latency passed at runtime'
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $directory 'build_manifest.json') -Encoding utf8
} finally {
    $env:PATH = $savedPath
    $env:SHELL = $savedShell
    $env:VERILATOR_ROOT = $savedVerilatorRoot
    Pop-Location
}

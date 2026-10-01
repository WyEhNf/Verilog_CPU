param(
    [string]$Mdir = 'build/vlt/course_axi_split',
    [int]$BuildJobs = 1,
    [string]$CompilerBin = 'E:/mingw64/bin',
    [hashtable]$Parameters = @{}
)
$ErrorActionPreference = 'Stop'
# Keep the original builder immutable for candidates already frozen with it.
# This changes host C++ grouping only: no RTL, bus, memory or cycle semantics.
$repoRoot = Split-Path -Parent $PSScriptRoot
$savedPath = $env:PATH
$savedShell = $env:SHELL
$savedVerilatorRoot = $env:VERILATOR_ROOT
$savedMakeFlags = $env:MAKEFLAGS
$savedOptFast = $env:OPT_FAST
$savedOptSlow = $env:OPT_SLOW
Push-Location $repoRoot
try {
    if ($BuildJobs -lt 1) { throw 'BuildJobs must be positive' }
    $suite = Join-Path $repoRoot '.deps/oss-cad-suite-install/oss-cad-suite'
    $framework = Join-Path $repoRoot '.deps/RISC-V-CPU-2026'
    $gitExecutable = (Get-Command git.exe).Source
    $gitRoot = Split-Path -Parent (Split-Path -Parent $gitExecutable)
    $gitBin = Join-Path $gitRoot 'bin'
    $gitUsrBin = Join-Path $gitRoot 'usr/bin'
    $env:PATH = "$CompilerBin;$gitUsrBin;$gitBin;$suite/bin;$suite/lib;$savedPath"
    $env:SHELL = Join-Path $gitBin 'sh.exe'
    $env:VERILATOR_ROOT = Join-Path $suite 'share/verilator'
    $env:MAKEFLAGS = '-e'
    $env:OPT_FAST = '-Os'
    $env:OPT_SLOW = '-Os'
    $filelist = (Resolve-Path verilog/filelist.f).Path
    $sources = @(Get-Content -LiteralPath $filelist | ForEach-Object {
        $entry = ($_ -split '#', 2)[0].Trim()
        if ($entry) { (Resolve-Path -LiteralPath (Join-Path (Split-Path $filelist) $entry)).Path }
    })
    $sources += Join-Path $framework 'scripts/ram/sram_fakeram.sv'
    $directory = [IO.Path]::GetFullPath($(if ([IO.Path]::IsPathRooted($Mdir)) {
        $Mdir
    } else { Join-Path $repoRoot $Mdir }))
    if (Test-Path -LiteralPath $directory) {
        throw 'Split builds require a fresh Mdir; previous artifacts are preserved'
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
    New-Item -ItemType Directory -Path $directory | Out-Null
    $originalDriver = Join-Path $framework 'scripts/sim.cpp'
    $driverText = [IO.File]::ReadAllText($originalDriver)
    $anchor = '        top.final();'
    if ([regex]::Matches($driverText, [regex]::Escape($anchor)).Count -ne 1) {
        throw 'Official driver changed: expected exactly one observation insertion point'
    }
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
    # Verilator defaults output grouping to the build job count. Explicitly
    # disable it so -j1 does not merge the large ROB model into one giant TU.
    $arguments = @('--cc', '--exe', '--build', '--trace', '--assert', '-Wno-fatal',
        '--output-groups', '0', '--output-split', '1000', '--output-split-cfuncs', '1000',
        '-Irtl', '--top-module', 'student_top', '--Mdir', $directory,
        '-o', 'sim_course', '-j', "$BuildJobs", '-CFLAGS', '-std=c++17 -DVL_TIME_CONTEXT') + $parameterArguments + $sources + @($observedDriver)
    & (Join-Path $suite 'bin/verilator_bin.exe') @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Split course AXI Verilator build failed' }
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
        compiler_flags = '-std=c++17 -DVL_TIME_CONTEXT (official explicit VerilatedContext time)'
        host_compilation = [ordered]@{
            verilator_output_groups = 0
            verilator_output_split = 1000
            verilator_output_split_cfuncs = 1000
            build_jobs = $BuildJobs
            model_opt_fast = '-Os'
            model_opt_slow = '-Os'
            makeflags = '-e'
            hardware_change = $false
            arguments = $arguments
        }
        source_sha256 = $hashes
        executable = $executable
        executable_sha256 = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash
        generated_driver = $observedDriver
        generated_driver_sha256 = (Get-FileHash -LiteralPath $observedDriver -Algorithm SHA256).Hash
        driver_change = 'exactly one read-only debug_instret print after top.final(); no memory or cycle changes'
        external_memory = 'official sim.cpp: shared AXI4-Lite 32-bit AR/R and AW/W/B, FIFO depth16, latency passed at runtime'
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $directory 'build_manifest.json') -Encoding utf8
} finally {
    $env:PATH = $savedPath
    $env:SHELL = $savedShell
    $env:VERILATOR_ROOT = $savedVerilatorRoot
    $env:MAKEFLAGS = $savedMakeFlags
    $env:OPT_FAST = $savedOptFast
    $env:OPT_SLOW = $savedOptSlow
    Pop-Location
}

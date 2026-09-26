param(
    [Parameter(Mandatory = $true)][string]$Executable,
    [string]$ToolchainBin = "E:/Verilog_cpu/.deps/riscv-toolchain-install/xpack-riscv-none-elf-gcc-15.2.0-1/bin",
    [string]$HostCc = "E:/mingw64/bin/gcc.exe",
    [switch]$IncludePi,
    [int]$ExpectedIOutstanding = 16,
    [int]$ExpectedDOutstanding = 8,
    [ValidateRange(1, 268435456)][int]$MemorySizeBytes = 268435456,
    [string]$Report = "build/cpu2026/simulator_mmio_report.json"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$previousPrefix = $env:RISCV_PREFIX
Push-Location $repoRoot
try {
    $executablePath = (Resolve-Path -LiteralPath $Executable).Path
    $hostCcPath = (Resolve-Path -LiteralPath $HostCc).Path
    $env:RISCV_PREFIX = (Join-Path $ToolchainBin "riscv-none-elf-")
    $rows = @(Get-Content tests/manifest |
        Where-Object { $_.Trim() -ne "" -and -not $_.Trim().StartsWith("#") })
    if ($rows.Count -ne 18) { throw "Expected 18 simulator cases; got $($rows.Count)" }
    if (-not $IncludePi) {
        $rows = @($rows | Where-Object { -not $_.StartsWith("pi,") })
    }
    New-Item -ItemType Directory -Force build/cpu2026/simulator_host | Out-Null
    $results = @()
    foreach ($row in $rows) {
        $fields = $row.Split(",")
        if ($fields.Count -ne 4) { throw "Invalid manifest row: $row" }
        $name = $fields[0].Trim()
        $expectedLow8 = [int]$fields[1]
        $maxCycles = [int]$fields[2]
        $source = "RISC-V-CPU-Simulator/testcases/$name.c"
        $hostObject = "build/cpu2026/simulator_host/$name.o"
        $hostExecutable = "build/cpu2026/simulator_host/$name.exe"
        $imageDir = "build/cpu2026/simulator_mmio/$name"

        & $hostCcPath -O2 -Dmain=cpu_main -c $source -o $hostObject
        if ($LASTEXITCODE -ne 0) { throw "Host reference compile failed: $name" }
        & $hostCcPath $hostObject tools/host_full_return.c -o $hostExecutable
        if ($LASTEXITCODE -ne 0) { throw "Host reference link failed: $name" }
        $referenceOutput = @(& $hostExecutable)
        if ($LASTEXITCODE -ne 0 -or $referenceOutput.Count -ne 1) {
            throw "Host reference execution failed: $name"
        }
        $expectedFull = [int]$referenceOutput[0].Trim()
        if (($expectedFull -band 255) -ne $expectedLow8) {
            throw "Host full return disagrees with legacy low-8-bit manifest: $name"
        }

        $buildOutput = @(& python tools/make_image.py $source --arch rv32im `
            --exit-protocol mmio --memory-size $MemorySizeBytes --out-dir $imageDir 2>&1)
        if ($LASTEXITCODE -ne 0) {
            $buildOutput | Select-Object -Last 20
            throw "RISC-V image build failed: $name"
        }
        $runOutput = @(& $executablePath "+IMAGE=$imageDir/$name.image" `
            "+TEST=$name" "+EXPECTED=$expectedFull" "+MAX_CYCLES=$maxCycles" `
            "+MAX_NO_RETIRE_CYCLES=1000000" "+CHECK_LSQ" 2>&1)
        $exitCode = $LASTEXITCODE
        $runText = $runOutput -join [Environment]::NewLine
        $memoryPattern = "EVAL_MEMORY: unified=1 latency=20 i_outstanding=$ExpectedIOutstanding d_outstanding=$ExpectedDOutstanding line_bytes=16"
        if ($exitCode -ne 0 -or -not $runText.Contains($memoryPattern) -or
            $runText -notmatch "PASS: JOIN-02 image=$name ") {
            $runOutput | Select-Object -Last 25
            throw "CPU MMIO source regression failed: $name (full return $expectedFull)"
        }
        $passLine = $runOutput | Select-String "PASS: JOIN-02 image=$name " | Select-Object -First 1
        if ($passLine.Line -notmatch "return=(-?\d+) cycles=(\d+) instret=(\d+)") {
            throw "Missing MMIO return/cycle metrics: $name"
        }
        $actualReturn = [long]$Matches[1]
        $cycles = [long]$Matches[2]
        $instret = [long]$Matches[3]
        if (($actualReturn -band 0xffffffffL) -ne ($expectedFull -band 0xffffffffL)) {
            throw "Full 32-bit MMIO return mismatch: $name"
        }
        $results += [ordered]@{
            name = $name; status = "passed"; expected_signed = $expectedFull
            return = $actualReturn; cycles = $cycles; instret = $instret
        }
        Write-Host "$($passLine.Line) expected_signed=$expectedFull"
    }
    $reportPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $Report))
    New-Item -ItemType Directory -Force (Split-Path -Parent $reportPath) | Out-Null
    [ordered]@{
        format = "simulator-source-mmio-v1"
        executable = $executablePath
        image_memory_size_bytes = $MemorySizeBytes
        memory_latency_cycles = 20
        i_outstanding = $ExpectedIOutstanding; d_outstanding = $ExpectedDOutstanding
        pi_included = [bool]$IncludePi
        results = $results
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding utf8
    Write-Host "PASS: simulator source MMIO cases=$($rows.Count)"
} finally {
    $env:RISCV_PREFIX = $previousPrefix
    Pop-Location
}

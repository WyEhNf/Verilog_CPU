param(
    [Parameter(Mandatory = $true)][string]$Executable,
    [string]$ToolchainBin = 'E:/Verilog_cpu/.deps/riscv-toolchain-install/xpack-riscv-none-elf-gcc-15.2.0-1/bin'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$oldPrefix = $env:RISCV_PREFIX
Push-Location $repoRoot
try {
    $executablePath = (Resolve-Path -LiteralPath $Executable).Path
    $toolchainPath = (Resolve-Path -LiteralPath $ToolchainBin).Path
    $env:RISCV_PREFIX = Join-Path $toolchainPath 'riscv-none-elf-'
    $imageDir = 'build/images/ram_256m_last_word'
    $buildOutput = @(& python tools/make_image.py `
        tests/programs/ram_256m_last_word.c --arch rv32im `
        --exit-protocol mmio --memory-size 0x10000000 --out-dir $imageDir 2>&1)
    if ($LASTEXITCODE -ne 0) {
        $buildOutput | Select-Object -Last 20
        throw '256 MiB boundary image build failed'
    }

    $runOutput = @(& $executablePath `
        "+IMAGE=$imageDir/ram_256m_last_word.image" `
        '+TEST=ram-256m-last-word' '+EXPECTED=598' `
        '+MAX_CYCLES=100000' '+CHECK_LSQ' '+TRACE' 2>&1)
    $exitCode = $LASTEXITCODE
    $runText = $runOutput -join [Environment]::NewLine
    foreach ($required in @(
        'EVAL_MEMORY: unified=1 latency=20 i_outstanding=16 d_outstanding=8 line_bytes=16',
        'PASS: JOIN-02 image=ram-256m-last-word return=598',
        'mem-d write=1 line=0ffffff0',
        'dcache load-resp'
    )) {
        if (-not $runText.Contains($required)) {
            $runOutput | Select-Object -Last 30
            throw "256 MiB boundary test missing: $required"
        }
    }
    if ($exitCode -ne 0 -or $runText -notmatch 'PERF_CACHE: .*d_wb=([1-9][0-9]*)') {
        $runOutput | Select-Object -Last 30
        throw '256 MiB boundary test did not complete a dirty cache writeback'
    }
    $runOutput | Where-Object {
        $_ -match '^(PASS:|PERF_CACHE:)' -or
        $_ -match 'mem-d write=1 line=0ffffff0' -or
        $_ -match 'dcache load-resp.*addr=0ffffffc'
    }
} finally {
    $env:RISCV_PREFIX = $oldPrefix
    Pop-Location
}

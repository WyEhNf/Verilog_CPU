param(
    [string]$ToolchainBin = "E:/Verilog_cpu/.deps/riscv-toolchain-install/xpack-riscv-none-elf-gcc-15.2.0-1/bin",
    [string]$CadBin = "E:/Verilog_cpu/.deps/oss-cad-suite-install/oss-cad-suite/bin",
    [string]$CadLib = "E:/Verilog_cpu/.deps/oss-cad-suite-install/oss-cad-suite/lib",
    [int]$RobEntries = 64,
    [int]$PhysRegs = 96,
    [int]$LsqEntries = 16,
    [int]$DcacheLines = 512,
    [string]$Executable = ""
)

$ErrorActionPreference = "Stop"
$oldPath = $env:PATH
$oldPrefix = $env:RISCV_PREFIX
try {
    $env:PATH = "$CadBin;$CadLib;$oldPath"
    $env:RISCV_PREFIX = (Join-Path $ToolchainBin "riscv-none-elf-")
    $cases = @(
        @{ Name = "vmul"; Expected = 8 },
        @{ Name = "vvadd"; Expected = 72 },
        @{ Name = "accumulate"; Expected = 5050 },
        @{ Name = "halfword_smoke"; Expected = 0 },
        @{ Name = "m_isa_smoke"; Expected = 90 }
    )
    $rtl = @(Get-Content rtl/filelist.f | Where-Object { $_ -and ($_ -notmatch '^\s*#') })
    $sources = $rtl + @("tb/models/rv32im_memory_model.v", "tb/integration/cpu_core_image_tb.v")
    $parameters = @(
        "-P", "cpu_core_image_tb.FE_WIDTH=4",
        "-P", "cpu_core_image_tb.BE_WIDTH=4",
        "-P", "cpu_core_image_tb.PHYS_REGS=$PhysRegs",
        "-P", "cpu_core_image_tb.ROB_ENTRIES=$RobEntries",
        "-P", "cpu_core_image_tb.RS_ENTRIES=16",
        "-P", "cpu_core_image_tb.LSQ_ENTRIES=$LsqEntries",
        "-P", "cpu_core_image_tb.INT_ISSUE_WIDTH=4",
        "-P", "cpu_core_image_tb.CDB_WIDTH=4",
        "-P", "cpu_core_image_tb.DCACHE_LINES=$DcacheLines",
        "-P", "cpu_core_image_tb.DCACHE_WAYS=2",
        "-P", "cpu_core_image_tb.DCACHE_INDEX_HASH=1",
        "-P", "cpu_core_image_tb.CHECKPOINT_IMPL=1",
        "-P", "cpu_core_image_tb.MEMORY_LATENCY=20",
        "-P", "cpu_core_image_tb.LEGACY_SENTINEL_HALT=0"
    )
    $output = "build/cpu2026/final_basic.vvp"
    # With an existing executable, test that exact frozen CPU configuration;
    # the hardware sizing options above apply only to the Icarus build mode.
    if ($Executable) {
        $executablePath = (Resolve-Path -LiteralPath $Executable).Path
    } else {
        & iverilog -g2012 -I rtl -s cpu_core_image_tb @parameters -o $output @sources
        if ($LASTEXITCODE -ne 0) { throw "Icarus P4 final basic compile failed" }
    }

    foreach ($case in $cases) {
        $imageDir = "build/cpu2026/final_basic/$($case.Name)"
        & python tools/make_image.py "tests/programs/$($case.Name).c" --arch rv32im `
            --exit-protocol mmio --memory-size 0x10000000 --out-dir $imageDir
        if ($LASTEXITCODE -ne 0) { throw "Image build failed: $($case.Name)" }
        $runArgs = @("+IMAGE=$imageDir/$($case.Name).image", "+TEST=$($case.Name)",
                     "+EXPECTED=$($case.Expected)", "+MAX_CYCLES=1000000", "+CHECK_LSQ")
        $runOutput = if ($Executable) { @(& $executablePath @runArgs 2>&1) }
                     else { @(& vvp $output @runArgs 2>&1) }
        $runOutput
        if ($LASTEXITCODE -ne 0 -or
            -not ($runOutput -match "PASS: JOIN-02 image=$($case.Name) return=$($case.Expected) ")) {
            throw "CPU basic program failed: $($case.Name)"
        }
    }
    Write-Host "PASS: final basic MMIO programs=$($cases.Count)"
}
finally {
    $env:PATH = $oldPath
    $env:RISCV_PREFIX = $oldPrefix
}

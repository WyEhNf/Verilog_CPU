param(
    [string]$ToolchainBin = "E:/Verilog_cpu/.deps/riscv-toolchain-install/xpack-riscv-none-elf-gcc-15.2.0-1/bin",
    [string]$CadBin = "E:/Verilog_cpu/.deps/oss-cad-suite-install/oss-cad-suite/bin",
    [string]$CadLib = "E:/Verilog_cpu/.deps/oss-cad-suite-install/oss-cad-suite/lib"
)

$ErrorActionPreference = "Stop"
$oldPath = $env:PATH
$oldPrefix = $env:RISCV_PREFIX
try {
    $env:PATH = "$CadBin;$CadLib;$oldPath"
    $env:RISCV_PREFIX = (Join-Path $ToolchainBin "riscv-none-elf-")
    $imageDir = "build/cpu2026/final_mmio_smoke"
    & python tools/make_image.py tests/programs/mmio_exit.c --arch rv32im `
        --exit-protocol mmio --memory-size 0x10000000 --out-dir $imageDir
    if ($LASTEXITCODE -ne 0) { throw "MMIO image build failed" }

    $rtl = @(Get-Content rtl/filelist.f | Where-Object { $_ -and ($_ -notmatch '^\s*#') })
    $sources = $rtl + @("tb/models/rv32im_memory_model.v", "tb/integration/cpu_core_image_tb.v")
    foreach ($profile in @("p2", "p4_assoc2")) {
        $output = "build/cpu2026/mmio_$profile.vvp"
        $parameters = @(
            "-P", "cpu_core_image_tb.LEGACY_SENTINEL_HALT=0",
            "-P", "cpu_core_image_tb.MEMORY_LATENCY=20"
        )
        if ($profile -eq "p4_assoc2") {
            $parameters += @(
                "-P", "cpu_core_image_tb.FE_WIDTH=4",
                "-P", "cpu_core_image_tb.BE_WIDTH=4",
                "-P", "cpu_core_image_tb.PHYS_REGS=96",
                "-P", "cpu_core_image_tb.ROB_ENTRIES=64",
                "-P", "cpu_core_image_tb.RS_ENTRIES=16",
                "-P", "cpu_core_image_tb.LSQ_ENTRIES=16",
                "-P", "cpu_core_image_tb.INT_ISSUE_WIDTH=4",
                "-P", "cpu_core_image_tb.CDB_WIDTH=4",
                "-P", "cpu_core_image_tb.DCACHE_LINES=256",
                "-P", "cpu_core_image_tb.DCACHE_WAYS=2"
            )
        }
        & iverilog -g2012 -I rtl -s cpu_core_image_tb @parameters -o $output @sources
        if ($LASTEXITCODE -ne 0) { throw "Icarus compile failed: $profile" }
        & vvp $output "+IMAGE=$imageDir/mmio_exit.image" "+TEST=mmio_$profile" `
            +EXPECTED=305419896 +MAX_CYCLES=10000
        if ($LASTEXITCODE -ne 0) { throw "MMIO simulation failed: $profile" }
    }
}
finally {
    $env:PATH = $oldPath
    $env:RISCV_PREFIX = $oldPrefix
}

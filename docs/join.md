# JOIN-02 single-issue image regression

`cpu_core_image_tb` connects the integrated core to the 50-cycle byte-addressed
memory model. The image is loaded with the memory model's `+IMAGE` argument,
and the testbench checks precise HALT, no architectural error, the manifest
return value, the per-image cycle limit, and a configurable consecutive
no-retirement watchdog. The watchdog defaults to 100,000 cycles and may be
overridden with `+MAX_NO_RETIRE_CYCLES=<cycles>` or the runner's
`-NoRetireCycles` parameter.

The testbench fixes `FE_WIDTH=1` and `BE_WIDTH=1`. JOIN-02 does not qualify
dual-issue or quad-issue configurations.

Run `make join02` to compile the testbench and execute every row in
`tests/manifest`. The runner prints one result per image so a timeout or wrong
return value identifies the failing program directly.

For faster local regression with an existing Verilator binary, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/run_join02.ps1 `
  -Executable build/verilator_join02/Vcpu_core_image_tb.exe `
  -Manifest tests/manifest -ImageRoot RISC-V-CPU-Simulator/testcases
```

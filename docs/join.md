# JOIN-02 单发射镜像回归

`cpu_core_image_tb` 将集成后的核心连接到按字节寻址、延迟为 50 周期的主存模型。镜像通过主存模型的 `+IMAGE` 参数加载。测试平台检查精确 HALT、无架构错误、清单中的返回值、各镜像周期上限，以及可配置的连续无退休监视器。该监视器默认上限为 100,000 周期，可通过 `+MAX_NO_RETIRE_CYCLES=<cycles>` 或运行器的 `-NoRetireCycles` 参数覆盖。

测试平台固定 `FE_WIDTH=1` 和 `BE_WIDTH=1`。JOIN-02 不验收双发射或四发射配置。

运行 `make join02` 编译测试平台，并执行 `tests/manifest` 中的每一项。运行器为每个镜像输出独立结果，便于直接定位超时或返回值错误的程序。

如已有 Verilator 可执行文件，可使用以下命令加快本地回归：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/run_join02.ps1 `
  -Executable build/verilator_join02/Vcpu_core_image_tb.exe `
  -Manifest tests/manifest -ImageRoot RISC-V-CPU-Simulator/testcases
```

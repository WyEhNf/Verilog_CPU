# H-04/S-05 验证与回归契约

`tools/check_commit_trace.py` 是唯一的架构退休 trace 检查入口。输入为 JSON Lines，每条记录必须包含 `cycle`、`lane`、`valid`、`pc`、`inst`、`rd`、`rd_we`、`value`、`is_store`、`store_addr`、`store_mask` 和 `store_data`。只有真正提交的连续 lane 前缀可以有副作用；无效 lane、写 x0、空 store mask、倒退周期、旧 tag 结果和超过 watchdog 的无退休间隔都会被拒绝。

`tools/regression.py` 从 `tests/manifest` 加载全部 18 个外部 `.data` 镜像，检查名称唯一、期望返回值和每项的周期上限，并保留 `build/regression/manifest.json`。没有提供 `CPU_RUNNER` 时，执行回归会明确失败而不会把 manifest 校验伪装成 CPU 通过；`--validate-only` 只用于验证回归基础设施。

成功的整机案例必须满足 `halted=1 && error=0 && return_value==expected`，并且没有触发总周期或连续无退休 watchdog。失败时 runner 保存首个失败案例的 stdout/stderr 和 manifest 报告；波形路径由具体 CPU runner 追加到同一报告。

## C++ reference 逐条差分

`tools/reference_trace.cpp` 是只读参考适配器。它只包含参考仓库公开的
`simulator.h/module_io.h`，并在每周期 evaluate/arbitrate 之后、latch 之前读取
`CycleWires.commit`。`tools/reference_trace.py` 负责发现参考仓库、用 C++20 构建适配器、
生成 JSONL 和按退休顺序比较 RTL CommitRecord；周期号和 lane 位置不参与架构比较。

整机 testbench 使用 `+COMMIT_TRACE=<path>` 输出所有有效退休 lane。典型诊断流程为：

```text
python tools/reference_trace.py --image RISC-V-CPU-Simulator/testcases/naive.data --reference-trace build/reference_trace/naive.reference.jsonl
vvp -N build/cpu_core_image_tb.vvp +IMAGE=RISC-V-CPU-Simulator/testcases/naive.data +TEST=naive +EXPECTED=94 +COMMIT_TRACE=build/reference_trace/naive.rtl.jsonl
python tools/reference_trace.py --reference-trace build/reference_trace/naive.reference.jsonl --rtl-trace build/reference_trace/naive.rtl.jsonl
```

若参考公开 API 或 C++20 编译器不可用，增加 `--optional` 会明确输出 `SKIP` 并返回成功，
不会把跳过伪装成差分通过。返回值、RTL CommitRecord 合法性和 watchdog 仍由原有硬门负责。

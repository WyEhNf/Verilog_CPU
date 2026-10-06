# OJ 提交构建开销优化

日期：2026-10-06。对象：当前 A109 的主机仿真器构建。

默认提交入口已更新；Windows 原生环境完整生成、编译、归档和链接成功，返回码均为 0。本轮没有运行 CPU 程序，没有重新测 IPC、面积或 STA。OJ 的实际编译时限和内存上限仍未取得，不能把本机成功解释为 OJ 已通过。

## 最终构建设置

- 官方 `Makefile`、`scripts/sim.cpp` 和其余官方脚本保持原样，通过允许的 `VERILATOR` 配置选择 `tools/verilator_low_memory.py`。
- 先生成 C++，等待生成进程退出，再用 `make -j1 VM_PARALLEL_BUILDS=1` 编译，避免生成和编译同时占用内存。
- 默认 `--trace-depth 1` 保留顶层 AXI、时钟、复位和诊断信号的波形；官方 `trace()` 接口保留。
- `--protect-ids` 使用固定公开名称种子 `CPU2026-COMPILE-NAMES-V1` 缩短内部 C++ 名称；顶层端口原名不变。生成的 `Vstudent_top__idmap.xml` 保留反向名称映射，原始 RTL 仍完整提交。
- 文件拆分阈值从 2000 调到 8000，减少编译器启动和预编译头加载次数；函数和波形函数阈值保留 2000。
- Verilator 5.020 的 `--comp-limit-parens 32` 把深表达式分解为中间值。常规文件/函数拆分只能在边界切开代码，无法切开单条巨大 RAT 恢复表达式，因此还需要控制表达式深度。
- 保留已验证的 `--unroll-count 1024 --unroll-stmts 1000000`、`--assert` 和 C++ 优化级别：热代码/全局支持代码 `-Os`，冷代码保持官方默认。
- 构建日志分别输出生成与编译阶段的耗时和返回码。

`make CPU2026_TRACE_DEPTH=0 CPU2026_COMPACT_IDS=0` 可恢复完整内部波形和原始内部名称。完整追踪会明显增加代码量和构建耗时。设置 `VERILATOR` 为真实工具路径会绕过本包装器。

## 代码量与实际构建结果

代码大小按十进制 MB（1 MB = 1,000,000 字节）计算；内存按 MiB（1 MiB = 1,048,576 字节）计算。

| 指标 | 既有完整内部追踪构建 | 最终默认构建 |
|---|---:|---:|
| 生成 C++ 文件数 | 1630 | 460 |
| C++ 总量 | 246.783 MB | 41.217 MB |
| 波形 C++ 总量 | 132.638 MB | 2.104 MB |
| 生成耗时 | 未按同一方法记录 | 25.075 秒 |
| C++ 编译、归档和链接耗时 | 未按同一方法记录 | 250.150 秒 |
| 两阶段总耗时 | 未按同一方法记录 | 275.225 秒 |
| 生成进程历史 RSS 峰值 | 未测 | 1037.7 MiB |
| 编译单进程历史 RSS 峰值 | 未测 | 1098.0 MiB |
| 编译进程树采样 RSS 合计峰值 | 未测 | 1083.9 MiB |
| 编译进程树采样私有内存合计峰值 | 未测 | 1094.1 MiB |

C++ 总量减少 83.3%，波形代码减少 98.4%。既有完整追踪构建的时间记录包含 Windows 归档/链接修复和二次构建，因此不拿它计算同条件的耗时提升比例。

同一天先测的仅限制波形深度、文件阈值 8000 的候选，生成 C++ 108.747 MB，最大文件 9.364 MB，C++ 编译与链接 265.032 秒，进程树 RSS 合计峰值 2403.8 MiB。最终候选的同类采样峰值减少 54.9%；生成加编译总耗时从 287.683 秒降到 275.225 秒。最终最大 C++ 文件仍为 3.708 MB，拆分阈值不保证文件字节数或单进程内存上限。

## 测量条件和验证边界

- 操作系统：Windows 原生，未使用 WSL。
- Verilator：5.020，2024-01-01；原生工具配置在 `tools/course_windows_config.json`。
- 主机 C++ 编译器：MSYS2 MinGW `g++ (Rev4) 16.2.0`。本机耗时不能直接当成 OJ Linux 主机耗时。
- 两次完整构建均为单线程编译，无预先生成的目标文件；先生成再编译。中间只检查过生成代码量，没有执行 CPU 正确性或性能测试。
- 原生 Windows 验证使用已存在的 `sc_time_stamp()` 零值兼容对象和生成 Makefile 的路径斜杠转换；仅作用于本地生成目录，不写入官方脚本，也不成为 Linux OJ 的依赖。
- 用 Windows `GetProcessMemoryInfo` 读取生成进程历史峰值；编译阶段每 0.5 秒遍历构建进程树并读取内存。RSS 合计会重复计算共享页，采样也可能漏过瞬间峰值；单进程历史峰值由 API 提供，故可能高于进程树采样峰值。它们不是 OJ cgroup 的内存计费读数。
- 生成与编译结束分别核对 A109 的 41 项源文件 SHA-256，与既有测量快照一致；15 项官方框架文件与固定课程版本一致。
- 生成头文件核对全部 19 项要求的 AXI/时钟/复位端口原名及官方波形 API；官方 `sim.cpp` 已成功编译和链接。
- 默认模式、原名完整追踪模式、非法开关值和工具覆盖参数只做构建计划静态检查。
- 本轮没有重新验证仿真器运行速度；原有 IPC、面积、频率仍引用冻结 A109 报告，不作为这一构建配置的新测量结果。

## 原始证据

- 完整追踪代码统计：`F:/CPU2026CourseRuns/A109_readme_interface_no_pi_20261006/build/obj/`，只读。
- 第一轮完整编译诊断：`build/oj_compile_trace1_20261006/`。
- 最终诊断：`build/oj_compile_depth32_20261006/plan.json`、`generation.log`、`generation_result.json`、`compilation.log`、`compilation_result.json`。
- 最终本机可执行文件：`build/oj_compile_depth32_20261006/sim.exe`，SHA-256 `01f7ec715d4afec9b43afdcbaed84d4a2ce8d0f3fc427bb2867d9ddf7c199d22`，8965911 字节。
- 上述生成代码、日志和可执行文件均留在忽略的本地目录，不加入提交。

课程框架版本 `54fc150ffc290f52aa024209ffb9a29d43856f6d`；testcases 子模块版本 `29f980727f7d99a1842a58f34091c7579ba3fe85`。

参数依据：[Verilator 5.020 官方选项说明](https://github.com/verilator/verilator/blob/v5.020/docs/guide/exe_verilator.rst)、[该版本编译器深度阈值实现](https://github.com/verilator/verilator/blob/v5.020/src/V3Options.cpp)、[深表达式拆分实现](https://github.com/verilator/verilator/blob/v5.020/src/V3Depth.cpp)。提交入口依据：[课程 OJ 提交要求](https://github.com/ACMClassCourse-2025/RISC-V-CPU-2026#oj-submission)、[ACMOJ Git 提交帮助](https://acm.sjtu.edu.cn/OnlineJudge/help/view-submit-and-judge-problems)。

# OJ 编译设置、主机环境和库的影响

2026-10-06，Windows 原生审阅。确认了可复现的 MinGW 运行库混用故障，以及旧仿真生成设置的显著影响；固定环境下仍主要消耗 CPU 执行模型，不能仅通过换库解释或解决 Pi 超时。没有重新构建或运行完整 Pi/正确性套件，也没有重新综合。

## 工具与实际编译命令

课程 AppImage 固定 Verilator 5.020；当前原生版本也是 5.020。课程 README 要求宿主 C++17 编译器，没有固定 GCC 版本。现有计时构建明确调用 F:/c26/msys64/mingw64/bin/g++.exe，GCC 16.2.0 Rev4，POSIX 线程模型。当前 PATH 却先选到 E:/mingw64/bin/g++.exe，GCC 15.2.0，win32 线程模型。两者均可满足语言版本要求，但不能混用生成物及依赖库。

生成命令和实际编译日志相互核对：热模型/官方驱动 `-O3`，公共运行库 `-Os`，冷代码默认未优化；`VM_PROFC=0`、`VM_COVERAGE=0`、`VM_SC=0`、`VM_TIMING=0`，无 `-g`、`VL_DEBUG`、sanitizer、LTO 或 PGO。默认目标为 nocona、调优 generic；`-O3` 确实启用严格别名和循环/SLP 向量化，未按本机 znver4 生成专用代码。此处没有更改架构编译参数，也没有测量它们可能的收益。

历史原生入口也不等于当前提交入口：course_windows_config.json 的 verilator_build_driver 仍指向旧 verilator_course.exe，它附加 unroll-stmts1000000/output-split2000，不选择本轮字级仿真和数组调度提示；该 JSON 的 source/out 等指向旧冻结测量。build_course_verilator_split.ps1 则引用另一套 OSS CAD Suite，并使用新版本的 output-groups 选项。保留这些历史入口供追溯，当前运行报告只依据明确记录的新生成/编译计划，不能混用这些入口的结果。

`-j1` 约束构建并发，不代表 DUT 只能发射一条指令。生成模型声明 threads() 为 1，因此没有多线程执行模型。Verilator 5.020 上下文默认采用 hardware_concurrency()，会额外创建辅助线程；其 workerLoop 初次等待不会自旋。诊断观察到 35 个 OS 线程，但 CPU 使用约一个核，不能把 OS 线程数解释为 35 核仿真。

官方 sim.cpp 在 OJ 模式不打开波形文件；只有带 WAVE 参数的本地模式才 trace.open/dump。编入 trace 支持不等于运行时写波形。没有 OPT/OPT_FAST/OPT_SLOW/OPT_GLOBAL/CXXFLAGS/CPPFLAGS/LDFLAGS/MAKEFLAGS 等环境覆盖；当前包装器也移除继承的 Make jobserver 设置。

## 同一二进制的动态库诊断

两次均使用 SHA-256 `556cab11c76598b805586c4f72b68c9eb44a7bd36dbc3db2dd80144c0c4d8242`、同一 Pi 输入、50000 周期上限、latency10；顺序执行，不重编译。这是环境诊断，不是完整 Pi 正确性测试。

| 环境 | 结果 | CPU 时间 | 墙钟时间 | 实际观测 |
|---|---|---:|---:|---|
| 默认 PATH | 0xC0000005 访问违规；没有程序结果 | 0.109375 秒 | 5.983605 秒 | libgcc/libwinpthread 来自 E 盘；出现 UCRT |
| F 盘固定运行库在 PATH 前端 | 正常到达 50000 周期上限，预期退出码 1 | 4.078125 秒 | 4.515744 秒 | libgcc/libstdc++/libwinpthread 全来自 F 盘 |

前一次不是运行速度对照值；它已经崩溃，不能拿 5.98/4.52 计算加速比。未定位单个故障 DLL 或取得调用栈。E 盘 libstdc++ 的导入表依赖 UCRT，F 盘依赖 MSVCRT；F 构建的 sim 本身也导入 MSVCRT。证据支持混用环境故障，不能把所有原 OJ 超时归因于同一个 Windows DLL 问题。既有 Word4、qsort、tak 计时已经使用 F 盘固定环境，故这次诊断没有修正那些既有周期/时间结果。

固定环境 CPU/墙钟比约 0.903，包含启动、等待和诊断开销。大多数时间在执行模型；它不支持“几十倍时间都花在库等待”这一解释，也不能精确分离功耗、调度与缓存影响。

新增 [原生启动器](../tools/run_course_sim_windows.py) 对这套配置构建的二进制显式选择配套运行库，不修改全局 PATH；同时检查可执行文件旁是否存在冲突 DLL。它不用于 Linux OJ，也不能为其他工具链构建的二进制保证 ABI 兼容。

```powershell
python tools/run_course_sim_windows.py --dry-run build/oj_runtime_word4_20261006/sim.exe
python tools/run_course_sim_windows.py build/oj_runtime_word4_20261006/sim.exe testcases/correctness_pi/program.data 112 100000 10
```

本次只静态检查启动器计划，未再执行后一个示例。

## 资源与库边界

CPU 是 Ryzen 9 8945HX，16 核/32 线程。采样时总体 CPU 约 19%，队列 0；游戏进程两秒样本消耗约 3.39 个逻辑核。可用内存约 5.5 GiB，PageReads/sec 与 Pages/sec 为 0。电源方案为平衡，Processor Performance 为基准的 187%；WMI 的 2501 MHz 是所报基准值，不能据此断言没有睿频。后台活动使本机计时有噪声，本次没有关闭其他应用或更改电源计划。

ASAP7 .lib、Yosys、ABC、OpenSTA 参与硬件面积/时序估计，不是仿真器的动态链接依赖。仿真的 SRAM 使用课程 sram_fakeram.sv 行为模型，外部 RAM 是官方 256 MiB vector；二者文件没有修改。RAM 占用解释约 266.6 MiB 的进程 RSS，不能据此认为每周期都重新初始化 256 MiB 内存。

官方框架 15 项文件 SHA-256 全匹配现有固定版本；当前 RTL 与 Word4 已编译输入一致，四个文件剥离字级仿真分支后的综合正文与冻结结构一致。课程版本吻合仅限这些已核对内容；3201 包记录的另一框架提交及 OJ 实际宿主 GCC/运行环境仍未知。

## 已有设置对照与结论

| 配置 | UNOPTFLAT 数 | Pi 10 万周期 | 构建时间 |
|---|---:|---:|---:|
| 原结构模型，热代码 O1 | 59 | 30.906677 秒 | 94.071534 秒 |
| 原结构模型，拆分选择数组，热代码 O1 | 2 | 14.658579 秒 | 98.695003 秒 |
| 模块内联及热代码 O2 | 2 | 10.037575 秒 | 117.395704 秒 |
| 等价字模型、热代码 O3，当前采用 | 0 | 8.243627 秒 | 102.090326 秒 |
| 状态模块禁止内联，未采用 | 0 | 12.267013 秒 | 123.970926 秒 |

第一项与第二项保留相同原 RTL 和 O1，数组调度提示明显减少求值开销。后续同时改变多个参数，没有独立测出 O1→O3 的净收益；代码共享的尝试反而变慢。当前约 12131 模拟周期/秒，Pi 需要在 100 秒内达到约 388535 周期/秒，差约 32 倍。需要继续减少模型计算或实际 MDU 周期，不能凭更换编译器/库承诺这一幅度。

原始记录位于 `build/oj_host_environment_audit_20261006/` 的 static_audit.json、runtime_environment.json、probe_environment.py 及 stdout/stderr。诊断 JSON 记录实际 DLL 路径和 SHA-256。完整运行证据和采用范围见 [运行报告](OJ_runtime_2026-10-06.md)。

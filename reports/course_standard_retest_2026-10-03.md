# 课程标准版本 Windows 原生复测

复测已完成。全部工具构建和测试均使用 Windows 原生环境。当前采用的同一组 RTL / 参数配置得到 **IPC 0.9801279406499007、课程估算最高频率 32.39788654411997 MHz、总面积 46309.69349394434 µm²**，三项均未达到 Tier3。

## 已确认结果

| 官方程序 | 动态指令数 | 仿真周期 | IPC |
|---|---:|---:|---:|
| perf_median | 6961 | 10154 | 0.6855426433 |
| perf_multiply | 21722 | 19659 | 1.1049392136 |
| perf_qsort | 139900 | 191738 | 0.7296414899 |
| perf_rsort | 195719 | 161191 | 1.2142055078 |
| perf_towers | 5278 | 5636 | 0.9364797729 |
| perf_vvadd | 4524 | 3207 | 1.4106641721 |
| **几何平均** | | | **0.9801279406499007** |

六个性能程序均经过课程原始输出比较；本次未重跑全部 19 个正确性用例。

| 指标 | 当前课程标准结果 | Tier3 要求 |
|---|---:|---:|
| IPC 几何平均 | 0.9801279406499007 | ≥ 1.0985 |
| 估算最高频率 MHz | 32.39788654411997 | ≥ 300 |
| 最小周期 ns | 30.8662109375 | ≤ 3.3333333333 |
| 总面积 µm² | 46309.69349394434 | ≤ 36000 |
| 组合逻辑面积 µm² | 27841.793039944332 | 计入总面积 |
| 时序逻辑面积 µm² | 10642.2336 | 计入总面积 |
| SRAM 面积 µm² | 7825.666854000001 | **37 个宏，全部计入** |

综合采用原始课程 `MODE=opt`、ABC 目标周期 2 ns；时序约束为输入/输出延迟 0.2 ns，输入/时钟过渡 0.05 ns，不确定度 0.05 ns，输出负载 5 fF，reset=0，理想时钟、无布线寄生，频率搜索分辨率 0.001 ns。这是课程静态时序估算口径。

同一采用配置的旧工具结果为 53.43909821521762 MHz / 46298.423154 µm²。本次频率降低 39.3742%，面积增加约 0.02434%；RTL 没有改动，工具版本和评测入口已统一为课程版本，因此这里不能解释为本轮 RTL 优化造成的退化，也不能继续将旧频率作为课程验收结果。尚未通过工具交叉运行分离具体是哪一个版本变化造成这项差异。旧 IPC 使用不同程序镜像和延迟，不进行直接百分比比较。

本次最慢路径的到达时间约 30.80 ns，2 ns 目标下最差 setup slack 为 -28.865267 ns。路径中 `core.g_decode_pipeline.pipe.flush_i` 由 `NAND3xp33_ASAP7_75t_R` 单元 `_362281_` 驱动，扇出 **794**、负载 **410.6031 fF**，该段单元延迟 **9.4477 ns**。后续提高频率应首先处理恢复/清空控制的广播负载；仅增加数据流水线级数不能消除这段广播延迟。

## 版本与口径

全部编译和测量在 Windows 本机进行，MSYS2 仅提供 Windows 编译所需的 GNU 构建工具，最终工具和仿真程序均为原生 PE 可执行文件。先前 WSL 构建已停止，其产物未用于本次复测。

| 项目 | 课程固定版本 / 提交 |
|---|---|
| 框架 | `54fc150ffc290f52aa024209ffb9a29d43856f6d` |
| 官方测试镜像 | `29f980727f7d99a1842a58f34091c7579ba3fe85` |
| Yosys 0.63 | `70a11c6bf0e8dd669f56c7da3587f78b405138e2` |
| ABC | `8e401543d3ecf65e3a3631c7a271793a4d356cb0` |
| OpenSTA 3.1.0 | `f89887b59600cd3a2a10c3de31bda4235d904cdf` |
| CUDD | `f54f533303640afd5dbe47a05ebeabb3066f2a25` |
| Verilator 5.020 | `5c5314b39cd888f427807d626e1502cbf222c292` |
| ASAP7 源码 | `f970bd3c3292b79ae4d022a3ec80533534614066`，五个 RVT TT Liberty 文件 SHA256 与课程版本一致 |

使用课程原始 `build.py`、`sim.cpp`、`testcase.py`、`synth.py`、FakeRAM 与时序脚本。内存延迟为 10，IPC 分子为官方 `metrics.json` 中的 `dynamic_instructions`，周期由原始仿真器输出，总 IPC 为六项几何平均。旧 IPC 使用不同的本地镜像和延迟，因此不能直接用增减比例判断优化效果。

本次固定采用配置取自 `build/cpu2026/verified_frequency_combined_profile_20261003.json`，39 项覆盖参数已写入测量快照的顶层默认值。工程主树 RTL 未因工具升级而改变。

## Windows 编译适配

固定源码工具不是 Linux Docker 二进制的字节复制。Windows 使用 MinGW GCC 16.2.0；完整支持库版本和二进制 SHA256 均记录在工具清单中。Yosys、ABC、OpenSTA、Verilator 的算法源码无修改；CUDD 仅运行与课程构建相同的 `autoreconf`，生成文件按 Windows 主机依赖更新。

Verilator 5.020 按其原始文档提高循环展开限额：`--unroll-count 1024 --unroll-stmts 1000000`；C++ 拆分参数为 `--output-split 2000 --output-split-cfuncs 2000`。Windows 缺少所需弱符号支持，采用该版本 FAQ 明确给出的 `double sc_time_stamp() { return 0; }` 链接补充；课程驱动依旧使用原来的 `VerilatedContext::timeInc(1)` 推进时间。构建归档命令改用正斜杠路径，ABC 链接使用响应文件，OpenSTA 生成命令显式调用原生 Tcl。这些适配均未调整 RTL、CPU 时钟周期计数、测试镜像或内存延迟。

## 证据位置

- 工具配置：`E:/Verilog_cpu/tools/course_windows_config.json`
- 工具固定提交、二进制、支持库、Windows 适配 SHA256：`F:/CPU2026CourseTools/win54fc150/toolchain_manifest.json`
- 固定源码和参数：`F:/CPU2026CourseRuns/current_adopted_20261003/source_manifest.json`
- 原生 CPU 构建身份和链接适配：`F:/CPU2026CourseRuns/current_adopted_20261003/native_build_unroll_v2/build_identity.json`
- 官方 IPC 原始输出：`F:/CPU2026CourseRuns/current_adopted_20261003/result/perf.log`
- IPC 精确值：`F:/CPU2026CourseRuns/current_adopted_20261003/result/ipc.json`
- 综合与时序输出：`F:/CPU2026CourseRuns/current_adopted_20261003/result/synth/opt/`
- 汇总结果：`F:/CPU2026CourseRuns/current_adopted_20261003/result/result.json`
- 当前课程标准配置记录：`E:/Verilog_cpu/build/cpu2026/verified_course_standard_windows_profile_20261003.json`

评测入口为 `tools/run_course_standard_windows.py` / `make course-standard-measure`；版本核验为 `make course-standard-versions`。已保存的测量目录不会被覆盖。旧研究脚本和历史报告仍保留作溯源，当前验收以此固定版本的官方测量为准。

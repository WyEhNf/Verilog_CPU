# 课程评测规范与工具、库版本核对（2026-10-03）

结论：**部分匹配，尚不能称为严格复现课程默认环境。** ASAP7 库、FakeRAM 模型、面积计入方式和 STA 约束匹配；历史 IPC 使用的程序镜像、外存延迟及工具版本未完全对齐。

本次核对未运行功能测试，也未启动新的综合作业。已有频率优化候选的后台作业继续运行。历史结果和冻结源码保留。

## 已匹配的项目

| 项目 | 证据 |
| --- | --- |
| 课程框架 | 本地和远端 HEAD 均为 `54fc150ffc290f52aa024209ffb9a29d43856f6d`，课程仓库跟踪文件无修改；历史测量冻结的 9 个课程脚本与当前原文件哈希一致。 |
| ASAP7 | 五个 7.5-track r28 RVT TT NLDM 库全部匹配课程指定提交 `f970bd3c3292b79ae4d022a3ec80533534614066`。先核对官方 Git tree 的压缩包 blob SHA-1，再解压核对实际测量所用 Liberty 的 SHA-256。未使用项目中的过滤库。 |
| FakeRAM | 三种宏 Liberty 内容与原版 `fakeram.py` 重新生成的内容完全一致；字节哈希差异仅由 Windows CRLF 换行造成。模型为 `fakeram-asap7-v1`，37 个实际宏计入总面积，SRAM 为 7,825.666854 µm²。 |
| 面积范围 | 统计完整 `student_top`，含 AXI 接口和芯片内 SRAM；256 MiB 外存属于测试平台，不计入芯片面积。 |
| STA | 原版 `timing.tcl`；ns/fF 单位、输入/输出延迟 0.2 ns、输入/时钟转换 0.05 ns、时钟不确定度 0.05 ns、输出负载 5 fF；reset 固定为 0，完整 CPU 和 SRAM 均参与分析。 |
| 综合目标 | `MODE=opt`，标准 ABC 命令，`-D 2000` 与课程默认 2 ns 综合目标一致。2 ns 是优化目标，报告 Fmax 仍由原版 STA 搜索可行周期；300 MHz 对应 3.333 ns。 |
| CUDD | 当前提交和课程固定提交均为 `f54f533303640afd5dbe47a05ebeabb3066f2a25`。 |

## 未对齐的项目

| 项目 | 课程参考环境 | 历史测量环境 |
| --- | --- | --- |
| Yosys | 0.63，提交 `70a11c6bf0e8dd669f56c7da3587f78b405138e2` | 0.68+120，`a34d3baae-dirty` |
| ABC | 随固定 Yosys 构建，子模块提交 `8e401543d3ecf65e3a3631c7a271793a4d356cb0` | OSS CAD Suite 的 ABC 1.01，编译日期 2026-08-22；未记录精确源码提交 |
| OpenSTA | 提交 `f89887b59600cd3a2a10c3de31bda4235d904cdf` | 3.1.0，构建配置记录提交 `6be0b1d7da7c98391f5a7fe2a26b3323d28565cc` |
| Verilator | 推荐 AppImage 内置 5.020；Docker 使用 Ubuntu 包 | 5.051 开发版，`v5.050-243-g459711ba7 (mod)` |
| 外存延迟 | Makefile、run.py、testcase.py 默认 10 周期 | 20 周期 |
| 性能程序 | 指定测试集中的全部 `perf_* / program.data` | 六个同名程序的本地重新编译镜像；解析为实际内存字节后，六个都不同 |
| IPC 分子 | 测试集 `metrics.json` 的 `dynamic_instructions` | CPU 的 `debug_instret` |
| 官方正确性覆盖 | 全部 19 个 `correctness_*` | 原本地套件并非同一组官方镜像，且排除了 pi；历史通过项数不能证明当前官方套件全部通过 |

课程允许在 `config.mk` 指定原生工具和运行参数，因此工具版本差异、延迟覆盖不等于课程禁止；它们意味着结果没有严格复现默认参考环境。程序镜像差异则直接影响官方 IPC 比较，不能通过更换分子或缩放旧结果补救。

| benchmark | 官方动态指令数 | 历史本地动态指令数 |
| --- | ---: | ---: |
| median | 6,961 | 7,062 |
| multiply | 21,722 | 27,637 |
| qsort | 139,900 | 139,606 |
| rsort | 195,719 | 289,966 |
| towers | 5,278 | 3,803 |
| vvadd | 4,524 | 4,525 |

## ABC 报错的解释

历史映射日志出现 99 次 `merged SCL conversion failed`，失败命令有 Windows 引号错误。新版 Yosys 随后使用 `read_lib -w` 和 `read_lib -m -w`，以及标准 `&nf -D 2000` 命令。核对课程固定的 Yosys 0.63 源码后，这个回退后的库导入和默认 ABC 命令序列与 0.63 相同。**这条报错本身不足以证明 53 MHz 是环境错误导致的，也不能据此承诺恢复合并功能会提高频率。** 工具与 ABC 的精确版本仍需统一后才能判断数值差异。

## 历史结果的使用范围与后续口径

53.439098 MHz、46,298.423154 µm² 使用了正确课程库、SRAM 模型与时序约束，但尚未在课程固定工具链上复现。IPC 1.008782 属于本地重编译程序、延迟 20 的结果，**不能作为课程 IPC 或 Tier 达标证据**。之前 ±10% 的 IPC 比较也只适用于同一套本地镜像与延迟。

官方测试集已经取回并固定到课程子模块要求的提交 `29f980727f7d99a1842a58f34091c7579ba3fe85`。后续正式评测使用课程固定工具链、未修改的 `scripts/testcase.py`、这些原始 `program.data / metrics.json` 和默认延迟 10；IPC 为六项几何平均。正式 IPC 基线和候选必须使用同一套官方程序及延迟。功能测试继续挂起，待频率取得显著收益后集中验证。

完整机器可读证据：[audit.json](F:/CPU2026Proofs/requirements_audit_20261003/audit.json)。各库完整哈希、课程脚本哈希、程序字节差异、工具提交和下次评测合同均保存在该文件。

官方依据：[课程 README](https://github.com/ACMClassCourse-2025/RISC-V-CPU-2026/blob/54fc150ffc290f52aa024209ffb9a29d43856f6d/README-ZH.md)、[Dockerfile](https://github.com/ACMClassCourse-2025/RISC-V-CPU-2026/blob/54fc150ffc290f52aa024209ffb9a29d43856f6d/Dockerfile)、[Makefile](https://github.com/ACMClassCourse-2025/RISC-V-CPU-2026/blob/54fc150ffc290f52aa024209ffb9a29d43856f6d/Makefile)、[官方测试集](https://github.com/ACMClassCourse-2025/RISC-V-CPU-2026-Testcases/tree/29f980727f7d99a1842a58f34091c7579ba3fe85)、[Yosys 0.63 的 ABC 实现](https://github.com/YosysHQ/yosys/blob/70a11c6bf0e8dd669f56c7da3587f78b405138e2/passes/techmap/abc.cc)。

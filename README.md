# 参数化 RV32IM 乱序 CPU

使用 Verilog 实现寄存器重命名、ROB 顺序提交、RS/LSQ、分支预测、指令和数据缓存，以及课程 AXI4-Lite 接口。支持 RV32IM 运算与字节、半字、字访存。课程顶层是 `student_top`，主工程入口是 `verilog/filelist.f`。

**所有发射宽度与 Tier 档位共用同一套参数化 `cpu_core` 和 `rv32_backend_joint`。** FE/BE 宽度、整数发射和 CDB 端口、ROB/RS/LSQ、物理寄存器以及缓存资源均由参数配置，Tier1/Tier2 没有独立 CPU 实现。

## 当前结果

主工程默认配置（FE4/BE2、ROB32、PRF56、RS8、LSQ16，I-cache 128 行、D-cache 1024 行）在课程官方流程 `302f0cf3` 下，用仓库根目录的 `make synth` 和原始 `testcases/perf_*` 实测：

| 指标 | 2026-11-26 实测 | Tier3 门槛 |
| --- | ---: | ---: |
| 总面积，含 SRAM | 32,672.47 μm² | ≤ 36,000 |
| 六项程序 IPC 几何平均 | 1.117497 | ≥ 1.0985 |
| STA 估计最高频率 | 536.97 MHz | ≥ 300，加分线 400 / 500 |

三项来自同一份源码和同一份网表，使用未改动的官方综合脚本。六项性能和 19 项正确性程序全部通过；映射后的门级网表通过六项性能和 18 项正确性，周期数与 RTL 相同。

**536.97 MHz 依赖 `config.mk` 中的 `CLOCK_PERIOD_NS ?= 1.0`。** 这是课程 README 给出的 `make synth` 参数，只改变 ABC 映射的延迟目标，不改变 OpenSTA 的约束。用框架默认的 2.0 ns 目标（`make synth CLOCK_PERIOD_NS=2.0`），同一份源码是 475.62 MHz、32,653.78 μm²：仍满足 Tier3 和 400 MHz 加分线，不到 500 MHz。原因和数据见[优化过程报告](reports/CPU_optimization_500MHz_2026-11-26.md)第 3 节。

- [测量报告](reports/course_D1000_F537_2026-11-26.md)：条件、逐项周期、未验证的部分。
- [优化过程报告](reports/CPU_optimization_500MHz_2026-11-26.md)：从 37,981 μm² / 338 MHz 到当前结果的各步改动、参数敏感度和未采用的路线。
- [versions/course_D1000_F537](versions/course_D1000_F537/README.md)：实测网表、RAM 库、约束和证据，[版本指针](configs/latest_verified_version.json)记录身份。
- [SRAM 宏引脚驱动与综合约定](docs/sram_pin_drivers_2026-11-26.md)：新增 SRAM 或修改层级属性前先读。

上一个提取版本 [global_D1000_L056_RAMBUF4_F8](versions/global_D1000_L056_RAMBUF4_F8/README.md)（32,200.66 μm²、IPC 1.115263、489.02 MHz）使用自定义映射和综合后缓冲树，不属于官方流程，按原样保留。

## 课程要求与正式参数配置

| 档位 | 最大面积 μm² | 最低 IPC 几何平均 | 最低频率 MHz | 累计分数 | 配置 |
| --- | ---: | ---: | ---: | ---: | --- |
| Tier1 | 9,000 | 0.6000 | 300 | 90 | [tier1.json](configs/tier1.json) |
| Tier2 | 18,000 | 0.8450 | 300 | 95 | [tier2.json](configs/tier2.json) |
| Tier3 | 36,000 | 1.0985 | 300 | 100 | [tier3.json](configs/tier3.json) |

达到某档后，频率到 400 MHz 加 2 分，到 500 MHz 加 4 分。Tier3 配置就是 `student_top` 的默认参数。

Tier1/Tier2 是同一套 RTL 的参数覆盖。它们在旧版课程流程 54fc150f 下的冻结结果如下：

| 配置 | 面积 μm² | IPC 几何平均 | 频率 MHz | 冻结证据 |
| --- | ---: | ---: | ---: | --- |
| 共享参数化 Tier1 | 8,968.688155 | 0.601284216 | 305.854241 | [原始记录](reports/Tier1_shared_verified_2026-10-09.json) |
| 共享参数化 Tier2 | 17,997.018972 | 0.856141896 | 355.679055 | [原始记录](reports/Tier2_shared_verified_2026-10-09.json) |

2026-11-26 的改动换了 42 个 `student_top` 默认值，两个配置文件已显式写出这些参数的旧值，两档的六项周期数与冻结记录逐项相同。**两档的面积和频率没有在这次改动后重新综合**，上表数值属于旧流程和旧源码，不能当作当前源码的结果。

## 构建与测试

需要 Python 3.10+、GNU Make、C++17 编译器及课程 Verilator/Yosys/OpenSTA/ASAP7 工具。官方框架脚本和 RAM 模型位于 `scripts/`，当前同步版本为 `302f0cf3cccdaa5de084a2120e0d950c663e4cf5`；testcases 子模块固定为 `29f980727f7d99a1842a58f34091c7579ba3fe85`。

```sh
git submodule update --init testcases
make                         # 构建 RTL，生成课程 OJ 所需的 code
make build                   # 生成 build/sim
make test Case=correctness_array_test1
make perf LATENCY=10
make synth                   # 官方综合与 STA，约 21 分钟，峰值内存约 4.5 GB
```

仓库路径不能含空格，课程 Makefile 不处理这种情况。

工具路径通过 `config.mk`、命令行变量或未提交的 `config.local.mk` 设置。可将课程 AppImage 放在根目录，或显式配置原生工具。没有 AppImage 的 Linux 机器可用 `tools/build_pinned_course_tools_linux.sh all` 从源码构建课程固定版本的 Yosys、ABC、OpenSTA、Verilator 和 ASAP7 库，不需要 root。Windows 本机环境的启用与检查见[测试环境说明](docs/windows_test_environment.md)。不需要把本机工具二进制或 `.deps/` 提交到仓库。

`tools/verilator_low_memory.py` 将生成与串行 C++ 编译分开；`config.mk` 中的 `CPU2026_WORD_SIM`、`CPU2026_NATIVE_BITS`、`CPU2026_STABLE_MDU`、`CPU2026_ICO_PAIR` 和 `CPU2026_PGO` 控制现有模拟加速。它们不代表新增硬件性能结果，详细验证范围保留在 [OJ 加速记录](reports/OJ_pi_acceleration_research_2026-10-07.md)中。`CPU2026_TRACE_DEPTH=0` 可恢复完整内部波形。

`tools/staged_course_synth.py` 按官方流程的同一组命令分阶段综合并缓存中间结果，换一个 ABC 参数约 7 分钟，并把触发器按 RTL 寄存器命名以便阅读 STA 路径。它用于探索，正式数字以 `make synth` 为准。

参数档位可用现有工具独立冻结和测量：

```sh
python tools/run_tier_candidate.py --help
python tools/evaluate_current_course.py --help
```

IPC 使用原始课程驱动与程序测量；频率来自官方约束下的 STA，采用理想时钟与无寄生模型。重新评估时，优先运行有实质变化的配置和少量针对性正确性点。

## 目录与历史恢复

| 路径 | 内容 |
| --- | --- |
| `rtl/`、`verilog/` | 当前共享参数化 CPU 与主工程 filelist |
| `configs/` | Tier1/Tier2/Tier3 正式配置及最新已提取版本指针 |
| `versions/` | 已验证版本的完整冻结快照与独立提取入口 |
| `scripts/`、`tools/` | 官方框架、构建辅助、保留的测试和可复用诊断工具 |
| `tb/`、`tests/` | 模块与集成测试、测试程序源文件 |
| `reports/` | 关键验收结果、测量口径与模拟加速证据 |
| `docs/` | [原版与中文版文档索引](docs/README.md) |
| `history/` | [历史版本索引、清理清单与恢复说明](history/README.md) |

2026-10-26 的清理仅作用于当前分支。旧实验脚本、候选配置和过程报告仍完整保存在清理前提交 `8837b2fa0ab3693e7670cb9ad3c6ab409950b46a` 以及原有分支、标签中；没有重写 Git 历史。历史文档中已退役文件的链接指向该固定提交，原日期和测量数值保持原义。

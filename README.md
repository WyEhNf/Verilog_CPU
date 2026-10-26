# 参数化 RV32IM 乱序 CPU

使用 Verilog 实现寄存器重命名、ROB 顺序提交、RS/LSQ、分支预测、指令和数据缓存，以及课程 AXI4-Lite 接口。支持 RV32IM 运算与字节、半字、字访存。课程顶层是 `student_top`，主工程入口是 `verilog/filelist.f`。

**所有发射宽度与 Tier 档位共用同一套参数化 `cpu_core` 和 `rv32_backend_joint`。** FE/BE 宽度、整数发射和 CDB 端口、ROB/RS/LSQ、物理寄存器以及缓存资源均由参数配置，Tier1/Tier2 没有独立 CPU 实现。

## 最新提取版本

**[global_D1000_L056_RAMBUF4_F8](versions/global_D1000_L056_RAMBUF4_F8/README.md)** 包含真实冻结 RTL、实际测过的综合网表、单元/RAM 功能模型、映射步骤与校验清单。[版本指针](configs/latest_verified_version.json)记录完整身份。

| 指标 | 2026-10-15 实测 |
| --- | ---: |
| 总面积，含 SRAM | 32,200.657838 μm² |
| 六项程序 IPC 几何平均 | 1.115262691835 |
| STA 估计最高频率 | 489.016237 MHz |

六项门级性能基准答案通过，一个小正确性点 array_test1 通过。三项数值满足 Tier3 门槛，频率尚未达到 500 MHz。这是全局映射与 SRAM 输入缓冲树的实验结果，不等于官方默认 RTL 综合流程的提交分数。详见[测量报告](reports/global_D1000_L056_RAMBUF4_F8_latest_course_2026-10-15.md)。

在仓库根目录提取（Python 3.11+）：

```sh
python versions/global_D1000_L056_RAMBUF4_F8/release.py verify
python versions/global_D1000_L056_RAMBUF4_F8/release.py materialize --out build/global_D1000_L056_RAMBUF4_F8
```

版本目录内的 README 提供冻结网表的独立构建命令；主工程仍使用下述共享参数化 RTL。

## 课程要求与正式参数配置

| 档位 | 最大面积 μm² | 最低 IPC 几何平均 | 最低频率 MHz | 累计分数 | 配置 |
| --- | ---: | ---: | ---: | ---: | --- |
| Tier1 | 9,000 | 0.6000 | 300 | 90 | [tier1.json](configs/tier1.json) |
| Tier2 | 18,000 | 0.8450 | 300 | 95 | [tier2.json](configs/tier2.json) |
| Tier3 | 36,000 | 1.0985 | 300 | 100 | [tier3.json](configs/tier3.json) |

Tier1/Tier2 在旧版课程流程 54fc150f 下的冻结结果如下，不能直接当作新版流程的重新验收结果：

| 配置 | 面积 μm² | IPC 几何平均 | 频率 MHz | 冻结证据 |
| --- | ---: | ---: | ---: | --- |
| 共享参数化 Tier1 | 8,968.688155 | 0.601284216 | 305.854241 | [原始记录](reports/Tier1_shared_verified_2026-10-09.json) |
| 共享参数化 Tier2 | 17,997.018972 | 0.856141896 | 355.679055 | [原始记录](reports/Tier2_shared_verified_2026-10-09.json) |

当前主工程默认配置 FE4/BE2、ROB32、PRF56、RS8、LSQ16，I-cache 128 行、D-cache 1024 行。在官方新版流程 `302f0cf3` 下，实测面积 **37,981.394558 μm²**、IPC **1.115262691835**、频率 **338.065368 MHz**，由于面积超限，当前默认配置不满足 Tier3 联合门槛。这个结果与上面的已提取实验网表使用不同的映射流程，详见[默认配置报告](reports/Current_default_latest_course_2026-10-15.md)。

## 构建与测试

需要 Python 3.10+、GNU Make、C++17 编译器及课程 Verilator/Yosys/OpenSTA/ASAP7 工具。官方框架脚本和 RAM 模型位于 `scripts/`，当前同步版本为 `302f0cf3cccdaa5de084a2120e0d950c663e4cf5`；testcases 子模块固定为 `29f980727f7d99a1842a58f34091c7579ba3fe85`。

```sh
git submodule update --init testcases
make                         # 构建 RTL，生成课程 OJ 所需的 code
make build                   # 生成 build/sim
make test Case=correctness_array_test1
make perf LATENCY=10
make synth MODE=opt CLOCK_PERIOD_NS=2.0
```

工具路径通过 `config.mk`、命令行变量或未提交的 `config.local.mk` 设置。可将课程 AppImage 放在根目录，或显式配置原生工具。Windows 本机环境的启用与检查见[测试环境说明](docs/windows_test_environment.md)。不需要把本机工具二进制或 `.deps/` 提交到仓库。

`tools/verilator_low_memory.py` 将生成与串行 C++ 编译分开；`config.mk` 中的 `CPU2026_WORD_SIM`、`CPU2026_NATIVE_BITS`、`CPU2026_STABLE_MDU`、`CPU2026_ICO_PAIR` 和 `CPU2026_PGO` 控制现有模拟加速。它们不代表新增硬件性能结果，详细验证范围保留在 [OJ 加速记录](reports/OJ_pi_acceleration_research_2026-10-07.md)中。`CPU2026_TRACE_DEPTH=0` 可恢复完整内部波形。

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

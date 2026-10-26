# global_D1000_L056_RAMBUF4_F8

2026-10-26 从已验证的实验结果提取。这个目录包含对应的完整参数化 A109 RTL、实际测过的综合网表、标准单元功能模型、RAM 模型与生成库、映射参数及测试证据。它是同一个 CPU 的历史版本快照；主工程继续保留共享参数化 CPU 和 Tier1/Tier2 配置。

| 指标 | 2026-10-15 实测 |
| --- | ---: |
| 总面积（含 SRAM） | 32,200.657838 μm² |
| IPC 几何平均 | 1.115262691835 |
| STA 估计频率 | 489.016237 MHz |

六项门级性能基准答案全部通过，另一个小正确性点 array_test1 通过。三项数值满足 Tier3 阈值，频率尚未达到 500 MHz。这是自定义映射与 SRAM 缓冲树的实验版本，数值不等于官方默认 RTL 综合流程的提交分数。完整评估见 [已提交报告](../../reports/global_D1000_L056_RAMBUF4_F8_latest_course_2026-10-15.md)。本次提取只核对文件、哈希与构建入口，没有重复硬件测试。

## 提取与使用

在仓库根目录执行（Python 3.11+）：

```sh
python versions/global_D1000_L056_RAMBUF4_F8/release.py verify
python versions/global_D1000_L056_RAMBUF4_F8/release.py materialize --out build/global_D1000_L056_RAMBUF4_F8
python versions/global_D1000_L056_RAMBUF4_F8/framework/scripts/build.py --filelist build/global_D1000_L056_RAMBUF4_F8/filelist.f --out build/global_D1000_L056_RAMBUF4_F8/build
```

构建需要 Verilator、C++ 编译器与 Make；可传官方 build.py 的 `--verilator`、`--cxx`、`--ar`、`--make` 参数。上面的入口直接使用本版本冻结的官方驱动和 RAM 模型，默认不使用主工程的模拟加速补丁。需要本机适配时可显式选用主工程的构建包装器。

生成的模拟器支持原始课程协议。运行课程性能测试时先初始化 testcases 子模块，然后使用冻结的 `framework/scripts/testcase.py --testcases testcases --sim <生成的模拟器> --kind perf --latency 10`。Windows 二进制通常名为 sim.exe。

`source/verilog/filelist.f` 是本版本参数化 RTL 的独立入口。仅重新综合这些 RTL 不会自动得到已测网表；还需要 `recipe/mapping.json` 中的全局映射、ABC 约束和 SRAM 输入缓冲步骤。网表压缩只用于版本保存，提取后的 SHA256 必须为：

```text
ce1ae01b92aabfac41adcddb6f6ef937c9212babe481403c38f1d824814edf6c
```

## 文件与测量范围

- `source/`：生成该实验的真实冻结 RTL、头文件与 filelist，逐项核对原始源清单；不是后来 HEAD 的近似替代。
- `netlist/mapped.v.gz`：上述网表的确定性 gzip 存档，不包含宿主工具二进制。
- `simulation/`：本次六项门级基准实际使用的 Liberty 功能模型和 RAM 宏接口桥接。
- `framework/scripts/`：评估使用的官方框架 302f0cf3 原始脚本与 RAM 模型。
- `ram/`：官方 FakeRAM 生成的五种宏库、封装和配置清单。
- `recipe/`：映射参数、时序约束、便携的 SRAM 缓冲树生成步骤。重新映射的结果仍需单独验证，不能自动继承本版本实测值。
- `evidence/`：已完成的实测结果、网表身份及映射来源。
- `manifest.json`：上述文件 SHA256 清单以及未压缩网表的身份。

STA 使用官方 5 fF 输出负载、0.2 ns 输入输出延迟和 0.05 ns 时钟不确定度，理想时钟、无寄生参数。ABC 映射时的 0.56 fF 只影响映射决策，不改变 STA 的 5 fF 负载。门级仿真为零延迟功能仿真；最高频率由独立 STA 估计。

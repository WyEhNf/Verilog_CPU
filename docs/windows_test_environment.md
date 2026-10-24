# 本机 Windows 测试环境

工具安装在项目的 `.deps/` 中。路径配置仅对当前 PowerShell 会话生效。
课程 RTL、官方仿真驱动、综合脚本和验收标准保持原样。

## 启用

在项目根目录的 PowerShell 中执行：

```powershell
. .\tools\Enter-CpuEnvironment.ps1
make CONFIG=config.local.mk help
```

`config.local.mk` 和 `.deps/course_windows.local.json` 是本机专用配置，均不提交到 Git。
进入新的 PowerShell 窗口后重新执行启用命令。

## 工具与版本来源

| 工具 | 版本或固定源码提交 | 用途 |
| --- | --- | --- |
| Verilator | 5.020，`5c5314b39cd888f427807d626e1502cbf222c292` | 整机仿真、RTL 静态检查 |
| Yosys | 0.63，`70a11c6bf0e8dd669f56c7da3587f78b405138e2` | 综合和面积统计 |
| ABC | `8e401543d3ecf65e3a3631c7a271793a4d356cb0` | 门级映射 |
| OpenSTA | 3.1.0，`f89887b59600cd3a2a10c3de31bda4235d904cdf` | 完整 CPU 静态时序分析 |
| CUDD | `f54f533303640afd5dbe47a05ebeabb3066f2a25` | OpenSTA 依赖 |
| ASAP7 | 7.5-track r28 RVT TT，`f970bd3c3292b79ae4d022a3ec80533534614066` | 五份标准单元 Liberty 库 |
| Icarus Verilog | 13.0，MSYS2 官方软件包 | Verilog 单元测试 |
| GTKWave | 3.3.127，MSYS2 官方软件包 | 波形查看 |
| Python、GNU Make、GCC、CMake、Ninja、Flex、Bison、Tcl、SWIG | 本地 MSYS2 软件包，精确版本见 `.deps/course-tools/packages.txt` | 构建依赖 |
| 官方测试集 | `29f980727f7d99a1842a58f34091c7579ba3fe85` | 课程原始镜像、答案、指令数 |

工具源码提交与课程框架的固定构建配方一致。五份 ASAP7 库的 SHA256 与仓库历史测量记录逐份相同。
新机器上的编译器和工具二进制不同于历史机器，因此仍应重新测量所需候选，不能直接复用历史成绩。

源码来源和安装记录见 `.deps/course-tools/source_manifest.json`、
`.deps/course-tools/packages.txt` 及 `.deps/setup-logs/`。

## 验证环境

```powershell
.\tools\Test-CpuEnvironment.ps1
```

此命令检查版本、官方测试集提交和工艺库哈希，然后执行 Verilator 仿真、
Icarus Verilog-2005 仿真，以及含真实课程 FakeRAM 的小电路综合和 OpenSTA 分析。
报告写入 `.deps/environment_validation.json`，详细日志在 `.deps/smoke/`。
小电路的面积和频率只用于验证环境。

当前 CPU 的官方构建与短程序检查记录另存于 `build/environment_cpu_smoke/`。

2026-10-24 本机验证已通过：工具版本与五份工艺库核对、两种仿真器运行、
含 SRAM 的官方综合和完整时序分析均成功。当前 `4130954` 默认 CPU 的原生构建
和 `correctness_add_to_100` 通过；复用同一个可执行文件运行六项官方性能程序，
答案通过，周期为 7572 / 17490 / 143485 / 153155 / 4739 / 3725，
IPC 几何平均 1.1152626918348099，与历史 A109 的六项周期一致。
这是当前默认 CPU 的环境集成验证，不是 `global_D1000_L056_RAMBUF4_F8` 的测量。

## 运行课程测试

```powershell
. .\tools\Enter-CpuEnvironment.ps1
make CONFIG=config.local.mk build
make CONFIG=config.local.mk test SIM=build/sim.exe Case=correctness_add_to_100
make CONFIG=config.local.mk perf SIM=build/sim.exe LATENCY=10
make CONFIG=config.local.mk synth MODE=opt CLOCK_PERIOD_NS=2.0
```

IPC 使用六项官方 `perf_*` 镜像，分子来自各自 `metrics.json` 的动态指令数，
分母为官方驱动报告的周期数，最后取几何平均。面积包含实际实例化的全部 SRAM。
估算频率来自完整综合网表、标准单元库及 SRAM 时序模型。

本机默认关闭 PGO、MDU 计算缓存和输入区复用，以简化测量环境；
这些开关影响主机仿真开销，不增加或删除 CPU 时钟周期。
原有 `CPU2026_WORD_SIM` 等效仿真表达式保留，综合仍使用原结构分支。

Windows 原生启动器 `.deps/bin/verilator.exe` 调用项目原有的低内存构建包装器，
并在课程 `sim.cpp` 构建中加入仓库已有的 `verilator_windows_time_zero.cpp`，
解决 MinGW 缺少弱时间符号的链接差异。课程驱动继续按原方式推进仿真时间。

## 冻结候选并测量

```powershell
python tools/run_tier_candidate.py prepare --profile configs/tier3.json --out build/tier3_local --host-config $env:CPU2026_HOST_CONFIG
python tools/run_tier_candidate.py synth --out build/tier3_local
python tools/run_tier_candidate.py build --out build/tier3_local
python tools/run_tier_candidate.py perf --out build/tier3_local
```

每个候选使用独立输出目录，保存源码、工具和库的哈希。
脚本在完整面积与频率门通过后才进入普通构建阶段；原有性能优先入口仍可显式使用。

官方工具来源：

- [课程固定构建配方](https://github.com/ACMClassCourse-2025/RISC-V-CPU-2026/blob/54fc150ffc290f52aa024209ffb9a29d43856f6d/Dockerfile)
- [MSYS2 安装包](https://github.com/msys2/msys2-installer)
- [ASAP7 标准单元库](https://github.com/The-OpenROAD-Project/asap7sc7p5t_28/tree/f970bd3c3292b79ae4d022a3ec80533534614066)

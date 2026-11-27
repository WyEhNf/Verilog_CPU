# course_D1000_F537

2026-11-26 从提交 `dd690a8` 提取。这是主工程共享参数化 CPU 在**课程官方综合流程**下的实测版本：`make synth` 调用未改动的 `scripts/synth.py`，没有自定义映射脚本，也没有综合后的网表修改。

| 指标 | 实测 | Tier3 门槛 |
| --- | ---: | ---: |
| 总面积，含 SRAM | 32,672.47 μm² | ≤ 36,000 |
| 六项程序 IPC 几何平均 | 1.117497 | ≥ 1.0985 |
| STA 估计最高频率 | 536.97 MHz | ≥ 300，加分线 500 |
| 最小周期 | 1.8623 ns | 500 MHz 对应 ≤ 2.0 ns |

三项由同一份源码、同一份网表取得。面积细分：组合 17,743.86、时序 6,984.69、SRAM 7,943.91 μm²（100 个 FakeRAM 宏）。

**频率依赖一个综合参数，使用前请确认评测方式。** 本仓库 `config.mk` 设置 `CLOCK_PERIOD_NS ?= 1.0`。这是课程 README 列出的 `make synth` 参数，它只改变 ABC 映射时的延迟目标，OpenSTA 的输入输出延迟、时钟不确定度和负载不随它变化，频率由 OpenSTA 自己搜索最小周期得到。同一份源码用框架默认的 2.0 ns 目标（`make synth CLOCK_PERIOD_NS=2.0`）时，结果是 **475.62 MHz、32,653.78 μm²**。如果评测不读取仓库的 `config.mk`，频率就是后一个数字，仍满足 Tier3 和 400 MHz 加分线，但不到 500 MHz。

## 提取与使用

在仓库根目录执行（Python 3.11+）：

```sh
python versions/course_D1000_F537/release.py verify
python versions/course_D1000_F537/release.py materialize --out build/course_D1000_F537
python versions/course_D1000_F537/framework/scripts/build.py --filelist build/course_D1000_F537/filelist.f --out build/course_D1000_F537/build
```

生成的模拟器直接运行映射后的门级网表，支持原始课程协议：

```sh
python versions/course_D1000_F537/framework/scripts/testcase.py --kind perf --latency 10 \
    --testcases testcases --build build/course_D1000_F537/build --sim build/course_D1000_F537/build/sim
```

从源码复现综合结果不需要这个目录：在仓库根目录运行 `make synth` 即可，约 21 分钟，峰值内存约 4.5 GB。解压后的网表 SHA256 应为：

```text
5eaee13b03ad0db8cce59632c786d6964f413e41107935850fa2c7d51a068aae
```

## 测量范围

- **面积与频率**：一次 `make synth`，结果见 `evidence/report.txt` 和 `evidence/ppa.json`。STA 为理想时钟、无寄生参数，输入输出延迟 0.2 ns，时钟不确定度 0.05 ns，输出负载 5 fF。
- **IPC**：六项原始 `testcases/perf_*`，延迟 10，分子取各自 `metrics.json` 的动态指令数。门级网表仿真与 RTL 仿真的六项周期数逐项相同：7518 / 17506 / 143280 / 153139 / 4719 / 3725。
- **正确性**：RTL 仿真和门级网表仿真各 19 项全部通过，周期数逐项相同，含 `correctness_pi`（38,853,527 周期）。
- 门级仿真是零延迟功能仿真，使用原版 `build.py` 和 `sim.cpp`、Verilator 5.020，没有使用主工程的模拟加速包装。

工具是按课程 Dockerfile 固定的版本在 Linux 上从源码构建的：Yosys `70a11c6b`（ABC `8e401543`）、OpenSTA `f89887b5`、Verilator 5.020、ASAP7 `f970bd3c`。五个标准单元库的 SHA256 与上一个提取版本记录的一致。没有使用课程 AppImage，二进制哈希记录在 `recipe/mapping.json`。

## 文件

- `source/`：测量所用的 RTL、头文件、filelist 和 `config.mk`，与提交 `dd690a8` 逐字节相同。
- `netlist/mapped.v.gz`：`make synth` 写出的 `mapped.v`，确定性 gzip 存档。
- `simulation/`：门级仿真用的标准单元功能模型（由 Liberty 生成，与上一版本相同）和 FakeRAM 宏到官方 `sram_fakeram` 的接口桥接。
- `framework/scripts/`：官方框架 `302f0cf3` 的脚本与 RAM 模型，与上游逐字节相同。
- `ram/`：官方 `fakeram.py` 为本设计生成的五种宏库、封装和清单。
- `recipe/`：ABC 约束文件和完整的流程参数。
- `evidence/`：面积、时序、性能、正确性、源码身份，以及 diagnose 模式的层级面积。
- `manifest.json`：以上文件的 SHA256 清单和网表身份。

设计改动、各步数据和未采用的尝试见[优化过程报告](../../reports/CPU_optimization_500MHz_2026-11-26.md)，本版本的完整测量见[测量报告](../../reports/course_D1000_F537_2026-11-26.md)。

# A109：课程 README 接口检查与测试（跳过 Pi）

本次使用已测 A109 冻结快照重新编译、仿真和 opt 综合。接口检查与所请求的仿真测试通过，综合与 STA 执行成功；2 ns 时序约束未满足。Pi 按用户要求未运行。

源码：`F:/CPU2026CourseRuns/ER1_A109_tier3_20261006/source`；产物：`F:/CPU2026CourseRuns/A109_readme_interface_no_pi_20261006`。
冻结清单 SHA256：`33d1f29453657f5edd5ac5ee641e20cb0f1f991f567e1d10efc367c40aadd5ba`；157 个冻结输入和候选的 41 份源码逐一核对。
新仿真器 SHA256：`540fa2caf8cb59321ba5968a4eaf7524837b9bf361e9abde0ba13fcea1f864a9`。未修改 A109 RTL、官方 Makefile、scripts、程序镜像或 Golden 答案。

## 顶层与 AXI4-Lite

- `student_top` 已列入相对路径 `verilog/filelist.f`；必需的 19 个端口名称、方向、位宽均匹配 README 模板。
- 另有 `debug_instret`、`debug_core_cycles`、`debug_error` 三个观察输出；官方未修改的 sim.cpp 已实际编译并正常运行。
- 高电平复位 5 周期期间 ARVALID/AWVALID/WVALID/RREADY/BREADY 均为 0；外部读写地址按 4 字节对齐。
- 外部 RAM 配置为 256 MiB 小端；最高有效字地址 0x0ffffffc 的既有工程读写/回写边界程序通过，返回 598。
- 发送端 VALID 和载荷在背压期间保持稳定；AW 与 W 可分别先握手，完成配对后等待 B 响应。
- 正确拼接四个 32 位读响应、恢复 I/D 请求身份、传递字节写掩码、跳过零掩码字、聚合 SLVERR/DECERR。
- 按 A109 实际 READ_LINES=8、WRITE_LINES=4、WORD_QUEUE=16、READ_PAYLOAD_SRAM=1、RESPONSE_FIFO_DEPTH=2 检查；另以 WORD_QUEUE=4 加压。
- Yosys 展平到位级门网表后 SCC=0；外部 AXI 输出没有经过组合逻辑依赖 READY、RVALID、BVALID 或响应载荷的路径。SRAM 按课程规定的同步边界处理。
- 完整 CPU 的 add_to_100 波形检查通过：退出地址 0x80000000，WSTRB=0xf，WDATA=5050，在 BVALID/BREADY 握手时确认退出。

协议测试为定向仿真和结构检查，不是对所有可能 AXI 时序的形式证明。

## 本次实际执行

| 项目 | 结果 |
|---|---|
| make help | 通过 |
| make build JOBS=2 + Windows 归档/链接续编 | 新构建通过 |
| make test Case=...（18 项，排除 Pi） | 18/18 |
| make perf（全部六项） | 6/6 |
| make run + WAVE + LOG | 通过 |
| 256 MiB RAM 最高地址补充测试 | 通过，返回 598 |
| AXI 桥接与响应 FIFO 场景 | 5/5 |
| AXI 位级组合依赖与环路 | 通过 |
| make synth MODE=opt CLOCK_PERIOD_NS=2.0 | 流程完成，2 ns 时序约束未满足 |

正确性 MAX_CYCLES=10000000，性能 MAX_CYCLES=1000000，LATENCY=10；测试 runner 和内存从机均为课程原版。
官方 Makefile 无排除单项的参数，因此逐个执行 make test Case=...，没有执行包含 Pi 的全量 make test。

## 正确性用例

| 测试点 | 周期 | 标准答案 | 结果 |
|---|---:|---:|---|
| correctness_add_to_100 | 447 | 5050 | PASS |
| correctness_array_test1 | 433 | 123 | PASS |
| correctness_array_test2 | 466 | 43 | PASS |
| correctness_basicopt1 | 690965 | 88 | PASS |
| correctness_bulgarian | 171539 | 159 | PASS |
| correctness_expr | 414 | 136 | PASS |
| correctness_gcd | 427 | 178 | PASS |
| correctness_hanoi | 3348 | 184 | PASS |
| correctness_lvalue2 | 210 | 175 | PASS |
| correctness_magic | 363721 | 216 | PASS |
| correctness_manyarguments | 215 | 40 | PASS |
| correctness_multiarray | 1327 | 115 | PASS |
| correctness_naive | 214 | 97 | PASS |
| correctness_qsort | 887183 | 81 | PASS |
| correctness_queens | 240708 | 144 | PASS |
| correctness_statement_test | 1137 | 50 | PASS |
| correctness_superloop | 342639 | 134 | PASS |
| correctness_tak | 802145 | 186 | PASS |

`correctness_pi`：按要求跳过，本报告不将其计入通过项。

## 性能

| 基准 | 动态指令数 | 周期 | IPC |
|---|---:|---:|---:|
| perf_median | 6961 | 7572 | 0.919307976756 |
| perf_multiply | 21722 | 17490 | 1.241966838193 |
| perf_qsort | 139900 | 143485 | 0.975014809910 |
| perf_rsort | 195719 | 153155 | 1.277914531031 |
| perf_towers | 5278 | 4739 | 1.113737075332 |
| perf_vvadd | 4524 | 3725 | 1.214496644295 |
| GEOMEAN | | | 1.115262691835 |

动态指令数采用课程 metrics.json；周期来自新仿真器，IPC 和 GEOMEAN 按官方定义计算。

## 新综合与静态时序分析

| 指标 | 结果 |
|---|---:|
| 组合逻辑面积 | 20348.956079998 μm² |
| 时序逻辑面积 | 7598.804400000 μm² |
| SRAM 面积 | 7943.911838000 μm² |
| 总面积（含 SRAM） | 35891.672317998 μm² |
| 估算 Fmax | 321.608040201 MHz |
| 最低周期 | 3.109375000 ns |
| 2 ns 时钟约束下 Worst Setup Slack | -1.109175000 ns |

负 Slack 表示不满足 2 ns / 500 MHz 约束；以上 Fmax 是课程 ideal clock、no parasitics 模型的 STA 估算。
本次没有重构模块或做参数优化，因此只运行最终评估 opt 模式，没有重复 diagnose 模式。

## 工具适配与日志

Windows native：Verilator 5.020、Yosys 0.63、ABC、OpenSTA 3.1.0，使用同一课程 ASAP7/FakeRAM 库，工具 SHA256 已与安装清单核对。
原 make build 在 Windows 归档路径处退出 2；随后以斜杠工具路径运行同一生成目录的 Makefile，完成归档和链接，并加入已有 time-zero fallback。官方 build.py 和 sim.cpp 保持原样。不是无适配的一次 make build 成功。
辅助协议测试初试 Icarus 时因前向声明报错，随后使用课程 Verilator；辅助 C++ 编译统一 C++17，并采用斜杠路径解决 Windows 转义。初始失败日志保留。
Verilator 仍有 WIDTH、UNOPTFLAT 等告警。接口桥接部分已另做位级检查，未发现真实组合环路；未据此宣称全 CPU 所有告警消除。

## 复现与产物

可用以下命令在新的 F 盘目录复现本次全部流程（始终排除 Pi）：

```powershell
python E:/Verilog_cpu/tools/validate_a109_course_readme.py all --out F:/CPU2026CourseRuns/A109_readme_new_run
```

本次每条 make 命令、退出码、开始结束时间和日志哈希在 *.command.json 中；config.mk 保存实际工具与输出路径。

- validation.json：总验证清单及所有证据哈希。
- interface_audit.json / structural.json / protocols.json：接口、结构和协议证据。
- build/sim.exe、build_identity.json：新仿真器及源码身份。
- tests.json、correctness_*.log、make_perf.log：逐项结果。
- trace.vcd、run.log、waveform_axi.json：官方单程序运行及外部总线检查。
- synth/opt/report.txt、report.json、timing.rpt、area.json、timing.json、constraints.sdc：新综合完整产物。

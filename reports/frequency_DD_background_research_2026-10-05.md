# DD 后台统一测量与同期研究

上一目标轮是实现进展：CZ/DA/DB/DC/DD 已采用、冻结，活动 40 个输入与 157 个快照输入一致，并已向用户发送 [测试前报告](E:/Verilog_cpu/reports/frequency_batch_DD_pretest_2026-10-05.md)。目标没有完成，300 MHz 尚无新证据。

2026-10-05 00:44:23（Asia/Shanghai）启动原生后台根 **PID 40700**，命令是固定的 `run_course_standard_windows.py --config architecture_DD_20261005/course_windows_config.json --correctness`。没有新建 WSL 或重新安装工具。源输入仍为 [DD 冻结身份](F:/CPU2026CourseRuns/architecture_DD_20261005/source_manifest.json)，stdout/stderr 位于同一目录；CPU 构建与原课程综合并行，六项 perf 和十九项 correctness 仍由原驱动依次运行一次。

本轮已经通过 live process/command line 核对根、Verilator/原生 make 子进程和 Yosys 子进程，不以锁文件或静态状态推断运行。读取时 C++ 已进入对象编译、Yosys 正处理 RTL。Verilator 有 UNOPTFLAT 数组/树告警，未观察到 `%Error` 或 LATCH；这些告警不等于已经证明逻辑有环，也不能据此宣布全部功能或时序通过。不能因日志暂时未更新另起一份同批测量。

## 少量定向覆盖，复用相同 CPU

准备 [三个有限程序](F:/CPU2026CourseRuns/architecture_DD_20261005/directed_cases/cases.json)，不另编译 RTL：

| 程序 | 架构检查点 | 目的 |
|---|---:|---|
| rv32m_edges | 60 | 十二组 32 位边界/编码位型的四种乘法，与 signed/unsigned DIV/REM 的零除、溢出、舍入边界；每组四种乘法先独立发出，再检查各自结果 |
| lsq_wrap_forward | 96 | word/byte/half 重叠 store，signed byte/unsigned half 读，以及地址等待 DIV 的旧 store 对年轻 load 的约束；事务数量超过 16 行，使队列继续复用 |
| recovery_reuse | 80 | 旧 MUL/DIV 的存活、错误路径目的及 store 不提交、恢复后新 MDU 任务的进展；反复分配以刺激 ROB/物理目的/LSQ 复用 |

总计 236 个架构检查点，三个输出都独立返回 0，失败则返回对应检查编号。程序没有修改官方 testcase；六项 perf 的数字仍只来自原 `metrics.json`。RV32M 乘法期望值由 Python 的任意精度乘法与 signed32/高低半抽取产生，没有调用 RTL 算法；DIV 边界使用写明的常量答案。程序及原生 GNU assembler/binutils 身份全部保存。

准备工具为 [frequency_directed_cases_native.py](E:/Verilog_cpu/tools/frequency_directed_cases_native.py)。后台等待工具只读取同批 `build_identity.json`，用 Windows process handle 核对原根的真实存活；构建 COMPLETE 后复用其 exact executable SHA、固定 Verilator 和原课程 `oj_io` stdin/输出比较。内存延迟仍为 10，每个程序上限 100000 周期，不放宽官方测试上限。失败与全部日志保留，不自动重跑。

这些是架构层有限刺激。没有内部状态探针证明一定出现了每一种 held-result 反压、最后一拍 DIV kill 或迟到响应，不能把 236 个结果当作完整状态覆盖或 ISA 证明。

## 同期结构分析：下一步依据

现有 RS 并非简单串行年龄扫描：它已有 66 位相对年龄矩阵、CW 的平衡 decoded low rank、共享匹配、16 位数据选择域。把 issue bypass 的 wake value 选择移到 lane 级，可以减少重复数据 mux，但需要先对选中的行汇总 match，再选择六个 producer 的值；late rank 之后可能多一段 OR/mux。若新报告显示的是数值广播负载而非 rank 深度，再评价该重排，不能默认面积省就频率快。

物理折叠 age-ordered queue 可以换静态优先选择，但每拍 issue/allocate 需要移动宽 metadata/操作数。当前 12 项的 cached-value 队列会使移位矩阵很宽；仅移动逻辑 slot pointer 则需动态读 ready 和年龄关系，不能把它算作免费解码。本轮仍保留既有顺序，不在测量期间偷偷换 issue policy。

[BOOM v2 原作者论文](https://people.eecs.berkeley.edu/~krste/papers/celio-boom2-carrv2017.pdf)记录了 issue/register-file/rename 的瓶颈与拆分，并指出增加 load 到依赖指令的延迟会损失 IPC。其工艺、存储器和物理流程与课程不同，无法移植 MHz 或增益数值；它支持在路径证据下设计边界与端口责任，而非只数流水级。

另查 checkpoint 后确认当前 `CHECKPOINT_IMPL=1` 已使用 old-phys undo 重建 RAT，没有每个 ROB 项完整 RAT 存储。不能再次把“删 64 份完整 checkpoint”作为新优化或面积收益。当前并行 RAT recovery 的 killed-writer 分组、旧目的、branch 自身新目的也已经存在，后续只针对新路径定位其实际消费者。

可保留的一项新条件方向是容量阈值的精确 lookahead credit：若新报告确认为 occupancy/free-count→allocation-ready 的路径，可以把每 lane 可分配阈值随当前同拍净增减更新为少量 FF，避免在分配资格前再做计数减法。需同时覆盖正常 alloc/commit、恢复 occupancy、hold 和 reset；更新阈值的路径也可能成为新瓶颈。它尚未实现或测试，更未取代当前 counter。是否采用由新的最慢路径决定。

当时计划是待本批产生实际映射，用只读汇总工具定位最大门、电容/slew 和串行结构；在该记录时点，主工作树与冻结测量输入均为 DD。任何实现修正须另冻身份，不能把改后源码和当前测量混用。

## 已完成指标与下一批，2026-10-05 更新

DD 实测频率 273.943285 MHz、最小周期 3.650390625 ns，总面积含 SRAM 为 51,233.753154 μm²，IPC 为 0.7823728642。六项 perf 周期与旧 CD1 完全相同，三项有限定向共 236 个检查全部通过。完整十九项目前观察到 pi/qsort 在 1,000,000 周期超时，其他结果继续从原根 PID40700 读取，没有重跑。详见 [DD 测量报告](E:/Verilog_cpu/reports/frequency_DD_measurement_2026-10-05.md)。

最差五条检查属于数据 SRAM 地址命令同一个锥：local_array_write 的 96.36 fF 根负载、八个重复 word owner 与末级四宏共享地址。只读负载清单/反向锥还定位了 LSQ selected-address/access-mask 广播与 byte routing。这些新证据已落实为 DE 每 way SRAM command owner，以及 DF/DF1 每行 forward-query + 七窗口解码；命名问题在源码审阅时修正，没有运行候选 DF 的编译。

主工作树现为独立冻结的 DF1，只比 DD 多改变两个 RTL 文件，40/157 个输入身份一致。DF1 尚未运行任何 HDL/EDA/仿真；旧 DD 指标保留为 previous/background measurement。已形成 [DF1 测试前报告](E:/Verilog_cpu/reports/frequency_batch_DF1_pretest_2026-10-05.md)，新的测试不会使用旧 DD 的可执行文件，也不会把 273.94 MHz 填给 DF1。

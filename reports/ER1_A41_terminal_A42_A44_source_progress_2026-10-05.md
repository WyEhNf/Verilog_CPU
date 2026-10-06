# ER1：A41 实测完成，A42–A44 源码进展

记录时间：2026-10-05T12:13:07.535277+00:00。原 A41 进程 PID 51000 已确认不存在，结果状态为 COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE；没有重新启动任何旧测量。

| 方案 | 综合 IPC | 总面积，含 SRAM（μm²） | 频率（MHz） |
|---|---:|---:|---:|
| A36 | 0.991897791 | 35686.138058 | 297.242380 |
| A41 | 1.011656507 | 35559.510758 | 308.062575 |
| 目标 | ≥1.1 | ≤36000 | >300 |

A41 的面积、频率已满足数值目标；IPC 尚未达标，还需相对提高 8.733%。相对 A36，IPC +1.992%，频率 +3.640%，面积 -0.355%。面积余量 440.489242 μm²，频率余量 8.062575 MHz。

测量采用原 Windows 原生课程工具链、固定课程框架 54fc150ffc290f52aa024209ffb9a29d43856f6d、原程序及 dynamic_instructions 分子、latency=10、六项 IPC 几何平均。157 个源快照文件及冻结的主机脚本、工具、库哈希再次核对。SRAM 7943.911838 μm²，时序单元 7573.435200 μm²，组合逻辑 20042.163720 μm²。

六个性能程序的官方答案校验通过；19 项完整正确性套件、完整 M 扩展和针对新旁路/恢复/缓存行为的覆盖尚未执行。未采用 A41，也未将目标标记完成。

| 程序 | A36 周期 | A41 周期 | 周期变化 | A41 IPC |
|---|---:|---:|---:|---:|
| perf_median | 9452 | 8171 | -13.553% | 0.851915 |
| perf_multiply | 18273 | 18197 | -0.416% | 1.193713 |
| perf_qsort | 159725 | 167060 | +4.592% | 0.837424 |
| perf_rsort | 161366 | 161376 | +0.006% | 1.212814 |
| perf_towers | 5815 | 5737 | -1.341% | 0.919993 |
| perf_vvadd | 4010 | 4010 | +0.000% | 1.128180 |

median 明显改善，但 qsort 退步。A37–A41 是一批联合变化，因此不能把某程序的周期变化单独归因于 gshare、LSQ 回收或恢复发射中的某一项；尚无 A41 分项事件画像。后续需要根据真实分支/访存停顿归因选择更大收益的架构变化。

## 本轮源码工作，没有新测试

- A42：将数据 SRAM 的读有效和数据来源按 way 记录。前一 store 写一个 way 时，下一 load 可以查询 tag，并读取其他 way；所选 way 未读到数据则延后读取，命中旁路也必须检查该 way 数据有效。两路配置仅增加 2 个状态位，SRAM 宏、容量、端口不变。此前已准备，本轮继续复核。
- A43：当拍命中旁路交给 LSQ，同时让 waiter 或返回的 miss 响应进入原有响应寄存器。valid 不依赖 ready；背压时命中保留在寄存器中、其他 load 响应仍由原生产者持有。失败的 dirty-victim writeback 也参与 waiter 仲裁，避免 waiter 被消费后其数据被更高优先级失败响应覆盖。没有增加状态、响应端口或流水边界。
- A44：预测查询、RAS 和取指包 PC 使用现有前端待处理请求 PC，避免先等待 Icache 响应 PC 选择。响应接受增加 pending、完整 PC 相等检查，并保留原 epoch/line 身份检查。只在同步非阻塞缓存且 OoO 配置启用；其他配置保留原来源。没有增加 PC 寄存器或流水边界。

三者都保存为独立冻结候选，A42/A43/A44 的 IPC、面积、频率未知。源码检查及哈希不能证明 HDL 等价或正确性。主 E:/Verilog_cpu 活动 EU 源码保持原哈希。

## 当前关键路径及下一步

从已存在的 A41 mapped.v、design.json 和 critical_paths.json 读取，最慢路径到达时间 3.190 ns，路径经过 Icache line-filter 响应选择、frontend.bundle_pc、gshare bank_training_index、BHT 查询以及 chained if_req_pc。私有顶层单元 209126 个，对照映射文本/JSON 的排序类型全部一致，选定相邻路径连线在两份产物中核对；没有重新综合或 STA。起终点 FF 的精确业务字段未识别，不据此作更强结论。

A44 旨在去掉这段路径中的晚到 PC 选择，并为后续 IPC 改动留出频率余量；新路径和总面积需要今后测量，不能声称已有频率收益。A42/A43 消除的是已定位的请求/响应串行条件，实际碰撞次数尚未知。

下一步继续检查 load 的 allocation→selection→cache query 边界，以及在现有面积余量内加入 bimodal/gshare 自适应选择的可行性。方向预测候选应保留预测时 gshare 行索引、低 6 位历史 checkpoint 和两种原始方向；现有 16 位元数据在 history≤6 时有 2 个高位可用，可评估双表、按 PC 选择器和缩小 indirect-only BTB 的面积交换。必须先复核恢复历史掩码、完整反馈 lane 身份、频率路径和面积预算，不能把联合批次的 qsort 退步当成单项因果证据。

另外，代码本身已有四项 speculative RAS；不重复添加已有结构。RISC-V 的 x1/x5 call/return 提示规则见[官方 ISA](https://docs.riscv.org/reference/isa/v20240411/unpriv/rv32.html)，BOOM 的 RAS 定义见[官方文档](https://docs.boom-core.org/en/latest/sections/terminology.html)。这些资料不能证明本核 IPC。qsort 静态反汇编没有大规模递归 call/return，不把扩展 RAS 作为当前首要收益来源。

本轮不启动 A42–A44 的 HDL/仿真/综合/STA/单元回归。先发展完整批次及收益依据，测试前另行汇报。目标仍为 IPC≥1.1、总面积≤36000 μm²、频率>300 MHz，并保留 RV32IM/OoO/顺序提交等完整要求。

证据：F:\CPU2026CourseRuns\ER1_A41_tier3_20261005\result\result.json；F:\CPU2026CourseRuns\ER1_A41_tier3_20261005\result\ipc.json；F:\CPU2026CourseRuns\ER1_A41_tier3_20261005\result\synth\opt\report.json；F:\CPU2026Proofs\ER1_A41_critical_frontend_owner_20261005.json。A42/A43/A44 来源与哈希见对应 candidate.json、A42_source_review.json、A43_source_review.json、A44_source_review.json。

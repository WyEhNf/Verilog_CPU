# 取指队列one-hot读口重构与证据

## 06:36补充：完整CPU收益没有达到孤立模块幅度

同参数PRF48/RS8、ROB32、TAG1/I128、**旧store管线**两份完整默认ABC结果已配对完成，清单参数完全相同，仅frontend SHA不同。整机面积 **46,154.839314→45,947.628354 µm²**，实际节省207.210960 µm²（0.448947%）；新组成27,609.489900组合 +10,512.471600时序 +7,825.666854 SRAM。383,537个实际叶实例、37个实际宏，未计价/未展开0、最终check0、独立VERIFIED。

同一构建IPC仍为0.9519069653774248，完整6/5/17/边界通过。完整SRAM时序的最小周期 **44.7958984375 ns**、Fmax **22.323472346363 MHz**，较旧动态索引版本24.993287935369 MHz变差。此改动的孤立局部结构收益成立，但不能声称CPU频率改善。完整关键路径存在1384扇出起点，以及928/434/1158扇出的串联节点；必须按新整机路径继续定位，不能凭局部STA推导达标。

新整机路径已实际追溯：起点 `_765348_` 是 **ROB head_o[0]**，不是原取指队列head；终点 `_730463_` 是 **AXI桥bus.i_resp_id[0]**。对应同一design.json中的原cell分别为 `$auto$ff.cc:337:slice$688370` / `$auto$ff.cc:337:slice$1028574`，mapped.v中的D/QN连接与排序自动名逐项吻合；prepared.il中其dfflibmap反相器分别直接连接 `core.g_ooo_backend.backend.rob.head_o[0]`（3860735–3860738）和 `bus.i_resp_id[0]`（3852555–3852558）。起点1384扇出、最慢中段NAND1158扇出/13.9615 ns增量均来自完整timing.rpt，不凭局部模块推断。该证据表明消除一个前端读口瓶颈后仍有ROB控制传播到存储响应路径的整机瓶颈；尚未为该新路径实施RTL修复或证明其优化收益。

新网表SHA256 `abff6777f1fbc7e20f6151be53271aff0517def973ac2895ab2598ecd5b4cfcc`；完整证据 `D:/CPU2026AreaAudits/frontend_onehot_tagbanks_i128_r32p48rs8_standard_20261001`。PRF64/RS16同类one-hot旧cache审计仍运行。之后的store管线优化相对本节快照改变了cache文件，最新cache结果应等待其独立网表，不能混用本节PPA。下面较早运行状态以本补充为准。

## 目的与版本边界

完整课程默认ABC网表的真实关键路径为取指队列head_reg[0]至RS的src1_value_mem[15][9]。TAG1/I128网表的起点DFF扇出3398、XOR输出扇出539、后续NAND输出扇出1292，完整最小周期39.0390625 ns，25.615369221533 MHz。来源 `D:/CPU2026AreaAudits/latest_tagbanks_i128_standard_20261001/timing.rpt`；按同一design.json导出的保留内部名字网表和prepared.il反向追踪确认，不凭源码猜测。

前端原四路动态数组读口将head指针直接送入大量宽mux。现在将head译成共享one-hot行选择，各lane循环旋转行选择后掩码OR归并完整packet。存储内容、深度、四发射宽度、尾指针写入、metadata、所有握手、重定向/stop/error及事件输出均保持不变，不增加流水拍、不缩小乱序窗口。RTL `rtl/frontend/rv32_fetch_frontend.v`。

基线frontend SHA256 `8f1727f4ff09b8a68aa9c74d0c897c02586b82241d61287469d990537f055d72`；新RTL SHA256 `d5d3418495051a724ff477aefa4137386c64f1bb9c806679b1766b0d53d74de5`。

## 验证

- `make a04`：FE_WIDTH=1/2/4四态前端测试、Verilator lint及Yosys检查通过。
- `make lint unit matrix`通过；日志 `build/frontend_onehot_unit_matrix_20261001.log`。
- `tools/test_frontend_read_equivalence.py`：对完整顺序模块而非单一读mux做equiv_simple/equiv_induct，最后equiv_status -assert。FE_WIDTH=1/2/4与FQ_DEPTH=2/4/8/16/32所有合法组合共14组，全部PROVEN。包含全部模块输出与队列状态，基线来自冻结源码，不是改写的参考模型。日志/脚本/输入SHA在 `D:/CPU2026Proofs/frontend_onehot_20261001/report.json`。
- 新真实AXI冻结构建 `D:/CPU2026Builds/frontend_onehot_tagbanks_i128_20261001`：benchmark6/6、basic5/5（含LH/LHU/SH和RV32M八操作）、simulator17/17、256MiB末地址脏回写边界通过；pi冻结。报告 `build/cpu2026/frontend_onehot_tagbanks_i128_{benchmark,basic,simulator,boundary}_20261001.json`。
- 与相同TAG1/I128旧冻结构建对比，六项的cycles/instret逐项精确相等，IPC GEOMEAN仍为0.959647821888849；不将读口时序改善冒称IPC改善。

## 孤立前端的实测结构收益（不是整机成绩）

`tools/audit_frontend_read.py` 对完整前端各端口保留，FE4/FQ16，相同五份原始ASAP7 r28 RVT TT、memory_map、默认ABC、2 ns目标、常量单元和原课程完整STA约束。没有黑盒阵列。计价叶单元与独立Decimal相符、未展开0。所有输出显式标记not_a_cpu_result=true。

| 孤立前端 | 标准单元面积 µm² | 叶实例 | 完整最小周期 ns | 孤立频率 MHz |
|---|---:|---:|---:|---:|
| 原动态索引读口 | 1,654.509240 | 16,399 | 24.2617187500 | 41.217195299 |
| one-hot掩码归并 | 1,505.399580 | 13,489 | 3.9931640625 | 250.427977501 |

孤立模块面积降低149.109660 µm²（9.01232%），频率提升约6.07581倍。此比较仅证明改动的局部结构收益；不能从整机面积减去149.109660来宣布新总面积，也不能把250.43 MHz作为CPU频率。

新孤立关键路径已转移到if_resp_pc_i[3]至队列写端；下一阶段仍须关注响应bundle/truncation/尾指针写控制路径，而不是继续把head读口当成孤立前端最慢路径。

证据 `D:/CPU2026AreaAudits/frontend_read_diagnostic_20261001/comparison.json`、baseline/onehot下各自area_audit.json、full_timing_audit.json、timing.rpt、map.ys、map.log和网表。新整机冻结默认ABC在 `D:/CPU2026AreaAudits/frontend_onehot_tagbanks_i128_standard_20261001`，当前仍在运行；最终面积/频率未发布。Tier3三项要求仍未达到。

## 冻结构建回归机制

另外完成同一重构前源码的PRF48/RS8缩参PPA：完整默认ABC面积46,154.839314µm²、IPC0.9519069653774248、完整频率24.993287935369MHz。该缩参节省10.054716%总面积，性能损失0.806635%，但没有本报告的one-hot读口；二者不可相减拼接。结合新读口的同资源构建 `D:/CPU2026Builds/frontend_onehot_tagbanks_i128_r32p48rs8_20261001` 已编译完成并通过新6/5/17/边界回归，各项benchmark周期/退休数与重构前PRF48/RS8版本精确相等，IPC仍为0.9519069653774248。报告 `build/cpu2026/frontend_onehot_tagbanks_i128_r32p48rs8_*_20261001.json`。新完整默认ABC计价在 `D:/CPU2026AreaAudits/frontend_onehot_tagbanks_i128_r32p48rs8_standard_20261001` 运行中，面积/时序尚未发布。

`tools/run_course_axi_tests.py` 默认继续逐项要求工作树与build manifest SHA相同。新增显式--source-snapshot，只从不可变面积快照验证同样的build输入SHA，原exe/观察驱动SHA和“一条只读计数输出”条件完全不变，运行前后仍检查输入。报告明确evaluated_source_root、evaluates_current_worktree、current_source_differences。旧默认构建在没有此参数时被修改后的frontend拒绝，且不会产生报告；指定其原面积快照后，6/5/17/边界实际运行通过。该选项不允许用旧编译代码冒称当前源码。

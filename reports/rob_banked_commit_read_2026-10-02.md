# ROB 分银行提交读取原型（2026-10-02）

**09:51核验更新**：完整48组原协议已全部 COMPLETE，证据 `F:/CPU2026Proofs/rob_banked_commit_read_protocol_full_v1_20261002/report.json`；不能把 protocol 报告的泛用 scope 视作形式证明。BE1/2/4、ROB8的17517个equiv仍是已完成的小配置完整模块证据，实际ROB64正在证明输出。独立旧版PPA已明确失败于共享scratch变量age的六位多驱动，没有面积/频率结果，失败日志保留；它还缺少库导入前的原external-module检查。紧凑推进函数另已七项字面SAT和48项协议通过，过程临时变量拆分候选开始验证，详见[紧凑推进与修复范围](rob_bounded_advance_2026-10-02.md)。下文“48组在测/PPA运行”按09:02历史保留。

目标不变：同一当前配置总面积≤36,000µm²、六项benchmark IPC GEOMEAN≥1.0985、全SRAM频率≥300MHz，完整RV32IM/自然对齐访存、乱序执行、严格顺序提交与官方共享内存保持。Pi冻结，Tier3未达成。

## 已实现的独立候选

原型位于 `F:/CPU2026Candidates/rob_banked_commit_read_20261002`，主树ROB和当前43个构建输入未修改。新增默认关闭 `COMMIT_BANKED_READ=0/1`，仅改变组合读取布局，状态数组、分配/完成/恢复/退休写入优先级、generation标签、所有提交字段与接口均保留，不加流水拍、不缩小窗口、不删除调试或checkpoint能力。

原提交窗口是head起连续BE_WIDTH项，其中每个物理 modulo-BE bank恰好包含一项。候选先从每个bank的ROB_ENTRIES/BE_WIDTH行读取一个完整包，再按head低位旋转为严格程序顺序的提交lane，避免每个lane独立扫描全部ROB行。分配和CDB仍保持原多写行为，**本轮没有把完成端口或写端口伪减成单端口**。

BE_WIDTH保持1/2/4；ROB_ENTRIES<BE_WIDTH及启用旧控制寄存器/ASAP7树的组合使用原完整读取fallback，未缩小原合法参数范围。边缘BE4/ROB2仍须实际顺序证明，不拿普通64项测试代替。

## 当前验证证据（09:02）

`F:/CPU2026Proofs/rob_banked_commit_read_protocol_smoke_v1_20261002/report.json`：初检6/6完成，BE1/2/4、ROB64、开关0/1，保留全部原ROB协议检查。新增测试通过正常分配/完成/退休遍历全部64个head，每次全宽分配、逆序完成lane、逐项独立检查PC/指令/值/完整标签/rename字段和顺序提交，停顿两拍检查稳定。共384次head位置访问、896次lane独立检查，无层级注入状态。原store可见性、ack错误、恢复保留分支、旧generation拒绝、HALT/错误精确提交检查未删减。

完整48组原协议矩阵已启动：BE1/2/4×ROB4/8/32/64×控制寄存器0/1×开关0/1；证据目录 `F:/CPU2026Proofs/rob_banked_commit_read_protocol_full_v1_20261002`，尚未称完成。

实际完整ROB顺序等价初检在 `F:/CPU2026Proofs/rob_banked_commit_read_formal_smoke_v1_20261002`：以当前原ROB为gold、真实候选为gate，不用手写mux夹具替代、不约束任意分配/完成/恢复输入，比较全部模块输出及同名状态。09:05复核BE1/2/4、ROB8已分别证明4842/5590/7085个equiv，合计17517、未证明0；实际BE4/ROB64已进入证明。后续还包含BE4/ROB2、默认关闭、新旧store退休和checkpoint模式；当前不宣称全部8组或CPU形式证明通过。

## 面积和时序必须实际测量

`tools/probe_rob_banked_read.py`已启动两套完整真实独立ROB的原始默认synth/ABC、五ASAP7库综合及独立Decimal逐叶核价，再执行原完整时序；证据目录 `F:/CPU2026Probes/rob_banked_commit_read_actual_rob_v1_20261002`。所有原ROB输入/输出、字段和状态都保留，仅开关0→1，ROB64/PRF64/4发射、checkpoint实现1、posted store1；该模块实际没有SRAM，未制造宏或省略任何存在的存储。

它不是CPU PPA：独立ROB全部输出可观测，与CPU内常量传播、其他模块负载和共享不同。因此即使得到组件面积差，也不能直接从旧CPU面积相减，更不能拼上当前IPC宣称Tier3。当前尚无这两套组件面积/频率结果；主树两套新布局整机审计保持原任务运行。

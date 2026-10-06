# ROB 指针推进函数紧凑化（2026-10-02）

**10:54独立组件基线**：实际过程scratch拆分ROB的bank0原版PPA完成，14950.667340µm²（组合11108.254140＋时序3842.413200、实际SRAM0）、71.086428323MHz、14.0673828125ns，检查0问题，映射SHA `0bfc98bb1363cf8a008363e17f2742504889c91d298c9ce2e778f6b45a337f67`。全部真实ROB端口与字段保留、官方external-module验证在导库前，独立Decimal全叶计价，明确不是CPU成绩。bank1正在展开，对照尚未完成，无分银行读取面积/频率收益结论；它也不包含后来分银行分配写。

**10:39实际模块证明完成**：过程scratch拆分候选的八套小/边缘完整ROB顺序等价全部 COMPLETE，51464个equiv、未证明0；直接原主树ROB为gold，没有删状态/输出或收窄输入。覆盖BE1/2/4、ROB8，BE4/ROB2，以及分银行读关闭、checkpoint0/1、store退休0/1的指定八套组合，checkpoint宽度32；不是所有参数、ROB64或全CPU证明。证据 `F:/CPU2026Proofs/rob_process_locals_formal_smoke_v1_20261002/report.json`，候选SHA `89fd126640ed3613d5ff52e5f1ade1f04d330de20a0a292cdb3fee4243130774`。48协议与七种容量字面指针SAT已完成，实际完整ROB组件PPA仍map，未预报收益。

**10:09更新**：紧凑推进但未拆scratch的组件PPA也已明确终止于age六位多驱动的check，未得到面积/频率；该失败与原循环版本一样，不放宽检查。拆scratch新候选48/48原协议和七种容量推进函数SAT全部完成；实际整模块等价已完成BE1/2/4、ROB8及BE4/ROB2，余下关闭bank/不同checkpoint/store模式仍在测。新组件PPA已通过原检查及展开、进入映射，目录 `F:/CPU2026Probes/rob_process_locals_actual_rob_v1_20261002`，尚无PPA数字。下文09:51运行状态属于历史时刻。

验收目标保持完整：同一最终当前配置总面积≤36,000µm²、六项 benchmark IPC GEOMEAN≥1.0985、包含全部实际 SRAM 的 Fmax≥300MHz，以及完整 RV32IM、自然对齐访存、乱序执行、严格顺序提交和原共享 AXI 内存接口。Pi 冻结，Tier 3 尚未达成。

## 已实现与证明

独立候选 `F:/CPU2026Candidates/rob_bounded_advance_20261002` 以实际分银行读取 ROB 为基础，仅将 `advance_slot` 的逐项循环改成幂二容量下的截位加法。负步长、零步长以及步长达到或超过容量时仍返回原位置，保留原循环最多推进完整一圈的行为；不是只假设步长在 0…4。

候选 ROB SHA256：`5c80d044b18f4762285a36fa743d40b0922fb239632e93622467f41c5b2c8695`。与原分银行候选去掉这一个字面函数后，剩余 RTL 完全相同。主树 ROB 未被替换。

`tools/test_rob_advance.py` 直接抽取冻结原始/候选函数体，保留 `input integer amount` 的有符号 32-bit 签名，以任意 head 与任意 amount 比较。容量 2/4/8/16/32/64/128 的七项 SAT 全部 PROVEN，证据为 `F:/CPU2026Proofs/rob_bounded_advance_literal_v1_20261002/report.json`。这是确定二态输入下的字面函数证明，不是任意 X 输入的四态等价，也不是全 ROB/CPU 顺序证明。

实际原协议矩阵 48/48 全部通过：BE1/2/4 × ROB4/8/32/64 × 控制寄存器开关0/1 × 分银行读取开关0/1。增加的所有 head 位置、逆序完成、全宽提交、两拍停顿检查保留；字段检查改用 case inequality，检测未知输出。原 store/ACK 错误/恢复/generation/HALT 协议未删减。证据 `F:/CPU2026Proofs/rob_bounded_advance_protocol_full_v1_20261002/report.json`，报告的 phase 是 protocol，不能把泛用 scope 文本当成 formal 已完成。

## PPA 与后续边界（09:51）

完整独立 ROB 探针 `F:/CPU2026Probes/rob_bounded_advance_actual_rob_v1_20261002` 在原 SRAM/external-module 检查之后使用原五库与默认 ABC，目前映射仍 live，无面积/频率结果。它完整保留实际 ROB 的全部端口与字段，但不是 CPU 分数。

较早循环版独立 ROB 探针已终止于 `check -assert`：共享临时变量 `age` 有六个多驱动位，未产生可用 PPA；该旧探针还没有先运行框架的 external-module 检查，不将其当作正式整机流程。失败文件保留。

新独立候选 `F:/CPU2026Candidates/rob_process_locals_20261002` 将组合与时序进程共用的 `age`、分配/提交 lane 和 slot 临时变量拆开。只隔离过程 scratch，不增加流水拍或删减真实状态，仍保留完整分银行读取和上述推进函数。新候选的七种容量字面推进函数 SAT 也全部 PROVEN，证据 `F:/CPU2026Proofs/rob_process_locals_advance_literal_v1_20261002/report.json`；新协议与小规模实际整模块证明在测，尚不宣称修复后的完整 PPA 或全规模等价通过。

任何组件优化均须进一步接入、原生完整回归并测量同源码整机面积和全 SRAM 时序，不能把组件面积差从历史 CPU 面积直接相减。

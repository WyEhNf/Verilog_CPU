# D-cache 同沿注册索引实验（2026-10-02）

**10:30层级身份核验完成**：控制2＋注册索引1的全69个功能模块、62475个实际计价叶的完整命名net/每cell-pin/顶层与子模块端口指纹恒等，原图和标准库/SRAM计价不变。最差路径起点确为 `request_index[1]`，终点为 `mshr_victim_entry[3][0]`，不是按STA编号猜测；证据 `F:/CPU2026Diagnostics/dcache_banked_registered_index_identity_v3_20261002/identity.json`。直接FF负载1919；STA后级INV总负载1350含层级内部，诊断root_pin_fanout546只统计根模块pin，二者口径不同，不将其当成负载减少。诊断v1/v2分别因转义模块namespace、无空格module header解析失败而终止，均保留；五项parser/fingerprint单元检查通过。下一方向是实际索引/元数据选择与更新的局部化，不将当前26MHz组件报告冒称CPU提频。

**10:09新完整组件对照**：控制分组2与注册索引0/1的原版完整Cache PPA已经完成，两个参数的组合不胜过只注册索引。主树尚未接入注册索引，当前整机PPA仍在测，不能由本表宣布CPU成绩。

| STATIC_UPDATES | REGISTERED_INDEX | 完整独立Cache面积 µm² | 含全部SRAM Fmax MHz | SRAM宏数 |
|---|---|---:|---:|---:|
| 0 | 0 | 12612.325760 | 25.859238869668427 | 36 |
| 0 | 1 | 12831.434000 | 31.748984590580722 | 36 |
| 2 | 0 | 13143.037760 | 16.083180197584383 | 36 |
| 2 | 1 | 13303.359440 | 26.000406256347755 | 36 |

新证据 `F:/CPU2026Probes/dcache_registered_index_banked_actual_cache_v2_20261002/report.json`，两个新网表分别以各自原默认ABC、五库、官方RAM/external-module验证、独立Decimal完整叶核价及全SRAM STA测量。两份父报告共有16个冻结来源逐项SHA一致；诊断helper文件名不同，新helper只把根模块改名放在所有参数子模块展开之后，不更换RTL或映射策略。第一次探针已明确终止于顶层名字丢失，失败目录保留，第二目录修复后完成；不是观察超时重启。

相同注册索引1下开启分组2，面积增加471.925440µm²且频率降低，当前不选该组合。新组合最差路径的FF负载1919，后级INV负载1350、延迟15.4054ns；这些是实际STA负载，但源寄存器身份仍在完整层级图核验，未按编号猜测。

只注册索引（模式0/1）的残余NOR1955负载已完成真实物理下游追踪：第一个顺序边界1021位，其中1010个legacy_dirty_bits与11个resp_word_reg位。证据 `F:/CPU2026Diagnostics/dcache_registered_index_residual_cone_20261002/control_cone.json`；原netlist/完整连线指纹及预ABC寄存器dump SHA均核验，全部实际叶/SRAM独立计价不变。该结果是依赖归属，不等于每种输入下的逻辑敏化，也不是模块面积或新频率。下一方向据此优先元数据更新控制网络，不先推断乘法器或新增执行单元是时序瓶颈。

目标保持同一当前配置：总面积≤36,000µm²、六项 benchmark IPC GEOMEAN≥1.0985、全 SRAM 频率≥300MHz；完整 RV32IM/自然对齐访存、乱序执行、严格顺序提交与原共享外部内存不变。Pi 冻结，Tier 3 尚未达成。

## 实现与范围

实际原型位于 `F:/CPU2026Candidates/dcache_registered_index_20261002`，**尚未接入主工作树或 CPU**。三个覆盖文件为真实 `rv32_dcache_nonblocking.v` 和两个原 Cache 测试台，而非简化控制夹具。

新增默认关闭的 `REGISTERED_INDEX=0/1`。在 TAG_SRAM=1 的原 `input_fire` 接受沿，同时捕获请求地址对应的 demand set index 和下一行 prefetch set index；后续命中控制、延迟数据读地址及 forwarding 使用这些索引。没有新增访问拍、SRAM、端口或外部访存通道。索引状态与原 query_addr 同样无全局清零要求，warm reset/flush 不取消已接受请求的所有权。TAG_SRAM=0 保留原组合路径。

这不是随意移动寄存器来改变协议：两个测试台从活动的完整 query_addr 独立重算索引，包括32-bit下一行加法的截断及哈希规则，保留原数据、背压、预取、写回、恢复、写掩码和 SRAM 访问断言。

## 完成的协议证据

- 初检12项全部通过：`F:/CPU2026Proofs/dcache_registered_index_smoke_v1_20261002/report.json`。
- 完整360项全部通过：`F:/CPU2026Proofs/dcache_registered_index_full_v1_20261002/report.json`。覆盖 REGISTERED_INDEX 0/1、STATIC_UPDATES 0/1/2、TAG_SRAM 0/1、ways 1/2、lines 16/64/1024、hash 0/1、prefetch 0/1、merge delay 0/16/32；使用官方四态同步 SRAM 模型。
- 活动查询的独立索引检查合计408114次。180组仅索引开关不同的成对 profile 的查询检查次数一致；这不是完整逐周期输出等价证明，也不是整 CPU 形式证明。
- 实际被测 Cache 源 SHA256 为 `48462f7a3ef0e041dedcfcd038c8ffb376c26b3691ab8b069c82d09e5912180d`；主树 Cache SHA 为 `ad2ee03fac46e01f60f0ca7c7a029812fe69b521ad0badb164e594347b41e7f4`，主树未被原型覆盖。

## 完整真实独立 Cache PPA：并非 CPU 成绩

证据：`F:/CPU2026Probes/dcache_registered_index_actual_cache_v3_20261002/report.json`。使用原始默认 synth/ABC、五个 ASAP7 RVT TT 库、官方 SRAM 校验/面积模型与全部36个实际 SRAM。保留所有 Cache 接口，仅重命名根模块以供原报告器使用；没有 AXI 适配器、后端或前端，明确标记 `not_a_cpu_result=true`、`integrated_into_cpu=false`。

固定 TAG17/MSHR4/waiter8、prefetch1、D1024/2way/hash1/merge16/TAG_SRAM1/STATIC_UPDATES0，仅改变注册索引：

| REGISTERED_INDEX | 总面积 µm² | 全 Cache SRAM Fmax MHz | 最小周期 ns | SRAM 数 |
|---|---:|---:|---:|---:|
| 0 | 12612.325760 | 25.859238869668427 | 38.6708984375 | 36 |
| 1 | 12831.434000 | 31.748984590580722 | 31.4970703125 | 36 |

面积增加219.108240µm²，频率提高约22.7762%，周期降低约18.5510%。原始逐叶 Decimal 核价和递归层级计数一致、全部 SRAM 时序边界保留；理想时钟、无布线寄生，非 PnR。**只是局部改善，仍远未到300MHz；不得与任何 CPU IPC 或旧整机面积拼成三项成绩。**

两套实际网表 SHA 分别为 `531a1288e71ca7d9d41cce0006efda6df81cf418887ac60c42bd19bb93b2c1f4`、`a0e11ca4ff2df8eaa1277de448a0e4bff65b63a518c1ff05af6986dfb705d429`。v1字符串/Path类型错误、v2头文件路径错误均为已终止的准备失败，源快照、失败日志和说明保留；v3两套完成，不是超时重启。

开启版最差路径从 `mem_resp_id_i[0]` 到 `_101043_`，数据到达31.4388ns；其中 `_053794_` NOR负载900、延迟5.1159ns，`_062359_` NOR负载1955、延迟15.8374ns。剩余问题是响应相关控制网络的实际负载，不能只优化索引后宣称解决时序。

后续诊断已严格解析端点：`_101043_` / `_101028_` 分别对应原实际 `resp_word_reg[31]` / `[16]`，不是乘法器。证据 `F:/CPU2026Diagnostics/dcache_registered_index_residual_identity_20261002/identity.json`。重导出的文本因公共别名选择而不逐字节相同，但全部53305个实际叶的命名网别名类、每个单元引脚连接及所有顶层端口指纹完全一致；保留原网表SHA，独立核价与36 SRAM计数一致。仅在诊断目录复现原脚本至ABC前的准备阶段，追踪相同FF身份及dfflibmap输出反相器，未更改正式网表、库、约束或任何成绩。

另外检查过整行写替代字节写的方向，但未实施：官方 FakeRAM 模型面积为总位数×0.0419904µm²，拆分/合并写粒度不减少容量面积；其 clock-to-Q 随宏写粒度增大。实际 Cache 允许下一条store在前一条DATA写周期接受、仅先读tag，整行读改写可能额外等待data。没有面积收益且存在IPC/时序代价，不能以减少宏实例个数冒称省面积。

## 当前整机边界

当前源码 RS metadata=1、地址2、Cache控制0/2两套均完成 benchmark6/basic5/simulator17/256MiB边界1。严格机器对照 `F:/CPU2026Proofs/rs_metadata_dcache_modes_native_exact29_20261002/report.json` 再核验全部当前43个构建来源、原驱动与共享256MiB/20cycle/FIFO16/B握手语义，仅 DCACHE_STATIC_UPDATES 0→2；全部29项 cycle/instret/退出结果相同，六项 IPC 均1.1213155347352615。

这两套当前源码整机 PPA 仍在运行。之前地址1/旧布局的冻结整机控制0/2 PPA 为59205.207774/27.09281405439729MHz与60175.215174/15.632394473704297MHz、IPC均1.0881243892617036；该对照的控制分组是明确负收益，不选择局部夹具替代整机结论。

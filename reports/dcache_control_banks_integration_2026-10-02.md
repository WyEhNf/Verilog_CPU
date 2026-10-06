# D-cache 真功能控制分组接入（2026-10-02）

目标保持同一最终配置总面积≤36,000µm²、六项 benchmark IPC GEOMEAN≥1.0985、包含全部真实 SRAM 的频率≥300MHz，完整 RV32IM/自然对齐访存、乱序执行、严格顺序提交与官方共享内存不变。Pi 冻结，尚未达成 Tier 3。

## 07:46完整整机PPA与严格计数核验

**08:35后续完成**：当前RS metadata1/地址2的控制0/2各29项全部通过，精确单参数机器对照 cycle/instret/退出码完全相同、当前43构建来源一致，六项IPC均1.1213155347352615；当前整机PPA待完成，不能配用下表旧来源。注册索引独立原型360项全部通过，实际完整独立Cache与36 SRAM的原版PPA为12612.325760→12831.434000µm²、25.86→31.75MHz，未接入CPU、不是整机成绩。下方12项/360在测为早先状态；详见[新证据](dcache_registered_index_2026-10-02.md)。

接入前同源码、只改变`DCACHE_STATIC_UPDATES 0→2`的地址1/四发射ROB64/PRF64/RS16/LSQ16、I128/D1024/2way/TAG1/预测1/CPL16/AXI8/4/16/FIFO2两套已完成原始默认ABC/五库综合、独立Decimal核价和全SRAM STA。两套旧版29项逐项cycle/instret/退出码相同、六项IPC均1.0881243892617036；这是新共享AGU和RS/ALU布局接入之前的冻结CPU，不与当前IPC1.1213155347352615配用。

| 更新模式 | 组合 µm² | 时序 µm² | 全部SRAM µm² | 总面积 µm² | 全SRAM Fmax MHz | 最小周期 ns |
|---|---:|---:|---:|---:|---:|---:|
| 0，原动态更新 | 38487.613320 | 12891.927600 | 7825.666854 | 59205.207774 | 27.09281405439729 | 36.91015625 |
| 2，功能状态分组 | 39457.620720 | 12891.927600 | 7825.666854 | 60175.215174 | 15.632394473704297 | 63.9697265625 |

原版流程、实际宏数均37，未计价/未展开/遗漏存储边界均0；理想时钟/无连线寄生的综合后估计，不是布局布线成绩。模式2实际多970.007400µm²且频率下降，**本组整机对照不支持把控制分组选为优胜方案**；默认0保留。下面局部515.35MHz和PPA“仍运行”均不得覆盖本次完整CPU结论。

证据根目录为`F:/CPU2026AreaAudits/axi_response_fifo2_branch1_bus8w4q16_i128_r64p64rs16_lsq16_rat1_earlystore1_standard_20261002dc0integrated`和对应`earlystore1_dcupdate2_standard_20261002dc2integrated`，各有`independent_verification.json`、`full_timing_audit.json`及`timing.rpt`。网表SHA分别`2d2ba3ae1b43f8389f4b550a21eced92b4414eb0d96e9dab7a0a3c5e44633bb2`与`42a98f9f90eb70860b8df1505cd8128e980cc2e7a1826a4033988fe96eaec9a7`。

旧链的`--require-current`因8个输入变化严格失败，保留原失败日志；后续独立冻结核验没有要求当前树一致，其报告列出所有变化，不能宣称当前源码成绩。首次冻结核验还揭示Yosys 0.68类型表包含68个功能子模块引用，而`num_cells`仅统计534610个物理叶实例。核验器现递归展开每个功能模块的实际实例倍数，并同时核对每层叶/子模块数量、全局逐类型叶与层级计数、未知类型与全部原始库/SRAM价格，而不是简单过滤或忽略模块。15组正/负测试通过，包括嵌套重复实例、同总数换类型、漏SRAM、递归/不可达模块、非法倍数、未展开对象；旧扁平RAT1网表重核仍为43713.418314µm²。综合脚本、网表、五库和SRAM系数均未修改。

冻结控制2路径中的实际`mapped.v`连接直接将`_0515052_/Y`指向Cache哈希索引、`_0515085_/Y`指向`prefetch_index[1]`，相应INV负载1624/1882、延迟15.7202/29.4689ns。索引计算位于已寄存请求之后，下一步的注册索引候选只在独立目录实现，复用原查询接受沿，不加访问拍；12项真实Cache初检通过、360项在测。尚无其完整CPU面积/频率或IPC成绩，不将它冒称已解决300MHz。

**最新验证边界**：补充的实际1024行Cache顺序等价证明已因资源优先级明确取消，并非反例或观察超时；取消前核实精确Yosys进程及脚本，私有内存约8.9GiB、主机剩余提交容量约6.2GiB。四套已完成小配置证明、所有源快照和部分日志保留，1024行案例未完成且不宣称证明通过。证据目录中的`deliberate_cancellation_20261002.md`记录此决定；180项Cache协议和整机回归是独立证据，不替代全规模形式证明。总面积、计分IPC、全SRAM时序和完整RV32IM的正式目标不变。下方旧“仍在运行”按本段更新，旧Cache控制PPA为RS/ALU新布局接入前冻结来源。

## 实际接入

`rv32_dcache_nonblocking.STATIC_UPDATES=2` 现在接入真实 `rv32_dcache_metadata_bank` 与 `rv32_dcache_mshr_data_bank`，两个 CPU filelist 均包含这些模块。每 16 行拥有局部 valid/dirty/LRU 状态，每个 MSHR 拥有自己的 128-bit 写数据状态和字节掩码更新。只读状态视图与不同实现的寄存器所有权分离，避免模块输出与过程赋值混合驱动。

模式 0（原动态写）与模式 1（原扁平静态使能）均保留，默认仍为 0。模式 2 不新增流水拍，不使用标准单元空桩，不更换 Cache 数据/标签 SRAM，保持 refill > local fill > prefetch/miss > store-hit 优先级和 dirty 无全局复位值语义。原默认 ABC 保留真实功能层级；收益必须整机测量。

## 已验证与证据

- `F:/CPU2026Proofs/dcache_control_banks_protocol_v2_20261002integrated/report.json`：180/180 四态真实 SRAM/Cache 协议用例通过，更新模式 0/1/2 每模式 60 项。对应矩阵覆盖 TAG_SRAM 0/1、ways 1/2、lines 16/64/1024、hash 0/1、prefetch 0/1，以及 SRAM 协议 merge delay 0/16/32。
- 1024 行测试初始使原 4KiB 参考内存越界，模式 0 即读出 X；现按容量扩展真实单元模型与参考数组，随机访存、脏受害者地址/数据等断言未减少。失败记录保留于 `F:/CPU2026Proofs/dcache_control_banks_protocol_20261002integrated`。不改变官方 256MiB/20-cycle 内存。
- 完整控制器/每个原始 SRAM 引脚的模式 0/2 顺序等价证据在 `F:/CPU2026Proofs/dcache_control_banks_full_cache_equivalence_v3_20261002integrated`；ff_direct/sram_direct/ff_2way/sram_2way 分别 2957/3106/3077/3786 个 equiv 全部证明，合计12926、未证明0。实际1024行/MSHR4/waiter8配置已按上述资源优先级取消，未完成、未称全部五套通过。仅 proof 流程展开真实功能状态模块、将各 SRAM rdata 化为共享任意输入，并检查每个 SRAM 输入引脚；不证明存储内部，不是整机形式证明。
- 初始两个 proof 准备失败记录均保留。动态端口使候选被 hierarchy 重新派生，原候选名消失；脚本现独立展开两侧后按真实 top 重命名、保存与合并，没有跳过未证明节点。
- `F:/CPU2026Proofs/windowearly_rob64_host_exact29_20261002/report.json`：接入前 ROB64 分文件 -Os 与低优化 -O0 的全部 29 项 cycle/instret/退出结果逐项相同；旧低优化任务正常完成、未取消。这是历史冻结硬件的主机编译对照，不是新模式 2 的成绩。

## 新整机在测

构建 `F:/CPU2026Builds/axi_response_fifo2_branch1_bus8w4q16_i128_r64p64rs16_lsq16_rat1_earlystore1_dcupdate2_20261002dc2integrated`：四发射、ROB64/PRF64/RS16/LSQ16、RAT1/early-store1、I128/D1024/2way/TAG1、预测模式1、CPL16、AXI8/4/16、响应 FIFO2、控制模式2。执行官方 benchmark6/basic5/simulator17/边界1，随后原版完整 default ABC/五库独立总面积与全 SRAM STA。

模式0/2均已完成原始6/5/17/边界全部29项，六项周期10166/11871/161179/204069/5194/3973、退休数合计472599、IPC **1.0881243892617036**。29项cycle/instret/退出码全部逐项机器完全一致，42个硬件/清单/头文件/构建助手输入相同，唯一参数变化DCACHE_STATIC_UPDATES 0→2；证据 `F:/CPU2026Proofs/dcache_control_banks_native_exact29_20261002integrated/report.json`。这是所测程序的严格原始回归对照，不是整机形式证明。

两套原版完整PPA仍在运行。模式2已成功完成elaborate并进入prepare；模式0在elaborate。进程与原执行handle均核实live，未因等待或日志刷新慢重启。尚未取得完整面积/频率结果，也未把1024行顺序证明的运行中节点算作PROVEN。

仅主机助手增加 `--output-split 1000 --output-split-cfuncs 1000`，保持 -Os/原官方驱动，不改变硬件、周期、内存或计分规则。仍存在约6.6MB单大函数、约17.3GB编译峰值，不能宣称峰值已解决；两套正常编译已完成，Verilator报告约927/818秒。新输出使用F盘，避免D盘输出与分页共同耗尽空间；WSL已验证能访问F盘。

之前小窗口43,713.418314µm² / IPC0.956280586 / 31.170096189MHz是接入前冻结参考，不能当作新工作树或ROB64的PPA。旧模式0的ROB64/PRF64 IPC1.088124389与PRF96 IPC1.088693260均已29项通过，新模式2也已29项通过，但面积/频率尚未完成。

## 大窗口下的剩余IPC机会

`F:/CPU2026Diagnostics/rob64_dcupdate2_lsq_reasons_20261002integrated/lsq_reasons_observation.json`：新真实模式2模型复用，只读每一活动周期并与真实LSQ eligibility逐位断言一致，六项官方cycle/instret/结果全部不变。rsort在无候选93686周期中，同时出现未知更老store地址阻塞load55288周期；vvadd无候选1569周期中等待返回1539、未知store地址60。重叠计数不是互斥CPI分解。

`F:/CPU2026Diagnostics/rob64_dcupdate2_store_address_opportunity_v2_20261002integrated/store_address_opportunity.json`：以完整ROB tag匹配真实live RS/LSQ，观察实际src1/src2 effective readiness与ROB立即数，不改变RTL或驱动时序。对提前推算地址逐项等待后续真实LSQ地址核验，36924次一致；另6305次因恢复/回收取消，不算证明成功。六项官方计数均严格不变。

| 程序 | 总周期 | 同时有store基址ready而数据未ready | 无候选且反事实可放行load | 后续真实地址核验次数 |
|---|---:|---:|---:|---:|
| qsort | 161179 | 27291 | 3844 | 7902 |
| rsort | 204069 | 97020 | 35649 | 28608 |
| towers | 5194 | 1092 | 258 | 409 |
| vvadd | 3973 | 72 | 58 | 3 |

反事实假设当拍发布全部已可计算地址，且继续检查其他未知store和重叠未ready数据；不等于真实单AGU可以省掉这些周期，也不是性能预测。median没有未知store地址、multiply反事实机会0，故不能指望该方向改善所有程序。仅rsort改善且其余不变时，跨过1.0985门槛需rsort周期减少约5.535%；只是几何平均公式推导，不是已实现结果。

下一IPC实现方向是复用RS已有的基址就绪/值、从LSQ待地址store中选最老项，用共享AGU/独立全LSQ-tag地址更新发布地址，数据仍等待原ALU，store请求仍严格由ROB授权。优先避免新增每项CDB监听/基址寄存器或16套加法器；不先提前load退休，以免RS尚未执行时ROB/LSQ槽回收造成旧标签映射风险。必须验证SB/SH/SW掩码、重叠load阻塞、非重叠load放行、同拍正常ALU更新、恢复保留/取消和槽generation回收，再用正式六项/完整PPA衡量真实收益。当前尚未实现该AGU通路。

后续必须完成剩余控制器/SRAM引脚证明、全部整机回归与同源码模式0/2的完整面积/频率对照，才决定是否启用分组。隔离夹具515.35MHz不代表CPU提频；不缩小窗口、不省略真实SRAM来冒称Tier3达标。

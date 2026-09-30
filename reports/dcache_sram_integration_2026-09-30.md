# D-cache课程SRAM接入与验证

2026-10-01最新版本边界：已实现可选同步标签SRAM（DCACHE_TAG_SRAM=1）、两份真实1RW标签副本及按way数据bank、单拍load-hit旁路和held-query标签/数据写入转发。四态协议12组、随机hash32组及真实AXI6/5/17/边界通过，pi冻结。同I128容量/默认ABC下，TAG0面积60,619.503366µm²/IPC1.001507321/频率14.720681MHz，TAG1为51,314.351394µm²/0.959647822/25.615369MHz，37个宏全部计价；TAG1的约4.18% IPC损失尚需处理，未作为达标性能候选。源码默认仍TAG0/I64，其冻结结果59,445.084949µm²/0.982501248/17.228326MHz。随后工作树已重构取指读口，完整PPA另行运行；前述数值不冒称新读口结果。详见 `reports/latest_total_area_2026-09-30.md` 和 `reports/frontend_onehot_2026-10-01.md`，下文为之前阶段记录。

2026-09-30。目标仍是同一配置完整面积≤36,000µm²、IPC GEOMEAN≥1.0985、完整频率≥300MHz；没有宣布Tier3通过。pi按用户要求冻结。

2026-10-01版本更新：I-cache数据也已迁移实际1RW SRAM。最新AXI默认配置已加入16周期store合并窗口，完整覆盖且RFO尚未offer的行可local fill；部分掩码仍正常RFO，脏行仍先写回，背压offer锁定槽位，已完成waiter不会被复用MSHR覆盖。修复版冻结构建 `build/vlt/course_axi_storemerge16_fixed_20261001` 通过6/5/17/256MiB边界，正式IPC GEOMEAN=0.982501248101083；pi冻结。窗口16相对关闭约+0.18%，32收益更小，64退化。协议测试覆盖1/2way×0/16/32窗口，以及完整行skip、部分字节保留、load waiter、反压/flush、脏victim、ready waiter槽复用和低索引重新eligible时的发送稳定性。`make lint unit matrix`通过。

最新修复版面积重新计价已启动，目录 `build/synth/course_axi_storemerge16_fixed_classic_20261001`；PPA尚未完成。此前不含store合并的I/D数据SRAM版本经典ABC面积64,740.978349µm²，其默认ABC映射仍在运行；再前一D-cache SRAM/I-cache FF版本默认全局opt已完成为62,953.004372µm²、同网表完整频率8.108054608MHz。下文9月30日的分层65,968.760732µm²/6.650574MHz及“全局仍在运行”是历史状态，不替代上述已完成或当前待测版本。不能跨源码/映射方式拼接三项分数。

## 实现

非阻塞D-cache数据从普通128bit数组迁移到课程原版 `sram_fakeram`，深度由CACHE_LINES参数控制，WIDTH=128、WRITE_GRANULARITY=8。最终候选容量1024条16-byte line（16KiB）、2way/hash=1。

单端口仲裁：成功refill写优先于命中读、命中store写和dirty victim读；不需要阵列的MSHR合并/转发仍可并行。store-hit直接使用16bit字节掩码，消除读改写。命中同步读与响应元数据同时变为有效，仍为一周期命中；下一沿捕获SRAM结果，保证随后idle/write使rdata未定义时，背压响应仍稳定。dirty victim首周期由SRAM结果旁路给回写，下一沿捕获到MSHR；内存背压、其它SRAM读写或flush均不丢已承接的store。

不清空SRAM内容；reset清valid和读结果来源标志，避免暴露旧数据。tag/valid/dirty/LRU、MSHR、waiter以及其它CPU阵列仍按实际标准单元计价；不借用单端口宏面积替换多端口结构。

## 验证

- `tools/test_dcache_hash.ps1`：16/16组合通过。hash=0/1、lines=16/64、ways=1/2、prefetch=0/1，每组包含1000个hash逆地址检查、500组随机掩码写/读以及1024word全量回访和脏victim物理地址/数据检查。
- `tools/test_dcache_sram.ps1`：课程四态模型下，一周期命中、连续命中、读响应背压期间同地址写、byte/half符号扩展、refill对命中读/写的端口优先级、dirty victim旁路及背压捕获、flush不丢已承接store、warm reset屏蔽旧payload全部通过。
- `make lint`：通过，包含Icarus/Verilator/Yosys层级检查。Yosys未绑定接口阶段的SRAM输出未驱动警告不用于面积/时序证明；正式面积流程将其替换为有定价和时序的宏。
- `make unit matrix`：通过，包括CPU基础通道/统计开关/非法参数和FE/BE宽度矩阵。该项不代替整机程序正确性。
- 本地双128-bit line端口冻结模型：6/6 benchmark、5/5基础/半字/M、17/17仿真程序（pi排除）以及256MiB末地址脏回写通过。这里的20周期是每整条line延迟，不能等同课程共享32-bit AXI的每word延迟。

持久构建目录 `build/vlt/dcache_sram_p4_r32p64_lsq8_ram256m`，原临时构建目录后来不再存在，因此在持久目录重新构建并重跑回归，不依赖临时可执行文件。参数不变：FE/BE/INTissue/CDB4，ROB32/PRF64/RS16/LSQ8，I/D MSHR8/4，Icache64line/2way，Dcache1024line/2way/hash1，CheckpointImpl1，fetchQ/completion16，20cycle统一256MiB RAM，outstandingI16/D8，sentinel关闭。全部RTL/模型/头文件和可执行文件SHA在构建清单中冻结。

本地line模型六项benchmark IPC几何平均 **1.0986481457856145**，累计退休/周期IPC=1.2618354056918883；与旧全FF版本1.0991968369025882相比轻微下降。benchmark报告 `build/cpu2026/dcache_sram_ram256m_report.json`，17项报告 `build/cpu2026/simulator_mmio_dcache_sram_ram256m_report.json`；程序全32bit MMIO返回值与参考一致。这些是本地模型的历史对照，不证明正式Tier3 IPC达标。

## 正式共享 AXI 内存口径重测

课程原版 `scripts/sim.cpp` 的外部内存是共享32-bit AR/R、独立AW/W/B、每通道FIFO16、每word延迟20周期；一个16-byte line需要4次word读取，退出在MMIO写B握手判定。新增 `rtl/course/student_top.v` 和 `rv32_axi_lite_bridge.v` 对接真实端口，不改变外部内存语义。原C++驱动只在 `top.final()` 后增加一行只读 `debug_instret` 输出，运行器逐字验证其余内容相同；Windows编译使用 `VL_TIME_CONTEXT` 连接原驱动实际维护的时间上下文。

冻结构建 `build/vlt/course_axi_p4_r32p64_ctx` 的六项动态 IPC GEOMEAN **0.982319982**，低于1.0985。median/multiply/qsort/rsort/towers/vvadd周期分别为10,630 / 12,119 / 163,866 / 203,492 / 5,809 / 6,064；各项instret仍为7,062 / 27,637 / 139,606 / 289,966 / 3,803 / 4,525。报告 `build/cpu2026/course_axi_benchmark_report.json`。

该同一冻结构建在正式内存下通过5/5基础（包括半字和8项M操作）、17/17仿真程序（pi冻结）及256MiB末地址脏回写；分别见 `course_axi_basic_report.json`、`course_axi_simulator_report.json`、`course_axi_boundary_report.json`。仿真suite首次导入旧PowerShell JSON因UTF-8 BOM失败，运行器改用 `utf-8-sig` 后重新完整运行17项，通过不依赖旧line模型返回值/周期。

AXI独立单元测试通过：共享读FIFO、不同周期AW/W接受、返回背压、I响应阻塞时D响应前进、32-bit byte mask、错误聚合、word队列满/环绕，以及仅对MMIO执行word0全掩码写。队列中已承接事务完整保存；它们全部按标准单元计入面积。

## 完整面积与时序

CPU核心的课程默认opt/flatten综合已完成，目录 `build/synth/dcache_sram_p4_course_opt_20260930`：组合39,608.523720、时序17,882.078400、SRAM5,503.765712，总计62,994.367832µm²。16个1024×8宏各343.985357µm²，其它普通数组全部计标准单元；558,342个叶实例，未计价/未展开存储均0。这份核心网表没有新增AXI顶层，不可用作最新版整机总面积。

新增AXI后的完整保留核心边界网表审计已完成：65,968.760732µm²，含AXI2,974.392900µm²；583,462个计价叶实例。最终网表重读、Yosys统计、课程函数及独立Decimal累加均通过，详情 `reports/latest_total_area_2026-09-30.md`。这不是零面积黑盒相加，也不是默认全局优化结果。真实AXI `student_top` 全局默认opt重新综合在 `build/synth/course_axi_p4_opt_20260930` 运行中。

默认流程：原版 `prepare_memories`生成包装/宏Liberty；课程 `synth -noabc -flatten`、dfflibmap、默认ABC、常量驱动映射、完整映射检查；原版 `area_report`逐实例计价，再独立Decimal叶累加核对。其它普通数组全部展开。前一完整全FF参考148,169.833200µm²不再代表当前工作树。

完整时序入口 `tools/run_course_full_timing.py` 已测量同一CPU核心网表及全部SRAM/标准单元库，使用课程原版时序约束，结果约6.6506MHz，最小周期150.3630ns。**实际AXI整机网表的完整STA也已完成，同样为6.650574MHz**，报告 `build/synth/course_axi_p4_hier_20260930/full_timing_audit.json`；对应上面的65,968.760732µm²整机网表SHA256，两者没有跨版本拼接。关键路径包含数千扇出的小驱动门，不能以历史305.19MHz的存储边界省略版本覆盖这一结果。实际AXI顶层需 `--clock-port clock`；核心入口为 `clk/reset`，测试fixture的 `clk_i/reset_i` 不适用于CPU。Tier3目标保持未完成，后续需同时解决面积、正式AXI IPC和完整频率。

# 参数化直接完成网络：实现、验证与实测边界

**完整面积已完成（2026-10-01 09:12）**：同一模式2/LSQ8/PRF48/RS8/TAG1/I128冻结构建，原始ASAP7 r28 RVT TT、全局默认ABC，组合 **25,952.545800**、时序 **10,105.106400**、实际37个SRAM宏 **7,825.666854**，整机 **43,883.319054 µm²**；360,511个叶实例，未计价/未展开0、最终网表重读check0、独立Decimal VERIFIED。相比其模式0对照45,793.940574减少1,910.621520 µm²（4.1722147%），IPC却从0.9558133327368818下降到0.946078833733971；不能按面积下降宣布Tier3达标。网表SHA `92afe77a20cc9748af84beb9454ca105cb949fc0fcaf506b007f2159deea0158`，证据 `D:/CPU2026AreaAudits/direct_cdb_precise_tagbanks_i128_r32p48rs8_standard_20261001`。完整全SRAM STA仍在运行，不沿用模式0频率。该快照先于后续LSQ接收/预测器参数改动，独立核验明确列出当前6个源码差异，未宣称--require-current。后文面积“运行中”为当时历史状态，以本段为准。

## 实现

额外诊断 `tools/audit_sequential_ownership.py` 从最终真实FF身份回溯同一已核验prepared.il的输出反相器/原始寄存器，不重新综合、不把门级组合逻辑猜归模块。34,654个FF的10,105.106400 µm²逐项价格与完整面积中时序项精确相等，35个FF/10.206000 µm²保留UNRESOLVED，未遗漏计价；没有未决归属的实例被当作零面积。主要时序归属：D-cache本体1,603.216800（另tag控制146.383200）、AXI桥1,513.404000、backend胶水1,298.786400、I-cache本体1,141.322400、四bank预测器合计1,250.380800 µm²。**仅触发器归属，不是模块总面积/组合部分排名，也不是新预测器或新AXI容量的面积**。详细 `sequential_ownership.json` 与完整面积同目录，首次只用purge后别名会大量UNRESOLVED，现按精确未变的FF标识追溯prepared并保留未解项，结果不替代正式整机计价。

同一上述网表的完整时序也已完成：全部37个真实SRAM宏参与、遗漏存储边界0；OpenSTA3.1/原版ns-fF约束、理想时钟/无寄生，最小周期 **44.3681640625 ns**、估计Fmax **22.538683335901 MHz**、2 ns目标setup slack **-42.368080 ns**。相比FIFO同资源27.925495650277 MHz反而下降。该模式完整配对成绩为 **43,883.319054 µm² / IPC0.946078833733971 / 22.538683335901 MHz**，三项Tier3均未达标，未冒充当前后续源码或选择为性能优化。前文“STA运行中”记录完成之前状态，由本段覆盖。

新增 `COMPLETION_BYPASS=2`，在现有同名参数通路上真正支持CDB_WIDTH=1/2/4（且≤BE_WIDTH），不是旧BYPASS=1的单CDB最小面积模式。模式0/1及源码默认值均保留。

每周期从持有结果的ALU/MDU/LSQ中选取至多CDB_WIDTH个不同来源，直接提供全部完成payload。round-robin公平仲裁避免持续ALU流量饿死后面的MDU/LSQ；每个背压lane只锁来源编号及完整generation-tag，不复制宽payload。所有已锁来源先被预留，之后才填充自由lane，防止低lane抢走高lane的held来源而重复广播。选择不依赖ready；实际握手才推进轮转。源被generation/recovery取消、完整tag改变、reset或flush时解除相应锁。stale结果即使所有live lane堵塞也能被消费。

恢复由backend逐来源提供target_live过滤，FIFO的kill_mask不冒充直接通路来源kill-mask。branch_pending保留最后CDB槽，其余lane可以独立前进。直接模式没有隐藏FIFO/多端口SRAM：entry_valid/tag、occupancy均为0，真正结果存储仍在已有功能单元输出寄存器；新增来源/tag锁和仲裁逻辑按正常标准单元综合。

消除完成FIFO延迟同时发现load错误传递的真实时序边界：LSQ结果与错误标志捕获可以同拍到达ROB。已在backend加入完整tag匹配的即时load-error通路（仅模式2启用），普通缓存/分支恢复映射后的完成lane均带上该错误；没有依赖尚未更新的load_error_mem。修复前的整合负例明确报LOAD_ERROR_MISSING_FAIL，日志保留。

## 验证

- `tools/test_completion_direct.ps1`：24组BE/CDB/来源数量测试，BE1/2/4×合法CDB1/2/4×SOURCES1/2/6/9。覆盖密集并发、来源数小于lane数、全payload校验、全背压、晚到来源、跨lane来源锁、stale独立消费、tag复用、flush/reset、1200周期随机背压/取消、ready改变不影响选择，以及持续竞争公平性；全部通过。
- 整合backend模式0/2×BE1/2/4×store-retire0/1，共12组通过：RAW/WAW/WAR、MDU与LSQ竞争、load精确错误、MMIO ACK精确错误、年轻指令恢复取消、JALR link/RAT/free-list正确性。测试原来只观察commit lane0，会在真实多退休时丢掉lane1+；现改为全部退休lane的有序历史，不降低结果/顺序检查。
- posted普通store可在LSQ接收时退休，因此原测试在STORE_BUFFERED_RETIRE=1下用普通地址期待未来ACK错误变成精确ROB异常不成立，旧FIFO模式也实际失败。该配置改测必须等待ACK的32-bit MMIO地址0x80000000，仍严格检查ACK前不可见/ACK后错误可见。
- 模式2单CDB不会同拍接受MDU与LSQ两个结果。整合冲突测试阻塞真实CDB握手并制造两来源同时有效，随后检查它们依次退休、不丢不重；多路吞吐另由24组直接网络测试验证。保留仅force MDU私有ready但让CDB握手继续的旧测试会制造不合法的生产者契约，未将它用于模式2。
- `tools/test_completion_equivalence.py`：从两份完整冻结模块证明模式0/1所有BE1/2/4和合法CDB组合，共12组全部PROVEN，未证明0。证据 `D:/CPU2026Proofs/completion_legacy_modes_20261001`，包含源码/头文件快照、脚本/日志指纹和完整顺序equiv_status -assert。新模式2改变延迟/仲裁，不伪称与FIFO逐周期等价。
- 实际四发射新构建 `D:/CPU2026Builds/direct_cdb_precise_tagbanks_i128_r32p48rs8_20261001`：benchmark6/6、basic5/5、simulator17/17及256MiB脏回写边界全部通过，pi冻结。

## IPC实测：不是已选定的性能优化

资源固定四发射ROB32/PRF48/RS8/LSQ8、TAG1/I128/D1024、store合并16，模式2对照上一冻结模式0：

| benchmark | FIFO周期 | 直接完成周期 | 退休数 |
|---|---:|---:|---:|
| median | 10906 | 10732 | 7062 |
| multiply | 12170 | 12157 | 27637 |
| qsort | 169012 | 170581 | 139606 |
| rsort | 224250 | 224684 | 289966 |
| towers | 5731 | 5920 | 3803 |
| vvadd | 6185 | 6405 | 4525 |

直接完成IPC GEOMEAN **0.946078833733971**，总周期430479、退休472599，低于FIFO版0.9558133327368818；退休数逐项一致。不能因移除流水拍就宣布IPC提升。模式2暂保留为完整面积候选，未改变默认模式。较早无即时load-error修复的原型构建只作诊断，不作为最终正确性/PPA证据。`make lint unit matrix b07 b09`通过；直接网络与整合的36组一键脚本也重新完整通过。

## 不改变执行行为的计数诊断

`tools/observe_course_perf.py`复用冻结模型和runtime对象，只在原课程观察驱动增加头文件及最终只读计数打印；逐项核对周期/退休数/结果与原严格六项报告完全相等，保存model/header/compiler/driver/输出指纹。不是替代评测驱动或新的成绩口径；周期类别可能重叠，不能相加。

证据 `D:/CPU2026Tests/completion_direct_20261001/perf_{baseline,direct}/perf_observation.json`：

- FIFO版vvadd的LSQ-full为4361/6185周期（约70.5%），backend-stall4457；直接版LSQ-full4583/6405（约71.6%），backend-stall4785。其RS-full112→258、ROB-full38→0。移除完成FIFO未消除主要LSQ约束。
- towers的LSQ-full1993→2163，分别约34.8%/36.5%；ROB-full始终0、RS-full仅49→81。
- qsort issue_count213079→216411、退休139606不变，branch_pending10455→10430；I-cache需求miss均22、D-cache外部读均1039。额外发射比例和分支相关开销仍值得专项检查，但这些计数本身不能唯一证明误预测来源或直接归因全部周期。
- multiply的指令以软件乘法循环为主，MDU-busy计数0，不能凭benchmark名把它当作硬件M乘法器吞吐瓶颈。

## 单参数LSQ容量实验：占满不是独立因果证明

保留相同四发射、ROB32/PRF48/RS8、TAG1/I128/D1024、MSHR4和模式2，只改变LSQ8→16。冻结构建 `D:/CPU2026Builds/direct_cdb_lsq16_tagbanks_i128_r32p48rs8_20261001` 的6/5/17/边界全部通过，退休仍472599、总周期430279，IPC GEOMEAN **0.949231678649818**，仅比直接LSQ8提高约0.333%，仍低于旧FIFO版0.955813333。

单项周期median10731/multiply12154/qsort170522/rsort224659/towers5804/vvadd6409。vvadd不仅未改善，6405→6409，LSQ-full却从4583降到0；同时RS-full258→2170、ROB-full0→1037，backend-stall4785→3231。qsort LSQ-full16774→0而周期仅170581→170522，额外issue_count216411→218296。证据 `D:/CPU2026Tests/completion_direct_20261001/perf_lsq16/perf_observation.json`，诊断与原严格结果逐项相等。

所以先前“LSQ经常占满”只能定位背压传播位置，不能单独证明容量就是根因。扩大LSQ主要把积压转移到RS/ROB，未解决后端处理速率/内存依赖/分支投机开销；没有将更大的LSQ选为最终配置或据此宣称达到IPC目标。后续优先检查store admission/回收与cache读写端口实际吞吐、branch预测及恢复，不再盲目仅加窗口。

## 面积与频率边界

新模式2完整默认ABC/原ASAP7 r28/真实片上SRAM计价在 `D:/CPU2026AreaAudits/direct_cdb_precise_tagbanks_i128_r32p48rs8_standard_20261001` 实际运行。完成、独立复核、同一网表全部SRAM STA之前，不发布其面积或频率，不从旧FIFO45,793.940574 µm²中估减寄存器位数凑成绩。

旧FIFO45,793.940574/0.9558133327368818/27.925495650277是其明确冻结版本，不是本轮新源码/模式2的组合成绩。当前Tier3仍未完成；默认没有改为IPC退化的直接模式。
